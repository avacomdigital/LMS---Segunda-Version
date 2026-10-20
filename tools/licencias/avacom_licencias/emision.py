"""
La lógica de EMITIR, sin entrada ni salida: de una solicitud verificada y una petición (plan + ajustes) a una `Licencia` del dominio del nodo, y de ahí a los bytes firmados.

Reglas que importan (están en la guía interna y en `requerimientos.md`, §8.1):

  · La HUELLA de la licencia es la de la solicitud, tal cual (`k` de `n` hashes); `hash_clave_nodo` es el SHA-256 de la llave pública del nodo que la pidió.
  · `desde` = hoy a las 00:00 UTC MENOS UN DÍA: un colegio sin internet puede tener el reloj atrasado y una licencia que «todavía no empieza» lo devolvería a la evaluación (H-08).
  · `vence` = las 23:59:59.999 UTC del día elegido.
  · Sólo se emiten los tipos `produccion` y `evaluacion`: el de `desarrollo` no se firma con una llave de producción.
  · Lo que se escribe se vuelve a LEER con el lector del nodo y debe decir exactamente lo pedido: un archivo que no verifica no se entrega.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone

from . import planes as pl
from .dominio_nodo import firma, licencia, tlv

DIA_MS = 86_400_000
MARGEN_DESDE_DIAS = 1
SOLICITUD_VIEJA_DIAS = 30


class ErrorDeEmision(ValueError):
    """Algo de lo pedido no se puede emitir. El mensaje se le muestra tal cual a quien opera."""


@dataclass(frozen=True)
class Peticion:
    aula: str
    tipo: str
    gracia_dias: int
    equipos: int
    usuarios: int
    normal: int
    pico: int
    capacidades: frozenset[str]
    hasta: date | None = None
    meses: int | None = None
    liberacion_dias: int | None = None      # un número = licencia con LIBERACION_PENDIENTE por esos días (JRN-020, caso B)

    @property
    def sin_tope(self) -> bool:
        return licencia.ILIMITADO in (self.equipos, self.usuarios, self.normal, self.pico)


def validar(p: Peticion) -> None:
    if p.tipo not in pl.TIPOS_EMITIBLES:
        raise ErrorDeEmision(f"El tipo «{p.tipo}» no se emite con una llave de producción. Sólo: {', '.join(pl.TIPOS_EMITIBLES)}.")
    if not 0 <= p.gracia_dias <= licencia.MAX_GRACIA_DIAS:
        raise ErrorDeEmision(f"La gracia debe estar entre 0 y {licencia.MAX_GRACIA_DIAS} días.")
    for nombre, valor in (("equipos", p.equipos), ("usuarios", p.usuarios), ("concurrentes normales", p.normal), ("concurrentes en pico", p.pico)):
        if valor != licencia.ILIMITADO and not 1 <= valor < licencia.ILIMITADO:
            raise ErrorDeEmision(f"El límite de {nombre} debe ser mayor que cero (o «sin_tope»).")
    if p.normal > p.pico:
        raise ErrorDeEmision("Los concurrentes normales no pueden superar a los de pico.")
    try:
        pl.validar_capacidades(sorted(p.capacidades))
    except pl.ErrorDePlan as error:
        raise ErrorDeEmision(str(error)) from error
    if p.liberacion_dias is not None and not 1 <= p.liberacion_dias <= licencia.MAX_GRACIA_DIAS:
        raise ErrorDeEmision(f"Los días de liberación pendiente deben estar entre 1 y {licencia.MAX_GRACIA_DIAS}.")
    if (p.hasta is None) == (p.meses is None):
        raise ErrorDeEmision("Indica la vigencia: o una fecha (--hasta AAAA-MM-DD) o unos meses (--meses N), no las dos ni ninguna.")


# --------------------------------------------------------------------------------------------------------------- fechas
def hoy_utc(ahora_ms: int) -> date:
    return datetime.fromtimestamp(ahora_ms / 1000, tz=timezone.utc).date()


def dia_a_ms(d: date) -> int:
    """Medianoche UTC de ese día, en milisegundos."""
    return calendar.timegm(d.timetuple()) * 1000


def inicio_de_dia(ms: int) -> int:
    return ms - ms % DIA_MS


def fin_de_dia(ms: int) -> int:
    return inicio_de_dia(ms) + DIA_MS - 1


def sumar_meses(d: date, n: int) -> date:
    mes = d.month - 1 + n
    anio, mes = d.year + mes // 12, mes % 12 + 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def fechas(ahora_ms: int, *, hasta: date | None, meses: int | None) -> tuple[int, int]:
    """`(desde, vence)` en ms UTC: ver el encabezado."""
    desde = inicio_de_dia(ahora_ms) - MARGEN_DESDE_DIAS * DIA_MS
    destino = hasta if hasta is not None else sumar_meses(hoy_utc(ahora_ms), int(meses or 0))
    vence = fin_de_dia(dia_a_ms(destino))
    if vence <= ahora_ms:
        raise ErrorDeEmision("La vigencia ya terminó: elige una fecha posterior a hoy.")
    if vence - desde > licencia.MAX_VIGENCIA_MS:
        raise ErrorDeEmision("La vigencia es demasiado larga (el máximo es de 25 años).")
    return desde, vence


# --------------------------------------------------------------------------------------------------------------- construir y firmar
def limpiar_aula(texto: str | None) -> str:
    t = re.sub(r"\s+", " ", texto or "").strip()
    t = "".join(c for c in t if ord(c) >= 32 and ord(c) != 127)
    return t[:120].strip()


def construir(sol, p: Peticion, *, licencia_id: str, serie: int, ahora_ms: int) -> licencia.Licencia:
    """La `Licencia` del dominio del nodo, lista para firmar. `sol` es una `Solicitud` YA verificada."""
    validar(p)
    if serie < 1:
        raise ErrorDeEmision("La serie debe ser 1 o mayor.")
    desde, vence = fechas(ahora_ms, hasta=p.hasta, meses=p.meses)
    pendiente = p.liberacion_dias is not None
    return licencia.Licencia(
        id=licencia_id, serie=serie, aula=limpiar_aula(p.aula or sol.aula), emitida=ahora_ms, desde=desde, vence=vence, gracia_dias=p.gracia_dias,
        limites=licencia.Limites(p.equipos, p.usuarios, p.normal, p.pico), capacidades=frozenset(p.capacidades), huella=sol.huella, tipo=p.tipo,
        liberacion_pendiente=pendiente, liberacion_dias=int(p.liberacion_dias or 0), hash_clave_nodo=firma.huella_de_clave(sol.clave_nodo))


def firmar(lic: licencia.Licencia, kid: str, privada: bytes) -> bytes:
    return tlv.sellar(licencia.sin_firma(lic, kid), lambda datos: firma.firmar(privada, datos))


def verificar_salida(datos: bytes, kid: str, publica: bytes, esperada: licencia.Licencia) -> licencia.Licencia:
    """Lee `datos` con el lector del NODO y comprueba que dice exactamente lo que se quiso emitir."""
    try:
        leida = licencia.leer(datos, {kid: publica})
    except Exception as error:     # noqa: BLE001 — cualquier rechazo del lector del nodo es un archivo que no se entrega
        raise ErrorDeEmision(f"El archivo recién firmado no lo acepta el lector del nodo ({error}). No se entrega.") from error
    campos = ("id", "serie", "aula", "emitida", "desde", "vence", "gracia_dias", "limites", "capacidades", "huella", "tipo", "liberacion_pendiente", "liberacion_dias",
              "hash_clave_nodo")
    for campo in campos:
        if getattr(leida, campo) != getattr(esperada, campo):
            raise ErrorDeEmision(f"El archivo recién firmado no dice lo mismo que se pidió en «{campo}». No se entrega.")
    return leida


# --------------------------------------------------------------------------------------------------------------- nombres y avisos
def nombre_de_archivo(aula: str, ahora_ms: int, serie: int) -> str:
    base = unicodedata.normalize("NFKD", aula or "").encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40].strip("-") or "aula"
    return f"{base}-{hoy_utc(ahora_ms).strftime('%Y%m%d')}-s{serie}"


def advertencias_de_solicitud(sol, ahora_ms: int, nivel_instalacion: str) -> list[str]:
    """Lo que quien opera debería saber antes de firmar. Nunca impide emitir."""
    avisos: list[str] = []
    if sol.nivel == nivel_instalacion:
        avisos.append("La huella es de nivel «instalación» (más débil: el equipo no trae datos de fábrica útiles). Se puede emitir; avisa al colegio que no borre la carpeta de licencia.")
    dias = (ahora_ms - sol.creada) // DIA_MS
    if dias > SOLICITUD_VIEJA_DIAS:
        avisos.append(f"La solicitud dice que se creó hace {dias} días. Si el colegio la acaba de generar, el reloj de su equipo está atrasado: pídele que corrija la fecha y la hora antes de activar. "
                      "Si es vieja de verdad, pide una nueva.")
    elif dias < -1:
        avisos.append(f"La solicitud dice que se creó dentro de {-dias} días: el reloj del equipo del colegio está adelantado. Pídele que lo corrija.")
    return avisos
