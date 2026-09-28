"""
Catálogos del contenido tal como lo publica AVACOM Biblioteca (manifiesto de curso,
`schemaVersion` 1.0) y su traducción a los componentes que pinta el cliente MAUI.

Son VALORES del dominio, no tablas: el LMS no guarda el curso (artículo 14), pero
sí necesita saber qué clase de experiencia pedagógica es cada objeto (`tipo`) y
con qué componente se representa (`componente`). Los códigos de la izquierda son
los de la biblioteca y no se traducen; los de la derecha son los nombres que
consumen las pantallas.
"""
from __future__ import annotations

# ------------------------------------------------------------ objetos de lección
# Primero se decide QUÉ experiencia se construye (objeto) y después QUÉ contenido
# visual necesita (bloque). Un video y un examen nunca están al mismo nivel.
TIPOS_OBJETO: dict[str, str] = {
    "lecture": "presentacion",            # láminas proyectables (la «presentación» del aula)
    "explanation": "lectura",             # páginas de lectura guiada con audio y pdf
    "simulation_lab": "laboratorio_web",  # simulación HTML5 en WebView
    "activity": "actividad",              # práctica con preguntas y retroalimentación
    "exam": "examen",                     # fuera de MOD-007: lo gobierna MOD-010
}

# Objetos que MOD-007 muestra en la estructura pero NO ejecuta: se marcan con el
# módulo dueño y se entregan sin preguntas.
OBJETOS_FUERA_DE_ALCANCE: dict[str, str] = {"exam": "MOD-010"}

# --------------------------------------------------------------- bloques de contenido
TIPOS_BLOQUE: dict[str, str] = {
    "heading": "titulo",
    "text": "texto",
    "list": "lista",
    "formula": "formula",                 # LaTeX (`latex`, `display`); el cliente la pinta como texto matemático
    "image": "imagen",
    "video": "video",
    "audio": "audio",
    "pdf": "pdf",
}

# --------------------------------------------------------------------- preguntas
TIPOS_PREGUNTA: dict[str, str] = {
    "multiple_choice": "opcion_multiple",
    "true_false": "verdadero_falso",
    "fill_blanks": "completar",
    "matching": "relacionar",
    "ordering": "ordenar",
    "open": "abierta",
}

# ----------------------------------------------------------------------- medios
# `kind` del catálogo global `media` del manifiesto → componente MAUI sugerido.
CLASES_MEDIO: dict[str, str] = {
    "image": "imagen",
    "video": "video",
    "audio": "audio",
    "pdf": "pdf",
    "simulation": "webview",
}

# Ítems del contrato 1 de la biblioteca (secciones/items) → objeto normalizado.
# Sirve mientras la biblioteca publique el árbol antiguo; el normalizador acepta ambos.
TIPOS_ITEM_CONTRATO1: dict[str, tuple[str, str]] = {
    "imagen": ("recurso", "imagen"),
    "video": ("recurso", "video"),
    "audio": ("recurso", "audio"),
    "documento": ("recurso", "pdf"),
    "interactivo": ("simulation_lab", "laboratorio_web"),
    "leccion": ("explanation", "lectura"),
    "actividad": ("activity", "actividad"),
    "evaluacion": ("exam", "examen"),
    "banco": ("banco", "no_soportado"),
    "scorm": ("scorm", "no_soportado"),
}

# ------------------------------------------------------------------- modos y vías
MODOS = ("simple", "class", "exam", "review", "free_learning")
VIAS_ORIGEN = ("arbol", "leccion", "recurso", "libre")   # BR-044, DEC-001

# --------------------------------------------------------- lo que nunca se reenvía
# Claves de corrección del manifiesto (camelCase) y del contrato 1 (español). El
# normalizador construye la vista con campos explícitos, así que estas claves no
# llegan por construcción; el barrido recursivo final es la segunda línea de
# defensa (artículo 14.5 y CA-08). Se aplica a TODOS los roles: la corrección y
# la revisión docente con rúbrica son de MOD-010/MOD-011, no del aula.
CLAVES_DE_CORRECCION = frozenset({
    # manifiesto 1.0: ANSWER_KEY_FIELDS, ANSWER_KEY_OPTION_FIELDS y ANSWER_KEY_BLANK_FIELDS del
    # validador de referencia de la biblioteca (spec-driven/02-classroom-engine/validate_course.py).
    # `keywords` de una pregunta abierta y `numericTolerance` de un hueco también revelan la clave.
    "isCorrect", "answer", "acceptedAnswers", "wrongAnswers", "numericTolerance", "pairs", "wrongPairs",
    "correctOrder", "wrongOrders", "modelAnswer", "rubric", "incorrectExamples", "keywords", "feedback",
    # séptimo tipo `drag_drop` del esquema que trae AVACOM Contenido 2.1.7 (no está en el validador entregado)
    "placements", "wrongPlacements",
    # contrato 1
    "clave", "clave_respuesta", "respuesta", "respuesta_correcta", "correcta", "es_correcta", "solucion",
})

# Campos que sólo ve el docente.
CAMPOS_DOCENTE = frozenset({"teacherNotes"})

ROLES = ("estudiante", "docente")
