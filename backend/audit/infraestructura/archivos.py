"""
Archivos de la bitácora en disco (019-06, 019-07): tramos rotados y exportaciones, en JSON Lines con un manifiesto
firmado. Viven junto a los logs del nodo (`<carpeta de logs>\\auditoria\\`), que el instalador marca como «no desinstalar».
Las filas de la tabla NUNCA se borran al rotar (INV-027): el archivo es una copia congelada.
"""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings

from .firma import VERSION_FORMATO, firmar


def carpeta_auditoria() -> Path:
    base = Path(getattr(settings, "AVACOM_LMS_DIR_LOGS_EFECTIVO", Path(settings.BASE_DIR) / "logs"))
    return base / "auditoria"


def carpeta_exportaciones() -> Path:
    return carpeta_auditoria() / "exportaciones"


def fila_como_dict(fila) -> dict:
    return {
        "id": fila.id, "secuencia": fila.secuencia, "huella_previa": fila.huella_previa, "huella": fila.huella,
        "ocurrido_en": fila.ocurrido_en, "usuario_id": fila.usuario_id, "actor_tipo": fila.actor_tipo, "roles_activos": fila.roles_activos,
        "modulo": fila.modulo, "accion": fila.accion, "resultado": fila.resultado, "objeto_tabla": fila.objeto_tabla,
        "objeto_id": fila.objeto_id, "valor_anterior": fila.valor_anterior, "valor_nuevo": fila.valor_nuevo, "motivo": fila.motivo,
        "origen": fila.origen, "dispositivo_id": fila.dispositivo_id, "correlacion_id": fila.correlacion_id, "evento_id": fila.evento_id,
        "tramo_id": fila.tramo_id,
    }


def manifiesto(tramo_id: str, desde: int, hasta: int, huella_inicial: str, huella_cierre: str, total: int,
               exportado_por: str | None, exportado_en: int, alcance: str, motivo: str | None = None) -> dict:
    return {"version_formato": VERSION_FORMATO, "tramo_id": tramo_id, "desde": desde, "hasta": hasta, "huella_inicial": huella_inicial,
            "huella_cierre": huella_cierre, "total": total, "exportado_por": exportado_por, "exportado_en": exportado_en,
            "alcance": alcance, "motivo": motivo}


def escribir(ruta: Path, asientos, manifiesto_dict: dict) -> tuple[Path, str]:
    """Escribe el archivo: primera línea el manifiesto firmado, después un asiento por línea. Devuelve (ruta, firma)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    firma = firmar(manifiesto_dict)
    temporal = ruta.with_suffix(ruta.suffix + ".parcial")
    with temporal.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"manifiesto": manifiesto_dict, "firma": firma}, ensure_ascii=False, sort_keys=True) + "\n")
        for fila in asientos:
            f.write(json.dumps(fila_como_dict(fila) if not isinstance(fila, dict) else fila, ensure_ascii=False, sort_keys=True) + "\n")
    temporal.replace(ruta)
    return ruta, firma


def leer_manifiesto(ruta: Path) -> tuple[dict, str] | None:
    try:
        with Path(ruta).open(encoding="utf-8") as f:
            primera = json.loads(f.readline())
        return primera["manifiesto"], primera["firma"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
