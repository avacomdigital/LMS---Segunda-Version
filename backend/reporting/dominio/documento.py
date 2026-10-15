"""
El documento exportable (FUN-146): lo MISMO que se ve en pantalla, aplanado en una cabecera, un resumen y una o más tablas. Un archivo suelto debe seguir diciendo de dónde
vino y qué tan fresco es (BR-083), así que la cabecera lleva el nombre del reporte, el grupo o el alumno, el periodo, quién lo generó y cuándo, el corte de los datos, el estado
de integración, si se aplicó el umbral de privacidad y la versión del nodo.

Aquí no se escribe ningún formato: `infraestructura/archivos.py` convierte este documento a xlsx o csv. Función PURA sobre el diccionario del reporte (la misma fuente que la
pantalla: si el archivo y la pantalla difirieran sería un defecto). Este archivo no importa Django.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import catalogos as cat
from . import texto as tx

TEXTO, ENTERO, DECIMAL, PORCENTAJE, MINUTOS = "texto", "entero", "decimal", "porcentaje", "minutos"


@dataclass(frozen=True)
class Columna:
    clave: str
    titulo: str
    tipo: str = TEXTO


@dataclass
class Tabla:
    nombre: str
    columnas: list[Columna]
    filas: list[list]


@dataclass
class Documento:
    titulo: str
    sujeto: str                                              # un código de grupo o un periodo: va en el nombre del archivo (nunca el nombre de una persona)
    cabecera: list[tuple[str, str]]
    resumen: list[tuple[str, object, str]] = field(default_factory=list)      # (etiqueta, valor, tipo)
    tablas: list[Tabla] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    nominal: bool = False

    @property
    def filas(self) -> int:
        return sum(len(t.filas) for t in self.tablas)


def _nota_de(e: dict) -> str:
    """Cómo se escribe la calificación de una evaluación: la presentada con la escala del nivel (con su desempeño) o, en modo simple, el estado."""
    p = e.get("presentacion")
    if p:
        pres = p.get("presentada") or {}
        texto = str(pres.get("etiqueta") or pres.get("valor") or "")
        nivel = (p.get("desempeno") or {}).get("nivel")
        if nivel and nivel != texto:
            texto += f" · {nivel}"
        return texto + (" (provisional)" if p.get("provisional") else "")
    return tx.ETIQUETA_DEL_ESTADO_SIMPLE.get(e.get("estado_simple") or "", "")


def _cabecera(r: dict, ctx: dict, sujeto_etiqueta: str, sujeto_valor: str, periodo: str) -> list[tuple[str, str]]:
    integ = (r.get("corte") or {}).get("integracion") or {}
    estado = integ.get("texto", "")
    if integ.get("estado") == "incompleta" and integ.get("motivos"):
        estado += " (" + "; ".join(m["texto"] for m in integ["motivos"]) + ")"
    return [("Reporte", ctx["titulo"]), (sujeto_etiqueta, sujeto_valor), ("Periodo", periodo or "—"), ("Generado por", ctx["generado_por"]), ("Generado el", ctx["generado_el"]),
            ("Datos al corte", ctx["corte_texto"] + ". " + tx.EXPLICACION_DEL_CORTE), ("Estado de integración", estado or "—"),
            ("Umbral de privacidad aplicado", tx.si_no(bool((r.get("privacidad") or {}).get("aplicada")))), ("Versión del nodo", ctx["version_nodo"] or "—")]


def _notas(r: dict) -> list[str]:
    notas = []
    priv = r.get("privacidad") or {}
    if priv.get("aplicada"):
        notas.append(priv["aviso"])
    notas.append("Dominio por objetivo: aún no disponible." if not (r.get("objetivos") or {}).get("disponible") else "")
    if r.get("nominal"):
        notas.append("Este archivo incluye nombres de alumnos. Una vez fuera del equipo del colegio, quien lo guarda es responsable de quién lo abre.")
    else:
        notas.append("Este archivo no incluye datos de personas.")
    return [n for n in notas if n]


# ------------------------------------------------------------------------------------------------------ una clase

def de_clase(r: dict, ctx: dict) -> Documento:
    c, t = r["clase"], r["totales"]
    grupo = c.get("grupo") or {}
    columnas = [Columna("alumno", "Alumno"), Columna("estado", "Presencia"), Columna("presente", "Presente (min)", MINUTOS), Columna("recibidas", "Actividades recibidas", ENTERO),
                Columna("entregadas", "Actividades entregadas", ENTERO), Columna("participacion", "Participación (%)", PORCENTAJE),
                Columna("calificadas", "Respuestas calificadas", ENTERO), Columna("aciertos", "Aciertos", ENTERO), Columna("pct_aciertos", "Aciertos (%)", PORCENTAJE),
                Columna("cola", "Entregas desde la cola de la tableta", ENTERO)]
    filas = [[f["alumno"], tx.ETIQUETA_DE_PRESENCIA.get(f["estado"], f["estado"]), tx.minutos(f["presente_ms"]), f["actividades_recibidas"], f["actividades_entregadas"],
              f["porcentaje_participacion"], f["calificadas"], f["aciertos"], f["porcentaje_aciertos"], f["entregas_por_cola"]] for f in r["filas"]]
    resumen = [("Curso", c.get("curso_rotulo") or "—", TEXTO), ("Lección", c.get("leccion_rotulo") or "—", TEXTO), ("Duración de la clase", tx.duracion(c.get("duracion_ms")), TEXTO),
               ("Participantes", t["participantes"], ENTERO), ("Actividades lanzadas", t["actividades"], ENTERO),
               ("Promedio de participación (%)", t["promedio_participacion"], PORCENTAJE), ("Promedio de aciertos (%)", t["promedio_aciertos"], PORCENTAJE)]
    return Documento(ctx["titulo"], grupo.get("codigo") or "clase", _cabecera(r, ctx, "Grupo", (grupo.get("nombre") or grupo.get("codigo") or "Sin grupo"), grupo.get("periodo") or ""),
                     resumen, [Tabla("Alumnos", columnas, filas)] if filas else [], _notas(r), bool(r.get("nominal")))


# ------------------------------------------------------------------------------------------------------ un grupo

def de_grupo(r: dict, ctx: dict) -> Documento:
    g, t = r["grupo"], r["totales"]
    alumnos = [Columna("alumno", "Alumno"), Columna("asistidas", "Clases a las que asistió", ENTERO), Columna("clases", "Clases cerradas", ENTERO),
               Columna("participacion", "Participación (%)", PORCENTAJE), Columna("aciertos", "Aciertos (%)", PORCENTAJE),
               Columna("presentadas", "Evaluaciones presentadas", ENTERO), Columna("evaluaciones", "Evaluaciones", ENTERO), Columna("sin_presentar", "Evaluaciones sin presentar", ENTERO),
               Columna("estudio", "Tareas de estudio completadas", ENTERO), Columna("estudios", "Tareas de estudio", ENTERO), Columna("atencion", "Necesita atención"),
               Columna("motivo", "Motivo")]
    f_alumnos = [[a["alumno"], a["clases_asistidas"], a["clases_total"], a["porcentaje_participacion"], a["porcentaje_aciertos"], a["evaluaciones_presentadas"],
                  a["evaluaciones_total"], a["evaluaciones_sin_presentar"], a["estudios_completados"], a["estudios_total"], tx.si_no(bool(a["atencion"])), a["motivo"]]
                 for a in r["alumnos"]]
    clases = [Columna("fecha", "Clase"), Columna("curso", "Curso"), Columna("leccion", "Lección"), Columna("participantes", "Participantes", ENTERO),
              Columna("participacion", "Participación promedio (%)", PORCENTAJE), Columna("aciertos", "Aciertos promedio (%)", PORCENTAJE), Columna("incompleta", "Datos incompletos")]
    f_clases = [[ctx["fecha"](c["finalizada_en"]), c.get("curso_rotulo") or "", c.get("leccion_rotulo") or "", c["participantes"], c["promedio_participacion"],
                 c["promedio_aciertos"], tx.si_no(bool(c["incompleta"]))] for c in r["clases"]]
    evals = [Columna("evaluacion", "Evaluación"), Columna("estado", "Estado"), Columna("presentaron", "Presentaron", ENTERO), Columna("pendientes", "Sin presentar", ENTERO),
             Columna("por_revisar", "Por revisar", ENTERO), Columna("publicadas", "Con calificación publicada", ENTERO)]
    f_evals = [[e["titulo"], e["estado"], e["presentaron"], e["pendientes"], e["por_revisar"], e["publicadas"]] for e in r["evaluaciones"]]
    # Con la privacidad aplicada no se cuenta quién necesita atención (la pantalla pone «—»): un «0» en el archivo diría «nadie necesita atención», que no es lo que se sabe.
    atencion = None if (r.get("privacidad") or {}).get("aplicada") else t["en_atencion"]
    resumen = [("Alumnos", t["alumnos"], ENTERO), ("Clases cerradas", t["clases"], ENTERO), ("Evaluaciones", t["evaluaciones"], ENTERO), ("Tareas de estudio", t["estudios"], ENTERO),
               ("Alumnos que necesitan atención", atencion, ENTERO), ("Promedio de participación (%)", t["promedio_participacion"], PORCENTAJE),
               ("Promedio de aciertos (%)", t["promedio_aciertos"], PORCENTAJE), ("Modo de calificación", "Calificaciones" if r.get("modo") == "calificaciones" else "Simple (sin notas)", TEXTO)]
    tablas = [x for x in (Tabla("Alumnos", alumnos, f_alumnos) if f_alumnos else None, Tabla("Clases", clases, f_clases) if f_clases else None,
                          Tabla("Evaluaciones", evals, f_evals) if f_evals else None) if x]
    return Documento(ctx["titulo"], g.get("codigo") or "grupo", _cabecera(r, ctx, "Grupo", g.get("nombre") or g.get("codigo") or "", g.get("periodo") or ""), resumen, tablas, _notas(r),
                     bool(r.get("nominal")))


# ------------------------------------------------------------------------------------------------------ un alumno

def de_alumno(r: dict, ctx: dict) -> Documento:
    a = r["alumno"]
    grupos = r["grupos"]
    resumen: list[tuple[str, object, str]] = []
    ev_cols = [Columna("grupo", "Grupo"), Columna("evaluacion", "Evaluación"), Columna("estado", "Estado de la evaluación"), Columna("calificacion", "Calificación"),
               Columna("publicada", "Publicada")]
    es_cols = [Columna("grupo", "Grupo"), Columna("tarea", "Tarea de estudio"), Columna("estado", "Estado"), Columna("avance", "Avance (%)", PORCENTAJE), Columna("vencida", "Vencida")]
    cl_cols = [Columna("grupo", "Grupo"), Columna("clase", "Clase"), Columna("asistio", "Asistió"), Columna("recibidas", "Actividades recibidas", ENTERO),
               Columna("entregadas", "Actividades entregadas", ENTERO), Columna("aciertos", "Aciertos (%)", PORCENTAJE)]
    ev_f, es_f, cl_f = [], [], []
    for g in grupos:
        cod = (g["grupo"].get("codigo") or g["grupo"].get("nombre") or "")
        s = g["resumen"]
        resumen += [(f"{cod} · Clases a las que asistió", f'{s["clases_asistidas"]} de {s["clases_total"]}', TEXTO),
                    (f"{cod} · Actividades de clase entregadas", f'{s["actividades_entregadas"]} de {s["actividades_recibidas"]}', TEXTO),
                    (f"{cod} · Aciertos en clase (%)", s["porcentaje_aciertos"], PORCENTAJE),
                    (f"{cod} · Necesita atención", g["motivo_de_atencion"] or "No", TEXTO)]
        ev_f += [[cod, e["titulo"], tx.ETIQUETA_DEL_ESTADO_DE_CALIFICACION.get(e["estado"], e["estado"]) if e["presento"] else "Sin presentar", _nota_de(e) if e["presento"] else "",
                  tx.si_no(bool(e["publicada"]))] for e in g["evaluaciones"]]
        es_f += [[cod, t["titulo"], tx.ETIQUETA_DEL_ESTADO_DE_ESTUDIO.get(t["estado"], t["estado"]), t["avance_pct"], tx.si_no(bool(t["vencida"]))] for t in g["estudios"]]
        cl_f += [[cod, ctx["fecha"](c["finalizada_en"]), tx.si_no(bool(c["asistio"])), c["recibidas"], c["entregadas"], c["porcentaje_aciertos"]] for c in g["clases"]]
    tablas = [x for x in (Tabla("Evaluaciones", ev_cols, ev_f) if ev_f else None, Tabla("Estudio", es_cols, es_f) if es_f else None, Tabla("Clases", cl_cols, cl_f) if cl_f else None) if x]
    grupos_txt = ", ".join((g["grupo"].get("codigo") or g["grupo"].get("nombre") or "") for g in grupos)
    periodos = ", ".join(sorted({g["grupo"].get("periodo") or "" for g in grupos} - {""}))
    return Documento(ctx["titulo"], (grupos[0]["grupo"].get("codigo") if grupos else "") or "alumno", _cabecera(r, ctx, "Alumno", f'{a["rotulo"]} (grupo {grupos_txt})', periodos),
                     resumen, tablas, _notas(r), True)


# ------------------------------------------------------------------------------------------------------ uso de equipos

def de_uso(r: dict, ctx: dict) -> Documento:
    t = r["totales"]
    equipos = [Columna("equipo", "Equipo"), Columna("tipo", "Tipo"), Columna("plataforma", "Plataforma"), Columna("version", "Versión de la app"), Columna("clases", "Clases", ENTERO),
               Columna("tiempo", "Tiempo en clase (min)", MINUTOS), Columna("alumnos", "Alumnos distintos", ENTERO), Columna("ultimo", "Último uso"), Columna("estado", "Estado")]
    f_equipos = [[e["nombre"], e["tipo"], e["plataforma"], e["version_app"], e["clases"], tx.minutos(e["tiempo_total_ms"]), e["alumnos"],
                  ctx["fecha"](e["ultimo_uso_en"]) if e.get("ultimo_uso_en") else "", "Bloqueado" if e.get("bloqueado") else ("Retirado" if e.get("activo") is False else "En uso")]
                 for e in r["equipos"]]
    clases = [Columna("fecha", "Clase"), Columna("grupo", "Grupo"), Columna("duracion", "Duración (min)", MINUTOS), Columna("participantes", "Participantes", ENTERO),
              Columna("equipos", "Equipos", ENTERO), Columna("incompleta", "Datos incompletos")]
    f_clases = [[ctx["fecha"](c["finalizada_en"]), (c.get("grupo") or {}).get("codigo") or "—", tx.minutos(c["duracion_ms"]), c["participantes"], c["equipos"],
                 tx.si_no(bool(c["incompleta"]))] for c in r["clases"]]
    p = r["periodo"]
    resumen = [("Clases finalizadas", t["clases"], ENTERO), ("Equipos distintos", t["equipos"], ENTERO), ("Tiempo total en clase (min)", tx.minutos(t["tiempo_total_ms"]), MINUTOS),
               ("Duración media de una clase (min)", tx.minutos(t["duracion_media_ms"]), MINUTOS)]
    tablas = [x for x in (Tabla("Equipos", equipos, f_equipos) if f_equipos else None, Tabla("Clases", clases, f_clases) if f_clases else None) if x]
    periodo = f'{ctx["fecha"](p["desde"]) if p.get("desde") else "desde el inicio"} a {ctx["fecha"](p["hasta"]) if p.get("hasta") else "hoy"}'
    return Documento(ctx["titulo"], "equipos", _cabecera(r, ctx, "Ámbito", "Uso de equipos y sesiones", periodo), resumen, tablas, _notas(r), False)


CONSTRUCTORES = {cat.CLASE: de_clase, cat.GRUPO: de_grupo, cat.ALUMNO: de_alumno, cat.USO: de_uso}


def de_reporte(tipo: str, reporte: dict, ctx: dict) -> Documento:
    """El documento de un reporte ya armado. `ctx`: `titulo`, `generado_por`, `generado_el`, `corte_texto`, `version_nodo` y `fecha` (ms → texto)."""
    return CONSTRUCTORES[tipo](reporte, ctx)
