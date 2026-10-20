"""
Los reportes (sólo lectura sobre lo que ya calcularon los otros módulos):

  ReporteDeClase    CAP-081  participación y aciertos de cada alumno en una clase TERMINADA, con el promedio de la clase (TST-008)
  ReporteDeGrupo    FUN-139  quién necesita atención primero, con su motivo en una línea; las clases, las evaluaciones y el estudio del grupo
  ReporteDeAlumno   CAP-082  el informe nominal de un alumno (FUN-140): clases, evaluaciones con su calificación YA presentada por el libro, estudio
  ReporteDeUso      FUN-142  qué equipos se usaron y cuánto, sin datos de personas; sólo si hay clases finalizadas en el periodo
  ListaDeClases · Filtros · Alumnos · Recientes   lo que las pantallas de OPS necesitan para llegar a un reporte sin escribir

Todos llevan lo mismo (BR-083, BR-086, art. 14): el bloque `corte` (instante de corte, antigüedad, estado de integración de los equipos), el bloque `privacidad`, `nominal`
y `objetivos` (aún no disponible: MOD-012 no existe). Cada uno tiene `armar` (calcula, sin efectos) y `ejecutar` (armar + dejar el rastro: reciente, evento y asiento de un reporte
nominal). Un fallo al dejar el rastro NO impide ver el reporte.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time

from ..dominio import archivo as arch
from ..dominio import avance as av
from ..dominio import boletin as bol
from ..dominio import catalogos as cat
from ..dominio import clase as clase_dom
from ..dominio import integracion
from ..dominio import privacidad as priv
from ..dominio import texto as tx
from ..dominio.errores import AlumnoSinGrupo, ClaseEnCurso, DatosInvalidos, FueraDeAlcance, NoEncontrado, SinPermiso, SinSesionesFinalizadas
from ..dominio.metricas import como_numero, promedio
from .base import NODO_PARAMETROS, _CasoDeUso, bloque_de_corte, estado_y_corte, exigir_en_clase, exigir_nodo_instalado, filtro_de_nodo, grupo_resumido, parametros_de_nodo
from .consumidor import ConsumirEventos, RecalcularGrupos
from .proyectar import Proyector, senales_de_estudio
from .puertos import Actor, UnidadDeTrabajo

log = logging.getLogger("avacom.reporting.reportes")

OBJETIVOS = {"disponible": False, "texto": "Aún no disponible: el dominio por objetivo llega con el módulo de objetivos."}


class _Lector(_CasoDeUso):
    """Lo común de los reportes: ponerse al día, el bloque de cabecera, los nombres y dejar el rastro."""

    def _al_dia(self) -> None:
        """Antes de responder, los reportes se ponen al día con lo que los módulos ya publicaron (el hilo del nodo puede ir unos segundos detrás). Un fallo aquí no impide leer lo
        que ya hay: el reporte lo dirá con su antigüedad."""
        if not self.s.config.sincronizar_al_consultar:
            return
        try:
            ConsumirEventos(self.s).hasta_vaciar(paginas=5)
        except Exception:   # noqa: BLE001
            log.exception("Reportes no pudo ponerse al día con los módulos antes de responder")

    def _grupos_al_dia(self, grupo_ids: list[str]) -> None:
        """Un grupo desactualizado (o que nunca se calculó) se recalcula en el momento en que alguien lo pide: el reporte nunca enseña un avance viejo sin decirlo."""
        with self.s.uow(lectura=True) as uow:
            pendientes = [g for g in grupo_ids if (f := uow.avances.grupo(g)) is None or f["desactualizado"]]
        if pendientes:
            RecalcularGrupos(self.s).ejecutar(pendientes)

    # ------------------------------------------------------------------------------------------------------------------ piezas
    def _cabecera(self, uow: UnidadDeTrabajo, actor: Actor, tipo: str, ahora: int, *, senales: list[dict], equipos: int, alumnos: int, nominal: bool,
                  umbral_activo: bool, avisos: list[dict]) -> dict:
        estado, corte_en = estado_y_corte(uow, ahora)
        rotulo = uow.identidad.rotulos_personas([actor.id]).get(actor.id) if actor.id else None
        return {
            "tipo": tipo, "titulo": f"Reporte {cat.NOMBRE_DE_TIPO[tipo]}", "generado_en": ahora, "generado_por": {"id": actor.id, "rotulo": rotulo or actor.rotulo or actor.id},
            "corte": bloque_de_corte(self.s, ahora, estado, corte_en, senales, equipos), "privacidad": priv.bloque(alumnos, umbral_activo), "nominal": nominal, "objetivos": OBJETIVOS,
            "avisos": [a for a in avisos if a and a.get("texto")], "servidor_en": ahora}

    @staticmethod
    def _nombres(uow: UnidadDeTrabajo, ids: list[str]) -> dict[str, str]:
        return uow.identidad.rotulos_personas(sorted(set(ids)))

    def _dejar_rastro(self, actor: Actor, tipo: str, parametros: dict, reporte: dict, *, grupo_id: str = "") -> None:
        """La reciente, el evento `reporte.*_generado.v1` y —sólo si el reporte es nominal— el asiento de la bitácora. Todo en UNA transacción corta y al final: un fallo se anota y
        el reporte se entrega igual."""
        try:
            ahora = self.s.reloj.ahora_ms()
            filas = len(reporte.get("filas") or reporte.get("alumnos") or reporte.get("grupos") or reporte.get("equipos") or reporte.get("boletines") or
                        (reporte.get("boletin") or {}).get("evaluaciones") or [])
            with self.s.uow() as uow:
                if actor.id:
                    uow.recientes.registrar(actor.id, tipo, parametros, ahora)
                evento = cat.EVENTO_DE_TIPO.get(tipo)
                if evento:
                    self._publicar(uow, "Reporte", tipo, evento, {"tipo": tipo, "grupo_id": grupo_id, "filas": filas, "nominal": bool(reporte["nominal"]),
                                                                  "corte_en": reporte["corte"]["en"], "incompleto": reporte["corte"]["incompleto"], "por": actor.id}, ahora)
                if reporte["nominal"]:
                    uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_GENERADO, "m13_reporte", "", nuevo={
                        "reporte": tipo, "alcance": parametros, "filas": filas, "corte_en": reporte["corte"]["en"], "rol": actor.rol or None})
        except Exception:   # noqa: BLE001
            log.exception("Reportes no pudo dejar el rastro de un reporte %s", tipo)

    def _ms(self, valor, campo: str, *, fin_de_dia: bool = False) -> int | None:
        """Un instante en milisegundos: un entero, un texto numérico o una fecha `AAAA-MM-DD` (a medianoche de la zona del nodo; con `fin_de_dia`, al final de ese día)."""
        if valor in (None, ""):
            return None
        if isinstance(valor, bool):
            raise DatosInvalidos(f"`{campo}` debe ser un instante en milisegundos o una fecha AAAA-MM-DD.", campo=campo)
        if isinstance(valor, int) or (isinstance(valor, str) and valor.strip().lstrip("-").isdigit()):
            return int(valor)
        try:
            dia = date.fromisoformat(str(valor).strip())
        except ValueError:
            raise DatosInvalidos(f"`{campo}` debe ser un instante en milisegundos o una fecha AAAA-MM-DD.", campo=campo, valor=str(valor)[:20])
        zona = self.s.reloj.a_local(0).tzinfo
        inicio = datetime.combine(dia, time.min, tzinfo=zona)
        return int(inicio.timestamp() * 1000) + (86_400_000 - 1 if fin_de_dia else 0)


# =================================================================================================================== una clase (CAP-081)

class ReporteDeClase(_Lector):
    def ejecutar(self, actor: Actor, sesion_id: str, consulta: dict | None = None) -> dict:
        self._al_dia()
        reporte = self.armar(actor, sesion_id)
        self._dejar_rastro(actor, cat.CLASE, {"sesion_id": sesion_id}, reporte, grupo_id=reporte["clase"]["grupo"]["id"] if reporte["clase"]["grupo"] else "")
        return reporte

    def armar(self, actor: Actor, sesion_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            sesion = uow.aula.sesion(sesion_id) if sesion_id else None
            if sesion is None:
                raise NoEncontrado("No existe esa clase.", sesion_id=sesion_id)
            exigir_en_clase(self.s.autorizacion, actor, cat.P_VIEW, {"grupo_id": sesion["grupo_id"], "profesor_id": sesion["profesor_id"]})
            if sesion["estado"] not in cat.SESIONES_TERMINADAS:
                raise ClaseEnCurso("Esta clase aún no termina: su reporte se arma cuando la cierres.", sesion_id=sesion_id)
            existe = uow.clases.get(sesion_id) is not None
        if not existe:                                         # terminó pero su reporte aún no se calculó (la cola va por detrás): se calcula ahora
            with self.s.uow() as uow:
                Proyector(self.s).clase(uow, sesion_id, ahora)
        with self.s.uow(lectura=True) as uow:
            clase = uow.clases.get(sesion_id)
            if clase is None:
                raise NoEncontrado("No se pudo armar el reporte de esa clase.", sesion_id=sesion_id)
            config = uow.config.get()
            filas = uow.clases.alumnos(sesion_id)
            aplicada = priv.aplica(clase["participantes"], config["umbral_privacidad"])
            grupo = grupo_resumido(uow.identidad.grupo(clase["grupo_id"]), clase["grupo_id"]) if clase["grupo_id"] else None
            nombres = {} if aplicada else self._nombres(uow, [f["alumno_id"] for f in filas])
            base = self._cabecera(uow, actor, cat.CLASE, ahora, senales=clase["senales"], equipos=clase["equipos"], alumnos=clase["participantes"],
                                  nominal=not aplicada and bool(filas), umbral_activo=config["umbral_privacidad"], avisos=[])
            return {
                **base,
                "clase": {"sesion_id": sesion_id, "grupo": grupo, "curso_rotulo": sesion["curso_rotulo"] or "", "leccion_rotulo": sesion["leccion_rotulo"] or "",
                          "iniciada_en": clase["iniciada_en"], "finalizada_en": clase["finalizada_en"], "duracion_ms": clase["duracion_ms"], "participantes": clase["participantes"],
                          "actividades": clase["actividades"], "equipos": clase["equipos"]},
                "filas": [] if aplicada else [{**clase_dom.fila_para_pantalla(f), "alumno": nombres.get(f["alumno_id"], f["alumno_id"])}
                                              for f in sorted(filas, key=lambda x: (tx.clave_de_orden(nombres.get(x["alumno_id"], "")), x["alumno_id"]))],
                "totales": {"participantes": clase["participantes"], "actividades": clase["actividades"], "promedio_participacion": como_numero(clase["promedio_participacion"]),
                            "promedio_aciertos": como_numero(clase["promedio_aciertos"])}}


# =================================================================================================================== un grupo (FUN-139)

class ReporteDeGrupo(_Lector):
    def ejecutar(self, actor: Actor, grupo_id: str, consulta: dict | None = None) -> dict:
        self._al_dia()
        reporte = self.armar(actor, grupo_id, consulta or {})
        self._dejar_rastro(actor, cat.GRUPO, {"grupo_id": grupo_id, **self._parametros_de_nodo(consulta or {})}, reporte, grupo_id=grupo_id)
        return reporte

    @staticmethod
    def _parametros_de_nodo(consulta: dict) -> dict:
        return parametros_de_nodo(consulta)

    def armar(self, actor: Actor, grupo_id: str, consulta: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            exigir_nodo_instalado(uow)
            grupo = uow.identidad.grupo(grupo_id) if grupo_id else None
            if grupo is None:
                raise NoEncontrado("No existe ese grupo.", grupo_id=grupo_id)
            self.s.autorizacion.exigir(actor, cat.P_GROUP, grupo_id=grupo_id)
        self._grupos_al_dia([grupo_id])
        with self.s.uow(lectura=True) as uow:
            config = uow.config.get()
            avance = uow.avances.grupo(grupo_id) or {}
            alumnos_rows = uow.avances.alumnos(grupo_id)
            clases = uow.clases.de_grupo(grupo_id)
            cursos, aviso = filtro_de_nodo(uow, consulta)
            aplicada = priv.aplica(len(alumnos_rows), config["umbral_privacidad"])
            nombres = {} if aplicada else self._nombres(uow, [r["alumno_id"] for r in alumnos_rows])
            resumenes = {r["alumno_id"]: av.resumir(r["detalle"], cursos) for r in alumnos_rows}
            filas = []
            for r in alumnos_rows:
                s = resumenes[r["alumno_id"]]
                filas.append({"alumno_id": r["alumno_id"], "alumno": nombres.get(r["alumno_id"], ""), "clases_asistidas": s["clases_asistidas"], "clases_total": s["clases_total"],
                              "porcentaje_participacion": como_numero(s["porcentaje_participacion"]), "porcentaje_aciertos": como_numero(s["porcentaje_aciertos"]),
                              "evaluaciones_presentadas": s["evaluaciones_presentadas"], "evaluaciones_total": s["evaluaciones_total"],
                              "evaluaciones_sin_presentar": s["evaluaciones_sin_presentar"], "estudios_completados": s["estudios_completados"], "estudios_total": s["estudios_total"],
                              "atencion": s["atencion"], "motivo": av.motivo_de_atencion(s)})
            filas = av.ordenar_por_atencion(filas)
            clases_visibles = [c for c in clases if cursos is None or c["curso_ref"] in cursos]
            rotulos = _Rotulos(uow)
            evaluaciones = self._evaluaciones(uow, alumnos_rows, cursos)
            promedio_part = promedio(s["porcentaje_participacion"] for s in resumenes.values())
            promedio_aci = promedio(s["porcentaje_aciertos"] for s in resumenes.values())
            en_atencion = sum(1 for s in resumenes.values() if s["atencion"])
            senales = integracion.unir([s for c in clases for s in c["senales"]], senales_de_estudio(uow, [r["alumno_id"] for r in alumnos_rows]))
            filas_de_clases = uow.clases.alumnos_de_clases([c["sesion_id"] for c in clases])
            dispositivos = {f["dispositivo_id"] or f"persona:{f['alumno_id']}" for por_alumno in filas_de_clases.values() for f in por_alumno.values()}
            equipos = len(dispositivos | {s["equipo"] for s in senales})
            estudios = {e["asignacion_id"] for r in alumnos_rows for e in r["detalle"].get("estudios", []) if cursos is None or e["curso_ref"] in cursos}
            base = self._cabecera(uow, actor, cat.GRUPO, ahora, senales=senales, equipos=equipos, alumnos=len(alumnos_rows), nominal=not aplicada and bool(alumnos_rows),
                                  umbral_activo=config["umbral_privacidad"], avisos=[aviso] if aviso else [])
            return {
                **base, "grupo": grupo_resumido(grupo), "modo": avance.get("modo") or "simple", "escala": avance.get("escala"),
                "totales": {"alumnos": len(alumnos_rows), "clases": len(clases_visibles), "evaluaciones": len(evaluaciones), "estudios": len(estudios),
                            "en_atencion": 0 if aplicada else en_atencion, "promedio_participacion": como_numero(promedio_part), "promedio_aciertos": como_numero(promedio_aci)},
                "atencion": [] if aplicada else [f for f in filas if f["atencion"]], "alumnos": [] if aplicada else filas,
                "clases": [{"sesion_id": c["sesion_id"], "iniciada_en": c["iniciada_en"], "finalizada_en": c["finalizada_en"], "participantes": c["participantes"],
                            "curso_rotulo": rotulos.de(c["sesion_id"], "curso_rotulo"), "leccion_rotulo": rotulos.de(c["sesion_id"], "leccion_rotulo"),
                            "promedio_participacion": como_numero(c["promedio_participacion"]), "promedio_aciertos": como_numero(c["promedio_aciertos"]),
                            "incompleta": bool(integracion.vigentes(c["senales"], ahora))} for c in reversed(clases_visibles)],
                "evaluaciones": evaluaciones}

    @staticmethod
    def _evaluaciones(uow: UnidadDeTrabajo, alumnos_rows: list[dict], cursos: set[str] | None) -> list[dict]:
        """Por cada evaluación del grupo, cuántos presentaron, cuántos faltan, cuántas esperan revisión y cuántas ya tienen su calificación publicada (conteos: sin promedio)."""
        por_asignacion: dict[str, dict] = {}
        for r in alumnos_rows:
            for e in r["detalle"].get("evaluaciones", []):
                if cursos is not None and e["curso_ref"] not in cursos:
                    continue
                c = por_asignacion.setdefault(e["asignacion_id"], {"asignacion_id": e["asignacion_id"], "presentaron": 0, "pendientes": 0, "por_revisar": 0, "publicadas": 0, "alumnos": 0})
                c["alumnos"] += 1
                c["presentaron"] += 1 if e["presento"] else 0
                c["pendientes"] += 1 if e["sin_presentar"] else 0
                c["por_revisar"] += 1 if e["estado_intento"] == "en_revision" else 0
                c["publicadas"] += 1 if e["publicada"] else 0
        salida = []
        for asignacion_id, c in por_asignacion.items():
            a = uow.evaluacion.asignacion(asignacion_id) or {}
            salida.append({**c, "titulo": a.get("titulo") or "", "estado": a.get("estado") or "", "curso_rotulo": a.get("curso_rotulo") or ""})
        return sorted(salida, key=lambda x: (tx.clave_de_orden(x["titulo"]), x["asignacion_id"]))


# =================================================================================================================== un alumno (CAP-082, FUN-140)

class ReporteDeAlumno(_Lector):
    def ejecutar(self, actor: Actor, alumno_id: str, consulta: dict | None = None) -> dict:
        self._al_dia()
        consulta = consulta or {}
        reporte = self.armar(actor, alumno_id, consulta)
        parametros = {"alumno_id": alumno_id, **({"grupo_id": consulta["grupo_id"]} if consulta.get("grupo_id") else {}), **ReporteDeGrupo._parametros_de_nodo(consulta)}
        self._dejar_rastro(actor, cat.ALUMNO, parametros, reporte, grupo_id=reporte["grupos"][0]["grupo"]["id"] if reporte["grupos"] else "")
        return reporte

    def armar(self, actor: Actor, alumno_id: str, consulta: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        pedido = str(consulta.get("grupo_id") or "")
        with self.s.uow(lectura=True) as uow:
            exigir_nodo_instalado(uow)
            propios = uow.identidad.grupos_del_alumno(alumno_id) if alumno_id else []
            if pedido:
                self.s.autorizacion.exigir(actor, cat.P_STUDENT, grupo_id=pedido)
                if pedido not in propios:
                    raise NoEncontrado("Ese alumno no está en ese grupo.", alumno_id=alumno_id, grupo_id=pedido)    # el rótulo de cualquier persona no se da
                grupos = [pedido]
            else:
                self.s.autorizacion.exigir(actor, cat.P_STUDENT)
                if not propios:
                    raise AlumnoSinGrupo("Ese alumno no pertenece a ningún grupo activo: no hay avance que reportar.", alumno_id=alumno_id)
                visibles = self.s.autorizacion.grupos_visibles(actor, cat.P_STUDENT)
                grupos = [g for g in propios if visibles is None or g in visibles]
                if not grupos:
                    raise FueraDeAlcance("Ese alumno no está en ninguno de tus grupos.", alumno_id=alumno_id)
            grupos = sorted(grupos)
        self._grupos_al_dia(grupos)
        with self.s.uow(lectura=True) as uow:
            config = uow.config.get()
            cursos, aviso = filtro_de_nodo(uow, consulta)
            rotulo = uow.identidad.rotulos_personas([alumno_id]).get(alumno_id, alumno_id)
            salida = []
            senales: list[dict] = []
            dispositivos: set[str] = set()
            for g in grupos:
                fila = uow.avances.alumno(g, alumno_id)
                if fila is None:
                    continue
                grupo = uow.identidad.grupo(g)
                avance = uow.avances.grupo(g) or {}
                resumen = av.resumir(fila["detalle"], cursos)
                clases_del_grupo = {c["sesion_id"]: c for c in uow.clases.de_grupo(g)}
                senales = integracion.unir(senales, [s for c in clases_del_grupo.values() for s in c["senales"]], senales_de_estudio(uow, [alumno_id]))
                dispositivos |= {f["dispositivo_id"] or f"persona:{alumno_id}" for f in uow.clases.filas_de_alumno(alumno_id, list(clases_del_grupo))}
                salida.append({
                    "grupo": grupo_resumido(grupo, g), "modo": avance.get("modo") or "simple", "escala": avance.get("escala"), "resumen": av.resumen_para_pantalla(resumen),
                    "motivo_de_atencion": av.motivo_de_atencion(resumen),
                    "evaluaciones": self._evaluaciones(uow, fila["detalle"], cursos), "estudios": self._estudios(uow, fila["detalle"], cursos),
                    "clases": [{"sesion_id": c["sesion_id"], "finalizada_en": c["finalizada_en"], "asistio": c["asistio"], "recibidas": c["recibidas"], "entregadas": c["entregadas"],
                                "porcentaje_aciertos": como_numero(_pct(c["puntos"], c["puntos_maximos"]))}
                               for c in reversed(fila["detalle"].get("clases", [])) if cursos is None or c["curso_ref"] in cursos]})
            base = self._cabecera(uow, actor, cat.ALUMNO, ahora, senales=senales, equipos=len(dispositivos | {s["equipo"] for s in senales}), alumnos=1, nominal=True,
                                  umbral_activo=config["umbral_privacidad"], avisos=[aviso] if aviso else [])
            base["privacidad"] = priv.bloque(1, False)             # el informe de UN alumno es nominal por definición: el umbral no lo recorta (BR-086 es de los agregados)
            return {**base, "alumno": {"id": alumno_id, "rotulo": rotulo}, "grupos": salida}

    @staticmethod
    def _evaluaciones(uow: UnidadDeTrabajo, detalle: dict, cursos: set[str] | None) -> list[dict]:
        salida = []
        for e in detalle.get("evaluaciones", []):
            if cursos is not None and e["curso_ref"] not in cursos:
                continue
            a = uow.evaluacion.asignacion(e["asignacion_id"]) or {}
            salida.append({"asignacion_id": e["asignacion_id"], "titulo": a.get("titulo") or "", "curso_ref": e["curso_ref"], "estado_asignacion": e["estado_asignacion"],
                           "presento": e["presento"], "estado_intento": e["estado_intento"], "estado_simple": e["estado_simple"], "simbolo": tx.SIMBOLO_DEL_ESTADO_SIMPLE.get(e["estado_simple"], "vacio"),
                           "estado": e["estado"], "publicada": e["publicada"], "presentacion": e["presentacion"], "sin_presentar": e["sin_presentar"]})
        return sorted(salida, key=lambda x: (tx.clave_de_orden(x["titulo"]), x["asignacion_id"]))

    @staticmethod
    def _estudios(uow: UnidadDeTrabajo, detalle: dict, cursos: set[str] | None) -> list[dict]:
        salida = []
        for e in detalle.get("estudios", []):
            if cursos is not None and e["curso_ref"] not in cursos:
                continue
            a = uow.estudio.asignacion(e["asignacion_id"]) or {}
            salida.append({"asignacion_id": e["asignacion_id"], "titulo": a.get("titulo") or "", "curso_ref": e["curso_ref"], "estado": e["estado"], "avance_pct": e["avance_pct"],
                           "vencida": e["vencida"], "completada": e["completada"]})
        return sorted(salida, key=lambda x: (tx.clave_de_orden(x["titulo"]), x["asignacion_id"]))


class _Rotulos:
    """Los rótulos de evidencia (curso y lección) con que el AULA registró cada clase: se piden al dueño al mostrar, una vez por clase, y no se guardan aquí (artículo 14)."""

    def __init__(self, uow: UnidadDeTrabajo):
        self._uow = uow
        self._cache: dict[str, dict] = {}

    def de(self, sesion_id: str, campo: str) -> str:
        if sesion_id not in self._cache:
            self._cache[sesion_id] = self._uow.aula.sesion(sesion_id) or {}
        return self._cache[sesion_id].get(campo) or ""


def _pct(puntos, maximos):
    from ..dominio.metricas import a_decimal, porcentaje
    m = a_decimal(maximos)
    return porcentaje(puntos, maximos) if m is not None and m > 0 else None


# =================================================================================================================== el boletín académico individual

def _nombres_de_materias(uow: UnidadDeTrabajo) -> dict[str, str]:
    """`{código de materia: nombre}` según el árbol de la biblioteca (leído en vivo); vacío si no responde: las materias se muestran por su código en palabras."""
    disponible, _, nodos = uow.arbol.arbol()
    nombres: dict[str, str] = {}
    if not disponible:
        return nombres

    def recorrer(lista):
        for n in lista:
            if not isinstance(n, dict):
                continue
            if n.get("kind") == "subject" and n.get("code"):
                nombres.setdefault(str(n["code"]), str(n.get("name") or n["code"]))
            recorrer(n.get("children") or [])

    recorrer(nodos)
    return nombres


class ReporteDeBoletin(_Lector):
    """El boletín académico de UN estudiante (o de todos los de un grupo, uno por estudiante): el modelo de información común armado sobre lo que el libro ya presentó, con la
    plantilla del país y del nivel. Es nominal por naturaleza (el umbral de privacidad es de los agregados) y exige `reports.student.view` sobre el grupo."""

    def ejecutar(self, actor: Actor, alumno_id: str, consulta: dict | None = None) -> dict:
        self._al_dia()
        consulta = consulta or {}
        reporte = self.armar(actor, alumno_id, consulta)
        parametros = {"alumno_id": alumno_id, "grupo_id": reporte["grupo"]["id"], **parametros_de_nodo(consulta)}
        self._dejar_rastro(actor, cat.BOLETIN, parametros, reporte, grupo_id=reporte["grupo"]["id"])
        return reporte

    def ejecutar_grupo(self, actor: Actor, grupo_id: str, consulta: dict | None = None) -> dict:
        self._al_dia()
        consulta = consulta or {}
        reporte = self.armar_grupo(actor, grupo_id, consulta)
        self._dejar_rastro(actor, cat.BOLETIN, {"grupo_id": grupo_id, **parametros_de_nodo(consulta)}, reporte, grupo_id=grupo_id)
        return reporte

    def _grupo_del_alumno(self, uow: UnidadDeTrabajo, actor: Actor, alumno_id: str, pedido: str) -> dict:
        propios = uow.identidad.grupos_del_alumno(alumno_id) if alumno_id else []
        if pedido:
            self.s.autorizacion.exigir(actor, cat.P_STUDENT, grupo_id=pedido)
            if pedido not in propios:
                raise NoEncontrado("Ese alumno no está en ese grupo.", alumno_id=alumno_id, grupo_id=pedido)       # el rótulo de cualquier persona no se da
            grupo_id = pedido
        else:
            self.s.autorizacion.exigir(actor, cat.P_STUDENT)
            if not propios:
                raise AlumnoSinGrupo("Ese alumno no pertenece a ningún grupo activo: no hay boletín que armar.", alumno_id=alumno_id)
            visibles = self.s.autorizacion.grupos_visibles(actor, cat.P_STUDENT)
            grupos = sorted(g for g in propios if visibles is None or g in visibles)
            if not grupos:
                raise FueraDeAlcance("Ese alumno no está en ninguno de tus grupos.", alumno_id=alumno_id)
            grupo_id = grupos[0]
        grupo = uow.identidad.grupo(grupo_id)
        if grupo is None:
            raise NoEncontrado("No existe ese grupo.", grupo_id=grupo_id)
        return grupo

    def _modelo(self, uow: UnidadDeTrabajo, alumno_id: str, grupo: dict, materia: dict, config: dict, politica: dict, nombres: dict[str, str]) -> dict | None:
        boletin = uow.libro.boletin_de_alumno(alumno_id, grupo["id"], materia or None)
        if boletin is None:
            return None
        return bol.armar_modelo(boletin, uow.libro.progreso_del_alumno(alumno_id), politica, config, nombres_de_materias=nombres)

    def armar(self, actor: Actor, alumno_id: str, consulta: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        materia = parametros_de_nodo(consulta)
        with self.s.uow(lectura=True) as uow:
            exigir_nodo_instalado(uow)
            grupo = self._grupo_del_alumno(uow, actor, alumno_id, str(consulta.get("grupo_id") or ""))
            config = uow.config.get()
            modelo = self._modelo(uow, alumno_id, grupo, materia, config, uow.libro.politica_institucional(), _nombres_de_materias(uow))
            if modelo is None:
                raise NoEncontrado("Ese alumno no está en ese grupo.", alumno_id=alumno_id, grupo_id=grupo["id"])
            base = self._cabecera(uow, actor, cat.BOLETIN, ahora, senales=[], equipos=0, alumnos=1, nominal=True, umbral_activo=config["umbral_privacidad"], avisos=[])
            base["privacidad"] = priv.bloque(1, False)             # el boletín de UN estudiante es nominal por definición: el umbral es de los agregados
            base["titulo"] = f"Boletín académico · {modelo['estudiante']['rotulo']}"
            return {**base, "alumno": dict(modelo["estudiante"]), "grupo": grupo_resumido(grupo), "plantilla": modelo["plantilla"], "boletin": modelo}

    def armar_grupo(self, actor: Actor, grupo_id: str, consulta: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        materia = parametros_de_nodo(consulta)
        with self.s.uow(lectura=True) as uow:
            exigir_nodo_instalado(uow)
            grupo = uow.identidad.grupo(grupo_id) if grupo_id else None
            if grupo is None:
                raise NoEncontrado("No existe ese grupo.", grupo_id=grupo_id)
            self.s.autorizacion.exigir(actor, cat.P_STUDENT, grupo_id=grupo_id)
            alumnos = sorted(uow.identidad.alumnos_del_grupo(grupo_id), key=lambda a: (tx.clave_de_orden(a["rotulo"]), a["id"]))
            if len(alumnos) > cat.MAX_BOLETINES_POR_ARCHIVO:
                raise DatosInvalidos(f"Este grupo tiene más de {cat.MAX_BOLETINES_POR_ARCHIVO} estudiantes: genera los boletines por estudiante.", alumnos=len(alumnos))
            config, politica, nombres = uow.config.get(), uow.libro.politica_institucional(), _nombres_de_materias(uow)
            boletines = [m for m in (self._modelo(uow, a["id"], grupo, materia, config, politica, nombres) for a in alumnos) if m is not None]
            base = self._cabecera(uow, actor, cat.BOLETIN, ahora, senales=[], equipos=0, alumnos=len(boletines), nominal=bool(boletines), umbral_activo=config["umbral_privacidad"], avisos=[])
            base["privacidad"] = priv.bloque(len(boletines), False)   # un boletín por estudiante no compara personas: el umbral no lo recorta
            base["titulo"] = f"Boletines académicos · grupo {grupo['codigo'] or grupo['nombre']}"
            plantilla = boletines[0]["plantilla"] if boletines else bol.elegir_plantilla(config.get("plantilla_boletin") or cat.PLANTILLA_AUTO, politica.get("pais") or "", grupo["nivel_clave"] or "")
            return {**base, "grupo": grupo_resumido(grupo), "plantilla": plantilla, "boletines": boletines,
                    "totales": {"estudiantes": len(alumnos), "boletines": len(boletines), "con_nota": sum(1 for b in boletines if b["resumen"]["con_nota"] > 0)}}


# =================================================================================================================== uso de equipos (FUN-142)

class ReporteDeUso(_Lector):
    def ejecutar(self, actor: Actor, consulta: dict | None = None) -> dict:
        self._al_dia()
        consulta = consulta or {}
        reporte = self.armar(actor, consulta)
        self._dejar_rastro(actor, cat.USO, {"desde": reporte["periodo"]["desde"], "hasta": reporte["periodo"]["hasta"], **({"grupo_id": consulta["grupo_id"]} if consulta.get("grupo_id") else {})},
                           reporte, grupo_id=str(consulta.get("grupo_id") or ""))
        return reporte

    def armar(self, actor: Actor, consulta: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        desde, hasta = self._ms(consulta.get("desde"), "desde"), self._ms(consulta.get("hasta"), "hasta", fin_de_dia=True)
        if desde is not None and hasta is not None and desde > hasta:
            raise DatosInvalidos("El periodo está al revés: «desde» es posterior a «hasta».", desde=desde, hasta=hasta)
        grupo_id = str(consulta.get("grupo_id") or "")
        with self.s.uow(lectura=True) as uow:
            exigir_nodo_instalado(uow)
            if grupo_id:
                self.s.autorizacion.exigir(actor, cat.P_USAGE, grupo_id=grupo_id)
                grupos = [grupo_id]
            else:
                self.s.autorizacion.exigir(actor, cat.P_USAGE)
                grupos = self.s.autorizacion.grupos_visibles(actor, cat.P_USAGE)
            config = uow.config.get()
            cursos, aviso = filtro_de_nodo(uow, consulta)
            clases = [c for c in uow.clases.listar(grupo_ids=grupos, desde=desde, hasta=hasta, limite=cat.MAX_CLASES_EN_LISTA * 5) if cursos is None or c["curso_ref"] in cursos]
            if not clases:
                raise SinSesionesFinalizadas("No hay clases finalizadas en este periodo. Elige otro periodo.", desde=desde, hasta=hasta)
            por_clase = uow.clases.alumnos_de_clases([c["sesion_id"] for c in clases])
            por_equipo: dict[str, dict] = {}
            for c in clases:
                for fila in por_clase.get(c["sesion_id"], {}).values():
                    eq = fila["dispositivo_id"]
                    if not eq:
                        continue
                    e = por_equipo.setdefault(eq, {"clases": set(), "tiempo_total_ms": 0, "alumnos": set(), "ultimo_uso_en": 0})
                    e["clases"].add(c["sesion_id"])
                    e["tiempo_total_ms"] += int(fila["presente_ms"])
                    e["alumnos"].add(fila["alumno_id"])
                    e["ultimo_uso_en"] = max(e["ultimo_uso_en"], int(c["finalizada_en"]))
            equipos = []
            for eq, e in por_equipo.items():
                ficha = uow.equipos.por_id(eq) or {}
                equipos.append({"dispositivo_id": eq, "nombre": ficha.get("nombre") or "Equipo sin nombre", "tipo": ficha.get("tipo") or "", "plataforma": ficha.get("plataforma") or "",
                                "version_app": ficha.get("version_app") or "", "clases": len(e["clases"]), "tiempo_total_ms": e["tiempo_total_ms"], "alumnos": len(e["alumnos"]),
                                "ultimo_uso_en": e["ultimo_uso_en"] or None, "activo": ficha.get("activo", True), "bloqueado": bool(ficha.get("bloqueado"))})
            equipos.sort(key=lambda x: (-x["tiempo_total_ms"], x["nombre"].casefold(), x["dispositivo_id"]))
            grupos_vistos = {c["grupo_id"]: grupo_resumido(uow.identidad.grupo(c["grupo_id"]), c["grupo_id"]) for c in clases if c["grupo_id"]}
            total_ms = sum(int(c["duracion_ms"]) for c in clases)
            senales = [s for c in clases for s in c["senales"]]
            base = self._cabecera(uow, actor, cat.USO, ahora, senales=senales, equipos=len(equipos), alumnos=0, nominal=False, umbral_activo=config["umbral_privacidad"],
                                  avisos=[aviso] if aviso else [])
            base["privacidad"] = priv.bloque(0, False)
            return {
                **base, "periodo": {"desde": desde, "hasta": hasta},
                "totales": {"clases": len(clases), "equipos": len(equipos), "tiempo_total_ms": total_ms, "duracion_media_ms": total_ms // len(clases)},
                "equipos": equipos,
                "clases": [{"sesion_id": c["sesion_id"], "grupo": grupos_vistos.get(c["grupo_id"]), "iniciada_en": c["iniciada_en"], "finalizada_en": c["finalizada_en"],
                            "duracion_ms": c["duracion_ms"], "participantes": c["participantes"], "equipos": c["equipos"], "incompleta": bool(integracion.vigentes(c["senales"], ahora))} for c in clases]}


# =================================================================================================================== listas para llegar a un reporte

class ListaDeClases(_Lector):
    def ejecutar(self, actor: Actor, consulta: dict | None = None) -> dict:
        self._al_dia()
        consulta = consulta or {}
        ahora = self.s.reloj.ahora_ms()
        desde, hasta = self._ms(consulta.get("desde"), "desde"), self._ms(consulta.get("hasta"), "hasta", fin_de_dia=True)
        try:
            limite = max(1, min(int(consulta.get("limite") or 50), cat.MAX_CLASES_EN_LISTA))
        except (TypeError, ValueError):
            raise DatosInvalidos("`limite` debe ser un número.", limite=str(consulta.get("limite"))[:10])
        grupo_id = str(consulta.get("grupo_id") or "")
        with self.s.uow(lectura=True) as uow:
            if grupo_id:
                self.s.autorizacion.exigir(actor, cat.P_VIEW, grupo_id=grupo_id)
                grupos, propias = [grupo_id], ""
            else:
                self.s.autorizacion.exigir(actor, cat.P_VIEW)
                grupos = self.s.autorizacion.grupos_visibles(actor, cat.P_VIEW)
                propias = actor.id if (grupos is not None and actor.autenticado and actor.id) else ""
            cursos, aviso = filtro_de_nodo(uow, consulta)
            filas = uow.clases.listar(grupo_ids=grupos, profesor_id=propias, desde=desde, hasta=hasta, limite=limite)
            rotulos = _Rotulos(uow)
            vistos: dict[str, dict | None] = {}
            clases = []
            for c in filas:
                if cursos is not None and c["curso_ref"] not in cursos:
                    continue
                if c["grupo_id"] and c["grupo_id"] not in vistos:
                    vistos[c["grupo_id"]] = grupo_resumido(uow.identidad.grupo(c["grupo_id"]), c["grupo_id"])
                clases.append({"sesion_id": c["sesion_id"], "grupo": vistos.get(c["grupo_id"]), "curso_rotulo": rotulos.de(c["sesion_id"], "curso_rotulo"),
                               "leccion_rotulo": rotulos.de(c["sesion_id"], "leccion_rotulo"), "iniciada_en": c["iniciada_en"], "finalizada_en": c["finalizada_en"],
                               "duracion_ms": c["duracion_ms"], "participantes": c["participantes"], "actividades": c["actividades"],
                               "promedio_participacion": como_numero(c["promedio_participacion"]), "promedio_aciertos": como_numero(c["promedio_aciertos"]),
                               "incompleta": bool(integracion.vigentes(c["senales"], ahora))})
            estado, corte_en = estado_y_corte(uow, ahora)
            return {"clases": clases, "total": len(clases), "avisos": [aviso] if aviso and aviso["texto"] else [], "estado": estado, "corte_en": corte_en, "servidor_en": ahora}


class Filtros(_Lector):
    """FUN-143: lo que las fichas de OPS ofrecen para llegar a un reporte (nunca un campo de texto): los grupos que se pueden ver, sus periodos y el árbol académico de la biblioteca."""

    def ejecutar(self, actor: Actor) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir_alguno(actor, (cat.P_VIEW, cat.P_GROUP, cat.P_STUDENT, cat.P_USAGE))
            visibles: list[str] | None = []
            for permiso in (cat.P_GROUP, cat.P_VIEW, cat.P_STUDENT, cat.P_USAGE):
                if self.s.autorizacion.puede(actor, permiso):
                    v = self.s.autorizacion.grupos_visibles(actor, permiso)
                    if v is None:
                        visibles = None                       # algún permiso llega a toda la organización
                        break
                    visibles = sorted(set(visibles) | set(v))
            ids = uow.identidad.todos_los_grupos() if visibles is None else visibles
            # BR-085: «cuántos alumnos» y sobre todo «cuántos necesitan atención» son datos académicos. Quien sólo puede ver el uso de equipos (el técnico) recibe los grupos para
            # poder filtrar, y nada más: sin cifras, y sin asiento porque no pidió nada que se le negara.
            academico = any(self.s.autorizacion.puede(actor, p) for p in (cat.P_VIEW, cat.P_GROUP, cat.P_STUDENT))
            grupos = []
            for g in sorted(ids):
                ficha = uow.identidad.grupo(g)
                if ficha is None or not ficha["activo"]:
                    continue
                avance = uow.avances.grupo(g) or {}
                grupos.append({**grupo_resumido(ficha), "alumnos": avance.get("alumnos") if academico else None, "en_atencion": avance.get("en_atencion") if academico else None,
                               "desactualizado": avance.get("desactualizado", True)})
            grupos.sort(key=lambda x: ((x["periodo"] or ""), (x["codigo"] or "").casefold()))
            disponible, motivo, nodos = uow.arbol.arbol()
            return {"grupos": grupos, "periodos": sorted({g["periodo"] for g in grupos if g["periodo"]}, reverse=True),
                    "nodos": {"disponible": disponible, "motivo": motivo, "arbol": _recortar(nodos)}, "objetivos": OBJETIVOS,
                    "puede": {"clase": self.s.autorizacion.puede(actor, cat.P_VIEW), "grupo": self.s.autorizacion.puede(actor, cat.P_GROUP),
                              "alumno": self.s.autorizacion.puede(actor, cat.P_STUDENT), "uso": self.s.autorizacion.puede(actor, cat.P_USAGE),
                              "exportar": self.s.autorizacion.puede(actor, cat.P_EXPORT), "reconstruir": self.s.autorizacion.puede(actor, cat.P_REBUILD),
                              "configurar": self.s.autorizacion.puede(actor, cat.P_SETTINGS)}, "servidor_en": ahora}


def _recortar(nodos: list[dict]) -> list[dict]:
    return [{"kind": n.get("kind"), "code": n.get("code"), "name": n.get("name"), "count": n.get("count"), "children": _recortar(n.get("children") or [])} for n in nodos]


class AlumnosDelGrupo(_Lector):
    """La lista de alumnos de un grupo para elegirlos tocando (fichas de inicial), no escribiendo. Requiere poder ver el informe del alumno."""

    def ejecutar(self, actor: Actor, grupo_id: str) -> dict:
        with self.s.uow(lectura=True) as uow:
            exigir_nodo_instalado(uow)
            if not grupo_id or uow.identidad.grupo(grupo_id) is None:
                raise NoEncontrado("No existe ese grupo.", grupo_id=grupo_id)
            self.s.autorizacion.exigir(actor, cat.P_STUDENT, grupo_id=grupo_id)
        self._grupos_al_dia([grupo_id])
        with self.s.uow(lectura=True) as uow:
            alumnos = uow.identidad.alumnos_del_grupo(grupo_id)
            atencion = {r["alumno_id"]: bool(r["atencion"]) for r in uow.avances.alumnos(grupo_id)}
            filas = sorted(({"id": a["id"], "rotulo": a["rotulo"], "inicial": _inicial(a["rotulo"]), "necesita_atencion": atencion.get(a["id"], False)} for a in alumnos),
                           key=lambda a: (tx.clave_de_orden(a["rotulo"]), a["id"]))
            iniciales: dict[str, int] = {}
            for f in filas:
                iniciales[f["inicial"]] = iniciales.get(f["inicial"], 0) + 1
            return {"grupo_id": grupo_id, "alumnos": filas, "iniciales": [{"inicial": k, "cantidad": v} for k, v in sorted(iniciales.items())]}


def _inicial(rotulo: str) -> str:
    """La inicial con la que se agrupa a un alumno en las fichas: sin tildes y en mayúscula (Á → A); la ñ se conserva; lo que no es letra va a «#»."""
    import unicodedata
    for ch in (rotulo or "").strip():
        if ch.lower() == "ñ":
            return "Ñ"
        base = unicodedata.normalize("NFD", ch)[0]
        if base.isalpha():
            return base.upper()
        if base.isdigit():
            break
    return "#"


class Recientes(_Lector):
    """Los reportes que ESTA persona abrió hace poco (sólo sus parámetros): se vuelven a abrir (y a exportar) sin repetir los filtros. Una reciente cuyo reporte ya no se puede ver
    —cambió el rol, el grupo ya no es suyo, la clase desapareció— no aparece."""

    def ejecutar(self, actor: Actor) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            filas = uow.recientes.de(actor.id, cat.MAX_RECIENTES * 3) if actor.id else []
            salida = []
            for f in filas:
                titulo = self._titulo(uow, actor, f)
                if titulo is None:
                    continue
                titulo += self._sufijo(f)
                salida.append({"tipo": f["tipo"], "parametros": f["parametros"], "titulo": titulo, "ultima_vez_en": f["ultima_vez_en"], "veces": f["veces"],
                               "ultima_exportacion_en": f["ultima_exportacion_en"]})
                if len(salida) >= cat.MAX_RECIENTES:
                    break
            return {"recientes": salida, "servidor_en": ahora}

    def _sufijo(self, f: dict) -> str:
        """Lo que distingue un reciente de otro del MISMO reporte: el filtro de materia y, en el uso de equipos, desde cuándo se miró. Sin esto, tres «Grupo 8A» no se podrían diferenciar.
        Los parámetros se reabren tal cual se guardaron (un periodo «Últimos 7 días» guarda su fecha de inicio), y el título lo dice."""
        p, extra = f["parametros"], []
        if f["tipo"] == cat.USO and p.get("desde"):
            extra.append(f"desde {tx.fecha_corta(self.s.reloj.a_local(int(p['desde'])))}")
        if any(p.get(k) for k in NODO_PARAMETROS):
            extra.append("con filtro de materia")
        return "".join(f" · {e}" for e in extra)

    def _titulo(self, uow: UnidadDeTrabajo, actor: Actor, f: dict) -> str | None:
        p, tipo = f["parametros"], f["tipo"]
        try:
            if tipo == cat.CLASE:
                c = uow.clases.get(p.get("sesion_id", ""))
                if c is None:
                    return None
                exigir_en_clase(self.s.autorizacion, actor, cat.P_VIEW, c)
                g = uow.identidad.grupo(c["grupo_id"]) if c["grupo_id"] else None
                return f"Clase de {(g or {}).get('codigo') or 'sin grupo'} · {tx.fecha_corta(self.s.reloj.a_local(c['finalizada_en']))}"
            if tipo == cat.GRUPO:
                self.s.autorizacion.exigir(actor, cat.P_GROUP, grupo_id=p.get("grupo_id", ""))
                g = uow.identidad.grupo(p.get("grupo_id", ""))
                return None if g is None else f"Grupo {g['codigo'] or g['nombre']}"
            if tipo == cat.ALUMNO:
                if p.get("grupo_id"):
                    self.s.autorizacion.exigir(actor, cat.P_STUDENT, grupo_id=p["grupo_id"])
                else:
                    self.s.autorizacion.exigir(actor, cat.P_STUDENT)
                nombre = uow.identidad.rotulos_personas([p.get("alumno_id", "")]).get(p.get("alumno_id", ""))
                return None if nombre is None else nombre
            if tipo == cat.USO:
                self.s.autorizacion.exigir(actor, cat.P_USAGE)
                return "Uso de equipos"
            if tipo == cat.BOLETIN:
                self.s.autorizacion.exigir(actor, cat.P_STUDENT, grupo_id=p.get("grupo_id", ""))
                g = uow.identidad.grupo(p.get("grupo_id", ""))
                if g is None:
                    return None
                if p.get("alumno_id"):
                    nombre = uow.identidad.rotulos_personas([p["alumno_id"]]).get(p["alumno_id"])
                    return None if nombre is None else f"Boletín de {nombre}"
                return f"Boletines del grupo {g['codigo'] or g['nombre']}"
        except (SinPermiso, FueraDeAlcance):
            return None
        return None
