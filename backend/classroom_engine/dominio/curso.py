"""
El curso, tal como llega de la fuente (AVACOM Biblioteca o el manifiesto de
ejemplo), convertido en la «vista de aula» que consumen OPS y Student.

Reglas:
  - No se guarda nada: esta función es pura y se ejecuta en cada petición.
  - Los identificadores del manifiesto se conservan como referencias (`*_ref`):
    son lo que MOD-007 escribe en el foco, la distribución y el resumen.
  - Ninguna clave de corrección sale de aquí, para ningún rol (catalogos.CLAVES_DE_CORRECCION).
  - Las notas del docente sólo salen con rol «docente».
  - Cada objeto y cada bloque llevan `componente`: el nombre del control MAUI sugerido.
"""
from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Callable
from typing import Any

from . import catalogos as cat
from .errores import ReferenciaNoEncontrada

UrlMedio = Callable[[str, str | None], str]
"""(media_ref, ruta_interna | None) → ruta HTTP del medio en el backend del LMS."""

# El subconjunto «AVACOM Markdown» de RichText (course.schema.json §$defs/RichText): **negrita**,
# *cursiva*, listas, saltos de línea y matemática en línea entre $...$. Sin HTML (el esquema lo
# prohíbe). Las listas y los saltos de línea viajan tal cual en `texto`: la etiqueta los respeta.
_MARCADO = re.compile(
    r"\*\*(.+?)\*\*"                                    # 1 · negrita
    r"|(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])"       # 2 · cursiva (un asterisco que no es de negrita ni un producto «2*3»)
    r"|\$(?!\s)([^$\n]+?)(?<!\s)\$"                     # 3 · matemática en línea
)


# ------------------------------------------------------------------ texto

def _tramo(texto: str, *, negrita: bool = False, cursiva: bool = False, matematica: bool = False) -> dict:
    return {"texto": texto, "negrita": negrita, "cursiva": cursiva, "matematica": matematica}


def tramos(texto: str | None) -> list[dict]:
    """Descompone el marcado del manifiesto (**negrita**, *cursiva*, $matemática$) en tramos
    para un FormattedString de MAUI. Sin librería de Markdown ni motor LaTeX en la tableta: la
    matemática en línea se entrega ya legible (`texto_formula`) y marcada con `matematica`."""
    if not texto:
        return []
    salida: list[dict] = []
    posicion = 0
    for coincidencia in _MARCADO.finditer(texto):
        if coincidencia.start() > posicion:
            salida.append(_tramo(texto[posicion:coincidencia.start()]))
        negrita, cursiva, formula = coincidencia.groups()
        if negrita is not None:
            salida.append(_tramo(negrita, negrita=True))
        elif cursiva is not None:
            salida.append(_tramo(cursiva, cursiva=True))
        else:
            salida.append(_tramo(texto_formula(formula), matematica=True))
        posicion = coincidencia.end()
    if posicion < len(texto):
        salida.append(_tramo(texto[posicion:]))
    return salida


def texto_plano(texto: str | None) -> str:
    """El texto sin marcado; la matemática en línea queda en su lectura («1/3 × 2»)."""
    return _MARCADO.sub(lambda m: m.group(1) or m.group(2) or texto_formula(m.group(3)), texto or "")


_FRACCION = re.compile(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}")
_SIMBOLOS = (("\\times", "×"), ("\\cdot", "·"), ("\\div", "÷"), ("\\pm", "±"), ("\\le", "≤"), ("\\ge", "≥"), ("\\neq", "≠"),
             ("\\approx", "≈"), ("\\infty", "∞"), ("\\pi", "π"), ("\\%", "%"), ("\\,", " "), ("\\;", " "), ("\\ ", " "))


def texto_formula(latex: str) -> str:
    """Lectura aproximada de una fórmula LaTeX sencilla para pintarla sin motor matemático:
    `\\frac{1}{3}` → «1/3», `\\times` → «×». Lo que no se reconoce se deja tal cual."""
    texto = _FRACCION.sub(lambda m: f"{m.group(1)}/{m.group(2)}", latex or "")
    for origen, destino in _SIMBOLOS:
        texto = texto.replace(origen, destino)
    texto = re.sub(r"\^\{([^{}]*)\}", r"^\1", texto)
    texto = re.sub(r"_\{([^{}]*)\}", r"_\1", texto)
    return texto.replace("{", "").replace("}", "").replace("$", "").strip()


def slug(valor: str) -> str:
    """«Matemáticas» → «matematicas»: el código de una asignatura del contrato 1 se deriva de su nombre."""
    plano = unicodedata.normalize("NFKD", valor or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", plano.lower()).strip("-") or "sin-codigo"


# ------------------------------------------------------------- utilidades

def sin_claves(valor: Any) -> Any:
    """Barrido recursivo: quita cualquier clave de corrección que se hubiera colado."""
    if isinstance(valor, dict):
        return {k: sin_claves(v) for k, v in valor.items() if k not in cat.CLAVES_DE_CORRECCION}
    if isinstance(valor, list):
        return [sin_claves(v) for v in valor]
    return valor


def contiene_clave(valor: Any) -> str | None:
    """Devuelve la primera clave de corrección encontrada, o None. Lo usan las pruebas."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            if k in cat.CLAVES_DE_CORRECCION:
                return k
            hallada = contiene_clave(v)
            if hallada:
                return hallada
    elif isinstance(valor, list):
        for v in valor:
            hallada = contiene_clave(v)
            if hallada:
                return hallada
    return None


def es_manifiesto(datos: dict) -> bool:
    """Manifiesto de curso (schemaVersion 1.0, `lessons`) frente al árbol del contrato 1 (`secciones`)."""
    return isinstance(datos, dict) and ("lessons" in datos or "schemaVersion" in datos)


def _notas(rol: str, origen: dict) -> dict | None:
    if rol != "docente":
        return None
    notas = origen.get("teacherNotes")
    return dict(notas) if isinstance(notas, dict) else None


def _con_notas(destino: dict, rol: str, origen: dict) -> dict:
    notas = _notas(rol, origen)
    if notas is not None:
        destino["notas_docente"] = notas
    return destino


def _referencias(origen: dict) -> list[dict]:
    """`curriculumRefs` (DBA, EBC, SEP…) pueden venir en el curso, la lección, el objeto o la pregunta."""
    return [
        # `relation` (teaches | assesses) sólo existe en el esquema que trae AVACOM Contenido 2.1.7; en el entregado no.
        {"marco": r.get("framework"), "codigo": r.get("code"), "descripcion": r.get("description"), "relacion": r.get("relation")}
        for r in (origen.get("curriculumRefs") or []) if isinstance(r, dict)
    ]


# --------------------------------------------------------------- clasificación

def _nodo(valor) -> dict | None:
    if not isinstance(valor, dict):
        return None
    return {"codigo": str(valor.get("code", "")), "nombre": str(valor.get("name", "")), "orden": valor.get("order")}


def clasificacion_de(manifiesto: dict) -> dict:
    """`classification` del manifiesto → panel de navegación. País ISO 3166-1, idioma BCP 47."""
    c = manifiesto.get("classification") or {}
    asignatura = c.get("subject") or {}
    return {
        "pais": str(c.get("country", "")).upper(),
        "idioma": str(manifiesto.get("language", "")),
        # `track` (school | complementary) llega con AVACOM Contenido 2.1.7; ausente significa school.
        "pista": c.get("track") or "school",
        "nivel": _nodo(c.get("level")),
        "grado": _nodo(c.get("grade")),
        "asignatura": {"codigo": str(asignatura.get("code", "")), "nombre": str(asignatura.get("name", ""))},
        "tema": _nodo(c.get("topic")),
    }


def clasificacion_contrato1(curso: dict) -> dict:
    """El árbol del contrato 1 trae nivel, grado y asignatura como texto."""
    asignatura = str(curso.get("asignatura", "") or "")
    nivel = str(curso.get("nivel", "") or "")
    grado = str(curso.get("grado", "") or "")
    return {
        "pais": str(curso.get("pais", "") or "").upper(),
        "idioma": str(curso.get("idioma", "") or ""),
        "pista": "school",
        "nivel": {"codigo": slug(nivel), "nombre": nivel.capitalize(), "orden": None} if nivel else None,
        "grado": {"codigo": grado, "nombre": grado, "orden": None} if grado else None,
        "asignatura": {"codigo": slug(asignatura), "nombre": asignatura},
        "tema": None,
    }


# ------------------------------------------------------------------- medios

def _medio(m: dict, url_medio: UrlMedio) -> dict:
    clase = str(m.get("kind", ""))
    media_ref = str(m.get("id", ""))
    entrada = m.get("entry")
    salida = {
        "media_ref": media_ref,
        "clase": clase,
        "componente": cat.CLASES_MEDIO.get(clase, "no_soportado"),
        "titulo": m.get("title"),
        "mime": m.get("mimeType"),
        "url": url_medio(media_ref, entrada if clase == "simulation" and entrada else None),
        "ancho": m.get("width"),
        "alto": m.get("height"),
        "duracion_seg": m.get("durationSec"),
        "paginas": m.get("pageCount"),
        "texto_alternativo": m.get("altText"),
        "tiene_voz": m.get("hasSpeech") if isinstance(m.get("hasSpeech"), bool) else None,   # 2.1.7: audio/video con habla exigen subtítulos y transcripción
        # El manifiesto de origen trae las rutas (`captionsPath`); la API v2 sólo dice si existen (`hasCaptions`).
        "subtitulos_url": url_medio(media_ref, "subtitulos") if (m.get("captionsPath") or m.get("hasCaptions")) else None,
        "transcripcion_url": url_medio(media_ref, "transcripcion") if (m.get("transcriptPath") or m.get("hasTranscript")) else None,
        "licencia": _licencia(m.get("license")),
    }
    if clase == "simulation":
        sim = m.get("simulation") or {}
        salida["base_url"] = url_medio(media_ref, None)
        salida["simulacion"] = {
            "entrada": entrada,
            "proveedor": sim.get("provider"),
            "tecnologia": sim.get("technology"),
            "orientacion": sim.get("orientation"),
            "ajustes": list(sim.get("shims") or []),             # block_network, scale_to_fit…
            "destinos": list(sim.get("supportsTargets") or []),  # screen, tablet
            "ancho_diseno": sim.get("designWidth"),
            "alto_diseno": sim.get("designHeight"),
        }
    return salida


def _licencia(lic) -> dict | None:
    if not isinstance(lic, dict):
        return None
    return {"tipo": lic.get("type"), "atribucion": lic.get("attribution"), "fuente_url": lic.get("sourceUrl")}


def _decimal(valor) -> float:
    """`points`, `score` y `durationSec` son `number` en el esquema: nunca se redondean a entero."""
    if valor is None or isinstance(valor, bool):
        return 0.0
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _medio_ausente(media_ref: str, url_medio: UrlMedio) -> dict:
    return {"media_ref": media_ref, "clase": None, "componente": "no_soportado", "titulo": None, "mime": None,
            "url": url_medio(media_ref, None), "ausente": True}


# ------------------------------------------------------------------ bloques

def _bloque(b: dict, medios: dict[str, dict], url_medio: UrlMedio) -> dict:
    tipo = str(b.get("type", ""))
    salida: dict[str, Any] = {"tipo": tipo, "componente": cat.TIPOS_BLOQUE.get(tipo, "no_soportado")}
    if tipo == "heading":
        salida.update(texto=b.get("text", ""), nivel=int(b.get("level") or 1), tramos=tramos(b.get("text")))
    elif tipo == "text":
        salida.update(texto=b.get("text", ""), estilo=b.get("style"), tramos=tramos(b.get("text")))
    elif tipo == "list":
        items = [str(i) for i in (b.get("items") or [])]
        salida.update(ordenada=bool(b.get("ordered")), items=items, items_tramos=[tramos(i) for i in items])
    elif tipo == "formula":
        latex = str(b.get("latex") or b.get("text") or "")
        salida.update(latex=latex, en_bloque=bool(b.get("display", True)), texto=texto_formula(latex),
                      tramos=tramos(texto_formula(latex)), pie=b.get("caption"))
    elif tipo in ("image", "video", "audio", "pdf"):
        media_ref = str(b.get("mediaId", ""))
        medio = medios.get(media_ref) or _medio_ausente(media_ref, url_medio)
        salida.update(media_ref=media_ref, url=medio.get("url"), pie=b.get("caption"), mime=medio.get("mime"),
                      titulo=medio.get("titulo"))
        if tipo == "image":
            salida.update(texto_alternativo=medio.get("texto_alternativo"), ancho=medio.get("ancho"), alto=medio.get("alto"))
        elif tipo == "video":
            # ancho/alto del medio (p. ej. 1280x720): la proporción real, para que el cliente
            # ajuste el alto de la WebView al ancho que le toque en cada pantalla, sin
            # deformar el video ni dejarlo con un tamaño fijo que no cabe o sobra.
            salida.update(desde_seg=b.get("startSec"), hasta_seg=b.get("endSec"), autoplay=bool(b.get("autoplay")),
                          duracion_seg=medio.get("duracion_seg"), subtitulos_url=medio.get("subtitulos_url"),
                          transcripcion_url=medio.get("transcripcion_url"),
                          ancho=medio.get("ancho"), alto=medio.get("alto"))
        elif tipo == "audio":
            salida.update(duracion_seg=medio.get("duracion_seg"), transcripcion_url=medio.get("transcripcion_url"))
        elif tipo == "pdf":
            desde = b.get("fromPage")
            salida.update(desde_pagina=desde, hasta_pagina=b.get("toPage"), paginas=medio.get("paginas"),
                          url_pagina_inicial=f"{medio.get('url')}#page={int(desde)}" if desde and medio.get("url") else medio.get("url"))
    else:
        # Un bloque que este LMS no conoce se entrega crudo (sin claves) para que el cliente lo muestre como aviso.
        salida["crudo"] = sin_claves({k: v for k, v in b.items() if k != "type"})
    return salida


def _bloques(lista, medios, url_medio) -> list[dict]:
    return [_bloque(b, medios, url_medio) for b in (lista or []) if isinstance(b, dict)]


# ---------------------------------------------------------------- preguntas

def _con_imagen(destino: dict, origen: dict, medios: dict[str, dict], url_medio: UrlMedio) -> dict:
    """Una opción o un ítem (`ChoiceItem`) puede llevar `mediaId` (imagen) en vez de, o además de, `text`."""
    media_ref = origen.get("mediaId")
    if media_ref:
        medio = medios.get(str(media_ref)) or _medio_ausente(str(media_ref), url_medio)
        destino.update(media_ref=str(media_ref), url=medio.get("url"), texto_alternativo=medio.get("texto_alternativo"))
    else:
        destino.update(media_ref=None, url=None, texto_alternativo=None)
    return destino


def _item(i: dict, medios: dict[str, dict], url_medio: UrlMedio) -> dict:
    """`ChoiceItem` de relacionar y ordenar: texto (RichText) o imagen."""
    return _con_imagen({"ref": str(i.get("id", "")), "texto": i.get("text", ""), "tramos": tramos(i.get("text"))}, i, medios, url_medio)


def _barajadas(elementos: list[dict], semilla: str) -> list[dict]:
    """Los mismos elementos en un orden que ya no es el de la fuente, siempre el mismo para la misma pregunta (determinista).

    En «ordenar» la fuente trae los ítems en el orden correcto y en «relacionar» la columna derecha alineada con la izquierda: mandarlas
    tal cual a un alumno sería mandarle la respuesta. Nunca devuelve el orden original (con dos o más elementos)."""
    if len(elementos) < 2:
        return list(elementos)
    orden = list(elementos)
    random.Random(semilla).shuffle(orden)
    if [e["ref"] for e in orden] == [e["ref"] for e in elementos]:
        orden = orden[1:] + orden[:1]
    return orden


def _pregunta(p: dict, medios: dict[str, dict], url_medio: UrlMedio, rol: str = "docente") -> dict:
    """Sólo lo que hace falta para PREGUNTAR. Nunca lo que hace falta para corregir (ni siquiera el orden de la fuente: al alumno,
    «ordenar» y la columna derecha de «relacionar» le llegan barajados)."""
    tipo = str(p.get("type", ""))
    salida: dict[str, Any] = {
        "pregunta_ref": str(p.get("id", "")),
        "tipo": tipo,
        "componente": cat.TIPOS_PREGUNTA.get(tipo, "no_soportado"),
        "enunciado": p.get("prompt", ""),
        "enunciado_tramos": tramos(p.get("prompt")),
        # `mediaIds`: imagen, video, audio o pdf que acompañan al enunciado (nunca simulaciones).
        "medios": [medios.get(str(m)) or _medio_ausente(str(m), url_medio) for m in (p.get("mediaIds") or []) if m],
        "tema_ref": p.get("topicRef"),
        "dificultad": p.get("difficulty"),
        "duracion_estimada_seg": p.get("estimatedSec"),
        "puntos": p.get("points"),                       # `number`: puede ser decimal
        "nivel_cognitivo": p.get("cognitiveLevel"),
        "credito_parcial": bool(p.get("partialCredit")),
        "referencias_curriculares": _referencias(p),
    }
    if tipo == "multiple_choice":
        salida["permite_varias"] = bool(p.get("allowMultiple"))
        salida["opciones"] = [
            _con_imagen({"opcion_ref": str(o.get("id", "")), "texto": o.get("text", ""), "tramos": tramos(o.get("text"))}, o, medios, url_medio)
            for o in (p.get("options") or []) if isinstance(o, dict)
        ]
    elif tipo == "true_false":
        salida["opciones"] = [{"opcion_ref": "true", "texto": "Verdadero", "tramos": tramos("Verdadero"), "media_ref": None, "url": None, "texto_alternativo": None},
                              {"opcion_ref": "false", "texto": "Falso", "tramos": tramos("Falso"), "media_ref": None, "url": None, "texto_alternativo": None}]
    elif tipo == "fill_blanks":
        salida["plantilla"] = p.get("template", "")
        salida["espacios"] = [{"espacio_ref": str(e.get("id", "")), "modo_entrada": e.get("inputMode", "text"),
                               "opciones": list(e.get("choices") or [])}
                              for e in (p.get("blanks") or []) if isinstance(e, dict)]
    elif tipo == "matching":
        salida["izquierda"] = [_item(i, medios, url_medio) for i in (p.get("left") or []) if isinstance(i, dict)]
        salida["derecha"] = [_item(i, medios, url_medio) for i in (p.get("right") or []) if isinstance(i, dict)]
        if rol != "docente":
            salida["derecha"] = _barajadas(salida["derecha"], f"aula|derecha|{salida['pregunta_ref']}")
    elif tipo == "ordering":
        salida["elementos"] = [_item(i, medios, url_medio) for i in (p.get("items") or []) if isinstance(i, dict)]
        if rol != "docente":
            salida["elementos"] = _barajadas(salida["elementos"], f"aula|elementos|{salida['pregunta_ref']}")
    elif tipo == "open":
        salida["formato_respuesta"] = p.get("responseFormat", "text")
        salida["longitud_maxima"] = p.get("maxLength")
    return salida


# ----------------------------------------------------------------- objetos

def _objeto(o: dict, rol: str, medios: dict[str, dict], url_medio: UrlMedio) -> dict:
    tipo = str(o.get("type", ""))
    salida: dict[str, Any] = {
        "objeto_ref": str(o.get("id", "")),
        "tipo": tipo,
        "componente": cat.TIPOS_OBJETO.get(tipo, "no_soportado"),
        "titulo": o.get("title", ""),
        "modos": list(o.get("modes") or []),
        "tema_ref": o.get("topicRef"),
        "duracion_estimada_seg": o.get("estimatedDurationSec"),
        "referencias_curriculares": _referencias(o),
        "fuera_de_alcance": tipo in cat.OBJETOS_FUERA_DE_ALCANCE,
        "modulo": cat.OBJETOS_FUERA_DE_ALCANCE.get(tipo, "MOD-007"),
    }
    _con_notas(salida, rol, o)

    if tipo == "lecture":
        laminas = []
        for indice, s in enumerate(o.get("slides") or [], start=1):
            lamina = {"unidad_ref": str(s.get("id", "")), "indice": indice, "titulo": s.get("title", ""),
                      "duracion_seg": s.get("estimatedSec"), "bloques": _bloques(s.get("blocks"), medios, url_medio)}
            laminas.append(_con_notas(lamina, rol, s))
        salida["laminas"] = laminas
        salida["total_unidades"] = len(laminas)
    elif tipo == "explanation":
        paginas = []
        for indice, pg in enumerate(o.get("pages") or [], start=1):
            pagina = {"unidad_ref": str(pg.get("id", "")), "indice": indice, "titulo": pg.get("title", ""),
                      "duracion_seg": pg.get("estimatedSec"), "bloques": _bloques(pg.get("blocks"), medios, url_medio)}
            paginas.append(_con_notas(pagina, rol, pg))
        salida["paginas"] = paginas
        salida["total_unidades"] = len(paginas)
    elif tipo == "simulation_lab":
        media_ref = str(o.get("mediaId", ""))
        medio = medios.get(media_ref) or _medio_ausente(media_ref, url_medio)
        parametros = dict(o.get("launchParams") or {})
        url = medio.get("url") or ""
        if parametros and url:
            consulta = "&".join(f"{k}={v}" for k, v in parametros.items())
            url = f"{url}{'&' if '?' in url else '?'}{consulta}"
        salida.update(
            simulacion=medio,
            parametros_lanzamiento=parametros,
            url_lanzamiento=url,
            objetivo_aprendizaje=o.get("learningGoal"),
            instrucciones=o.get("instructions"),
            instrucciones_tramos=tramos(o.get("instructions")),
            pasos=list(o.get("steps") or []),
            preguntas_guia=list(o.get("guidingQuestions") or []),
        )
    elif tipo == "activity":
        ajustes = o.get("settings") or {}
        preguntas = [_pregunta(p, medios, url_medio, rol) for p in (o.get("questions") or []) if isinstance(p, dict)]
        salida.update(
            instrucciones=o.get("instructions"),
            instrucciones_tramos=tramos(o.get("instructions")),
            ajustes={
                "retroalimentacion": ajustes.get("feedback", "immediate"),
                "intentos_permitidos": ajustes.get("attemptsAllowed"),
                "barajar_preguntas": bool(ajustes.get("shuffleQuestions")),
                "barajar_opciones": bool(ajustes.get("shuffleOptions")),
                "tiempo_limite_seg": ajustes.get("timeLimitSec"),
            },
            preguntas=preguntas,
            total_unidades=len(preguntas),
            # `points` es `number` en el esquema: la suma se conserva decimal (1.5 + 2 = 3.5), nunca se trunca.
            puntos_totales=round(sum(_decimal(p.get("puntos")) for p in preguntas), 4),
        )
    elif tipo == "exam":
        # El examen no lo ejecuta el aula (MOD-010): se muestra que existe y cómo está configurado, sin preguntas.
        ajustes = o.get("settings") or {}
        seleccion = ajustes.get("selection") or {}
        tiempo = ajustes.get("timeLimit") or {}
        # El esquema entregado dice `difficultyTolerancePct`, `timeLimit.policy` y `extraPct`; el que trae
        # AVACOM Contenido 2.1.7 dice `…Percent`, sin `policy` (fixedSec o extraPercent, uno solo). Se aceptan ambos.
        extra_pct = tiempo.get("extraPercent", tiempo.get("extraPct"))
        politica = tiempo.get("policy") or ("fixed" if tiempo.get("fixedSec") is not None else "sum_of_estimates" if extra_pct is not None else "none")
        salida.update(
            instrucciones=o.get("instructions"),
            ajustes={
                "seleccion": {"estrategia": seleccion.get("strategy"), "cantidad_preguntas": seleccion.get("questionCount"),
                              "tolerancia_dificultad_pct": seleccion.get("difficultyTolerancePercent", seleccion.get("difficultyTolerancePct")),
                              "tolerancia_tiempo_pct": seleccion.get("timeTolerancePercent", seleccion.get("timeTolerancePct")),
                              "cubrir_todos_los_temas": bool(seleccion.get("coverAllTopics"))},
                "tiempo": {"politica": politica, "fijo_seg": tiempo.get("fixedSec"), "extra_pct": extra_pct},
                "aprobacion_pct": ajustes.get("passingScorePct"),
                "mostrar_resultados": ajustes.get("showResults"),
                "navegacion_atras": bool(ajustes.get("allowBackNavigation")),
                "barajar_opciones": bool(ajustes.get("shuffleOptions")),
            },
            preguntas=[],
            total_preguntas_banco=len(o.get("questions") or []),
        )
    else:
        salida["crudo"] = sin_claves({k: v for k, v in o.items() if k not in ("id", "type", "teacherNotes")})
    return salida


def _leccion(l: dict, rol: str, medios: dict[str, dict], url_medio: UrlMedio) -> dict:
    salida = {
        "leccion_ref": str(l.get("id", "")),
        "titulo": l.get("title", ""),
        "resumen": l.get("summary"),
        "objetivos": list(l.get("objectives") or []),
        "duracion_estimada_min": l.get("estimatedDurationMin"),
        "modos": list(l.get("modes") or []),
        "referencias_curriculares": _referencias(l),
        "temas": [
            {"tema_ref": str(t.get("id", "")), "titulo": t.get("title", ""),
             "subtemas": [{"tema_ref": str(s.get("id", "")), "titulo": s.get("title", "")} for s in (t.get("subtopics") or [])]}
            for t in (l.get("topics") or []) if isinstance(t, dict)
        ],
        "objetos": [_objeto(o, rol, medios, url_medio) for o in (l.get("objects") or []) if isinstance(o, dict)],
    }
    return _con_notas(salida, rol, l)


# ------------------------------------------------------------------- resumen

def resumen_de(manifiesto: dict, fuente: str, url_medio: UrlMedio) -> dict:
    """La ficha del curso para la lista y el panel de asignaturas. Sin estructura."""
    medios = {str(m.get("id", "")): m for m in (manifiesto.get("media") or []) if isinstance(m, dict)}
    portada_ref = manifiesto.get("coverMediaId")
    lecciones = manifiesto.get("lessons") or []
    return {
        "fuente": fuente,
        "esquema": str(manifiesto.get("schemaVersion", "")),
        "curso_ref": str(manifiesto.get("id", "")),
        "version": str(manifiesto.get("version", "")),
        "titulo": manifiesto.get("title", ""),
        "subtitulo": manifiesto.get("subtitle"),
        "descripcion": manifiesto.get("description"),
        "idioma": manifiesto.get("language"),
        "grupo_traduccion": manifiesto.get("translationGroupId"),
        "clasificacion": clasificacion_de(manifiesto),
        "duracion_estimada_min": manifiesto.get("estimatedDurationMin"),
        "modos": list(manifiesto.get("modes") or []),
        "portada_url": url_medio(str(portada_ref), None) if portada_ref and str(portada_ref) in medios else None,
        "lecciones": len(lecciones),
        "objetos": sum(len(l.get("objects") or []) for l in lecciones if isinstance(l, dict)),
        "medios": len(medios),
        # La biblioteca lo lista pero no lo sirve (paquete que no pasa su verificación): {codigo, detalle, sugerencia}.
        "no_disponible": manifiesto.get("no_disponible") if isinstance(manifiesto.get("no_disponible"), dict) else None,
    }


def resumen_contrato1(curso: dict, fuente: str) -> dict:
    return {
        "fuente": fuente,
        "esquema": "contrato-1",
        "curso_ref": str(curso.get("curso_ref", "")),
        "version": str(curso.get("version_vigente") or curso.get("version") or ""),
        "titulo": curso.get("titulo", ""),
        "subtitulo": None,
        "descripcion": None,
        "idioma": curso.get("idioma"),
        "grupo_traduccion": None,
        "clasificacion": clasificacion_contrato1(curso),
        "duracion_estimada_min": None,
        "modos": [],
        "portada_url": None,
        "lecciones": int(curso.get("lecciones") or 0),
        "objetos": int(curso.get("elementos") or 0),
        "medios": None,
        "no_disponible": None,
    }


def agrupar_por_asignatura(resumenes: list[dict]) -> list[dict]:
    """El panel «Asignaturas»: una entrada por `subject.name`, con sus cursos."""
    grupos: dict[str, dict] = {}
    for r in resumenes:
        asignatura = (r.get("clasificacion") or {}).get("asignatura") or {}
        codigo = asignatura.get("codigo") or slug(asignatura.get("nombre", ""))
        grupo = grupos.setdefault(codigo, {"codigo": codigo, "nombre": asignatura.get("nombre") or codigo, "cursos": []})
        grupo["cursos"].append(r)
    return sorted(grupos.values(), key=lambda g: g["nombre"])


# --------------------------------------------------------------- normalizar

def normalizar(datos: dict, *, rol: str, fuente: str, url_medio: UrlMedio,
               url_medio_contrato1: Callable[[str, str | None], str] | None = None) -> dict:
    """Manifiesto (schemaVersion 1.0) o árbol del contrato 1 → vista de aula."""
    rol = rol if rol in cat.ROLES else "estudiante"
    if es_manifiesto(datos):
        vista = _normalizar_manifiesto(datos, rol, fuente, url_medio)
    else:
        vista = _normalizar_contrato1(
            datos, rol, fuente,
            url_medio_contrato1 or (lambda ref, ruta: f"/api/biblioteca/medio/{ref}/" + (ruta or "")),
        )
    return sin_claves(vista)


def _normalizar_manifiesto(m: dict, rol: str, fuente: str, url_medio: UrlMedio) -> dict:
    medios_lista = [_medio(x, url_medio) for x in (m.get("media") or []) if isinstance(x, dict)]
    medios = {x["media_ref"]: x for x in medios_lista}
    lecciones = [_leccion(l, rol, medios, url_medio) for l in (m.get("lessons") or []) if isinstance(l, dict)]
    creditos = m.get("credits") or {}
    objetos = [o for l in lecciones for o in l["objetos"]]
    por_tipo: dict[str, int] = {}
    for o in objetos:
        por_tipo[o["tipo"]] = por_tipo.get(o["tipo"], 0) + 1
    vista = {
        **resumen_de(m, fuente, url_medio),
        "rol": rol,
        "portada": medios.get(str(m.get("coverMediaId", ""))),
        "referencias_curriculares": _referencias(m),
        "palabras_clave": list(m.get("keywords") or []),
        "creditos": {"editor": creditos.get("publisher"), "autores": list(creditos.get("authors") or []),
                     "revisores": list(creditos.get("reviewers") or [])},
        "medios": medios_lista,
        "lecciones": lecciones,
        "resumen": {
            "lecciones": len(lecciones),
            "objetos": len(objetos),
            "objetos_por_tipo": por_tipo,
            "medios": len(medios_lista),
            "preguntas": sum(len(o.get("preguntas") or []) for o in objetos),
            "fuera_de_alcance": [{"objeto_ref": o["objeto_ref"], "tipo": o["tipo"], "modulo": o["modulo"]}
                                 for o in objetos if o["fuera_de_alcance"]],
        },
    }
    return _con_notas(vista, rol, m)


def _normalizar_contrato1(curso: dict, rol: str, fuente: str, url_medio: Callable[[str, str | None], str]) -> dict:
    """El árbol antiguo (secciones/items) expresado con la misma forma. Los detalles de
    lección y actividad no vienen inclusos: se indican las rutas donde pedirlos."""
    lecciones = []
    for seccion in curso.get("secciones") or []:
        objetos = []
        for item in seccion.get("items") or []:
            tipo_item = str(item.get("tipo", ""))
            tipo, componente = cat.TIPOS_ITEM_CONTRATO1.get(tipo_item, (tipo_item, "no_soportado"))
            ref = str(item.get("elemento_ref", ""))
            objeto: dict[str, Any] = {
                "objeto_ref": ref, "tipo": tipo, "componente": componente, "tipo_contrato1": tipo_item,
                "titulo": item.get("titulo", ""), "modos": [], "tema_ref": None,
                "duracion_estimada_seg": item.get("duracion_seg"), "version": item.get("version"),
                "fuera_de_alcance": tipo in cat.OBJETOS_FUERA_DE_ALCANCE,
                "modulo": cat.OBJETOS_FUERA_DE_ALCANCE.get(tipo, "MOD-007"),
                "visible": tipo_item not in ("banco", "scorm"),
            }
            if tipo == "recurso":
                objeto["medio"] = {"media_ref": ref, "clase": tipo_item, "componente": componente, "url": url_medio(ref, None),
                                   "titulo": item.get("titulo", "")}
            elif tipo == "simulation_lab":
                objeto["simulacion"] = {"media_ref": ref, "clase": "interactivo", "componente": "webview",
                                        "url": url_medio(ref, "index.html"), "base_url": url_medio(ref, None)}
                objeto["url_lanzamiento"] = url_medio(ref, "index.html")
            elif tipo == "explanation":
                objeto["paginas"] = []
                objeto["detalle_url"] = f"/api/biblioteca/leccion/{ref}/"
            elif tipo == "activity":
                objeto["preguntas"] = []
                objeto["detalle_url"] = f"/api/biblioteca/evaluacion/{ref}/"
            objetos.append(objeto)
        lecciones.append({
            "leccion_ref": str(seccion.get("codigo", "")), "titulo": seccion.get("titulo", ""), "resumen": None,
            "objetivos": [], "duracion_estimada_min": None, "modos": [], "temas": [],
            "tipo_seccion": seccion.get("tipo"), "orden": seccion.get("orden"), "objetos": objetos,
        })
    objetos = [o for l in lecciones for o in l["objetos"]]
    return {
        **resumen_contrato1(curso, fuente),
        "rol": rol,
        "huella": curso.get("huella"),
        "portada": None,
        "referencias_curriculares": [],
        "palabras_clave": [],
        "creditos": None,
        "medios": [],
        "lecciones": lecciones,
        "resumen": {"lecciones": len(lecciones), "objetos": len(objetos), "objetos_por_tipo": {}, "medios": 0,
                    "preguntas": 0,
                    "fuera_de_alcance": [{"objeto_ref": o["objeto_ref"], "tipo": o["tipo"], "modulo": o["modulo"]}
                                         for o in objetos if o["fuera_de_alcance"]]},
    }


# ----------------------------------------------------------------- localizar

def localizar(vista: dict, *, leccion_ref: str = "", objeto_ref: str = "", unidad_ref: str = "") -> dict:
    """Encuentra lección, objeto y unidad (lámina, página o pregunta) por referencia.

    Devuelve `{"leccion", "objeto", "unidad"}` con los dicts de la vista (o None) y
    lanza ReferenciaNoEncontrada si algo no está en el curso vigente. Es lo que hace
    que un foco o una distribución apunten siempre a algo que existe."""
    leccion = objeto = unidad = None
    for l in vista.get("lecciones", []):
        if leccion_ref and l.get("leccion_ref") == leccion_ref:
            leccion = l
        for o in l.get("objetos", []):
            if objeto_ref and o.get("objeto_ref") == objeto_ref:
                objeto, leccion = o, l
    if leccion_ref and leccion is None:
        raise ReferenciaNoEncontrada(f"La lección «{leccion_ref}» no está en el curso vigente.", leccion_ref=leccion_ref)
    if objeto_ref and objeto is None:
        raise ReferenciaNoEncontrada(f"El objeto «{objeto_ref}» no está en el curso vigente.", objeto_ref=objeto_ref)
    if unidad_ref:
        if objeto is None:
            raise ReferenciaNoEncontrada("Una unidad exige su objeto.", unidad_ref=unidad_ref)
        for coleccion in ("laminas", "paginas", "preguntas"):
            for u in objeto.get(coleccion) or []:
                if u.get("unidad_ref") == unidad_ref or u.get("pregunta_ref") == unidad_ref:
                    unidad = u
        if unidad is None:
            raise ReferenciaNoEncontrada(f"La unidad «{unidad_ref}» no está en el objeto «{objeto_ref}».", unidad_ref=unidad_ref)
    return {"leccion": leccion, "objeto": objeto, "unidad": unidad}


def primer_objeto(vista: dict, leccion_ref: str = "") -> dict | None:
    """El primer objeto ejecutable por el aula de una lección (o del curso): el foco inicial."""
    for l in vista.get("lecciones", []):
        if leccion_ref and l.get("leccion_ref") != leccion_ref:
            continue
        for o in l.get("objetos", []):
            if not o.get("fuera_de_alcance"):
                return {"leccion": l, "objeto": o}
    return None
