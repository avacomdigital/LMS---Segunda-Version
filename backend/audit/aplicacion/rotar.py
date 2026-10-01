"""
Rotar por tamaño (019-07, FUN-201, §4.3). Cuando el tamaño estimado del tramo abierto supera el umbral
(`AVACOM_LMS_AUDITORIA_UMBRAL_MB`, 100 MB por defecto): verificar el tramo → marcarlo `rotada` y escribir su archivo
(`<logs>\\auditoria\\tramo-<desde>-<hasta>.jsonl` con manifiesto firmado) → abrir un tramo nuevo cuyo primer asiento
toma `huella_previa = huella_cierre`. Las filas NO se borran de la tabla (INV-027): la rotación sólo las congela.
Emite `auditoria.bitacora_rotada.v1`.

El tamaño se estima sumando el largo de los campos variables de cada asiento más un fijo por fila: SQLite no da el
tamaño por tabla sin `dbstat`, y esta estimación es estable y barata.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection, transaction

from .. import contexto
from ..dominio import asiento as dom
from ..dominio import errores
from ..dominio import tramo as dom_tramo
from ..infraestructura import archivos, eventos
from ..logging_setup import CANAL_AUDITORIA, LOGGER_AUDITORIA
from ..models import Bitacora, BitacoraTramo, ahora_ms
from . import anexar as app
from . import verificar

log = logging.getLogger(LOGGER_AUDITORIA)

BYTES_FIJOS_POR_FILA = 320


def umbral_bytes() -> int:
    return int(getattr(settings, "AVACOM_LMS_AUDITORIA_UMBRAL_MB", 100)) * 1024 * 1024


def tamano_estimado(tramo_id: str | None = None) -> int:
    sql = ("SELECT COALESCE(SUM(LENGTH(COALESCE(valor_anterior, '')) + LENGTH(COALESCE(valor_nuevo, '')) + LENGTH(COALESCE(motivo, '')) "
           "+ LENGTH(COALESCE(roles_activos, '')) + %s), 0) FROM m19_bitacora")
    params: list = [BYTES_FIJOS_POR_FILA]
    if tramo_id:
        sql += " WHERE tramo_id = %s"
        params.append(tramo_id)
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return int(cursor.fetchone()[0] or 0)


def rotar_si_supera() -> dict | None:
    tramo = app.tramo_activo(bloquear=False)
    if tramo is None:
        return None
    if tamano_estimado(tramo.pk) < umbral_bytes():
        return None
    return rotar(motivo="umbral_tamano")


def rotar(motivo: str = "manual") -> dict:
    """Cierra el tramo abierto y abre el siguiente. Exige que el tramo verifique sin salto."""
    ctx = contexto.actual()
    with transaction.atomic():
        tramo = app.tramo_activo()
        if tramo is None:
            raise errores.NoEncontrado("No hay tramo abierto que rotar.")
        if tramo.hasta_secuencia < tramo.desde_secuencia:
            raise errores.DatosInvalidos("El tramo abierto aún no tiene asientos.")
        r = verificar.verificar_tramo(tramo, desde_cero=True)
        if not r.ok:
            raise errores.CadenaConSalto(f"El tramo tiene un salto en la secuencia {r.salto_en_secuencia} ({r.causa}); no se rota.",
                                         salto_en=r.salto_en_secuencia, causa=r.causa)
        ahora = ahora_ms()
        asientos = Bitacora.objects.filter(tramo=tramo).order_by("secuencia")
        huella_inicial = asientos.first().huella_previa
        manifiesto = archivos.manifiesto(tramo.pk, tramo.desde_secuencia, tramo.hasta_secuencia, huella_inicial, tramo.huella_cierre,
                                         asientos.count(), ctx.usuario_id, ahora, alcance=f"tramo:{tramo.pk}", motivo=motivo)
        ruta = archivos.carpeta_auditoria() / f"tramo-{tramo.desde_secuencia}-{tramo.hasta_secuencia}.jsonl"
        ruta, firma = archivos.escribir(ruta, asientos.iterator(), manifiesto)
        BitacoraTramo.objects.filter(pk=tramo.pk).update(estado=dom_tramo.ESTADO_ROTADA, abierta=False, rotado_en=ahora, archivo=str(ruta), firma=firma)
        nuevo = app.abrir_tramo(tramo.huella_cierre, tramo.hasta_secuencia + 1)
        fila = app.anexar("auditoria.bitacora_rotada", actor_tipo=dom.ACTOR_USUARIO if ctx.usuario_id else dom.ACTOR_SISTEMA,
                          usuario_id=ctx.usuario_id, modulo="auditoria", objeto_tabla="m19_bitacora_tramo", objeto_id=tramo.pk,
                          roles_activos=ctx.roles_activos() or None,
                          valor_nuevo={"desde": tramo.desde_secuencia, "hasta": tramo.hasta_secuencia, "archivo": ruta.name, "motivo": motivo,
                                       "tramo_nuevo": nuevo.pk, "huella_cierre": tramo.huella_cierre})
        eventos.publicar(eventos.EV_BITACORA_ROTADA, "bitacora_tramo", tramo.pk,
                         {"desde": tramo.desde_secuencia, "hasta": tramo.hasta_secuencia, "archivo": ruta.name, "tramo_nuevo": nuevo.pk, "secuencia": fila.secuencia})
    log.info("Bitácora rotada: tramo %s-%s → %s", tramo.desde_secuencia, tramo.hasta_secuencia, ruta.name,
             extra={"canal": CANAL_AUDITORIA, "evento": "auditoria.bitacora_rotada", "ruta": "happy",
                    "detalle": {"tramo_id": tramo.pk, "archivo": str(ruta), "tramo_nuevo": nuevo.pk, "motivo": motivo}})
    return {"tramo_id": tramo.pk, "desde": tramo.desde_secuencia, "hasta": tramo.hasta_secuencia, "archivo": str(ruta), "firma": firma,
            "tramo_nuevo": nuevo.pk, "secuencia_asiento": fila.secuencia}
