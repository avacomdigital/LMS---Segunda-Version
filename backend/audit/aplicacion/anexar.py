"""
Anexar un asiento (§1.2, §3.3): dentro de la transacción del caso de uso que registra el hecho.

    leer cabeza del tramo activo → secuencia = hasta + 1 → huella = SHA-256(huella_previa ‖ asiento) → INSERT →
    avanzar la cabeza → línea en backend-auditoria.log (sin valores) → si algo falla, el caso de uso revierte entero.

SQLite abre las transacciones con BEGIN IMMEDIATE (settings.DATABASES), así que los escritores hacen fila: no hay dos
asientos con la misma secuencia ni dos cabezas. Si no hay tramo activo (base recién creada, o vaciada en una prueba)
se abre la bitácora con el asiento génesis `auditoria.bitacora_abierta` (secuencia 1, huella_previa = 64 ceros).
"""
from __future__ import annotations

import logging

from django.db import DatabaseError, transaction

from .. import contexto
from ..dominio import asiento as dom
from ..dominio import catalogos, errores, huella
from ..dominio import tramo as dom_tramo
from ..logging_setup import CANAL_AUDITORIA, CANAL_ESCRITURA, LOGGER_AUDITORIA
from ..models import Bitacora, BitacoraTramo, ahora_ms

log = logging.getLogger(LOGGER_AUDITORIA)


def _cabeza_final() -> tuple[int, str]:
    """La última secuencia y huella de toda la cadena (el tramo rotado más reciente), o (0, génesis)."""
    ultimo = BitacoraTramo.objects.order_by("-hasta_secuencia").first()
    if ultimo is None:
        return 0, huella.GENESIS
    return int(ultimo.hasta_secuencia), ultimo.huella_cierre


def tramo_activo(bloquear: bool = True) -> BitacoraTramo | None:
    """El tramo abierto (recibe asientos): puede estar `activa`, `verificada` o `con_salto`; nunca `rotada`."""
    qs = BitacoraTramo.objects.filter(abierta=True)
    if bloquear:
        qs = qs.select_for_update()
    return qs.first()


def abrir_tramo(huella_inicial: str, desde: int) -> BitacoraTramo:
    return BitacoraTramo.objects.create(desde_secuencia=desde, hasta_secuencia=desde - 1, huella_cierre=huella_inicial,
                                        estado=dom_tramo.ESTADO_ACTIVA, creado_en=ahora_ms())


def _insertar(tramo: BitacoraTramo, asiento: dom.Asiento) -> Bitacora:
    asiento.validar()
    asiento.sellar(tramo.huella_cierre)
    fila = Bitacora.objects.create(
        secuencia=asiento.secuencia, huella_previa=asiento.huella_previa, huella=asiento.huella, ocurrido_en=asiento.ocurrido_en,
        usuario_id=asiento.usuario_id, actor_tipo=asiento.actor_tipo, roles_activos=asiento.roles_activos, modulo=asiento.modulo,
        accion=asiento.accion, resultado=asiento.resultado, objeto_tabla=asiento.objeto_tabla, objeto_id=asiento.objeto_id,
        valor_anterior=asiento.valor_anterior, valor_nuevo=asiento.valor_nuevo, motivo=asiento.motivo, origen=asiento.origen,
        dispositivo_id=asiento.dispositivo_id, correlacion_id=asiento.correlacion_id, evento_id=asiento.evento_id, tramo=tramo,
    )
    BitacoraTramo.objects.filter(pk=tramo.pk).update(hasta_secuencia=asiento.secuencia, huella_cierre=asiento.huella)
    tramo.hasta_secuencia, tramo.huella_cierre = asiento.secuencia, asiento.huella
    return fila


def _genesis(tramo: BitacoraTramo, ahora: int, ctx: contexto.Contexto) -> Bitacora:
    asiento = dom.Asiento(secuencia=tramo.hasta_secuencia + 1, ocurrido_en=ahora, accion="auditoria.bitacora_abierta",
                          modulo=catalogos.M_AUDITORIA, actor_tipo=dom.ACTOR_SISTEMA, origen=ctx.origen or "sistema",
                          correlacion_id=ctx.corr, valor_nuevo={"version_catalogo": catalogos.VERSION_CATALOGO})
    fila = _insertar(tramo, asiento)
    _linea(fila, "Bitácora abierta (asiento génesis)")
    return fila


def anexar(accion: str, *, actor_tipo: str, usuario_id: str | None, modulo: str, resultado: str = dom.RESULTADO_OK,
           objeto_tabla: str | None = None, objeto_id: str | None = None, valor_anterior=None, valor_nuevo=None,
           motivo: str | None = None, dispositivo_id: str | None = None, evento_id: str | None = None,
           roles_activos: list[str] | None = None, origen: str | None = None, correlacion_id: str | None = None,
           ocurrido_en: int | None = None) -> Bitacora:
    """Anexa un asiento ya resuelto contra el catálogo (ver `servicios.anexar` para la fachada con contexto)."""
    ctx = contexto.actual()
    ahora = ocurrido_en or ahora_ms()
    try:
        with transaction.atomic():
            tramo = tramo_activo()
            if tramo is None:
                secuencia_final, huella_final = _cabeza_final()
                tramo = abrir_tramo(huella_final, secuencia_final + 1)
                if secuencia_final == 0:
                    _genesis(tramo, ahora, ctx)
            asiento = dom.Asiento(
                secuencia=tramo.hasta_secuencia + 1, ocurrido_en=ahora, accion=accion, modulo=modulo, actor_tipo=actor_tipo,
                usuario_id=usuario_id, roles_activos=roles_activos, resultado=resultado, objeto_tabla=objeto_tabla,
                objeto_id=objeto_id, valor_anterior=valor_anterior, valor_nuevo=valor_nuevo, motivo=motivo,
                origen=origen or ctx.origen or "sistema", dispositivo_id=dispositivo_id, correlacion_id=correlacion_id or ctx.corr,
                evento_id=evento_id,
            )
            fila = _insertar(tramo, asiento)
    except errores.ErrorAuditoria:
        raise
    except DatabaseError as error:
        # §1.2: si la bitácora no puede escribirse, el hecho no ocurre. La traza va a backend-errores.log (canal escritura).
        log.exception("No se pudo escribir la bitácora", extra={"canal": CANAL_ESCRITURA, "evento": "bitacora.escritura_fallo",
                                                                "ruta": "bad", "detalle": {"accion": accion, "error": error.__class__.__name__}})
        raise errores.BitacoraNoDisponible(f"No se pudo escribir la bitácora: {error.__class__.__name__}.") from error
    _linea(fila, "Asiento anexado")
    return fila


def _linea(fila: Bitacora, mensaje: str) -> None:
    """§1.1: el log registra QUE se escribió el asiento (secuencia, acción, resultado y huella), nunca sus valores."""
    try:
        log.info("%s #%s %s", mensaje, fila.secuencia, fila.accion,
                 extra={"canal": CANAL_AUDITORIA, "evento": "bitacora.asiento", "ruta": "happy" if fila.resultado == dom.RESULTADO_OK else "sad",
                        "secuencia_bitacora": fila.secuencia,
                        "detalle": {"accion": fila.accion, "resultado": fila.resultado, "modulo": fila.modulo, "actor_tipo": fila.actor_tipo,
                                    "objeto_tabla": fila.objeto_tabla, "huella": fila.huella, "tramo_id": fila.tramo_id}})
    except Exception:   # noqa: BLE001 — el logger nunca eleva al llamador
        pass
