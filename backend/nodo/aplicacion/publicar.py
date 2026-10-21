"""
`publicar` (FUN-159, BR-001, INV-022, R-02): el evento se escribe en la MISMA transacción que el hecho, con UN `INSERT`, y nunca abre transacción propia. Fuera de un bloque
atómico falla con un error claro. Un tipo fuera del catálogo o una carga que no puede viajar: en pruebas y desarrollo fallan; en producción el hecho NO se pierde (R-06): el evento
entra marcado (`catalogado=False` o `carga_omitida=True`), se registra con ERROR y queda un asiento.
"""
from __future__ import annotations

import logging

from ..dominio import catalogo
from ..dominio import catalogos as cat
from ..dominio import sobre as dom
from ..dominio.errores import DatosInvalidos, FueraDeTransaccion, NombreInvalido, TipoNoCatalogado
from .base import _CasoDeUso
from .puertos import UnidadDeTrabajo

log = logging.getLogger("avacom.nodo")


class Publicar(_CasoDeUso):
    def ejecutar(self, uow: UnidadDeTrabajo, *, modulo: str, agregado_tipo: str, agregado_id: str, tipo: str, carga: dict, actor: str | None = None,
                 dispositivo_id: str | None = None, correlacion_id: str | None = None, version: int | None = None, creado_en: int | None = None) -> dom.Sobre:
        if not uow.en_transaccion():
            raise FueraDeTransaccion("`publicar` se llamó fuera de la transacción del hecho: el evento sólo se escribe junto con lo que lo originó (BR-001, INV-022).", tipo=tipo)
        cfg = self.s.config
        definicion = catalogo.resolver(tipo, cfg.ciclo_meses)
        catalogado = definicion is not None
        if catalogado:
            clase, sensibilidad = definicion.clase, definicion.sensibilidad
            version_efectiva = int(version or definicion.version)
            if modulo not in definicion.autores:
                mensaje = f"El tipo «{tipo}» lo publica «{definicion.modulo}», no «{modulo}» (R-09: un hecho tiene un solo autor)."
                if cfg.estricto:
                    raise DatosInvalidos(mensaje, tipo=tipo, modulo=modulo)
                log.error(mensaje, extra={"evento": "nodo.modulo_ajeno", "ruta": "bad"})
        else:
            if cfg.estricto:
                catalogo.validar_nombre(tipo)           # el error de nombre es más útil que «no catalogado»
                raise TipoNoCatalogado(f"El tipo de evento «{tipo}» no está en el catálogo de la cola (P-04): declárelo en `nodo/tools/generar_catalogo.py`.", tipo=tipo)
            try:
                version_efectiva = int(version or catalogo.analizar(tipo).version)
            except NombreInvalido:
                version_efectiva = int(version or 1)
            clase, sensibilidad = catalogo.clase_por_prefijo(tipo), cat.S_PERSONAL_MENOR      # lo desconocido se trata como lo más sensible
        ctx_actor, ctx_dispositivo, ctx_corr = self.s.contexto.actual()
        ahora = int(creado_en) if creado_en is not None else self.s.ahora_ms()
        sobre = dom.armar(tipo=tipo, version=version_efectiva, modulo=modulo, clase=clase, sensibilidad=sensibilidad, agregado_tipo=agregado_tipo, agregado_id=agregado_id,
                          carga=carga, creado_en=ahora, actor=actor or ctx_actor or cat.SISTEMA, dispositivo_id=dispositivo_id or ctx_dispositivo or cat.DISPOSITIVO_NODO,
                          correlacion_id=correlacion_id or ctx_corr or "", catalogado=catalogado, estricto=cfg.estricto)
        secuencia = uow.eventos.insertar(sobre)
        sobre = sobre.con_secuencia(secuencia)
        self.s.vivo.emitida(secuencia)
        self.s.anclar_si_toca(ahora)
        if not catalogado or sobre.carga_omitida:
            self._avisar(uow, sobre)
        return sobre

    def _avisar(self, uow: UnidadDeTrabajo, sobre: dom.Sobre) -> None:
        """R-06: lo que entró fuera de norma se dice con ERROR y queda en la bitácora (en la misma transacción), sin el contenido de la carga."""
        detalle = {"tipo": sobre.tipo, "modulo": sobre.modulo, "secuencia": sobre.secuencia, "evento_id": sobre.evento_id, "catalogado": sobre.catalogado,
                   "carga_omitida": sobre.carga_omitida}
        log.error("Evento %s fuera de norma en la cola: %s", sobre.tipo, "tipo no catalogado" if not sobre.catalogado else "carga con datos que no pueden viajar",
                  extra={"evento": "nodo.evento_fuera_de_norma", "ruta": "bad", "detalle": detalle})
        try:
            uow.auditoria.registrar(cat.SISTEMA, cat.A_EVENTO_NO_CATALOGADO, "m15_evento", str(sobre.secuencia), nuevo=detalle)
        except Exception:   # noqa: BLE001 — el hecho ya está en la cola; el asiento es un aviso
            log.exception("No se pudo asentar el evento fuera de norma")
