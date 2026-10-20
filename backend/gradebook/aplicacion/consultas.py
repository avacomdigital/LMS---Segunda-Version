"""
Las consultas del libro:

  LibroDelGrupo           el libro de calificaciones de un grupo: alumnos × evaluaciones, con estado de revisión y de publicación
  HistorialDelEstudiante  lo que lleva un alumno: sus calificaciones, agregados por periodo y retroalimentación
  CalificacionesDeAsignacion  intentos, resultados registrados, el que cuenta, estado de revisión y de publicación
  DetalleDeCalificacion   una calificación con todo su historial (versiones y revisiones)
  ResumenDePeriodo        lo que lleva cada alumno en cada curso durante un periodo (promedio simple, NO oficial)
  MisResultados           lo que ve el ALUMNO: nunca una nota sin publicar y, en modo simple, nunca un número

El profesor ve el resultado interno (0–100) y su presentación con la escala del nivel; el alumno sólo ve lo presentado y sólo cuando se publicó.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..dominio import catalogos as cat
from ..dominio import puntaje as pj
from ..dominio import resultado as res
from ..dominio.errores import FueraDeAlcance, NoEncontrado
from ..dominio import curso as cur
from .base import (
    _CasoDeUso,
    bruto_de,
    contexto_de,
    exigir_en_asignacion,
    exigir_sobre_resultado,
    filtro_de_materia,
    materias_de,
    modo_del_nivel,
    presentar_con,
    salida_calificacion,
    salida_version,
    sistema_de,
)
from .derivados import clasificacion_de, clasificacion_efectiva, politica_de_intentos
from .puertos import Actor, UnidadDeTrabajo

SIMBOLO_DE_ESTADO = {cat.NO_INICIADO: "vacio", cat.EN_PROGRESO: "medio", cat.COMPLETADO: "lleno"}
MINIMO_PARA_PROMEDIO = 3                      # CMP-043: con menos de tres alumnos, un promedio de grupo identificaría a una persona


def _escala_a_resumen(version: dict | None) -> dict | None:
    return None if version is None else sistema_de(version)


def _presentacion(c: dict, modo: str, version: dict | None) -> dict | None:
    """La presentación de una calificación para el docente, con la escala del nivel ya resuelta (una sola búsqueda por libro)."""
    if c["estado"] == cat.DEFINITIVA and c.get("presentacion"):
        return {**c["presentacion"], "provisional": False}
    if c["estado"] in (cat.REABIERTA, cat.ANULADA) or modo != cat.CALIFICACIONES or version is None:
        return None
    return {**presentar_con(version, c), "provisional": True}


def _agregado_a_salida(a: dict) -> dict:
    return {"curso_ref": a["curso_ref"], "periodo": a["periodo"], "calificaciones": a["calificaciones"], "promedio_simple": pj.como_numero(a["promedio_simple"]),
            "pendientes": a["pendientes"], "provisionales": a["provisionales"], "publicadas": a["publicadas"], "oficial": False, "ponderado": False}


def _media(puntajes: list) -> float | None:
    """La media simple de unos resultados internos, a dos decimales (informativa: no es una nota oficial ni está ponderada)."""
    if not puntajes:
        return None
    return pj.como_numero(pj.redondear(sum(puntajes) / len(puntajes), 2, cat.MITAD_ARRIBA))


def _contar(cuenta: dict, estado: str, simple: str, presentacion: dict | None, *, con_notas: bool = True) -> None:
    """Suma lo que una celda dice a un conteo (el de un estudiante o el de una evaluación): lo que ya tiene nota, lo que falta publicar, lo que espera revisión,
    lo calificado sin registrar y lo que aún no se hizo. Una celda sin presentación no cuenta como aprobada ni como no aprobada. En un nivel en MODO SIMPLE no hay
    notas que registrar, revisar ni publicar (todo lo completado es «sin registro» por definición): sólo se cuenta lo completado y lo pendiente."""
    if simple == cat.COMPLETADO:
        cuenta["completadas"] += 1
    if not con_notas:
        if estado == cat.PENDIENTE:
            cuenta["pendientes"] += 1
        return
    if estado in (cat.REVISADO, cat.DEFINITIVO):
        cuenta["con_nota"] += 1
        cuenta["publicadas" if estado == cat.DEFINITIVO else "sin_publicar"] += 1
        cumple = ((presentacion or {}).get("aprobacion") or {}).get("cumple_criterio")
        if cumple is True:
            cuenta["aprobadas"] += 1
        elif cumple is False:
            cuenta["no_aprobadas"] += 1
    elif estado in (cat.PROVISIONAL, cat.REABIERTO):
        cuenta["por_revisar"] += 1
    elif estado == cat.SIN_REGISTRO and simple == cat.COMPLETADO:
        cuenta["sin_registro"] += 1
    elif estado == cat.PENDIENTE:
        cuenta["pendientes"] += 1


def _presentado(version: dict | None, modo: str, promedio: float | None) -> dict | None:
    """El promedio simple visto con el sistema de calificación del nivel («3,8 · Básico · cumple»). Sin sistema (modo simple) o sin promedio, nada."""
    if version is None or modo != cat.CALIFICACIONES or promedio is None:
        return None
    p = presentar_con(version, {"puntaje_efectivo": Decimal(str(promedio)), "desempeno_docente": ""})
    return {"etiqueta": p["presentada"]["etiqueta"], "valor": p["presentada"]["valor"], "clave": p["presentada"]["clave"], "desempeno": p["desempeno"]["nivel"],
            "cumple_criterio": p["aprobacion"]["cumple_criterio"]}


def nota_simple_de(intento: dict, asignacion: dict, aciertos: int, total: int) -> dict | None:
    """La nota de un intento en un nivel en MODO SIMPLE: el porcentaje de MOD-010 tal cual (sin escala), con cuándo se publicó. Sin porcentaje (calificación pendiente), nada."""
    porcentaje = intento.get("porcentaje")
    if porcentaje is None:
        return None
    return {"porcentaje": pj.como_numero(pj.redondear(Decimal(str(porcentaje)), 1, cat.MITAD_ARRIBA)), "aciertos": aciertos, "preguntas": total,
            "numero_intento": intento.get("numero"), "publicada_en": asignacion.get("liberados_en")}


def _conteo_vacio() -> dict:
    return {"completadas": 0, "con_nota": 0, "publicadas": 0, "sin_publicar": 0, "por_revisar": 0, "sin_registro": 0, "pendientes": 0, "aprobadas": 0, "no_aprobadas": 0}


class LibroDelGrupo(_CasoDeUso):
    """El libro de un grupo. `completo=False` (la vista de lista del profesor) no manda las celdas alumno × evaluación: sólo el RESUMEN de cada estudiante y de cada
    evaluación, que es lo que una lista de estudiantes o de evaluaciones necesita; con cientos de evaluaciones al año la tabla completa no se puede leer ni descargar."""

    def ejecutar(self, actor: Actor, grupo_id: str, *, asignacion_id: str = "", periodo: str = "", curso_ref: str = "", q: str = "", completo: bool = True,
                 consulta: dict | None = None) -> dict:
        ahora = self.s.reloj.ahora_ms()
        materia = filtro_de_materia(consulta or {})
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir(actor, cat.P_READ, grupo_id=grupo_id)
            grupo = uow.identidad.grupo(grupo_id)
            if grupo is None:
                raise NoEncontrado("No existe ese grupo.", grupo_id=grupo_id)
            modo, version = modo_del_nivel(uow, grupo["nivel_clave"] or "")
            todas = [a for a in uow.evaluacion.asignaciones_de_grupo(grupo_id) if a["estado"] != "borrador"]
            materias = materias_de(uow, todas)             # lo que se ofrece para segmentar: SIEMPRE sobre todo el grupo, no sobre lo ya filtrado
            asignaciones = todas
            if asignacion_id:
                asignaciones = [a for a in asignaciones if a["id"] == asignacion_id]
            if curso_ref:
                asignaciones = [a for a in asignaciones if a["curso_ref"] == curso_ref]
            if materia:
                asignaciones = [a for a in asignaciones if cur.cumple(a["curso_ref"], materia)]
            if periodo and periodo != grupo["periodo"]:
                asignaciones = []                       # una asignación es del periodo de su grupo
            clasificacion = uow.clasificaciones.de([a["id"] for a in asignaciones])
            por_revisar: dict[str, int] = defaultdict(int)
            for intento in uow.evaluacion.intentos_en_revision([a["id"] for a in asignaciones]):
                por_revisar[intento["asignacion_id"]] += 1
            resultados = {(r["asignacion_id"], r["alumno_id"]): r for r in uow.resultados.de_grupo(grupo_id)}
            por_alumno_asignacion: dict[tuple[str, str], list[dict]] = defaultdict(list)
            for c in uow.calificaciones.de_grupo(grupo_id):
                por_alumno_asignacion[(c["asignacion_id"], c["alumno_id"])].append(c)
            agregados: dict[str, list[dict]] = defaultdict(list)
            for g in uow.agregados.de_grupo(grupo_id):
                agregados[g["alumno_id"]].append(g)
            alumnos = list(uow.identidad.alumnos_del_grupo(grupo_id))
            conocidos = {a["id"] for a in alumnos}
            extra = sorted({alumno for (_, alumno) in resultados if alumno not in conocidos})
            if extra:
                rotulos = uow.identidad.rotulos_personas(extra)
                alumnos += [{"id": i, "rotulo": rotulos.get(i, i)} for i in extra]
            filtro = q.strip().lower()
            if filtro:
                alumnos = [a for a in alumnos if filtro in (a["rotulo"] or "").lower()]
            # Modo simple: no hay calificación registrada, la nota es el porcentaje del último intento calificado y se ve cuando MOD-010 libera el resultado.
            notas_simples: dict[tuple[str, str], dict] = {}
            if modo == cat.SIMPLE and completo:
                for a in asignaciones:
                    ultimos: dict[str, dict] = {}
                    for i in uow.evaluacion.intentos_de_asignacion(a["id"]):
                        previo = ultimos.get(i["alumno_id"])
                        if i["estado"] == cat.I_CALIFICADO and (previo is None or (i.get("numero") or 0) > (previo.get("numero") or 0)):
                            ultimos[i["alumno_id"]] = i
                    for alumno_id, i in ultimos.items():
                        aciertos, total = uow.evaluacion.aciertos_de(i)
                        nota = nota_simple_de(i, a, aciertos, total)
                        if nota is not None:
                            notas_simples[(a["id"], alumno_id)] = {**nota, "publicada": uow.evaluacion.resultado_liberado(a, i)}
            filas = []
            sin_publicar = pendientes = 0
            por_evaluacion: dict[str, dict] = defaultdict(_conteo_vacio)
            for alumno in alumnos:
                celdas = {}
                resumen = {"evaluaciones": len(asignaciones), "conteo": _conteo_vacio()}
                puntajes = []
                for a in asignaciones:
                    r = resultados.get((a["id"], alumno["id"]))
                    califs = por_alumno_asignacion.get((a["id"], alumno["id"]), [])
                    aplicable = next((c for c in califs if r and c["id"] == r["calificacion_aplicable_id"]), None)
                    estado = r["estado_calificacion"] if r else cat.PENDIENTE
                    if estado == cat.REVISADO:
                        sin_publicar += 1
                    if estado in (cat.PENDIENTE, cat.PROVISIONAL):
                        pendientes += 1
                    presentacion = _presentacion(aplicable, modo, version) if aplicable else None
                    simple = r["estado_simple"] if r else cat.NO_INICIADO
                    _contar(resumen["conteo"], estado, simple, presentacion, con_notas=modo == cat.CALIFICACIONES)
                    _contar(por_evaluacion[a["id"]], estado, simple, presentacion, con_notas=modo == cat.CALIFICACIONES)
                    if estado in (cat.REVISADO, cat.DEFINITIVO) and aplicable:
                        puntajes.append(aplicable["puntaje_efectivo"])
                    celdas[a["id"]] = {
                        "estado_simple": r["estado_simple"] if r else cat.NO_INICIADO, "estado": estado, "publicada": bool(r and r["publicada"]),
                        "calificacion_id": aplicable["id"] if aplicable else None, "version": aplicable["version"] if aplicable else None,
                        "puntaje_efectivo": pj.como_numero(aplicable["puntaje_efectivo"]) if aplicable else pj.como_numero(r["puntaje_aplicable"]) if r else None,
                        "puntaje_original": pj.como_numero(aplicable["puntaje_original"]) if aplicable else None,
                        "ajustada": bool(aplicable and aplicable["puntaje_efectivo"] != aplicable["puntaje_fuente"]),
                        "presentacion": presentacion, "bruto": bruto_de(aplicable) if aplicable else None,
                        "intentos": {"total": r["intentos_total"] if r else 0, "registrados": r["intentos_registrados"] if r else 0},
                        "politica_intentos": r["politica_intentos"] if r else None, "nota_simple": notas_simples.get((a["id"], alumno["id"]))}
                resumen["promedio_simple"] = _media(puntajes)
                resumen["presentado"] = _presentado(version, modo, resumen["promedio_simple"])
                filas.append({"alumno_id": alumno["id"], "rotulo": alumno["rotulo"], "celdas": celdas if completo else {}, "resumen": resumen,
                              "agregados": [_agregado_a_salida(g) for g in agregados.get(alumno["id"], [])]})
            return {
                "grupo": {"id": grupo["id"], "codigo": grupo["codigo"], "nombre": grupo["nombre"], "periodo": grupo["periodo"], "nivel_clave": grupo["nivel_clave"]},
                "modo": modo, "escala": _escala_a_resumen(version), "politica_intentos": uow.politica.get()["politica_intentos"],
                "materias": materias, "filtro": {"materia": materia or None, "curso_ref": curso_ref or None, "asignacion_id": asignacion_id or None},
                "asignaciones": [{"id": a["id"], "titulo": a["titulo"], "curso_ref": a["curso_ref"], "curso_rotulo": a.get("curso_rotulo") or "", "materia": cur.materia_de(a["curso_ref"]), "estado": a["estado"],
                                  "tipo_evaluacion": clasificacion_de(a, clasificacion.get(a["id"]))["tipo_evaluacion"],
                                  "afecta_oficial": clasificacion_de(a, clasificacion.get(a["id"]))["afecta_oficial"], "resultados": a.get("resultados"),
                                  "liberados_en": a.get("liberados_en"), "liberados_por": a.get("liberados_por") or "",
                                  "por_revisar": por_revisar.get(a["id"], 0), "conteo": por_evaluacion.get(a["id"]) or _conteo_vacio()} for a in asignaciones],
                "alumnos": filas, "totales": {"alumnos": len(filas), "asignaciones": len(asignaciones), "pendientes": pendientes, "por_revisar": sum(por_revisar.values()),
                                              "sin_publicar": sin_publicar}, "servidor_en": ahora}


class HistorialDelEstudiante(_CasoDeUso):
    def ejecutar(self, actor: Actor, alumno_id: str, *, grupo_id: str = "") -> dict:
        with self.s.uow(lectura=True) as uow:
            visibles = self.s.autorizacion.grupos_visibles(actor, cat.P_READ)
            grupos = uow.identidad.grupos_del_alumno(alumno_id)
            if grupo_id:
                self.s.autorizacion.exigir(actor, cat.P_READ, grupo_id=grupo_id)
                if grupo_id not in grupos and not uow.calificaciones.de_alumno(alumno_id, grupo_id):
                    raise NoEncontrado("Ese alumno no está en ese grupo ni tiene calificaciones en él.", alumno_id=alumno_id, grupo_id=grupo_id)     # el rótulo de cualquier persona no se da
                grupos = [grupo_id]
            elif visibles is not None:
                grupos = [g for g in grupos if g in visibles]
            else:
                self.s.autorizacion.exigir(actor, cat.P_READ)
            if not grupos:
                raise FueraDeAlcance("Ese alumno no está en ninguno de tus grupos.", alumno_id=alumno_id)
            rotulo = uow.identidad.rotulos_personas([alumno_id]).get(alumno_id, alumno_id)
            salida_grupos = []
            for g in grupos:
                grupo = uow.identidad.grupo(g) or {"id": g, "codigo": "", "nombre": "", "periodo": "", "nivel_clave": ""}
                modo, version = modo_del_nivel(uow, grupo["nivel_clave"] or "")
                califs = [c for c in uow.calificaciones.de_alumno(alumno_id, g)]
                resultados = uow.resultados.de_alumno(alumno_id, g)
                intentos_por_c = {c["id"]: uow.evaluacion.intento(c["intento_id"]) for c in califs}
                salida_grupos.append({
                    "grupo": {"id": g, "codigo": grupo["codigo"], "nombre": grupo["nombre"], "periodo": grupo["periodo"], "nivel_clave": grupo["nivel_clave"]},
                    "modo": modo, "escala": _escala_a_resumen(version),
                    "calificaciones": [{**salida_calificacion(uow, c, intento=intentos_por_c[c["id"]])} for c in califs],
                    "resultados": [{"asignacion_id": r["asignacion_id"], "estado_simple": r["estado_simple"], "estado": r["estado_calificacion"], "publicada": r["publicada"],
                                    "puntaje_aplicable": pj.como_numero(r["puntaje_aplicable"]), "curso_ref": r["curso_ref"]} for r in resultados],
                    "agregados": [_agregado_a_salida(a) for a in uow.agregados.de_alumno(alumno_id) if a["grupo_id"] == g]})
            return {"alumno_id": alumno_id, "rotulo": rotulo, "grupos": salida_grupos, "servidor_en": self.s.reloj.ahora_ms()}


class CalificacionesDeAsignacion(_CasoDeUso):
    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            asignacion = uow.evaluacion.asignacion(asignacion_id)
            if asignacion is None:
                raise NoEncontrado("No existe esa asignación.", asignacion_id=asignacion_id)
            exigir_en_asignacion(uow, self.s.autorizacion, actor, cat.P_READ, asignacion)
            intentos: dict[str, list[dict]] = defaultdict(list)
            for i in uow.evaluacion.intentos_de_asignacion(asignacion_id):
                intentos[i["alumno_id"]].append(i)
            califs: dict[str, list[dict]] = defaultdict(list)
            for c in uow.calificaciones.de_asignacion(asignacion_id):
                califs[c["alumno_id"]].append(c)
            resultados = {r["alumno_id"]: r for r in uow.resultados.de_asignacion(asignacion_id)}
            alumnos = sorted(set(intentos) | set(califs))
            if not asignacion.get("grupo_id"):
                # A alumnos sueltos: quien enseña a unos de ellos no ve a los demás (sólo el que la asignó, o quien ve toda la organización, los ve a todos).
                visibles = self.s.autorizacion.grupos_visibles(actor, cat.P_READ)
                if visibles is not None and not (actor.autenticado and actor.id and actor.id == asignacion.get("profesor_id")):
                    permitidos = set(visibles)
                    alumnos = [a for a in alumnos if permitidos & set(uow.identidad.grupos_del_alumno(a))]
            rotulos = uow.identidad.rotulos_personas(alumnos)
            filas = []
            for alumno in alumnos:
                r = resultados.get(alumno)
                por_intento = {c["intento_id"]: c for c in califs.get(alumno, [])}
                filas.append({
                    "alumno_id": alumno, "rotulo": rotulos.get(alumno) or (intentos[alumno][0].get("alumno_rotulo") if intentos.get(alumno) else alumno),
                    "intentos": [{"id": i["id"], "numero": i["numero"], "estado": i["estado"], "porcentaje": i.get("porcentaje"), "calificado_por": i.get("calificado_por"),
                                  "entregado_en": i.get("entregado_en"), "requiere_revision": i.get("requiere_revision"), "calificacion_pendiente": i.get("calificacion_pendiente"),
                                  "calificacion": salida_calificacion(uow, por_intento[i["id"]], intento=i) if i["id"] in por_intento else None} for i in intentos.get(alumno, [])],
                    "resultado": None if r is None else {"estado_simple": r["estado_simple"], "estado": r["estado_calificacion"], "publicada": r["publicada"],
                                                         "calificacion_aplicable_id": r["calificacion_aplicable_id"] or None, "puntaje_aplicable": pj.como_numero(r["puntaje_aplicable"]),
                                                         "politica_intentos": r["politica_intentos"], "intentos_total": r["intentos_total"],
                                                         "intentos_registrados": r["intentos_registrados"]}})
            return {"asignacion": {"id": asignacion["id"], "titulo": asignacion["titulo"], "curso_ref": asignacion["curso_ref"], "estado": asignacion["estado"],
                                   "grupo_id": asignacion.get("grupo_id") or "", "intentos_permitidos": asignacion.get("intentos_permitidos"),
                                   "resultados": asignacion.get("resultados")},
                    "clasificacion": clasificacion_efectiva(uow, asignacion), "politica_intentos": politica_de_intentos(uow, asignacion), "alumnos": filas, "servidor_en": ahora}


class DetalleDeCalificacion(_CasoDeUso):
    def ejecutar(self, actor: Actor, calificacion_id: str) -> dict:
        with self.s.uow(lectura=True) as uow:
            c = uow.calificaciones.por_id(calificacion_id) if calificacion_id else None
            if c is None:
                raise NoEncontrado("No existe esa calificación.", calificacion_id=calificacion_id)
            exigir_sobre_resultado(uow, self.s.autorizacion, actor, cat.P_READ, grupo_id=c["grupo_id"], asignacion_id=c["asignacion_id"])
            intento = uow.evaluacion.intento(c["intento_id"])
            salida = salida_calificacion(uow, c, intento=intento)
            version_id = ((salida["presentacion"] or {}).get("escala") or {}).get("version_id")      # la versión con que se presentó (la estampada, si ya se publicó)
            version = uow.escalas.version(version_id) if version_id else None
            return {"calificacion": salida, "sistema": None if version is None else sistema_de(version),
                    "historial": [salida_version(v) for v in uow.versiones.de(c["id"])],
                    "revisiones": [{"pregunta_ref": r["pregunta_ref"], "numero": r["numero"], "tipo": r["tipo"], "forma": r["forma"], "puntaje": pj.como_numero(r["puntaje"]),
                                    "puntaje_maximo": pj.como_numero(r["puntaje_maximo"]), "criterios": r["criterios"], "comentario": r["comentario"],
                                    "revisor_id": r["revisor_id"], "revisada_en": r["revisada_en"]} for r in uow.revisiones.de_intento(c["intento_id"])],
                    "intento": None if intento is None else {"id": intento["id"], "numero": intento["numero"], "estado": intento["estado"], "porcentaje": intento.get("porcentaje"),
                                                            "calificado_por": intento.get("calificado_por"), "entregado_en": intento.get("entregado_en")},
                    "servidor_en": self.s.reloj.ahora_ms()}


class ResumenDePeriodo(_CasoDeUso):
    """Lo que lleva cada alumno en cada curso durante un periodo. El promedio es SIMPLE e INFORMATIVO: media de los resultados registrados de las
    evaluaciones que afectan la calificación oficial, sin ponderación (ninguna institución la ha declarado: V1). Nunca se presenta como una calificación
    oficial, y un promedio de grupo con menos de tres alumnos no se calcula."""

    def ejecutar(self, actor: Actor, grupo_id: str, *, periodo: str = "", curso_ref: str = "") -> dict:
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir(actor, cat.P_READ, grupo_id=grupo_id)
            grupo = uow.identidad.grupo(grupo_id)
            if grupo is None:
                raise NoEncontrado("No existe ese grupo.", grupo_id=grupo_id)
            filas = [a for a in uow.agregados.de_grupo(grupo_id, periodo or None) if not curso_ref or a["curso_ref"] == curso_ref]
            rotulos = uow.identidad.rotulos_personas(sorted({a["alumno_id"] for a in filas}))
            titulos = {a["curso_ref"]: a.get("curso_rotulo") or "" for a in uow.evaluacion.asignaciones_de_grupo(grupo_id)}
            cursos: dict[str, list[dict]] = defaultdict(list)
            for a in filas:
                cursos[a["curso_ref"]].append(a)
            salida = []
            for curso, lista in sorted(cursos.items()):
                promedios = [a["promedio_simple"] for a in lista if a["promedio_simple"] is not None]
                suficientes = len(promedios) >= MINIMO_PARA_PROMEDIO
                salida.append({
                    "curso_ref": curso, "curso_rotulo": titulos.get(curso, ""),
                    "alumnos": [{"alumno_id": a["alumno_id"], "rotulo": rotulos.get(a["alumno_id"], a["alumno_id"]), "periodo": a["periodo"], "calificaciones": a["calificaciones"],
                                 "promedio_simple": pj.como_numero(a["promedio_simple"]), "pendientes": a["pendientes"], "provisionales": a["provisionales"],
                                 "publicadas": a["publicadas"]} for a in sorted(lista, key=lambda x: rotulos.get(x["alumno_id"], ""))],
                    "promedio_del_grupo": pj.como_numero(pj.promedio(promedios)) if suficientes else None, "datos_suficientes": suficientes})
            return {"grupo": {"id": grupo["id"], "codigo": grupo["codigo"], "nombre": grupo["nombre"], "periodo": grupo["periodo"], "nivel_clave": grupo["nivel_clave"]},
                    "cursos": salida, "oficial": False, "ponderado": False,
                    "aviso": "Promedio simple informativo de lo ya registrado. No es una calificación oficial: la ponderación institucional y el cierre del periodo son de V1.",
                    "servidor_en": self.s.reloj.ahora_ms()}


# ================================================================================================ el alumno

def estado_de_entrega(intentos: list[dict], calificaciones: list[dict]) -> str:
    """Lo que el alumno puede saber de una evaluación cuya nota NO está publicada: sólo en qué va su entrega. Nunca una cifra."""
    if any(c["estado"] in (cat.REVISADA, cat.REABIERTA) for c in calificaciones):
        return "en_revision" if any(c["estado"] == cat.REABIERTA for c in calificaciones) else "resultado_no_publicado"
    estados = [i["estado"] for i in intentos if i["estado"] != cat.I_ANULADO]
    if cat.I_EN_REVISION in estados:
        return "en_revision"
    if cat.I_CALIFICADO in estados:
        return "resultado_no_publicado"
    if cat.I_ENTREGADO in estados:
        return "entregado"
    if any(e in cat.I_VIVOS for e in estados):
        return "en_progreso"
    return "no_iniciado"


class MisResultados(_CasoDeUso):
    """Lo que ve el ALUMNO. Reglas, comprobadas en el nodo y no sólo en la pantalla:
      · una nota sin publicar nunca sale; antes de publicar sólo se ve el estado de la entrega
      · en modo simple no hay notas ni letras ni números: un estado y símbolos
      · el resultado interno (0–100) no se muestra: se muestra lo presentado con la escala de su nivel, con la versión con que se publicó"""

    def ejecutar(self, actor: Actor) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir_alumno(actor)
            items = []
            sistemas: dict[str, dict | None] = {}                 # una lectura por versión de escala, no una por evaluación
            for a in uow.evaluacion.asignaciones_del_alumno(actor.id):
                items.append(self._item(uow, a, actor.id, sistemas))
            return {"alumno_id": actor.id, "items": items, "servidor_en": ahora}

    @staticmethod
    def _sistema(uow: UnidadDeTrabajo, presentacion: dict, sistemas: dict[str, dict | None]) -> dict:
        """El sistema de calificación con que se presentó la nota: su nombre, país, rango y desde dónde se aprueba. Se lee la versión con que se PUBLICÓ (no la
        vigente hoy), así que lo que el alumno lee es lo que significó su nota. Si esa versión ya no se puede leer, quedan al menos el nombre y el tipo."""
        publicada = presentacion.get("escala") or {}
        version_id = publicada.get("version_id")
        if version_id and version_id not in sistemas:
            version = uow.escalas.version(version_id)
            sistemas[version_id] = None if version is None else sistema_de(version)
        return (sistemas.get(version_id) if version_id else None) or {"nombre": publicada.get("nombre"), "tipo": publicada.get("tipo")}

    @staticmethod
    def _item(uow: UnidadDeTrabajo, a: dict, alumno_id: str, sistemas: dict[str, dict | None] | None = None) -> dict:
        intentos = uow.evaluacion.intentos_del_alumno(a["id"], alumno_id)
        contexto = contexto_de(uow, a, alumno_id)
        modo, _ = modo_del_nivel(uow, contexto["nivel_clave"])
        simple = res.estado_simple(intentos)
        base = {"asignacion_id": a["id"], "titulo": a["titulo"], "curso_rotulo": a.get("curso_rotulo") or "", "estado_simple": simple,
                "simbolo": SIMBOLO_DE_ESTADO[simple], "modo": modo}
        califs = uow.calificaciones.de_asignacion(a["id"], alumno_id)
        if modo == cat.SIMPLE:
            return {**base, **MisResultados._aciertos_simples(uow, a, intentos)}
        # Al alumno se le muestra EXACTAMENTE lo que cuenta en el libro: el intento que la política elige entre todos los que cuentan. Si ése aún no se publicó,
        # no se le enseña otro (una nota vieja publicada no es la que cuenta) y se le dice que el profesor aún no publica el resultado.
        vigentes = [c for c in califs if c["estado"] in cat.CUENTAN]
        aplicable_id, promedio = res.seleccionar_aplicable(politica_de_intentos(uow, a), vigentes)
        elegida = next((c for c in vigentes if c["id"] == aplicable_id and c["estado"] == cat.DEFINITIVA), None) if aplicable_id else None
        presentacion = (elegida or {}).get("presentacion") or {}
        numero_intento = elegida["numero_intento"] if elegida else None
        retro = (elegida or {}).get("retroalimentacion") or None
        publicada_en = elegida["publicada_en"] if elegida else None
        if aplicable_id is None and promedio is not None and all(c["estado"] == cat.DEFINITIVA for c in vigentes):
            # Con la política «promedio» lo que cuenta es la media de todos los intentos, y sólo se enseña cuando todos están publicados. Se presenta con la
            # versión de escala con que se publicó el más reciente (las versiones no cambian: el resultado se puede reproducir).
            ultima = max(vigentes, key=lambda c: (c["publicada_en"] or 0, c["id"]))
            version = uow.escalas.version(ultima["escala_version_id"]) if ultima.get("escala_version_id") else None
            if version is not None:
                presentacion = presentar_con(version, {**ultima, "puntaje_efectivo": promedio, "desempeno_docente": ""})
                publicada_en = ultima["publicada_en"]
                elegida = ultima
        if elegida is None or not presentacion:
            return {**base, "estado": estado_de_entrega(intentos, califs), "calificacion": None}
        # Con la nota publicada el alumno ve también lo BRUTO (los puntos que obtuvo sobre el máximo y el porcentaje), que es lo que MOD-010 le muestra de todos modos
        # cuando libera el resultado: la nota se lee con los tres (puntos · porcentaje · sistema). Con la política «promedio» los puntos son los del promedio: no hay.
        bruto = bruto_de(elegida) if aplicable_id is not None else {"puntos": None, "puntos_maximos": None, "aciertos": None, "preguntas": None, "porcentaje": pj.como_numero(promedio)}
        return {**base, "estado": "publicado", "calificacion": {
            "presentada": presentacion.get("presentada"), "desempeno": presentacion.get("desempeno"), "aprobacion": presentacion.get("aprobacion"),
            "escala": MisResultados._sistema(uow, presentacion, {} if sistemas is None else sistemas), "bruto": bruto,
            "retroalimentacion": retro, "publicada_en": publicada_en, "numero_intento": numero_intento}}

    @staticmethod
    def _aciertos_simples(uow: UnidadDeTrabajo, a: dict, intentos: list[dict]) -> dict:
        """En modo simple los aciertos se muestran como símbolos, y sólo si MOD-010 ya liberó ese resultado al alumno (la política de publicación de la
        evaluación manda). Nada de números."""
        entregados = [i for i in intentos if i["estado"] == cat.I_CALIFICADO]
        if not entregados:
            return {"aciertos": None, "retroalimentacion": None, "nota": None}
        ultimo = max(entregados, key=lambda i: i.get("numero", 0))
        if not uow.evaluacion.resultado_liberado(a, ultimo):
            return {"aciertos": None, "retroalimentacion": None, "nota": None}
        aciertos, total = uow.evaluacion.aciertos_de(ultimo)
        return {"aciertos": {"simbolos": ["acierto"] * aciertos + ["fallo"] * max(0, total - aciertos)}, "retroalimentacion": None,
                "nota": nota_simple_de(ultimo, a, aciertos, total)}
