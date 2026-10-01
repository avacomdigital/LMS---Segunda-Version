"""Resumen de la bitácora para `GET /api/auditoria/estado/` y el semáforo de OPS (§4.2, §5.1)."""
from __future__ import annotations

from django.conf import settings
from django.db import connection

from ..dominio import catalogos
from ..dominio import tramo as dom_tramo
from ..infraestructura import triggers
from ..models import Bitacora, BitacoraTramo
from . import anexar as app
from . import rotar


def abreviada(huella: str | None) -> str | None:
    return f"{huella[:8]}…{huella[-8:]}" if huella else None


def tramo_como_dict(t: BitacoraTramo, con_firma: bool = False) -> dict:
    salida = {
        "id": t.pk, "desde": t.desde_secuencia, "hasta": t.hasta_secuencia, "estado": t.estado, "abierta": t.abierta,
        "huella_cierre": abreviada(t.huella_cierre), "verificado_en": t.verificado_en, "verificado_hasta": t.verificado_hasta,
        "salto_en": t.salto_en_secuencia, "salto_causa": t.salto_causa or None, "exportado_en": t.exportado_en,
        "archivo": t.archivo, "rotado_en": t.rotado_en, "creado_en": t.creado_en, "asientos": max(0, t.hasta_secuencia - t.desde_secuencia + 1),
    }
    if con_firma:
        salida["firma"] = t.firma
    return salida


def estado() -> dict:
    activo = app.tramo_activo(bloquear=False)
    ultimo_verificado = BitacoraTramo.objects.exclude(verificado_en__isnull=True).order_by("-verificado_en").first()
    con_salto = BitacoraTramo.objects.filter(estado=dom_tramo.ESTADO_CON_SALTO).order_by("desde_secuencia").first()
    tamano = rotar.tamano_estimado(activo.pk if activo else None)
    umbral = rotar.umbral_bytes()
    return {
        "cabeza": {"secuencia": activo.hasta_secuencia if activo else 0, "huella": abreviada(activo.huella_cierre) if activo else None},
        "total_asientos": Bitacora.objects.count(),
        "tramo_activo": tramo_como_dict(activo) if activo else None,
        "ultimo_verificado_en": ultimo_verificado.verificado_en if ultimo_verificado else None,
        "salto_detectado": con_salto is not None,
        "salto": {"tramo_id": con_salto.pk, "secuencia": con_salto.salto_en_secuencia, "causa": con_salto.salto_causa} if con_salto else None,
        "triggers_ok": triggers.completos(connection),
        "tamano_bytes": tamano,
        "umbral_bytes": umbral,
        "porcentaje_umbral": round(100.0 * tamano / umbral, 2) if umbral else None,
        "tramos": BitacoraTramo.objects.count(),
        "version_catalogo": catalogos.VERSION_CATALOGO,
        "verificar_cada_s": int(getattr(settings, "AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S", 3600)),
    }
