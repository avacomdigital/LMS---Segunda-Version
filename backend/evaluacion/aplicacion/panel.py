"""
Lo que se LEE de la evaluación (no escribe nada salvo poner al día el reloj):

  PanelDeAsignacion      PAN-005 / PAN-121: una fila por alumno, ordenada por QUIÉN NECESITA AL PROFESOR, no alfabéticamente (CMP-034). No suena, no marca
                         en rojo y no ofrece «anular»: la pantalla de un examen no es un panel de vigilancia, es un panel de continuidad.
  ExpedienteDelIntento   PAN-062: el expediente de integridad, sólo lectura, con todos los incidentes y su contexto. Nunca ofrece anular.
  Elegibilidad           PAN-060 paso 4: qué tabletas alcanzan el nivel elegido (MSG-036)
  MisEvaluaciones        lo que sondea Student: las evaluaciones que le alcanzan al alumno y si puede comenzar
  Antesala               PAN-120 (alumno): duración, condiciones y qué se registra, ANTES de empezar
  ResultadosDeAsignacion los resultados (provisionales hasta MOD-011) para el profesor
"""
from __future__ import annotations

from ..dominio import bloqueo
from ..dominio import catalogos as cat
from ..dominio import intento as int_dom
from ..dominio.errores import NoEncontrado
from .alumno import _Alumno
from .asignaciones import vista_asignacion
from .base import Contexto, _CasoDeUso, alcanza_al_alumno, asignacion_del_alumno, destinatarios_de
from .motor import Motor
from .puertos import Actor, UnidadDeTrabajo

SIETE_DIAS_MS = 7 * 24 * 3_600_000


def _ultimo_por_alumno(intentos: list[dict]) -> dict[str, dict]:
    """El intento más reciente (el de mayor número) de cada alumno."""
    ultimos: dict[str, dict] = {}
    for it in intentos:
        previo = ultimos.get(it["alumno_id"])
        if previo is None or it["numero"] > previo["numero"]:
            ultimos[it["alumno_id"]] = it
    return ultimos


def totales_de(uow: UnidadDeTrabajo, asignacion: dict) -> dict:
    """Los contadores de una asignación, por alumno (su intento más reciente). Sirve a la lista, al panel y a los resultados."""
    destinatarios = destinatarios_de(uow, asignacion)
    ultimos = _ultimo_por_alumno(uow.intentos.de_asignacion(asignacion["id"]))
    admisiones = {a["alumno_id"] for a in uow.admisiones.de_asignacion(asignacion["id"], solo_en_espera=True)}
    con_incidentes = {iid for iid, lista in uow.incidentes.de_intentos([i["id"] for i in ultimos.values()]).items() if lista}
    cuenta = {e: 0 for e in cat.ESTADOS_INTENTO}
    for it in ultimos.values():
        cuenta[it["estado"]] += 1
    return {
        "destinatarios": len(destinatarios),
        "sin_intento": sum(1 for d in destinatarios if d["id"] not in ultimos),
        "en_espera_admision": len(admisiones), "no_iniciados": cuenta[cat.NO_INICIADO],
        "en_curso": cuenta[cat.EN_CURSO] + cuenta[cat.EN_CURSO_FUERA_DE_PLAZO], "suspendidos": cuenta[cat.PAUSADO], "restaurando": cuenta[cat.RESTAURANDO],
        "entregados": cuenta[cat.ENTREGADO], "en_revision": cuenta[cat.EN_REVISION], "calificados": cuenta[cat.CALIFICADO], "anulados": cuenta[cat.ANULADO],
        "con_incidentes": sum(1 for it in ultimos.values() if it["id"] in con_incidentes),
        "pendientes_decision": sum(1 for it in ultimos.values() if it.get("envio_tardio") == cat.TARDIO_PENDIENTE),
    }


def resumen_de_incidentes(lista: list[dict]) -> dict:
    por_severidad = {s: 0 for s in cat.SEVERIDADES}
    for i in lista:
        por_severidad[i["severidad"]] += 1
    ultimo = max(lista, key=lambda i: (i["ocurrido_en"], i["id"]), default=None)
    return {"total": len(lista), **por_severidad,
            "ultimo": {"tipo": ultimo["tipo"], "ocurrido_en": ultimo["ocurrido_en"], "severidad": ultimo["severidad"]} if ultimo else None}


class _Lectura(_CasoDeUso):
    def __init__(self, servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)

    def _asignacion(self, uow: UnidadDeTrabajo, asignacion_id: str, ahora: int) -> dict:
        asignacion = uow.asignaciones.por_id(asignacion_id) if asignacion_id else None
        if asignacion is None:
            raise NoEncontrado("No existe esa evaluación.", asignacion_id=asignacion_id)
        return self.motor.asegurar_asignacion(uow, asignacion, ahora)

    def _al_dia(self, uow: UnidadDeTrabajo, asignacion: dict, ahora: int) -> list[dict]:
        """Los intentos de la asignación con las transiciones del reloj ya aplicadas (un alumno sin señal se ve suspendido aunque nadie lo haya notado)."""
        salida = []
        for it in uow.intentos.de_asignacion(asignacion["id"]):
            salida.append(self.motor.asegurar_intento(uow, it, asignacion, ahora) if it["estado"] in cat.CORRIENDO else it)
        return salida

    @staticmethod
    def _tabletas(uow: UnidadDeTrabajo, asignacion: dict, alumno_ids: list[str]) -> dict[str, dict]:
        """La tableta conocida de cada alumno: la que usa en la clase y, si no, la que tiene asignada."""
        tabletas: dict[str, dict] = {}
        asignadas = uow.dispositivos.asignados_a(alumno_ids) if alumno_ids else {}
        for alumno_id, dispositivo in asignadas.items():
            tabletas[alumno_id] = dispositivo
        if asignacion.get("sesion_id"):
            for alumno_id, dispositivo_id in uow.aula.dispositivos_de(asignacion["sesion_id"]).items():
                dispositivo = uow.dispositivos.por_id(dispositivo_id)
                if dispositivo:
                    tabletas[alumno_id] = dispositivo
        return tabletas

    @staticmethod
    def _vista_tableta(dispositivo: dict | None, nivel: str) -> dict | None:
        if not dispositivo:
            return None
        capacidad = bloqueo.normalizar_capacidad(dispositivo.get("capacidad_control"))
        return {"id": dispositivo["id"], "nombre": dispositivo.get("nombre", ""), "capacidad": capacidad, "alcanza": bloqueo.alcanza(capacidad, nivel)}


class PanelDeAsignacion(_Lectura):
    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_READ, asignacion)
            destinatarios = destinatarios_de(uow, asignacion)
            intentos = self._al_dia(uow, asignacion, ahora)
            ultimos = _ultimo_por_alumno(intentos)
            incidentes = uow.incidentes.de_intentos([i["id"] for i in ultimos.values()])
            admisiones = {a["alumno_id"]: a for a in uow.admisiones.de_asignacion(asignacion_id, solo_en_espera=False)}
            tabletas = self._tabletas(uow, asignacion, [d["id"] for d in destinatarios])
            nivel = asignacion["nivel_examen"]
            filas = []
            for d in destinatarios:
                it = ultimos.get(d["id"])
                adm = admisiones.get(d["id"])
                tableta = (uow.dispositivos.por_id(it["dispositivo_id"]) if it and it.get("dispositivo_id") else None) or tabletas.get(d["id"])
                filas.append(self._fila(d, it, adm, tableta, incidentes.get(it["id"], []) if it else [], nivel, ahora))
            filas.sort(key=lambda f: (f["_prioridad"], f["rotulo"].lower()))
            for f in filas:
                f.pop("_prioridad")
            return {"asignacion": {k: asignacion[k] for k in ("id", "titulo", "estado", "nivel_examen", "nivel_declarado", "plazo", "abre_en", "limite_en",
                                                              "gracia_ms", "reactivacion", "intentos_permitidos", "sesion_id", "resultados", "liberados_en",
                                                              "objeto_rotulo", "curso_rotulo", "grupo_rotulo", "preguntas_por_alumno")},
                    "servidor_en": ahora, "totales": totales_de(uow, asignacion), "filas": filas}

    def _fila(self, alumno: dict, it: dict | None, adm: dict | None, tableta: dict | None, incidentes: list[dict], nivel: str, ahora: int) -> dict:
        en_espera = adm is not None and adm["estado"] == cat.EN_ESPERA
        suspendido = bool(it) and it["estado"] in cat.SUSPENDIDOS
        reloj = int_dom.reloj(it, ahora) if it and it["estado"] in cat.ACEPTAN_RESPUESTAS else None
        bloqueo_informe = (it or {}).get("bloqueo") or {}
        falla_bloqueo = bool(it) and it["estado"] in cat.ACEPTAN_RESPUESTAS and bloqueo_informe.get("resultado") in (cat.B_PARCIAL, cat.B_FALLIDO) \
            and nivel == cat.CONTROLADO
        if suspendido:
            prioridad = 0
        elif en_espera:
            prioridad = 1
        elif it and it.get("envio_tardio") == cat.TARDIO_PENDIENTE:
            prioridad = 2
        elif falla_bloqueo:
            prioridad = 3
        elif it and it["estado"] in cat.CORRIENDO:
            prioridad = 4
        elif it is None or it["estado"] == cat.NO_INICIADO:
            prioridad = 5
        elif it["estado"] == cat.ANULADO:
            prioridad = 7
        else:
            prioridad = 6
        return {
            "_prioridad": prioridad, "alumno_id": alumno["id"], "rotulo": alumno["rotulo"], "estado": it["estado"] if it else "sin_intento",
            "requiere_reactivacion": suspendido, "intento_id": it["id"] if it else None, "numero": it["numero"] if it else None,
            "nivel_efectivo": it["nivel_efectivo"] if it else None, "dispositivo": self._vista_tableta(tableta, nivel),
            "respondidas": len(it["respuestas"]) if it else 0, "total": len(it["armado"]) if it else 0,
            "pregunta_actual": (it or {}).get("pregunta_actual") or "", "reloj": reloj,
            "silencio_ms": int_dom.silencio_ms(it, ahora) if it and it["estado"] in cat.ACEPTAN_RESPUESTAS else None,
            "incidentes": resumen_de_incidentes(incidentes), "bloqueo": {"resultado": bloqueo_informe.get("resultado", "")} if bloqueo_informe else None,
            "admision": ({"id": adm["id"], "estado": adm["estado"], "nivel_exigido": adm["nivel_exigido"], "nivel_alcanzado": adm["nivel_alcanzado"]}
                         if adm else None),
            "fuera_de_plazo": bool(it and it.get("fuera_de_plazo")), "envio_tardio": (it or {}).get("envio_tardio") or "",
            "origen_entrega": (it or {}).get("origen_entrega") or "", "requiere_revision": bool(it and it.get("requiere_revision")),
            "porcentaje": it.get("porcentaje") if it and it["estado"] in cat.ENTREGADOS else None,
            "anulado_por": it.get("anulado_por") if it and it["estado"] == cat.ANULADO else None,
        }


class ExpedienteDelIntento(_Lectura):
    """PAN-062. Sólo lectura: ni siquiera ofrece la acción de anular junto al expediente (Guion, paso 7)."""

    def ejecutar(self, actor: Actor, intento_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento = uow.intentos.por_id(intento_id) if intento_id else None
            if intento is None:
                raise NoEncontrado("No existe ese intento.", intento_id=intento_id)
            asignacion = self._asignacion(uow, intento["asignacion_id"], ahora)
            self.s.autorizacion.exigir(actor, cat.P_READ, asignacion)
            if intento["estado"] in cat.CORRIENDO:
                intento = self.motor.asegurar_intento(uow, intento, asignacion, ahora)
            incidentes = uow.incidentes.de_intento(intento_id)
            admisiones = uow.admisiones.del_alumno(asignacion["id"], intento["alumno_id"])
            lineas = []
            if intento.get("iniciado_en"):
                lineas.append({"en": intento["iniciado_en"], "tipo": "intento_abierto", "origen": "alumno", "detalle": {"nivel_efectivo": intento["nivel_efectivo"]}})
            for p in intento.get("pausas") or []:
                lineas.append({"en": p["desde"], "tipo": "pausa", "origen": "nodo", "detalle": {"causa": p.get("causa"), "hasta": p.get("hasta"),
                                                                                             "reactivado_por": p.get("reactivado_por", "")}})
            for i in incidentes:
                lineas.append({"en": i["ocurrido_en"], "tipo": i["tipo"], "origen": i["origen"], "severidad": i["severidad"], "detalle": i["detalle"]})
            if intento.get("entregado_en"):
                lineas.append({"en": intento["entregado_en"], "tipo": "entregado", "origen": intento.get("origen_entrega") or "",
                               "detalle": {"fuera_de_plazo": bool(intento.get("fuera_de_plazo"))}})
            if intento.get("anulado_en"):
                lineas.append({"en": intento["anulado_en"], "tipo": "anulado", "origen": "profesor",
                               "detalle": {"por": intento["anulado_por"], "motivo": intento["motivo_anulacion"]}})
            lineas.sort(key=lambda x: x["en"] or 0)
            return {
                "intento": {k: intento.get(k) for k in ("id", "asignacion_id", "alumno_id", "alumno_rotulo", "numero", "estado", "nivel_efectivo", "dispositivo_id",
                                                        "curso_version", "semilla", "tiempo_limite_seg", "consumido_ms", "iniciado_en", "entregado_en",
                                                        "origen_entrega", "fuera_de_plazo", "envio_tardio", "decision_envio", "porcentaje", "requiere_revision",
                                                        "calificacion_pendiente", "calificado_por", "anulado_por", "motivo_anulacion", "anulado_en")},
                "respondidas": len(intento["respuestas"]), "total": len(intento["armado"]), "reloj": int_dom.reloj(intento, ahora),
                "incidentes": incidentes, "resumen_incidentes": resumen_de_incidentes(incidentes), "pausas": intento.get("pausas") or [],
                "sesiones": intento.get("sesiones") or [], "bloqueo": intento.get("bloqueo") or {}, "admisiones": admisiones,
                "linea_de_tiempo": lineas, "servidor_en": ahora}


class Elegibilidad(_Lectura):
    """PAN-060 paso 4: ¿qué tabletas alcanzan el nivel? Sólo se juzga la tableta que ya se conoce de cada alumno; el resto se sabrá al abrir el intento."""

    def ejecutar(self, actor: Actor, asignacion_id: str, nivel: str | None = None) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_READ, asignacion)
            nivel = bloqueo.validar_nivel(nivel) if nivel else asignacion["nivel_examen"]
            destinatarios = destinatarios_de(uow, asignacion)
            tabletas = self._tabletas(uow, asignacion, [d["id"] for d in destinatarios])
            filas = []
            for d in destinatarios:
                t = self._vista_tableta(tabletas.get(d["id"]), nivel)
                filas.append({"alumno_id": d["id"], "rotulo": d["rotulo"], "dispositivo_id": t["id"] if t else None,
                              "dispositivo_nombre": t["nombre"] if t else None, "capacidad": t["capacidad"] if t else None, "nivel_exigido": nivel,
                              "alcanza": t["alcanza"] if t else None})
            alcanzan = sum(1 for f in filas if f["alcanza"] is True)
            no = sum(1 for f in filas if f["alcanza"] is False)
            mensaje = (f"{no} tabletas no alcanzan para el nivel {nivel}. Puedes admitirlas en un nivel menor o cambiarlas." if no and nivel == cat.CONTROLADO
                       else None)
            return {"nivel_examen": nivel, "filas": filas, "resumen": {"alcanzan": alcanzan, "no_alcanzan": no, "sin_tableta": len(filas) - alcanzan - no},
                    "mensaje": mensaje, "servidor_en": ahora}


class ResultadosDeAsignacion(_Lectura):
    """Los resultados para el profesor (provisionales hasta MOD-011). Con menos de tres entregas no hay promedio (CMP-043)."""

    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_RESULTS_VIEW, asignacion)
            destinatarios = destinatarios_de(uow, asignacion)
            ultimos = _ultimo_por_alumno(self._al_dia(uow, asignacion, ahora))
            incidentes = uow.incidentes.de_intentos([i["id"] for i in ultimos.values()])
            aprobacion = asignacion.get("aprobacion_pct")
            filas, porcentajes = [], []
            for d in destinatarios:
                it = ultimos.get(d["id"])
                final = bool(it) and it["estado"] == cat.CALIFICADO
                if final and it["porcentaje"] is not None:
                    porcentajes.append(it["porcentaje"])
                filas.append({"alumno_id": d["id"], "rotulo": d["rotulo"], "intento_id": it["id"] if it else None, "estado": it["estado"] if it else "sin_intento",
                              "porcentaje": it.get("porcentaje") if it else None, "puntaje": it.get("puntaje") if it else None,
                              "puntaje_maximo": it.get("puntaje_maximo") if it else None, "definitivo": final,
                              "aprobado": (it["porcentaje"] >= aprobacion) if final and aprobacion is not None and it["porcentaje"] is not None else None,
                              "fuera_de_plazo": bool(it and it.get("fuera_de_plazo")), "requiere_revision": bool(it and it.get("requiere_revision")),
                              "incidentes": len(incidentes.get(it["id"], [])) if it else 0})
            return {"asignacion_id": asignacion_id, "titulo": asignacion["titulo"], "aprobacion_pct": aprobacion, "liberados_en": asignacion.get("liberados_en"),
                    "promedio_porcentaje": round(sum(porcentajes) / len(porcentajes), 2) if len(porcentajes) >= 3 else None,
                    "datos_suficientes": len(porcentajes) >= 3, "filas": filas, "servidor_en": ahora}


# ============================================================================================ el alumno

class _Estado(_Alumno):
    def _puede_comenzar(self, uow: UnidadDeTrabajo, ctx: Contexto, asignacion: dict, propios: list[dict]) -> tuple[bool, str, dict | None]:
        """(¿puede comenzar?, motivo si no, admisión). Una tableta que no alcanza el nivel SÍ puede pulsar «Comenzar»: eso crea la solicitud de
        admisión; lo que no puede es seguir mientras el profesor decide."""
        vivo = next((i for i in propios if i["estado"] in cat.VIVOS and i["estado"] != cat.NO_INICIADO), None)
        if vivo is not None:
            return True, "", None
        admision = uow.admisiones.de_terna(asignacion["id"], ctx.alumno_id, ctx.dispositivo_id) if ctx.dispositivo_id else None
        if asignacion["estado"] not in cat.ABIERTAS:
            return False, "no_abierta", admision
        usados = sum(1 for i in propios if i["estado"] not in (cat.NO_INICIADO, cat.ANULADO))
        permitidos = asignacion.get("intentos_permitidos")
        if permitidos is not None and usados >= permitidos:
            return False, "ya_entregado" if usados and permitidos == 1 else "intentos_agotados", admision
        if admision is not None and not bloqueo.alcanza(ctx.capacidad, asignacion["nivel_examen"]):
            if admision["estado"] == cat.RECHAZADO:
                return False, "rechazada", admision
            if admision["estado"] == cat.EN_ESPERA:
                return False, "espera_admision", admision
        return True, "", admision


class MisEvaluaciones(_Estado):
    """`datos`: `{dispositivo, alumno_id, todas?}`. No registra la tableta ni exige que esté registrada: es una lectura."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            estados = (cat.PROGRAMADA, cat.ACTIVA, cat.ACTIVA_FUERA_DE_PLAZO) + ((cat.CERRADA,) if datos.get("todas") else ())
            pendientes, recientes = [], []
            for fila in uow.asignaciones.listar(estados=estados):
                if not alcanza_al_alumno(uow, fila, ctx.alumno_id):
                    continue
                asignacion = self.motor.asegurar_asignacion(uow, fila, ahora)
                propios = uow.intentos.del_alumno(asignacion["id"], ctx.alumno_id)
                propios = [self.motor.asegurar_intento(uow, i, asignacion, ahora) if i["estado"] in cat.CORRIENDO else i for i in propios]
                ultimo = max(propios, key=lambda i: i["numero"], default=None)
                if asignacion["estado"] == cat.CERRADA:
                    if ultimo is None or ahora - (asignacion.get("cerrada_en") or 0) > SIETE_DIAS_MS:
                        continue
                    recientes.append(self._resumen(uow, ctx, asignacion, propios, ultimo, ahora))
                elif asignacion["estado"] in cat.ABIERTAS or asignacion["estado"] == cat.PROGRAMADA:
                    pendientes.append(self._resumen(uow, ctx, asignacion, propios, ultimo, ahora))
            return {"pendientes": pendientes, "recientes": recientes, "alumno_id": ctx.alumno_id, "servidor_en": ahora}

    def _resumen(self, uow: UnidadDeTrabajo, ctx: Contexto, asignacion: dict, propios: list[dict], ultimo: dict | None, ahora: int) -> dict:
        puede, motivo, _ = self._puede_comenzar(uow, ctx, asignacion, propios)
        return {"id": asignacion["id"], "titulo": asignacion["titulo"], "curso_rotulo": asignacion["curso_rotulo"], "estado": asignacion["estado"],
                "nivel_examen": asignacion["nivel_examen"], "abre_en": asignacion.get("abre_en"), "limite_en": asignacion.get("limite_en"),
                "plazo": asignacion["plazo"], "sesion_id": asignacion["sesion_id"], "preguntas": asignacion["preguntas_por_alumno"],
                "puede_comenzar": puede, "motivo": motivo,
                "mi_intento": ({"id": ultimo["id"], "numero": ultimo["numero"], "estado": ultimo["estado"],
                                "resultado_disponible": self.motor.resultado_disponible(asignacion, ultimo)} if ultimo else None)}


class EstudiantesConEvaluacion(_CasoDeUso):
    """El «¿Quién eres?» de la evaluación (D-19, D-25). Sin sesión (Q-34 abierta), la tableta pregunta a la persona quién es de entre los alumnos de los grupos que
    tienen una evaluación programada o abierta, sin código ni contraseña: el LMS es offline y no hay verificación central. Es lo mismo que hace Modo Estudio con
    sus lecciones. No lleva ni pide permiso y sólo nombra a quien puede presentar algo ahora."""

    def __init__(self, servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)

    def ejecutar(self) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            grupos: dict[str, dict] = {}
            for fila in uow.asignaciones.listar(estados=(cat.PROGRAMADA, cat.ACTIVA, cat.ACTIVA_FUERA_DE_PLAZO)):
                asignacion = self.motor.asegurar_asignacion(uow, fila, ahora)
                if asignacion["estado"] not in (cat.PROGRAMADA, *cat.ABIERTAS):
                    continue
                clave = asignacion.get("grupo_id") or "seleccion"
                grupo = grupos.setdefault(clave, {"id": clave, "nombre": asignacion.get("grupo_rotulo") or "Alumnos", "alumnos": {}})
                for d in destinatarios_de(uow, asignacion):
                    grupo["alumnos"][d["id"]] = d["rotulo"]
            salida = [{"id": g["id"], "nombre": g["nombre"],
                       "alumnos": [{"id": i, "rotulo": r} for i, r in sorted(g["alumnos"].items(), key=lambda x: (x[1] or "").lower())]}
                      for g in sorted(grupos.values(), key=lambda g: (g["nombre"] or "").lower()) if g["alumnos"]]
            return {"disponible": bool(salida), "motivo": "" if salida else "sin_evaluaciones", "grupos": salida, "servidor_en": ahora}


class Antesala(_Estado):
    """PAN-120 (alumno): lo que el alumno debe ver ANTES de empezar —duración, condiciones y qué se registra—. Iniciar sin que lo haya visto es lo que el
    sistema nunca hace."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            asignacion = asignacion_del_alumno(uow, ctx, asignacion_id)
            asignacion = self.motor.asegurar_asignacion(uow, asignacion, ahora)
            propios = [self.motor.asegurar_intento(uow, i, asignacion, ahora) if i["estado"] in cat.CORRIENDO else i
                       for i in uow.intentos.del_alumno(asignacion_id, ctx.alumno_id)]
            ultimo = max(propios, key=lambda i: i["numero"], default=None)
            puede, motivo, admision = self._puede_comenzar(uow, ctx, asignacion, propios)
            nivel = asignacion["nivel_examen"]
            usados = sum(1 for i in propios if i["estado"] not in (cat.NO_INICIADO, cat.ANULADO))
            tableta = self._vista_tableta(ctx.dispositivo, nivel) if ctx.dispositivo else None
            return {
                "asignacion": {"id": asignacion["id"], "titulo": asignacion["titulo"], "curso_rotulo": asignacion["curso_rotulo"], "estado": asignacion["estado"],
                               "preguntas": asignacion["preguntas_por_alumno"], "duracion_seg": self._duracion(asignacion),
                               "intentos_permitidos": asignacion.get("intentos_permitidos"), "intentos_usados": usados, "plazo": asignacion["plazo"],
                               "limite_en": asignacion.get("limite_en"), "resultados": asignacion["resultados"],
                               "permite_retroceso": bool(asignacion.get("permite_retroceso", True))},
                "condiciones": bloqueo.condiciones(nivel),
                "dispositivo": ({"id": tableta["id"], "capacidad": tableta["capacidad"], "alcanza": tableta["alcanza"], "nivel_exigido": nivel}
                                if tableta else {"id": None, "capacidad": ctx.capacidad, "alcanza": bloqueo.alcanza(ctx.capacidad, nivel), "nivel_exigido": nivel}),
                "admision": ({"id": admision["id"], "estado": admision["estado"], "nivel_admitido": admision.get("nivel_admitido", ""),
                              "nivel_exigido": admision["nivel_exigido"]} if admision else None),
                "mi_intento": ({"id": ultimo["id"], "numero": ultimo["numero"], "estado": ultimo["estado"]} if ultimo else None),
                "puede_comenzar": puede, "motivo": motivo, "servidor_en": ahora}

    @staticmethod
    def _duracion(asignacion: dict) -> int | None:
        if asignacion["tiempo_modo"] == cat.SIN_LIMITE:
            return None
        if asignacion["tiempo_modo"] == cat.TIEMPO_FIJO:
            return asignacion["tiempo_limite_seg"]
        return (asignacion.get("ajustes") or {}).get("limite_seg_estimado")

    @staticmethod
    def _vista_tableta(dispositivo: dict, nivel: str) -> dict:
        capacidad = bloqueo.normalizar_capacidad(dispositivo.get("capacidad_control"))
        return {"id": dispositivo["id"], "capacidad": capacidad, "alcanza": bloqueo.alcanza(capacidad, nivel)}
