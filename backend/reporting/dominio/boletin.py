"""
El boletín académico individual (propuesta del CTO, 2026-10-19): UN modelo de información común, con plantillas distintas según el país, el nivel educativo y el sistema de
evaluación de la institución. Responde cuatro preguntas:

  1. ¿Qué aprendió?            resultados por área/asignatura (Colombia), campo formativo (México primaria) o disciplina (México secundaria), con la nota en BRUTO (puntos sobre
                                el máximo y porcentaje) y presentada con el sistema configurado, y el nivel de desempeño
  2. ¿Qué competencias alcanzó? evidencias y logros (lo que el profesor anotó como fortalezas), aprendizajes pendientes (dificultades y evaluaciones que no cumplen el criterio)
  3. ¿Cómo ha progresado?      el promedio simple por curso en cada periodo en que estuvo (informativo, no ponderado, no oficial)
  4. ¿Qué debe mejorar?        las recomendaciones del profesor (frases del catálogo del libro y su texto), las oportunidades que anotó y el curso que conviene reforzar

Lo que NO es (consideración importante del CTO): un documento oficial. En Colombia la escala y la periodicidad las define el SIEE de cada institución (Decreto 1290 de 2009,
compilado en el Decreto 1075 de 2015) y la institución debe relacionar su escala con los desempeños nacionales Superior, Alto, Básico y Bajo; en México la boleta oficial de la SEP
(ciclo 2025–2026) tiene estructura y expedición reguladas (Acuerdo SEP 10/09/23): primaria por campos formativos y tres periodos, secundaria por disciplinas, preescolar sin cifras.
AVACOM no impone ninguna escala ni periodicidad: el boletín es la BASE para que, con pocas ediciones, el profesor arme el documento que su institución exige.

Todo lo que aquí se arma viene ya PRESENTADO por el libro (MOD-011): este archivo no convierte una nota, no promedia nada que el libro no haya promediado y no inventa un dato
que falte (lo pendiente es un guion). Funciones PURAS; este archivo no importa Django.
"""
from __future__ import annotations

from . import catalogos as cat
from . import texto as tx
from .documento import DECIMAL, ENTERO, PORCENTAJE, TEXTO, Columna, Documento, Tabla

LEYENDA_POR_DEFECTO = ("Documento de apoyo generado por AVACOM OPS a partir del libro de calificaciones. No es un boletín ni una boleta oficial: la institución expide el suyo "
                       "según su sistema de evaluación. El promedio es simple e informativo (no ponderado).")

# ---------------------------------------------------------------------------------------------------------------- las plantillas

PLANTILLAS: dict[str, dict] = {
    cat.PLANTILLA_CO: {
        "codigo": cat.PLANTILLA_CO, "nombre": "Colombia · boletín por áreas y asignaturas", "pais": "CO",
        "marco": "Decreto 1290 de 2009, compilado en el Decreto 1075 de 2015 (el SIEE de la institución define escala, periodicidad y promoción)",
        "organizacion": "Áreas y asignaturas", "rotulo_de_area": "Área / asignatura",
        "periodos": [],                                                  # el SIEE define cuántos (mínimo dos): no se imponen
        "desempenos_nacionales": ["Superior", "Alto", "Básico", "Bajo"],
        "evaluacion_cualitativa": "Desempeños, logros y dificultades",
        "referentes": "DBA, estándares y currículo institucional",
        "sin_cifras": False,
    },
    cat.PLANTILLA_MX: {
        "codigo": cat.PLANTILLA_MX, "nombre": "México · boleta por campos formativos (primaria) o disciplinas (secundaria)", "pais": "MX",
        "marco": "Acuerdo SEP 10/09/23 (la boleta oficial la expide la SEP; esto es una base de trabajo)",
        "organizacion": "Campos formativos", "rotulo_de_area": "Campo formativo",
        "periodos": ["1.er periodo", "2.º periodo", "3.er periodo"],
        "desempenos_nacionales": None,
        "evaluacion_cualitativa": "Observaciones y sugerencias según el nivel",
        "referentes": "Contenidos y procesos de desarrollo de aprendizaje",
        "sin_cifras": False,
    },
    cat.PLANTILLA_GENERICA: {
        "codigo": cat.PLANTILLA_GENERICA, "nombre": "Boletín genérico por asignaturas", "pais": "",
        "marco": "", "organizacion": "Asignaturas", "rotulo_de_area": "Asignatura", "periodos": [], "desempenos_nacionales": None,
        "evaluacion_cualitativa": "Observaciones del profesor", "referentes": "", "sin_cifras": False,
    },
}

# Los cuatro campos formativos de la educación básica mexicana y las materias (por el código del árbol de la biblioteca) que suelen caer en cada uno. Es una CORRESPONDENCIA
# ORIENTATIVA para empezar: la institución la ajusta; lo que no se reconoce queda «Sin clasificar» y nunca se adivina.
CAMPOS_FORMATIVOS = {
    "Lenguajes": ("language", "languages", "spanish", "english", "literature", "reading", "writing", "arts", "art", "music", "lengua", "lenguaje", "espanol", "español",
                  "ingles", "inglés", "artes", "comunicacion", "comunicación"),
    "Saberes y pensamiento científico": ("math", "maths", "mathematics", "science", "sciences", "biology", "chemistry", "physics", "technology", "geometry", "algebra",
                                         "matematicas", "matemáticas", "ciencias", "biologia", "quimica", "fisica", "tecnologia"),
    "Ética, naturaleza y sociedades": ("social-studies", "social_studies", "social", "history", "geography", "civics", "ethics", "environment", "sociales", "historia",
                                       "geografia", "civica", "etica", "formacion-civica", "ciudadania"),
    "De lo humano y lo comunitario": ("physical-education", "physical_education", "pe", "sports", "health", "life-skills", "educacion-fisica", "salud", "socioemocional",
                                      "deporte", "deportes"),
}
SIN_CLASIFICAR = "Sin clasificar"


def campo_formativo_de(materia: str) -> str:
    codigo = (materia or "").casefold()
    for campo, materias in CAMPOS_FORMATIVOS.items():
        if codigo in materias:
            return campo
    return SIN_CLASIFICAR


def elegir_plantilla(configurada: str, pais: str, nivel_clave: str) -> dict:
    """`auto` elige por el país de la política del libro (CO, MX o genérica); una plantilla fijada por la administración manda. En México, secundaria y bachillerato se organizan por
    DISCIPLINAS (no por campos formativos) y preescolar va sin cifras."""
    codigo = configurada if configurada in PLANTILLAS else {"CO": cat.PLANTILLA_CO, "MX": cat.PLANTILLA_MX}.get((pais or "").upper(), cat.PLANTILLA_GENERICA)
    plantilla = dict(PLANTILLAS[codigo])
    if codigo == cat.PLANTILLA_MX:
        if nivel_clave in ("secundaria", "bachillerato", "preuniversitario"):
            plantilla["organizacion"], plantilla["rotulo_de_area"] = "Disciplinas", "Disciplina"
        if nivel_clave == "preescolar":
            plantilla["sin_cifras"] = True
            plantilla["organizacion"], plantilla["rotulo_de_area"] = "Campos formativos (observaciones, sin calificación numérica)", "Campo formativo"
    return plantilla


def desempeno_nacional(presentado: dict | None, plantilla: dict) -> str | None:
    """En Colombia, el desempeño nacional (Superior, Alto, Básico, Bajo) cuando el tramo de la escala institucional ya lo dice con ese nombre; si la institución usa otros nombres,
    la equivalencia la declara su SIEE y aquí queda vacío (no se inventa)."""
    nacionales = plantilla.get("desempenos_nacionales")
    if not nacionales or not presentado:
        return None
    nivel = str(presentado.get("desempeno") or "")
    return nivel if nivel in nacionales else None


# ---------------------------------------------------------------------------------------------------------- el modelo común

def _area_de(curso: dict, plantilla: dict, nombres: dict[str, str]) -> tuple[str, str, str | None]:
    """`(código del área, rótulo, campo formativo)`: en México primaria el área ES el campo formativo; en los demás, la materia."""
    materia = curso.get("materia") or ""
    rotulo = nombres.get(materia) or _rotulo(materia)
    campo = campo_formativo_de(materia) if plantilla["codigo"] == cat.PLANTILLA_MX else None
    if plantilla["codigo"] == cat.PLANTILLA_MX and plantilla["organizacion"].startswith("Campos formativos"):
        return campo or SIN_CLASIFICAR, campo or SIN_CLASIFICAR, campo
    return materia or "", rotulo, campo


def _rotulo(materia: str) -> str:
    texto = (materia or "").replace("-", " ").replace("_", " ").strip()
    return texto[:1].upper() + texto[1:] if texto else "Sin materia"


def _bruto_vacio() -> dict:
    return {"puntos": None, "puntos_maximos": None, "porcentaje": None, "evaluaciones": 0}


def _sumar_bruto(partes: list[dict]) -> dict:
    con = [p for p in partes if p and p.get("puntos") is not None and p.get("puntos_maximos")]
    if not con:
        return _bruto_vacio()
    puntos = round(sum(float(p["puntos"]) for p in con), 2)
    maximos = round(sum(float(p["puntos_maximos"]) for p in con), 2)
    return {"puntos": puntos, "puntos_maximos": maximos, "porcentaje": round(puntos * 100 / maximos, 2) if maximos else None, "evaluaciones": sum(int(p.get("evaluaciones") or 0) for p in con)}


def _promedio_simple(valores: list) -> float | None:
    con = [float(v) for v in valores if v is not None]
    return round(sum(con) / len(con), 2) if con else None


def armar_modelo(boletin: dict, progreso: list[dict], politica: dict, config: dict, *, nombres_de_materias: dict[str, str] | None = None) -> dict:
    """El modelo de información común de UN estudiante a partir de lo que el libro ya presentó (`gradebook.servicios.boletin_de_alumno`), su progreso por periodo, la política
    institucional y la configuración del nodo. Puro: no consulta nada."""
    nombres = nombres_de_materias or {}
    grupo = boletin["grupo"]
    plantilla = elegir_plantilla(config.get("plantilla_boletin") or cat.PLANTILLA_AUTO, politica.get("pais") or "", grupo.get("nivel_clave") or "")
    if config.get("periodos_boletin"):
        plantilla["periodos"] = list(config["periodos_boletin"])
    modo = boletin.get("modo") or "simple"
    sin_cifras = plantilla["sin_cifras"] or modo != "calificaciones"
    leyenda = config.get("leyenda_boletin") or LEYENDA_POR_DEFECTO

    # ---- 1 · ¿qué aprendió? por área (y dentro, por curso)
    areas: dict[str, dict] = {}
    for curso in boletin.get("cursos") or []:
        codigo, rotulo, campo = _area_de(curso, plantilla, nombres)
        area = areas.setdefault(codigo, {"codigo": codigo, "rotulo": rotulo, "campo_formativo": campo, "materia": curso.get("materia") or "", "cursos": [], "evaluaciones": 0,
                                         "con_nota": 0, "aprobadas": 0, "no_aprobadas": 0, "completadas": 0})
        c = curso.get("conteo") or {}
        presentado = None if sin_cifras else curso.get("presentado")
        area["cursos"].append({
            "curso_ref": curso["curso_ref"], "curso_rotulo": curso.get("curso_rotulo") or curso["curso_ref"], "evaluaciones": curso.get("evaluaciones", 0), "con_nota": c.get("con_nota", 0),
            "completadas": c.get("completadas", 0), "aprobadas": c.get("aprobadas", 0), "no_aprobadas": c.get("no_aprobadas", 0), "pendientes": c.get("pendientes", 0),
            "bruto": (curso.get("bruto") if not sin_cifras else None) or _bruto_vacio(), "promedio_simple": None if sin_cifras else curso.get("promedio_simple"),
            "presentado": presentado, "desempeno": (presentado or {}).get("desempeno"), "cumple_criterio": (presentado or {}).get("cumple_criterio"),
            "desempeno_nacional": desempeno_nacional(presentado, plantilla)})
        area["evaluaciones"] += curso.get("evaluaciones", 0)
        for k in ("con_nota", "aprobadas", "no_aprobadas", "completadas"):
            area[k] += c.get(k, 0)
    for area in areas.values():
        area["bruto"] = _sumar_bruto([c["bruto"] for c in area["cursos"]])
        area["promedio_simple"] = _promedio_simple([c["promedio_simple"] for c in area["cursos"]])
        # El área se presenta con el curso que más pesa sólo cuando hay UNO: el libro no promedia entre cursos con sistemas distintos y aquí no se convierte nada.
        area["presentado"] = area["cursos"][0]["presentado"] if len(area["cursos"]) == 1 else None
        area["desempeno"] = area["cursos"][0]["desempeno"] if len(area["cursos"]) == 1 else None
        area["desempeno_nacional"] = area["cursos"][0]["desempeno_nacional"] if len(area["cursos"]) == 1 else None
    areas_lista = sorted(areas.values(), key=lambda a: (a["rotulo"] == SIN_CLASIFICAR, tx.clave_de_orden(a["rotulo"])))

    evaluaciones = []
    for e in sorted(boletin.get("evaluaciones", {}).get("items") or [], key=lambda i: (i.get("fecha") or 0, i["asignacion_id"])):
        presentacion = None if sin_cifras else e.get("presentacion")
        pres = (presentacion or {}).get("presentada") or {}
        area_codigo, area_rotulo, _ = _area_de({"materia": e.get("materia") or ""}, plantilla, nombres)
        evaluaciones.append({
            "asignacion_id": e["asignacion_id"], "titulo": e["titulo"], "curso_ref": e["curso_ref"], "curso_rotulo": e.get("curso_rotulo") or e["curso_ref"], "area": area_rotulo,
            "tipo_evaluacion": e.get("tipo_evaluacion"), "fecha": e.get("fecha"), "estado": e["estado"], "estado_simple": e["estado_simple"], "publicada": bool(e.get("publicada")),
            "bruto": (e.get("bruto") if not sin_cifras else None), "presentada": pres.get("etiqueta") or (str(pres["valor"]) if pres.get("valor") is not None else None),
            "desempeno": ((presentacion or {}).get("desempeno") or {}).get("nivel"), "cumple_criterio": ((presentacion or {}).get("aprobacion") or {}).get("cumple_criterio"),
            "provisional": bool((presentacion or {}).get("provisional")), "ajustada": bool(e.get("ajustada"))})

    # ---- 2 · ¿qué competencias alcanzó?
    comentarios = (boletin.get("insights") or {}).get("comentarios") or {}
    competencias = {
        "logros": list(comentarios.get("fortalezas") or []),
        "pendientes": list(comentarios.get("dificultades") or []),
        "evaluaciones_no_aprobadas": [e["titulo"] for e in evaluaciones if e["cumple_criterio"] is False],
        "evaluaciones_aprobadas": [e["titulo"] for e in evaluaciones if e["cumple_criterio"] is True],
        "objetivos": {"disponible": False, "texto": "La agregación por objetivos y competencias llega con el módulo de objetivos."},
    }

    # ---- 3 · ¿cómo ha progresado?
    rotulos_de_curso = {c["curso_ref"]: c.get("curso_rotulo") or c["curso_ref"] for a in areas_lista for c in a["cursos"]}
    progreso_filas = [{"periodo": p["periodo"], "grupo_codigo": p.get("grupo_codigo") or "", "curso_ref": p["curso_ref"], "curso_rotulo": rotulos_de_curso.get(p["curso_ref"], p["curso_ref"]),
                       "calificaciones": p.get("calificaciones", 0), "promedio_simple": None if p.get("modo") != "calificaciones" else p.get("promedio_simple"),
                       "presentado": None if p.get("modo") != "calificaciones" else p.get("presentado"), "actual": p.get("grupo_id") == grupo["id"]} for p in progreso]
    periodos_vistos = sorted({f["periodo"] for f in progreso_filas if f["periodo"]} | ({grupo["periodo"]} if grupo.get("periodo") else set()))
    tendencia = (boletin.get("insights") or {}).get("tendencia") or {}

    # ---- 4 · ¿qué debe mejorar?
    del_docente = []
    for o in boletin.get("observaciones") or []:
        del_docente.append({"curso_ref": o.get("curso_ref") or "", "curso_rotulo": rotulos_de_curso.get(o.get("curso_ref") or "", "") if o.get("curso_ref") else "General",
                            "recomendaciones": [r["texto"] if isinstance(r, dict) else str(r) for r in (o.get("recomendaciones") or [])], "texto": o.get("texto") or "",
                            "actualizada_en": o.get("actualizada_en")})
    recomendaciones = {"del_docente": del_docente, "oportunidades": list(comentarios.get("oportunidades") or []),
                       "curso_a_reforzar": (boletin.get("insights") or {}).get("curso_a_reforzar"), "mejor_curso": (boletin.get("insights") or {}).get("mejor_curso")}

    r = boletin.get("resumen") or {}
    conteo = r.get("conteo") or {}
    resumen = {"evaluaciones": r.get("evaluaciones", 0), "con_nota": conteo.get("con_nota", 0), "aprobadas": conteo.get("aprobadas", 0), "no_aprobadas": conteo.get("no_aprobadas", 0),
               "completadas": conteo.get("completadas", 0), "pendientes": conteo.get("pendientes", 0), "promedio_simple": None if sin_cifras else r.get("promedio_simple"),
               "presentado": None if sin_cifras else r.get("presentado"), "bruto": (r.get("bruto") if not sin_cifras else None) or _bruto_vacio(), "oficial": False, "ponderado": False}

    return {
        "plantilla": {**plantilla, "leyenda": leyenda},
        "institucion": {"nombre": politica.get("institucion") or "", "pais": politica.get("pais") or "", "jurisdiccion": politica.get("jurisdiccion") or ""},
        "estudiante": dict(boletin["alumno"]), "grupo": dict(grupo), "periodo": grupo.get("periodo") or "", "nivel_clave": grupo.get("nivel_clave") or "",
        "modo": modo, "sin_cifras": sin_cifras, "sistema": None if sin_cifras else boletin.get("sistema"),
        "areas": areas_lista, "evaluaciones": evaluaciones, "competencias": competencias,
        "progreso": {"periodos": periodos_vistos, "filas": progreso_filas, "tendencia": tendencia},
        "recomendaciones": recomendaciones, "resumen": resumen, "leyenda": leyenda,
        "preguntas": ["¿Qué aprendió?", "¿Qué competencias alcanzó?", "¿Cómo ha progresado?", "¿Qué debe mejorar?"],
    }


# ------------------------------------------------------------------------------------------------------------ el documento

def _texto_presentado(p: dict | None) -> str:
    if not p:
        return ""
    etiqueta = str(p.get("etiqueta") or (p.get("valor") if p.get("valor") is not None else "") or "")
    desempeno = p.get("desempeno")
    return f"{etiqueta} · {desempeno}" if desempeno and desempeno != etiqueta else etiqueta


def _puntos(b: dict | None) -> str:
    if not b or b.get("puntos") is None or b.get("puntos_maximos") is None:
        return ""
    return f"{b['puntos']:g} de {b['puntos_maximos']:g}"


def _cumple(valor) -> str:
    return "" if valor is None else ("Sí" if valor else "No")


def documento_de_boletin(modelo: dict, ctx: dict) -> Documento:
    """El boletín de un estudiante como documento exportable: la cabecera (institución, estudiante, grupo, periodo, plantilla, quién lo generó y el corte) y una hoja por pregunta,
    más una hoja «Datos» plana (lo mismo, una fila por evaluación, lista para CSV)."""
    p, est, g = modelo["plantilla"], modelo["estudiante"], modelo["grupo"]
    sin_cifras = modelo["sin_cifras"]
    cabecera = [("Boletín", p["nombre"]), ("Institución", modelo["institucion"]["nombre"] or "—"), ("Estudiante", est["rotulo"]), ("Grupo", g.get("nombre") or g.get("codigo") or ""),
                ("Periodo", modelo["periodo"] or "—"), ("Nivel educativo", modelo["nivel_clave"] or "—"), ("Organización", p["organizacion"]),
                ("Sistema de calificación", (modelo["sistema"] or {}).get("nombre") or ("Sin cifras (modo simple)" if sin_cifras else "—")),
                ("Marco de referencia", p["marco"] or "—"), ("Generado por", ctx["generado_por"]), ("Generado el", ctx["generado_el"]),
                ("Datos al corte", ctx["corte_texto"] + ". " + tx.EXPLICACION_DEL_CORTE), ("Versión del nodo", ctx["version_nodo"] or "—")]
    r = modelo["resumen"]
    resumen = [("Evaluaciones", r["evaluaciones"], ENTERO), ("Completadas", r["completadas"], ENTERO)]
    if not sin_cifras:
        resumen += [("Con nota", r["con_nota"], ENTERO), ("Cumplen el criterio de aprobación", r["aprobadas"], ENTERO), ("No lo cumplen", r["no_aprobadas"], ENTERO),
                    ("Puntos obtenidos sobre el máximo", _puntos(r["bruto"]), TEXTO), ("Porcentaje de puntos", r["bruto"].get("porcentaje"), PORCENTAJE),
                    ("Promedio simple (sobre 100, informativo)", r["promedio_simple"], DECIMAL), ("Promedio presentado", _texto_presentado(r["presentado"]), TEXTO)]
    notas = [modelo["leyenda"], "Este archivo incluye el nombre del estudiante. Una vez fuera del equipo del colegio, quien lo guarda es responsable de quién lo abre."]
    if p.get("desempenos_nacionales"):
        notas.append("Desempeño nacional (Colombia): " + ", ".join(p["desempenos_nacionales"]) + ". La equivalencia con la escala institucional la define el SIEE.")
    if p["codigo"] == cat.PLANTILLA_MX:
        notas.append("La correspondencia materia → campo formativo es orientativa; la boleta oficial la expide la SEP.")

    # 1 · qué aprendió
    col_area = p["rotulo_de_area"]
    c1 = [Columna("area", col_area), Columna("curso", "Curso"), Columna("evaluaciones", "Evaluaciones", ENTERO), Columna("completadas", "Completadas", ENTERO)]
    if not sin_cifras:
        c1 += [Columna("con_nota", "Con nota", ENTERO), Columna("puntos", "Puntos obtenidos"), Columna("porcentaje", "Porcentaje", PORCENTAJE), Columna("promedio", "Promedio simple (0–100)", DECIMAL),
               Columna("presentada", "Calificación (sistema configurado)"), Columna("desempeno", "Desempeño"), Columna("cumple", "Cumple el criterio")]
        if p.get("desempenos_nacionales"):
            c1.append(Columna("nacional", "Desempeño nacional"))
    f1 = []
    for a in modelo["areas"]:
        for c in a["cursos"]:
            fila = [a["rotulo"], c["curso_rotulo"], c["evaluaciones"], c["completadas"]]
            if not sin_cifras:
                fila += [c["con_nota"], _puntos(c["bruto"]), c["bruto"].get("porcentaje"), c["promedio_simple"], _texto_presentado(c["presentado"]), c["desempeno"] or "", _cumple(c["cumple_criterio"])]
                if p.get("desempenos_nacionales"):
                    fila.append(c["desempeno_nacional"] or "")
            f1.append(fila)

    c2 = [Columna("fecha", "Fecha"), Columna("area", col_area), Columna("curso", "Curso"), Columna("evaluacion", "Evaluación"), Columna("tipo", "Tipo"), Columna("estado", "Estado")]
    if not sin_cifras:
        c2 += [Columna("puntos", "Puntos"), Columna("porcentaje", "Porcentaje", PORCENTAJE), Columna("presentada", "Calificación"), Columna("desempeno", "Desempeño"),
               Columna("cumple", "Cumple el criterio"), Columna("publicada", "Publicada")]
    f2 = []
    for e in modelo["evaluaciones"]:
        fila = [ctx["fecha"](e["fecha"]) if e.get("fecha") else "", e["area"], e["curso_rotulo"], e["titulo"], (e.get("tipo_evaluacion") or "").capitalize(),
                tx.ETIQUETA_DEL_ESTADO_DE_CALIFICACION.get(e["estado"], e["estado"]) if not sin_cifras else tx.ETIQUETA_DEL_ESTADO_SIMPLE.get(e["estado_simple"], e["estado_simple"])]
        if not sin_cifras:
            fila += [_puntos(e["bruto"]), (e["bruto"] or {}).get("porcentaje"), (e["presentada"] or "") + (" (provisional)" if e["provisional"] else ""), e["desempeno"] or "",
                     _cumple(e["cumple_criterio"]), tx.si_no(e["publicada"])]
        f2.append(fila)

    # 2 · competencias
    c3 = [Columna("clase", "Qué"), Columna("texto", "Evidencia o aprendizaje"), Columna("evaluacion", "Evaluación"), Columna("fecha", "Fecha")]
    f3 = [["Logro", x["texto"], x.get("titulo") or "", ctx["fecha"](x["fecha"]) if x.get("fecha") else ""] for x in modelo["competencias"]["logros"]]
    f3 += [["Aprendizaje pendiente", x["texto"], x.get("titulo") or "", ctx["fecha"](x["fecha"]) if x.get("fecha") else ""] for x in modelo["competencias"]["pendientes"]]
    f3 += [["Evaluación que no cumple el criterio", t, t, ""] for t in modelo["competencias"]["evaluaciones_no_aprobadas"]]

    # 3 · progreso
    c4 = [Columna("periodo", "Periodo"), Columna("grupo", "Grupo"), Columna("curso", "Curso"), Columna("calificaciones", "Calificaciones", ENTERO),
          Columna("promedio", "Promedio simple (0–100)", DECIMAL), Columna("presentado", "Promedio presentado"), Columna("actual", "Periodo actual")]
    f4 = [[x["periodo"], x["grupo_codigo"], x["curso_rotulo"], x["calificaciones"], x["promedio_simple"], _texto_presentado(x["presentado"]), tx.si_no(x["actual"])] for x in modelo["progreso"]["filas"]]

    # 4 · recomendaciones
    c5 = [Columna("ambito", "Ámbito"), Columna("recomendacion", "Recomendación del docente"), Columna("texto", "Comentario")]
    f5 = []
    for o in modelo["recomendaciones"]["del_docente"]:
        for rec in o["recomendaciones"]:
            f5.append([o["curso_rotulo"] or "General", rec, ""])
        if o["texto"]:
            f5.append([o["curso_rotulo"] or "General", "", o["texto"]])
    for x in modelo["recomendaciones"]["oportunidades"]:
        f5.append([x.get("titulo") or "General", x["texto"], "Oportunidad anotada en una evaluación"])
    if modelo["recomendaciones"]["curso_a_reforzar"]:
        f5.append([modelo["recomendaciones"]["curso_a_reforzar"].get("curso_rotulo") or "", "Conviene reforzar este curso: es el de promedio más bajo", ""])

    # datos planos (para CSV)
    c6 = [Columna("estudiante", "Estudiante"), Columna("grupo", "Grupo"), Columna("periodo", "Periodo"), Columna("area", col_area), Columna("curso", "Curso"), Columna("evaluacion", "Evaluación"),
          Columna("tipo", "Tipo"), Columna("estado", "Estado"), Columna("puntos", "Puntos", DECIMAL), Columna("maximo", "Puntos máximos", DECIMAL), Columna("porcentaje", "Porcentaje", PORCENTAJE),
          Columna("presentada", "Calificación"), Columna("desempeno", "Desempeño"), Columna("cumple", "Cumple el criterio"), Columna("publicada", "Publicada")]
    f6 = [[est["rotulo"], g.get("codigo") or "", modelo["periodo"], e["area"], e["curso_rotulo"], e["titulo"], e.get("tipo_evaluacion") or "", e["estado"],
           (e["bruto"] or {}).get("puntos") if not sin_cifras else None, (e["bruto"] or {}).get("puntos_maximos") if not sin_cifras else None, (e["bruto"] or {}).get("porcentaje") if not sin_cifras else None,
           (e["presentada"] or "") if not sin_cifras else "", e["desempeno"] or "", _cumple(e["cumple_criterio"]) if not sin_cifras else "", tx.si_no(e["publicada"])] for e in modelo["evaluaciones"]]

    tablas = [Tabla("1 Qué aprendió", c1, f1), Tabla("1b Evaluaciones", c2, f2), Tabla("2 Competencias", c3, f3), Tabla("3 Progreso", c4, f4), Tabla("4 Qué debe mejorar", c5, f5), Tabla("Datos", c6, f6)]
    titulo = f"Boletín académico · {est['rotulo']}"
    return Documento(titulo, g.get("codigo") or "boletin", cabecera, resumen, tablas, notas, True)
