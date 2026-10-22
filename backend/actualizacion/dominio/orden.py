"""
La orden que Django deja al `Host` y el resultado que el `Host` devuelve (P-06, P-07). Django verifica y decide; el `Host` (servicio SYSTEM) aplica con el backend parado, paso a
paso y con un checkpoint antes de cada uno; al volver a arrancar, Django lee `resultado.json` y lo registra en el historial (FUN-187). Puro.

`orden.json` (formato 1):
    {"formato": 1, "orden_id", "paquete_id", "accion": "aplicar"|"revertir", "emitida_en", "emitida_por", "limite_minutos": 3|5, "ventana": {desde, hasta}|null,
     "paquete": {"nombre", "version_producto", "serie", "sha256", "bytes", "kid"},
     "modulos": [{"nombre", "version", "version_datos", "migraciones": [{"nombre", "reverso"}]}],
     "archivos": [{"ruta", "bytes", "sha256"}],                       (en una reversión: los que hay que restaurar desde la instantánea)
     "carpetas": {"staging", "instantanea"},                            (relativas a la carpeta de actualizaciones: el Host conoce la raíz)
     "pasos": [...]}

`resultado.json` (formato 1):
    {"formato": 1, "orden_id", "paquete_id", "accion", "resultado": "aplicado"|"revertido"|"reversion_fallida"|"aplazada"|"rechazada", "paso": "<último paso alcanzado>",
     "iniciado_en", "terminado_en", "duracion_ms", "detalle": "...", "respaldo": "<carpeta>"|null, "migraciones": [{"modulo", "nombre", "ok"}], "error": "..."|null}
"""
from __future__ import annotations

from dataclasses import dataclass

from . import catalogos as cat
from .errores import DatosInvalidos
from .manifiesto import Manifiesto

CARPETA_STAGING, CARPETA_VERSIONES, CARPETA_ANTERIOR = "staging", "versiones", "anterior"


def limite_minutos(m: Manifiesto) -> int:
    """C-3 / Q-U2: 3 minutos si el paquete toca `evaluacion`; 5 en general."""
    return cat.LIMITE_MIN_EVALUACION if m.toca_evaluacion else cat.LIMITE_MIN_GENERAL


def armar(*, orden_id: str, accion: str, m: Manifiesto, sha256: str, bytes_paquete: int, kid: str, ahora: int, actor: str, ventana: dict | None, nota: str = "") -> dict:
    if accion not in cat.ACCIONES:
        raise DatosInvalidos("Acción desconocida.")
    reversion = accion == cat.ACCION_REVERTIR
    return {
        "formato": cat.FORMATO_ORDEN, "orden_id": orden_id, "paquete_id": m.paquete_id, "accion": accion, "emitida_en": int(ahora), "emitida_por": actor,
        "limite_minutos": limite_minutos(m), "ventana": dict(ventana) if ventana else None, "nota": nota[:cat.MAX_NOTA],
        "paquete": {"nombre": m.nombre, "version_producto": m.version_producto, "serie": m.serie, "sha256": sha256, "bytes": int(bytes_paquete), "kid": kid},
        "modulos": [{"nombre": x.nombre, "version": x.version, "version_datos": x.version_datos, "version_contrato": x.version_contrato, "serie": x.serie,
                     "migraciones": [{"nombre": g.nombre, "reverso": g.reverso} for g in (reversed(x.migraciones) if reversion else x.migraciones)]} for x in m.modulos],
        "archivos": [{"ruta": a.ruta, "bytes": a.bytes, "sha256": a.sha256} for a in m.archivos],
        "carpetas": {"staging": f"{CARPETA_STAGING}/{m.paquete_id}", "instantanea": f"{CARPETA_VERSIONES}/{m.paquete_id}/{CARPETA_ANTERIOR}"},
        "pasos": list(cat.PASOS_REVERSION if reversion else cat.PASOS),
    }


@dataclass(frozen=True)
class Resultado:
    orden_id: str
    paquete_id: str
    accion: str
    resultado: str
    paso: str
    iniciado_en: int
    terminado_en: int
    duracion_ms: int
    detalle: str
    respaldo: str | None
    migraciones: tuple[dict, ...]
    error: str | None

    @property
    def exito(self) -> bool:
        return self.resultado in (cat.R_APLICADO, cat.R_REVERTIDO)

    def como_dict(self) -> dict:
        return {"orden_id": self.orden_id, "paquete_id": self.paquete_id, "accion": self.accion, "resultado": self.resultado, "paso": self.paso, "iniciado_en": self.iniciado_en,
                "terminado_en": self.terminado_en, "duracion_ms": self.duracion_ms, "detalle": self.detalle, "respaldo": bool(self.respaldo), "migraciones": list(self.migraciones),
                "error": self.error}


def _texto(valor, maximo: int = 2000) -> str:
    return str(valor or "")[:maximo]


def leer_resultado(datos) -> Resultado:
    """`resultado.json` validado. Lo que no tenga la forma esperada se rechaza (el Host es nuestro, pero el archivo vive en disco)."""
    if not isinstance(datos, dict) or datos.get("formato") != cat.FORMATO_ORDEN:
        raise DatosInvalidos("El resultado no tiene la forma esperada.")
    resultado, accion = str(datos.get("resultado") or ""), str(datos.get("accion") or "")
    if resultado not in cat.RESULTADOS or accion not in cat.ACCIONES:
        raise DatosInvalidos("El resultado trae una acción o un resultado desconocidos.")
    orden_id, paquete_id = _texto(datos.get("orden_id"), 64), _texto(datos.get("paquete_id"), 36)
    if not orden_id or not paquete_id:
        raise DatosInvalidos("El resultado no dice de qué orden es.")
    iniciado, terminado = datos.get("iniciado_en", 0), datos.get("terminado_en", 0)
    if not isinstance(iniciado, int) or not isinstance(terminado, int) or isinstance(iniciado, bool) or isinstance(terminado, bool) or terminado < iniciado:
        raise DatosInvalidos("El resultado trae instantes inválidos.")
    migraciones = datos.get("migraciones") or []
    if not isinstance(migraciones, list):
        raise DatosInvalidos("El resultado trae migraciones inválidas.")
    paso = _texto(datos.get("paso"), 32)
    return Resultado(orden_id=orden_id, paquete_id=paquete_id, accion=accion, resultado=resultado, paso=paso if paso in cat.PASOS else "", iniciado_en=iniciado, terminado_en=terminado,
                     duracion_ms=max(0, int(datos.get("duracion_ms") or (terminado - iniciado))), detalle=_texto(datos.get("detalle")), respaldo=_texto(datos.get("respaldo"), 500) or None,
                     migraciones=tuple({"modulo": _texto(g.get("modulo"), 32), "nombre": _texto(g.get("nombre"), 90), "ok": bool(g.get("ok"))} for g in migraciones if isinstance(g, dict)),
                     error=_texto(datos.get("error")) or None)
