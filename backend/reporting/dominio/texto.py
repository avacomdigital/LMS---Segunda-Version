"""
Los textos que el nodo escribe en un reporte (en pantalla y dentro del archivo): fechas en español claro, duraciones y la línea de corte que exige BR-083. Quien consulta es una
persona frente a una pantalla: nada de jerga ni de códigos. Este archivo no importa Django.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
EXPLICACION_DEL_CORTE = "Esto es lo que había en el nodo a esa hora."

ETIQUETA_DEL_ESTADO_SIMPLE = {"no_iniciado": "Sin empezar", "en_progreso": "En progreso", "completado": "Completado"}
SIMBOLO_DEL_ESTADO_SIMPLE = {"no_iniciado": "vacio", "en_progreso": "medio", "completado": "lleno"}      # los mismos símbolos que ve el alumno en Student
ETIQUETA_DEL_ESTADO_DE_CALIFICACION = {"pendiente": "Pendiente", "provisional": "Provisional", "revisado": "Revisado, sin publicar", "definitivo": "Publicado",
                                       "reabierto": "Reabierto", "anulado": "Anulado", "sin_registro": "Sin registro"}
ETIQUETA_DEL_ESTADO_DE_ESTUDIO = {"pendiente": "Pendiente", "en_curso": "En curso", "completada": "Completada"}
# La presencia de cada alumno al TERMINAR la clase: presente, con su tableta sin conexión, ya había salido, o fue retirado.
ETIQUETA_DE_PRESENCIA = {"conectado": "Presente al cerrar", "reconectando": "Sin conexión al cerrar", "salio": "Salió antes del cierre", "expulsado": "Retirado de la clase"}


def clave_de_orden(texto: str | None) -> str:
    """Para ordenar nombres como se ordenan en una lista: sin tildes y sin distinguir mayúsculas (Álvaro va con la A, no después de la Z). La ñ se ordena con la n."""
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").casefold()


def fecha_corta(dt: datetime) -> str:
    """`15 oct · 10:42`."""
    return f"{dt.day} {MESES[dt.month - 1]} · {dt:%H:%M}"


def fecha_larga(dt: datetime) -> str:
    """`15 oct 2026 · 10:42` (con el año: lo que va dentro del archivo, que puede abrirse meses después)."""
    return f"{dt.day} {MESES[dt.month - 1]} {dt.year} · {dt:%H:%M}"


def duracion(ms: int | None) -> str:
    """`1 h 05 min`, `42 min`, `menos de 1 min`."""
    if ms is None:
        return ""
    minutos = max(0, int(ms)) // 60_000
    if minutos < 1:
        return "menos de 1 min"
    horas, resto = divmod(minutos, 60)
    return f"{horas} h {resto:02d} min" if horas else f"{minutos} min"


def minutos(ms: int | None) -> float | None:
    """Minutos con un decimal (para una columna numérica del archivo)."""
    return None if ms is None else round(max(0, int(ms)) / 60_000, 1)


def linea_de_corte(corte_local: datetime, integracion: dict) -> str:
    """`Datos al 15 oct · 10:42 · 2 tabletas sin sincronizar` (BR-083). Sin pendientes, sólo la fecha: lo normal no se anuncia."""
    texto = f"Datos al {fecha_corta(corte_local)}"
    if integracion.get("estado") == "incompleta":
        texto += f" · {integracion['texto']}"
    return texto


def si_no(valor: bool) -> str:
    return "Sí" if valor else "No"
