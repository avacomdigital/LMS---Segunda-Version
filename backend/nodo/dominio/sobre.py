"""
El sobre de doce campos del Maestro (BR-002, Parte XI): ninguno es opcional y ninguno se reescribe una vez publicado. Aquí se ARMA y se VALIDA; la secuencia la pone la base al
insertar (P-02) y la inmutabilidad la impone un trigger (P-03).

La carga se revisa contra BR-127 / R-13: sin claves de credenciales, textos de respuestas, documentos, correos, nombres ni rutas, y con un tope de tamaño. Puro: no importa Django.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, replace

from . import catalogos as cat
from .errores import CargaInvalida, SobreIncompleto


@dataclass(frozen=True)
class Sobre:
    evento_id: str
    tipo: str
    version: int
    modulo: str
    creado_en: int
    agregado_tipo: str
    agregado_id: str
    actor: str
    dispositivo_id: str
    correlacion_id: str
    clase: str
    sensibilidad: str
    carga: dict
    secuencia: int | None = None            # la asigna la base al insertar
    catalogado: bool = True                 # False: el tipo no estaba en el catálogo y se aceptó en producción (R-06)
    carga_omitida: bool = False             # True: la carga traía datos que no pueden viajar y se reemplazó (R-06, R-13)

    def con_secuencia(self, secuencia: int) -> "Sobre":
        return replace(self, secuencia=int(secuencia))

    def como_dict(self) -> dict:
        return asdict(self)


def nuevo_evento_id() -> str:
    """UUID4 hexadecimal (P-02) hasta que exista el identificador de cinco segmentos (Q-N2)."""
    return uuid.uuid4().hex


def nuevo_id() -> str:
    """El generador de identificadores que MOD-015 expone a los demás módulos (Q-38): hoy UUID4 con guiones, como el resto del repo; el de cinco segmentos llega con Q-N2."""
    return str(uuid.uuid4())


def _texto(valor, campo: str, maximo: int, *, obligatorio: bool = True) -> str:
    if valor is None or valor == "":
        if obligatorio:
            raise SobreIncompleto(f"Al sobre le falta «{campo}»: ningún campo del sobre es opcional.", campo=campo)
        return ""
    texto = str(valor)
    if len(texto) > maximo:
        raise SobreIncompleto(f"«{campo}» supera los {maximo} caracteres.", campo=campo)
    return texto


def claves_prohibidas_en(carga, prohibidas: frozenset[str] = cat.CLAVES_PROHIBIDAS, _camino: str = "") -> list[str]:
    """Las rutas de las claves de la carga que están en la lista prohibida (a cualquier profundidad, en minúsculas y comparación exacta)."""
    halladas: list[str] = []
    if isinstance(carga, dict):
        for clave, valor in carga.items():
            ruta = f"{_camino}.{clave}" if _camino else str(clave)
            if str(clave).strip().lower() in prohibidas:
                halladas.append(ruta)
            halladas += claves_prohibidas_en(valor, prohibidas, ruta)
    elif isinstance(carga, (list, tuple)):
        for i, valor in enumerate(carga):
            halladas += claves_prohibidas_en(valor, prohibidas, f"{_camino}[{i}]")
    return halladas


def serializar_carga(carga) -> str:
    """La carga como JSON estable (claves ordenadas, sin espacios): lo que se guarda y lo que se mide."""
    return json.dumps(carga, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def revisar_carga(carga, limite_bytes: int = cat.CARGA_MAX_BYTES) -> list[str]:
    """Los problemas de una carga (vacío = ninguna objeción): no es un objeto JSON, no se puede serializar, pesa más del tope, o trae claves prohibidas (BR-127)."""
    problemas: list[str] = []
    if not isinstance(carga, dict):
        return ["la carga debe ser un objeto JSON"]
    try:
        texto = serializar_carga(carga)
    except (TypeError, ValueError) as error:
        return [f"la carga no se puede serializar como JSON ({type(error).__name__})"]
    if len(texto.encode("utf-8")) > limite_bytes:
        problemas.append(f"la carga pesa más de {limite_bytes} bytes")
    halladas = claves_prohibidas_en(carga)
    if halladas:
        problemas.append("claves que no pueden viajar en la cola: " + ", ".join(halladas))
    return problemas


CARGA_OMITIDA = {"_omitida": "carga_con_datos_personales"}


def armar(*, tipo: str, version: int, modulo: str, clase: str, sensibilidad: str, agregado_tipo: str, agregado_id: str, carga: dict, creado_en: int, actor: str,
          dispositivo_id: str, correlacion_id: str, evento_id: str | None = None, catalogado: bool = True, estricto: bool = True) -> Sobre:
    """
    Arma el sobre completo. Con `estricto` (pruebas y desarrollo) una carga con problemas FALLA (`CargaInvalida`); sin él (producción, R-06) el hecho no se pierde: la carga se
    reemplaza por `CARGA_OMITIDA` y el sobre lo dice (`carga_omitida`), para que quien lo publique lo registre como ERROR y deje asiento.
    """
    if clase not in cat.CLASES:
        raise SobreIncompleto(f"La clase «{clase}» no es una de las siete.", campo="clase")
    if sensibilidad not in cat.SENSIBILIDADES:
        raise SobreIncompleto(f"La sensibilidad «{sensibilidad}» no existe.", campo="sensibilidad")
    problemas = revisar_carga(carga)
    omitida = False
    if problemas:
        if estricto:
            raise CargaInvalida("La carga del evento no puede viajar en la cola: " + "; ".join(problemas), tipo=tipo, problemas=problemas)
        carga, omitida = dict(CARGA_OMITIDA), True
    return Sobre(
        evento_id=_texto(evento_id or nuevo_evento_id(), "evento_id", 64),
        tipo=_texto(tipo, "tipo", cat.MAX_TIPO),
        version=int(version),
        modulo=_texto(modulo, "modulo", cat.MAX_MODULO),
        creado_en=int(creado_en),
        agregado_tipo=_texto(agregado_tipo, "agregado_tipo", cat.MAX_AGREGADO_TIPO),
        agregado_id=_texto(agregado_id, "agregado_id", cat.MAX_AGREGADO_ID),
        actor=_texto(actor or cat.SISTEMA, "actor", cat.MAX_ACTOR),
        dispositivo_id=_texto(dispositivo_id or cat.DISPOSITIVO_NODO, "dispositivo_id", cat.MAX_DISPOSITIVO),
        correlacion_id=_texto(correlacion_id or uuid.uuid4().hex, "correlacion_id", cat.MAX_CORRELACION),
        clase=clase,
        sensibilidad=sensibilidad,
        carga=dict(carga),
        catalogado=bool(catalogado),
        carga_omitida=omitida,
    )


def completo(sobre: Sobre) -> bool:
    """¿Tiene los doce campos del Maestro con valor? (La secuencia cuenta sólo una vez insertado.)"""
    return all(getattr(sobre, campo) not in (None, "") for campo in cat.CAMPOS_DEL_SOBRE)
