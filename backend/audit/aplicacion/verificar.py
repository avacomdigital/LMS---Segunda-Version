"""
Verificar la cadena (019-04, FUN-198/199, §4.3): recorre cada tramo por secuencia recalculando la huella con la
previa y detecta (a) huella discordante, (b) hueco o repetición de secuencia, (c) `huella_previa` que no enlaza,
(d) cabeza del tramo discordante con sus asientos y (e) triggers de inmutabilidad ausentes en sqlite_master.

Verifica en bloques (5.000 asientos) retomando de la última secuencia verificada, para no bloquear el nodo durante
una clase. Resultado: `tramo.estado = verificada` y evento `auditoria.cadena_verificada.v1`, o `con_salto` con
`salto_en_secuencia` y evento `auditoria.salto_detectado.v1` (línea ERROR en backend-auditoria.log).
Precondición FUN-198: al menos dos asientos en la cadena.
"""
from __future__ import annotations

import logging

from django.db import connection, transaction

from .. import contexto
from ..dominio import asiento as dom
from ..dominio import tramo as dom_tramo
from ..infraestructura import eventos, triggers
from ..logging_setup import CANAL_AUDITORIA, LOGGER_AUDITORIA
from ..models import Bitacora, BitacoraTramo, ahora_ms
from . import anexar as app

log = logging.getLogger(LOGGER_AUDITORIA)

BLOQUE = 5000
MINIMO_ASIENTOS = 2


def _huella_inicial(tramo: BitacoraTramo) -> str:
    """La huella con la que empieza el tramo: la del último asiento del tramo anterior (o génesis)."""
    anterior = BitacoraTramo.objects.filter(hasta_secuencia__lt=tramo.desde_secuencia).order_by("-hasta_secuencia").first()
    if anterior is None:
        from ..dominio import huella
        return huella.GENESIS
    return anterior.huella_cierre


def verificar_tramo(tramo: BitacoraTramo, bloque: int = BLOQUE, desde_cero: bool = False) -> dom_tramo.ResultadoVerificacion:
    """Verifica (o retoma) un tramo. No cambia su estado si está `rotada` salvo para marcar un salto."""
    if not triggers.completos(connection):
        return _salto(tramo, tramo.desde_secuencia, dom_tramo.CAUSA_TRIGGERS, 0)
    inicio = tramo.desde_secuencia
    previa = _huella_inicial(tramo)
    if not desde_cero and tramo.verificado_hasta and tramo.verificado_hasta >= tramo.desde_secuencia:
        ultimo = Bitacora.objects.filter(secuencia=tramo.verificado_hasta, tramo=tramo).first()
        if ultimo is not None:
            inicio, previa = tramo.verificado_hasta + 1, ultimo.huella
    tope = tramo.hasta_secuencia
    verificados = 0
    esperada = inicio
    while esperada <= tope:
        filas = list(Bitacora.objects.filter(tramo=tramo, secuencia__gte=esperada).order_by("secuencia")[:bloque])
        if not filas:
            # Faltan asientos entre `esperada` y la cabeza: hueco al final.
            return _salto(tramo, esperada, dom_tramo.CAUSA_HUECO, verificados)
        lote = [{**f.canonico(), "huella_previa": f.huella_previa, "huella": f.huella} for f in filas]
        r = dom_tramo.verificar(lote, previa, esperada)
        verificados += r.verificados
        if not r.ok:
            return _salto(tramo, r.salto_en_secuencia or esperada, r.causa or dom_tramo.CAUSA_HUELLA, verificados)
        previa = r.huella_final or previa
        esperada = filas[-1].secuencia + 1
    if Bitacora.objects.filter(tramo=tramo, secuencia__gt=tope).exists() or (tope >= tramo.desde_secuencia and previa.lower() != tramo.huella_cierre.lower()):
        return _salto(tramo, tope, dom_tramo.CAUSA_CABEZA, verificados)
    return _verificado(tramo, tope, previa, verificados)


def _verificado(tramo: BitacoraTramo, hasta: int, huella_final: str, verificados: int) -> dom_tramo.ResultadoVerificacion:
    ahora = ahora_ms()
    campos = {"verificado_en": ahora, "verificado_hasta": hasta, "salto_en_secuencia": None, "salto_causa": ""}
    # El tramo abierto pasa a «verificada» (sigue recibiendo asientos: `verificado_hasta` dice hasta dónde se comprobó);
    # un tramo ya rotado conserva «rotada» y sólo anota la verificación.
    campos["estado"] = dom_tramo.ESTADO_ROTADA if tramo.rotado_en is not None else dom_tramo.ESTADO_VERIFICADA
    BitacoraTramo.objects.filter(pk=tramo.pk).update(**campos)
    for k, v in campos.items():
        setattr(tramo, k, v)
    log.info("Cadena verificada: tramo %s-%s (%s asientos)", tramo.desde_secuencia, hasta, verificados,
             extra={"canal": CANAL_AUDITORIA, "evento": "auditoria.cadena_verificada", "ruta": "happy",
                    "detalle": {"tramo_id": tramo.pk, "desde": tramo.desde_secuencia, "hasta": hasta, "verificados": verificados, "huella": huella_final}})
    return dom_tramo.ResultadoVerificacion(True, verificados, None, None, huella_final)


def _salto(tramo: BitacoraTramo, secuencia: int, causa: str, verificados: int) -> dom_tramo.ResultadoVerificacion:
    ahora = ahora_ms()
    BitacoraTramo.objects.filter(pk=tramo.pk).update(estado=dom_tramo.ESTADO_CON_SALTO, verificado_en=ahora, salto_en_secuencia=secuencia, salto_causa=causa)
    tramo.estado, tramo.verificado_en, tramo.salto_en_secuencia, tramo.salto_causa = dom_tramo.ESTADO_CON_SALTO, ahora, secuencia, causa
    log.error("SALTO en la cadena de auditoría: tramo %s-%s, secuencia %s (%s)", tramo.desde_secuencia, tramo.hasta_secuencia, secuencia, causa,
              extra={"canal": CANAL_AUDITORIA, "evento": "auditoria.salto_detectado", "ruta": "bad",
                     "detalle": {"tramo_id": tramo.pk, "salto_en": secuencia, "causa": causa, "verificados": verificados}})
    return dom_tramo.ResultadoVerificacion(False, verificados, secuencia, causa)


def verificar_cadena(todos: bool = False, bloque: int = BLOQUE) -> dict:
    """Verifica el tramo activo y los que aún no están verificados (o todos con `todos=True`). Deja un asiento y un
    evento por resultado. Devuelve `{estado, verificados, salto_en, causa, tramos}`."""
    if Bitacora.objects.count() < MINIMO_ASIENTOS:
        return {"estado": "insuficiente", "verificados": 0, "salto_en": None, "causa": None, "tramos": []}
    with transaction.atomic():
        candidatos = BitacoraTramo.objects.select_for_update().order_by("desde_secuencia")
        if not todos:
            candidatos = candidatos.exclude(estado=dom_tramo.ESTADO_ROTADA, verificado_en__isnull=False)
        resultados = []
        salto = None
        verificados = 0
        for tramo in list(candidatos):
            r = verificar_tramo(tramo, bloque=bloque, desde_cero=todos)
            verificados += r.verificados
            resultados.append({"tramo_id": tramo.pk, "desde": tramo.desde_secuencia, "hasta": tramo.hasta_secuencia, "estado": tramo.estado,
                               "verificados": r.verificados, "salto_en": r.salto_en_secuencia, "causa": r.causa})
            if not r.ok and salto is None:
                salto = r
        ctx = contexto.actual()
        if salto is None:
            fila = app.anexar("auditoria.cadena_verificada", actor_tipo=_actor_tipo(), usuario_id=ctx.usuario_id, modulo="auditoria",
                              objeto_tabla="m19_bitacora_tramo", roles_activos=ctx.roles_activos() or None,
                              valor_nuevo={"verificados": verificados, "tramos": [t["tramo_id"] for t in resultados]})
            eventos.publicar(eventos.EV_CADENA_VERIFICADA, "bitacora", fila.tramo_id, {"verificados": verificados, "secuencia": fila.secuencia})
            return {"estado": dom_tramo.ESTADO_VERIFICADA, "verificados": verificados, "salto_en": None, "causa": None, "tramos": resultados}
        fila = app.anexar("auditoria.salto_detectado", actor_tipo=_actor_tipo(), usuario_id=ctx.usuario_id, modulo="auditoria",
                          resultado=dom.RESULTADO_FALLIDO, objeto_tabla="m19_bitacora_tramo", roles_activos=ctx.roles_activos() or None,
                          valor_nuevo={"salto_en": salto.salto_en_secuencia, "causa": salto.causa, "verificados": verificados})
        eventos.publicar(eventos.EV_SALTO_DETECTADO, "bitacora", fila.tramo_id,
                         {"salto_en": salto.salto_en_secuencia, "causa": salto.causa, "prioridad": "alta", "secuencia": fila.secuencia})
        return {"estado": dom_tramo.ESTADO_CON_SALTO, "verificados": verificados, "salto_en": salto.salto_en_secuencia, "causa": salto.causa, "tramos": resultados}


def _actor_tipo() -> str:
    return dom.ACTOR_USUARIO if contexto.actual().usuario_id else dom.ACTOR_SISTEMA
