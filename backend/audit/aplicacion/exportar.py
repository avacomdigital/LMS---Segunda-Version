"""
Exportar un tramo firmado (019-06, FUN-200, BR-105, ESC-03, VER-04, TST-072, §4.3).

Precondiciones: permiso `audit.export`, autorización de salida VIGENTE por operación (una escalada temporal de
`audit.export` concedida por otra identidad, con motivo y caducidad), rango existente y cadena verificada sin salto en
ese rango. El archivo contiene el manifiesto firmado y los asientos del rango; se asienta `auditoria.tramo_exportado`
con alcance, rango, autor y motivo (lista cerrada: nodo táctil), y la escalada se cierra por consumo. Sin autorización:
`403 autorizacion_requerida`, NO se genera archivo y queda `auditoria.exportacion_denegada`.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from django.db import transaction

from .. import contexto
from ..dominio import asiento as dom
from ..dominio import errores
from ..dominio import tramo as dom_tramo
from ..infraestructura import archivos, eventos
from ..models import Bitacora, BitacoraTramo, ahora_ms
from . import anexar as app
from . import verificar

P_EXPORT = "audit.export"

# Motivos de exportación (lista cerrada, MSG-054): el nodo principal no tiene teclado.
MOTIVOS = {
    "inspeccion_interna": "Inspección interna",
    "auditoria_externa": "Auditoría externa",
    "requerimiento_legal": "Requerimiento legal o de la autoridad educativa",
    "respaldo_externo": "Respaldo externo de evidencia",
    "soporte_avacom": "Soporte técnico de AVACOM",
}

MSG_054 = "Queda registrado que exportaste {alcance}."


def motivos() -> list[dict]:
    return [{"codigo": c, "etiqueta": e} for c, e in MOTIVOS.items()]


def _rango(tramo_id: str | None, desde: int | None, hasta: int | None) -> tuple[int, int, BitacoraTramo | None, str]:
    if tramo_id:
        tramo = BitacoraTramo.objects.filter(pk=tramo_id).first()
        if tramo is None:
            raise errores.NoEncontrado("No existe ese tramo.")
        if tramo.hasta_secuencia < tramo.desde_secuencia:
            raise errores.DatosInvalidos("El tramo aún no tiene asientos.")
        return tramo.desde_secuencia, tramo.hasta_secuencia, tramo, f"tramo {tramo.desde_secuencia}-{tramo.hasta_secuencia}"
    desde, hasta = int(desde), int(hasta)
    existentes = Bitacora.objects.filter(secuencia__gte=desde, secuencia__lte=hasta).count()
    if existentes == 0:
        raise errores.NoEncontrado("No hay asientos en ese rango.")
    if existentes != hasta - desde + 1:
        raise errores.CadenaConSalto("El rango tiene secuencias faltantes: hay que aclarar el salto antes de exportar.", desde=desde, hasta=hasta)
    return desde, hasta, None, f"asientos {desde}-{hasta}"


def _exigir_verificado(desde: int, hasta: int) -> None:
    """FUN-200 pide un rango verificado: cada tramo que toca el rango debe estar verificado hasta donde el rango llega."""
    tramos = BitacoraTramo.objects.filter(hasta_secuencia__gte=desde, desde_secuencia__lte=hasta).order_by("desde_secuencia")
    for tramo in tramos:
        if tramo.estado == dom_tramo.ESTADO_CON_SALTO:
            raise errores.CadenaConSalto(f"El tramo {tramo.desde_secuencia}-{tramo.hasta_secuencia} tiene un salto en la secuencia {tramo.salto_en_secuencia}.",
                                         salto_en=tramo.salto_en_secuencia, causa=tramo.salto_causa)
        necesario = min(hasta, tramo.hasta_secuencia)
        if tramo.verificado_en is None or (tramo.verificado_hasta or 0) < necesario:
            r = verificar.verificar_tramo(tramo)
            if not r.ok:
                raise errores.CadenaConSalto(f"Salto en la secuencia {r.salto_en_secuencia} ({r.causa}).", salto_en=r.salto_en_secuencia, causa=r.causa)


def exportar(principal, autorizacion, *, tramo_id: str | None = None, desde: int | None = None, hasta: int | None = None,
             motivo_codigo: str, motivo_detalle: str = "") -> dict:
    ctx = contexto.actual()
    desde_s, hasta_s, tramo, alcance = _rango(tramo_id, desde, hasta)
    if motivo_codigo not in MOTIVOS:
        raise errores.DatosInvalidos("El motivo debe ser uno de la lista.", motivos=list(MOTIVOS))
    motivo = MOTIVOS[motivo_codigo] + (f": {motivo_detalle.strip()}" if motivo_detalle and motivo_detalle.strip() else "")
    if not autorizacion.tiene_escalada(principal, P_EXPORT):
        app.anexar("auditoria.exportacion_denegada", actor_tipo=dom.ACTOR_USUARIO, usuario_id=principal.usuario_id, modulo="auditoria",
                   resultado=dom.RESULTADO_DENEGADO, objeto_tabla="m19_bitacora_tramo", objeto_id=tramo.pk if tramo else None,
                   motivo=motivo[:dom.MAX_MOTIVO], roles_activos=ctx.roles_activos() or None,
                   valor_nuevo={"alcance": alcance, "desde": desde_s, "hasta": hasta_s, "causa": "autorizacion_requerida"})
        raise errores.AutorizacionRequerida("Exportar exige una autorización de salida vigente (escalada de audit.export por una operación).",
                                            permiso=P_EXPORT)
    with transaction.atomic():
        _exigir_verificado(desde_s, hasta_s)
        exportacion_id = str(uuid.uuid4())
        ahora = ahora_ms()
        asientos = Bitacora.objects.filter(secuencia__gte=desde_s, secuencia__lte=hasta_s).order_by("secuencia")
        primero, ultimo = asientos.first(), asientos.last()
        manifiesto = archivos.manifiesto(tramo.pk if tramo else "", desde_s, hasta_s, primero.huella_previa, ultimo.huella, asientos.count(),
                                         principal.usuario_id, ahora, alcance=alcance, motivo=motivo)
        manifiesto["exportacion_id"] = exportacion_id
        ruta = archivos.carpeta_exportaciones() / f"exportacion-{exportacion_id}.jsonl"
        ruta, firma = archivos.escribir(ruta, asientos.iterator(), manifiesto)
        if tramo is not None:
            BitacoraTramo.objects.filter(pk=tramo.pk).update(exportado_en=ahora)
        fila = app.anexar("auditoria.tramo_exportado", actor_tipo=dom.ACTOR_USUARIO, usuario_id=principal.usuario_id, modulo="auditoria",
                          objeto_tabla="exportacion", objeto_id=exportacion_id, motivo=motivo[:dom.MAX_MOTIVO], roles_activos=ctx.roles_activos() or None,
                          valor_nuevo={"alcance": alcance, "desde": desde_s, "hasta": hasta_s, "tramo_id": tramo.pk if tramo else None,
                                       "archivo": ruta.name, "archivo_ruta": str(ruta), "firma": firma, "total": manifiesto["total"],
                                       "motivo_codigo": motivo_codigo})
        eventos.publicar(eventos.EV_TRAMO_EXPORTADO, "exportacion", exportacion_id,
                         {"alcance": alcance, "desde": desde_s, "hasta": hasta_s, "exportado_por": principal.usuario_id, "secuencia": fila.secuencia})
    autorizacion.consumir_escalada(principal, P_EXPORT, operacion=f"exportacion:{exportacion_id}")
    return {"exportacion_id": exportacion_id, "alcance": alcance, "desde": desde_s, "hasta": hasta_s, "total": manifiesto["total"],
            "archivo": ruta.name, "firma": firma, "exportado_en": ahora, "secuencia_asiento": fila.secuencia,
            "mensaje": MSG_054.format(alcance=alcance), "descarga": f"/api/auditoria/exportaciones/{exportacion_id}/descargar/"}


def archivo_de(exportacion_id: str) -> tuple[Path, Bitacora]:
    fila = Bitacora.objects.filter(accion="auditoria.tramo_exportado", objeto_tabla="exportacion", objeto_id=exportacion_id).first()
    if fila is None:
        raise errores.NoEncontrado("No existe esa exportación.")
    ruta = Path((fila.valor_nuevo or {}).get("archivo_ruta") or "")
    if not ruta.is_file():
        raise errores.NoEncontrado("El archivo de esa exportación ya no está en el nodo.")
    return ruta, fila


def listar() -> list[dict]:
    salida = []
    for f in Bitacora.objects.filter(accion="auditoria.tramo_exportado", objeto_tabla="exportacion").order_by("-secuencia")[:200]:
        v = f.valor_nuevo or {}
        salida.append({"exportacion_id": f.objeto_id, "exportado_en": f.ocurrido_en, "exportado_por": f.usuario_id, "alcance": v.get("alcance"),
                       "desde": v.get("desde"), "hasta": v.get("hasta"), "total": v.get("total"), "archivo": v.get("archivo"), "motivo": f.motivo,
                       "disponible": Path(v.get("archivo_ruta") or "").is_file(), "descarga": f"/api/auditoria/exportaciones/{f.objeto_id}/descargar/"})
    return salida
