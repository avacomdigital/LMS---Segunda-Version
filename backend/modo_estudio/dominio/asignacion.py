"""
Validación de lo que el profesor manda al asignar o cambiar una asignación (CAP-050, D-9). Dominio puro: no importa Django ni sabe de HTTP.

El profesor de OPS no tiene teclado (Nodo principal táctil): la consigna es opcional y la fecha límite y el plazo se ofrecen por
opciones. Aquí sólo se valida la forma; que el grupo o los alumnos existan, y que la lección exista en el curso, lo comprueba la aplicación
contra sus puertos.
"""
from __future__ import annotations

from . import catalogos as cat
from .errores import DatosInvalidos
from .plazo import gracia_en_ms

MAX_DESTINATARIOS = 500
FUENTES = ("", "biblioteca", "ejemplo")
MAX_GRACIA_MIN = 7 * 24 * 60      # una semana: más que eso ya no es una gracia


def _texto(valor, nombre: str, maximo: int, obligatorio: bool = False) -> str:
    texto = str(valor or "").strip()
    if obligatorio and not texto:
        raise DatosInvalidos(f"Falta {nombre}.", campo=nombre)
    if len(texto) > maximo:
        raise DatosInvalidos(f"{nombre} supera los {maximo} caracteres.", campo=nombre)
    return texto


def validar_fecha_limite(valor) -> int | None:
    """Un instante en milisegundos del reloj del nodo, o ausente (sin fecha límite)."""
    if valor in (None, ""):
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or int(valor) != valor or valor <= 0:
        raise DatosInvalidos("`fecha_limite` debe ser un instante en milisegundos (un entero positivo).", fecha_limite=valor)
    return int(valor)


def validar_plazo(valor) -> str:
    plazo = str(valor or cat.BLANDO).strip().lower()
    if plazo not in cat.PLAZOS:
        raise DatosInvalidos(f"Plazo desconocido: {valor!r}. Plazos: {', '.join(cat.PLAZOS)}.", plazo=valor)
    return plazo


def validar_gracia(valor, por_defecto_ms: int) -> int:
    """`gracia_min` (minutos) → `gracia_ms`. Ausente: la del sistema (DEC-019, 15 minutos)."""
    if valor in (None, ""):
        return int(por_defecto_ms)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or int(valor) != valor or not 0 <= valor <= MAX_GRACIA_MIN:
        raise DatosInvalidos(f"`gracia_min` debe ser un entero de minutos entre 0 y {MAX_GRACIA_MIN}.", gracia_min=valor)
    return gracia_en_ms(int(valor))


def validar_alumnos(valor) -> list[str]:
    if not isinstance(valor, list) or not valor:
        raise DatosInvalidos("Una selección de alumnos no puede quedar vacía: falta `alumnos`.", campo="alumnos")
    ids = []
    for a in valor:
        texto = str(a or "").strip()
        if not texto or len(texto) > 64:
            raise DatosInvalidos("Cada alumno es un identificador de hasta 64 caracteres.", campo="alumnos")
        ids.append(texto)
    ids = list(dict.fromkeys(ids))
    if len(ids) > MAX_DESTINATARIOS:
        raise DatosInvalidos(f"Una asignación admite hasta {MAX_DESTINATARIOS} alumnos.", campo="alumnos", alumnos=len(ids))
    return ids


def validar_nueva(datos: dict, gracia_por_defecto_ms: int = cat.GRACIA_MS_POR_DEFECTO) -> dict:
    """Lo que OPS manda para asignar: `{alcance, grupo_id?, alumnos?, curso_ref, fuente?, leccion_ref, titulo?, consigna?, fecha_limite?,
    plazo?, gracia_min?, paquete_permitido?}` normalizado. `grupo`: todos los alumnos activos del grupo, también los que entren después.
    `seleccion`: los alumnos que se nombran (con o sin grupo)."""
    grupo_id = _texto(datos.get("grupo_id"), "grupo_id", 36)
    alcance = str(datos.get("alcance") or (cat.SELECCION if datos.get("alumnos") else cat.GRUPO)).strip().lower()
    if alcance not in cat.ALCANCES:
        raise DatosInvalidos(f"Alcance desconocido: {datos.get('alcance')!r}. Alcances: {', '.join(cat.ALCANCES)}.", alcance=datos.get("alcance"))
    if alcance == cat.GRUPO and not grupo_id:
        raise DatosInvalidos("Asignar a un grupo exige `grupo_id`.", campo="grupo_id")
    fuente = str(datos.get("fuente") or "").strip().lower()
    if fuente not in FUENTES:
        raise DatosInvalidos(f"Fuente desconocida «{fuente}». Fuentes: biblioteca, ejemplo.", fuente=fuente)
    permitido = datos.get("paquete_permitido", True)
    if not isinstance(permitido, bool):
        raise DatosInvalidos("`paquete_permitido` es verdadero o falso.", campo="paquete_permitido")
    return {
        "alcance": alcance, "grupo_id": grupo_id,
        "alumnos": validar_alumnos(datos.get("alumnos")) if alcance == cat.SELECCION else [],
        "curso_ref": _texto(datos.get("curso_ref"), "curso_ref", 200, obligatorio=True),
        "leccion_ref": _texto(datos.get("leccion_ref"), "leccion_ref", 120, obligatorio=True),
        "fuente": fuente, "titulo": _texto(datos.get("titulo"), "titulo", 250), "consigna": _texto(datos.get("consigna"), "consigna", 2000),
        "fecha_limite": validar_fecha_limite(datos.get("fecha_limite")), "plazo": validar_plazo(datos.get("plazo")),
        "gracia_ms": validar_gracia(datos.get("gracia_min"), gracia_por_defecto_ms), "paquete_permitido": permitido,
    }


def validar_cambios(datos: dict) -> dict:
    """Lo que se puede cambiar de una asignación abierta: `{fecha_limite?, plazo?, gracia_min?, titulo?, consigna?, paquete_permitido?}`.
    Devuelve sólo los campos presentes, ya con el nombre de columna. `fecha_limite: null` (o `quitar_fecha: true`) quita la fecha."""
    cambios: dict = {}
    if "fecha_limite" in datos or datos.get("quitar_fecha") is True:
        cambios["fecha_limite"] = None if datos.get("quitar_fecha") is True else validar_fecha_limite(datos.get("fecha_limite"))
    if "plazo" in datos and datos["plazo"] is not None:
        cambios["plazo"] = validar_plazo(datos["plazo"])
    if "gracia_min" in datos and datos["gracia_min"] is not None:
        cambios["gracia_ms"] = validar_gracia(datos["gracia_min"], cat.GRACIA_MS_POR_DEFECTO)
    if "titulo" in datos and datos["titulo"] is not None:
        cambios["titulo"] = _texto(datos["titulo"], "titulo", 250, obligatorio=True)
    if "consigna" in datos and datos["consigna"] is not None:
        cambios["consigna"] = _texto(datos["consigna"], "consigna", 2000)
    if "paquete_permitido" in datos and datos["paquete_permitido"] is not None:
        if not isinstance(datos["paquete_permitido"], bool):
            raise DatosInvalidos("`paquete_permitido` es verdadero o falso.", campo="paquete_permitido")
        cambios["paquete_permitido"] = datos["paquete_permitido"]
    if not cambios:
        raise DatosInvalidos("No hay nada que cambiar: envía fecha_limite, plazo, gracia_min, titulo, consigna o paquete_permitido.")
    return cambios


def validar_decision(datos: dict) -> dict:
    """La decisión del profesor sobre un envío pendiente (BR-074): `{alumno_id, secuencia, emisor_id?, decision}`."""
    decision = str(datos.get("decision") or "")
    if decision not in cat.DECISIONES:
        raise DatosInvalidos("La decisión es «aceptar» o «descartar».", decision=decision)
    alumno_id = _texto(datos.get("alumno_id"), "alumno_id", 64, obligatorio=True)
    secuencia = datos.get("secuencia")
    if isinstance(secuencia, bool) or not isinstance(secuencia, int) or secuencia < 1:
        raise DatosInvalidos("`secuencia` debe ser un entero ≥ 1.", secuencia=secuencia)
    emisor = _texto(datos.get("emisor_id"), "emisor_id", 64)
    return {"alumno_id": alumno_id, "secuencia": secuencia, "emisor_id": emisor or None, "decision": decision}
