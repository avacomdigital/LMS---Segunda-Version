"""
La asignación vista desde el profesor (FUN-105, 106, 107, 108, 118; CAP-063):

  CrearAsignacion       FUN-108 (+ FUN-105 el nivel, FUN-106 el plazo): asigna un examen de la biblioteca a un grupo o a alumnos
  IniciarAsignacion     publica una asignación en borrador o programada
  CerrarAsignacion      cierre manual: lo respondido se entrega tal cual
  ProrrogarAsignacion   `activa_fuera_de_plazo → activa` con un plazo nuevo
  ReabrirAsignacion     `cerrada → activa`
  ConfigurarPlazo       FUN-106: la fecha límite y la gracia
  EndurecerPlazo        FUN-107: al vencer, la asignación cierra
  DefinirNivel          FUN-105: el nivel mínimo, mientras no haya intentos abiertos
  DegradarNivel         FUN-118: BAJA el nivel de una evaluación en curso
  LiberarResultados     DEC-032: desde aquí el alumno ve su nota
  ListarAsignaciones · VerAsignacion

El examen (sus preguntas, sus claves) NO se crea aquí: FUN-103 y FUN-104 son de la biblioteca (D-2, artículo 14). Aquí sólo se ASIGNA.
"""
from __future__ import annotations

from ..dominio import armado as armado_dom
from ..dominio import asignacion as asig_dom
from ..dominio import bloqueo
from ..dominio import catalogos as cat
from ..dominio.errores import (
    DatosInvalidos,
    IntentosAbiertos,
    NoEncontrado,
    NoEsElTitular,
    TransicionInvalida,
)
from .base import Servicios, _CasoDeUso, exigir_nodo_instalado, nuevo_id
from .motor import Motor
from .puertos import Actor, UnidadDeTrabajo

ABIERTOS = (cat.EN_CURSO, cat.EN_CURSO_FUERA_DE_PLAZO, cat.PAUSADO, cat.RESTAURANDO)


def vista_asignacion(a: dict) -> dict:
    """La asignación hacia afuera: lo guardado más `gracia_min`. Nada de esto es contenido del curso ni una clave."""
    return {**a, "gracia_min": int(a["gracia_ms"] // 60_000)}


class _Docente(_CasoDeUso):
    """Base de los casos de uso del profesor: autorización con titularidad y la asignación al día con el reloj."""

    def __init__(self, servicios: Servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)

    def _asignacion(self, uow: UnidadDeTrabajo, asignacion_id: str, ahora: int, *, asegurar: bool = True) -> dict:
        asignacion = uow.asignaciones.por_id(asignacion_id) if asignacion_id else None
        if asignacion is None:
            raise NoEncontrado("No existe esa evaluación.", asignacion_id=asignacion_id)
        return self.motor.asegurar_asignacion(uow, asignacion, ahora) if asegurar else asignacion

    def _autorizar(self, actor: Actor, permiso: str, asignacion: dict | None = None) -> None:
        self.s.autorizacion.exigir(actor, permiso, asignacion)

    @staticmethod
    def _actor_id(actor: Actor) -> str:
        return actor.id or "docente"

    def _anotar(self, uow: UnidadDeTrabajo, asignacion: dict, accion: str, anterior: dict, nuevo: dict, actor: Actor, motivo: str | None = None) -> None:
        uow.auditoria.registrar(self._actor_id(actor), accion, "m10_asignacion", asignacion["id"], anterior=anterior, nuevo=nuevo,
                                **({"motivo": motivo} if motivo else {}))


# ======================================================================================== crear

class CrearAsignacion(_Docente):
    """FUN-108. `datos`: ver §4.1 del contrato. Devuelve la asignación y `armado_previo` (qué recibirá cada alumno y con qué avisos)."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        tipo = str(datos.get("tipo") or cat.EXAMEN).strip().lower()
        if tipo not in cat.TIPOS_QUE_ACEPTA_LA_API:
            raise DatosInvalidos("Sólo se asigna un examen. La actividad en clase la sigue llevando el aula y la de estudio, el modo de estudio.", tipo=tipo)
        curso_ref = str(datos.get("curso_ref") or "").strip()
        objeto_ref = str(datos.get("objeto_ref") or "").strip()
        if not curso_ref or not objeto_ref:
            raise DatosInvalidos("Faltan `curso_ref` y `objeto_ref`: qué examen de qué curso se asigna.")
        if not str(datos.get("nivel_examen") or "").strip():
            raise DatosInvalidos("Elige el nivel de control del examen (controlado, supervisado o abierto): el sistema no lo preselecciona.")
        nivel = bloqueo.validar_nivel(datos.get("nivel_examen"))
        ahora = self.s.reloj.ahora_ms()
        alcance, destinatarios = asig_dom.validar_alcance(datos.get("alcance"), datos.get("destinatarios"), datos.get("grupo_id"))
        plazo, limite_en, abre_en = asig_dom.validar_plazo(datos.get("plazo"), datos.get("limite_en"), datos.get("abre_en"), ahora)
        gracia_ms = asig_dom.validar_gracia_ms(datos.get("gracia_min"), datos.get("gracia_ms"), self.s.config.gracia_ms)
        intentos = asig_dom.validar_intentos_permitidos(datos["intentos_permitidos"]) if "intentos_permitidos" in datos else 1
        tiempo_modo, tiempo_limite = asig_dom.validar_tiempo(datos.get("tiempo"))
        reactivacion = asig_dom.validar_reactivacion(datos.get("reactivacion"), nivel)
        recursos = asig_dom.validar_recursos(datos.get("recursos"))

        self._autorizar(actor, cat.P_ASSIGN)
        self._autorizar(actor, cat.P_EXAM_MODE_SET)
        if limite_en is not None:
            self._autorizar(actor, cat.P_DEADLINE_SET)
        if plazo == cat.ENDURECIDO:
            self._autorizar(actor, cat.P_DEADLINE_ENFORCE)

        ficha = self.s.contenido.examen(str(datos.get("fuente") or ""), curso_ref, objeto_ref)     # puede lanzar NoEncontrado / FuenteNoDisponible
        ajustes = ficha["ajustes"]
        pool = ficha["pool"]
        resultados = asig_dom.validar_resultados(datos.get("resultados"), ajustes.get("mostrar_resultados") or cat.TRAS_LIBERAR)

        with self.s.uow() as uow:
            exigir_nodo_instalado(uow)
            grupo_id, grupo_rotulo = "", ""
            if alcance == cat.GRUPO:
                grupo = uow.identidad.grupo(str(datos["grupo_id"]).strip())
                if grupo is None:
                    raise NoEncontrado("No existe ese grupo.", grupo_id=datos.get("grupo_id"))
                grupo_id, grupo_rotulo = grupo["id"], grupo["nombre"]
                self._exigir_titular(uow, actor, grupo_id)
            else:
                conocidos = uow.identidad.alumnos_activos(destinatarios)
                faltan = [d for d in destinatarios if d not in conocidos]
                if faltan:
                    raise DatosInvalidos("Hay destinatarios que no existen o no están activos.", destinatarios=faltan)
                grupo_id = str(datos.get("grupo_id") or "").strip()
                grupo_rotulo = (uow.identidad.grupo(grupo_id) or {}).get("nombre", "") if grupo_id else ""
            sesion_id = str(datos.get("sesion_id") or "").strip()
            if sesion_id and uow.aula.sesion(sesion_id) is None:
                raise NoEncontrado("No existe esa clase.", sesion_id=sesion_id)

            estado = cat.BORRADOR
            publicada_en = None
            if bool(datos.get("iniciar")):
                estado = cat.PROGRAMADA if (abre_en is not None and abre_en > ahora) else cat.ACTIVA
                publicada_en = ahora
            nuevo_id_asignacion = nuevo_id()
            estrategia = ajustes.get("estrategia") or armado_dom.FIXED
            por_alumno = self._por_alumno(ajustes, pool)
            previo = self._armado_previo({"id": nuevo_id_asignacion, "estrategia": estrategia, "preguntas_por_alumno": por_alumno,
                                          "tiempo_modo": tiempo_modo, "tiempo_limite_seg": tiempo_limite, "total_banco": len(pool)}, ajustes, pool)
            ajustes = {**ajustes, "limite_seg_estimado": previo["limite_seg_estimado"]}
            fila = uow.asignaciones.crear({
                "id": nuevo_id_asignacion, "tipo": tipo, "sesion_id": sesion_id, "grupo_id": grupo_id, "grupo_rotulo": grupo_rotulo, "alcance": alcance,
                "destinatarios": destinatarios, "profesor_id": self._actor_id(actor)[:64], "profesor_rotulo": (actor.rotulo or "")[:120],
                "fuente_curso": ficha["fuente"], "curso_ref": ficha.get("curso_ref") or curso_ref, "curso_version": ficha["curso_version"],
                "curso_rotulo": ficha.get("curso_rotulo") or "", "leccion_ref": ficha.get("leccion_ref") or "", "objeto_ref": objeto_ref,
                "objeto_rotulo": ficha.get("objeto_rotulo") or "", "titulo": (str(datos.get("titulo") or "").strip() or ficha["titulo"])[:250],
                "estrategia": estrategia, "preguntas_por_alumno": por_alumno, "total_banco": len(pool), "ajustes": ajustes, "nivel_declarado": nivel, "nivel_examen": nivel, "tiempo_modo": tiempo_modo,
                "tiempo_limite_seg": tiempo_limite, "intentos_permitidos": intentos, "abre_en": abre_en, "limite_en": limite_en, "plazo": plazo,
                "gracia_ms": gracia_ms, "reactivacion": reactivacion, "recursos": recursos, "resultados": resultados, "liberados_en": None,
                "aprobacion_pct": ajustes.get("aprobacion_pct"), "permite_retroceso": bool(ajustes.get("navegacion_atras", True)),
                "mezclar_opciones": bool(ajustes.get("barajar_opciones", True)), "estado": estado, "creada_en": ahora,
                "publicada_en": publicada_en, "cerrada_en": None, "archivada_en": None, "creado_por": self._actor_id(actor)[:64]})
            base = {"asignacion_id": fila["id"], "curso_ref": curso_ref, "curso_version": fila["curso_version"], "objeto_ref": objeto_ref,
                    "grupo_id": grupo_id, "alcance": alcance}
            self.motor.publicar(uow, "Asignacion", fila["id"], cat.EV_NIVEL_DEFINIDO, {**base, "nivel_examen": nivel}, ahora)
            if limite_en is not None:
                self.motor.publicar(uow, "Asignacion", fila["id"], cat.EV_PLAZO_CONFIGURADO, {
                    **base, "limite_en": limite_en, "plazo": plazo, "gracia_ms": gracia_ms}, ahora)
            if publicada_en is not None:
                self.motor.publicar(uow, "Asignacion", fila["id"], cat.EV_ASIGNADA, {
                    **base, "nivel_examen": nivel, "limite_en": limite_en, "intentos_permitidos": intentos, "ponderacion": None}, ahora)
            uow.auditoria.registrar(self._actor_id(actor), "evaluacion.asignada", "m10_asignacion", fila["id"],
                                    nuevo={"estado": estado, "nivel_examen": nivel, "plazo": plazo, "objeto_ref": objeto_ref,
                                           "curso_version": fila["curso_version"], "alcance": alcance})
            self.motor.avisar(uow, fila)
            return {**vista_asignacion(fila), "armado_previo": previo}

    def _exigir_titular(self, uow: UnidadDeTrabajo, actor: Actor, grupo_id: str) -> None:
        """Con sesión, el profesor asigna sólo a sus grupos; la administración (nivel 3) a cualquiera. Sin sesión (Q-34) no se comprueba."""
        if actor.autenticado and actor.nivel < 3 and not uow.identidad.es_docente_del_grupo(grupo_id, actor.id):
            raise NoEsElTitular("Sólo el profesor del grupo (o la administración) le asigna un examen.", grupo_id=grupo_id)

    @staticmethod
    def _por_alumno(ajustes: dict, pool: list[dict]) -> int:
        if ajustes.get("estrategia") == armado_dom.RANDOM_BALANCED:
            return min(int(ajustes.get("cantidad_preguntas") or len(pool)), len(pool))
        return len(pool)

    def _armado_previo(self, fila: dict, ajustes: dict, pool: list[dict]) -> dict:
        """Qué recibirá cada alumno y con qué avisos (PAN-060): un armado de prueba con una semilla fija, sin guardar nada."""
        avisos: list[str] = []
        estimado = 0
        try:
            prueba = armado_dom.armar(pool, estrategia=fila["estrategia"], cantidad=fila["preguntas_por_alumno"],
                                      tolerancia_dificultad_pct=ajustes.get("tolerancia_dificultad_pct"),
                                      tolerancia_tiempo_pct=ajustes.get("tolerancia_tiempo_pct"),
                                      cubrir_temas=bool(ajustes.get("cubrir_todos_los_temas")), semilla="previo|" + fila["id"],
                                      intentos=self.s.config.armado_intentos)
            avisos = list(prueba.avisos)
            estimado = prueba.tiempo_total_seg
        except DatosInvalidos:
            avisos.append("E-EXAM-POOL-EMPTY")
        if fila["estrategia"] == armado_dom.RANDOM_BALANCED and int(ajustes.get("cantidad_preguntas") or 0) > len(pool):
            avisos.append("W-EXAM-POOL-SMALL")
        tiempo = ajustes.get("tiempo") or {}
        limite = armado_dom.limite_en_segundos(tiempo.get("politica"), estimado_seg=estimado, fijo_seg=tiempo.get("fijo_seg"),
                                               extra_pct=tiempo.get("extra_pct"))
        if fila["tiempo_modo"] == cat.TIEMPO_FIJO:
            limite = fila["tiempo_limite_seg"]
        elif fila["tiempo_modo"] == cat.SIN_LIMITE:
            limite = None
        return {"estrategia": fila["estrategia"], "preguntas_por_alumno": fila["preguntas_por_alumno"], "total_banco": fila["total_banco"],
                "limite_seg_estimado": limite, "avisos": sorted(set(avisos))}


# ================================================================================ cambios de estado

class IniciarAsignacion(_Docente):
    """Publica una asignación en `borrador` (o `programada`, para empezar ya)."""

    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_ASSIGN, asignacion)
            if asignacion["estado"] not in (cat.BORRADOR, cat.PROGRAMADA):
                raise TransicionInvalida(f"La evaluación está «{asignacion['estado']}»: sólo se inicia una en borrador o programada.",
                                         estado=asignacion["estado"], destino=cat.ACTIVA)
            programada = asignacion["estado"] == cat.BORRADOR and asignacion.get("abre_en") is not None and asignacion["abre_en"] > ahora
            destino = cat.PROGRAMADA if programada else cat.ACTIVA
            asig_dom.comprobar_transicion(asignacion["estado"], destino)
            anterior = asignacion["estado"]
            asignacion = uow.asignaciones.actualizar(asignacion_id, estado=destino, publicada_en=ahora)
            self.motor.publicar(uow, "Asignacion", asignacion_id, cat.EV_ASIGNADA, {
                "asignacion_id": asignacion_id, "curso_ref": asignacion["curso_ref"], "curso_version": asignacion["curso_version"],
                "objeto_ref": asignacion["objeto_ref"], "grupo_id": asignacion["grupo_id"], "alcance": asignacion["alcance"],
                "nivel_examen": asignacion["nivel_examen"], "limite_en": asignacion["limite_en"], "ponderacion": None}, ahora)
            self._anotar(uow, asignacion, "evaluacion.asignada", {"estado": anterior}, {"estado": destino}, actor)
            self.motor.avisar(uow, asignacion)
            return vista_asignacion(asignacion)


class CerrarAsignacion(_Docente):
    """Cierre manual: lo respondido se entrega tal cual y los `no_iniciado` quedan como evidencia (§5.1 del modelo)."""

    def ejecutar(self, actor: Actor, asignacion_id: str, motivo: str = "") -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_ASSIGN, asignacion)
            asig_dom.comprobar_transicion(asignacion["estado"], cat.CERRADA)
            anterior = asignacion["estado"]
            asignacion = uow.asignaciones.actualizar(asignacion_id, estado=cat.CERRADA, cerrada_en=ahora)
            entregados = self.motor._entregar_abiertos(uow, asignacion, ahora, ahora, cat.O_CIERRE)
            self.motor.publicar(uow, "Asignacion", asignacion_id, cat.EV_ASIGNACION_CERRADA, {
                "asignacion_id": asignacion_id, "origen": "profesor", "cerrada_en": ahora, "entregados": entregados}, ahora)
            self._anotar(uow, asignacion, "evaluacion.asignacion.cerrada", {"estado": anterior}, {"estado": cat.CERRADA, "entregados": entregados},
                         actor, motivo=(motivo or None))
            self.motor.avisar(uow, asignacion)
            return {**vista_asignacion(asignacion), "entregados": entregados}


class ProrrogarAsignacion(_Docente):
    """`activa_fuera_de_plazo → activa` con un plazo nuevo (o sólo mueve el plazo de una `activa`)."""

    def ejecutar(self, actor: Actor, asignacion_id: str, limite_en) -> dict:
        ahora = self.s.reloj.ahora_ms()
        nuevo = asig_dom.validar_limite_futuro(limite_en, ahora)
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_DEADLINE_SET, asignacion)
            if asignacion["estado"] not in (cat.ACTIVA, cat.ACTIVA_FUERA_DE_PLAZO):
                raise TransicionInvalida(f"La evaluación está «{asignacion['estado']}»: sólo se prorroga una abierta.",
                                         estado=asignacion["estado"], destino=cat.ACTIVA)
            anterior = {"estado": asignacion["estado"], "limite_en": asignacion["limite_en"]}
            campos = {"limite_en": nuevo}
            if asignacion["estado"] == cat.ACTIVA_FUERA_DE_PLAZO:
                asig_dom.comprobar_transicion(asignacion["estado"], cat.ACTIVA)
                campos["estado"] = cat.ACTIVA
            asignacion = uow.asignaciones.actualizar(asignacion_id, **campos)
            self.motor.publicar(uow, "Asignacion", asignacion_id, cat.EV_PLAZO_CONFIGURADO, {
                "asignacion_id": asignacion_id, "limite_en": nuevo, "plazo": asignacion["plazo"], "prorroga": True}, ahora)
            self._anotar(uow, asignacion, "evaluacion.asignacion.prorrogada", anterior, {"estado": asignacion["estado"], "limite_en": nuevo}, actor)
            self.motor.avisar(uow, asignacion)
            return vista_asignacion(asignacion)


class ReabrirAsignacion(_Docente):
    """`cerrada → activa` por decisión del profesor. Con plazo endurecido hace falta un plazo nuevo en el futuro: reabrir con el viejo cerraría otra
    vez al instante."""

    def ejecutar(self, actor: Actor, asignacion_id: str, limite_en=None) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_ASSIGN, asignacion)
            asig_dom.comprobar_transicion(asignacion["estado"], cat.ACTIVA)
            nuevo = asig_dom.validar_limite_futuro(limite_en, ahora) if limite_en not in (None, "", 0) else asignacion.get("limite_en")
            if asignacion["plazo"] == cat.ENDURECIDO and (nuevo is None or nuevo <= ahora):
                raise DatosInvalidos("Con plazo endurecido hay que fijar un `limite_en` en el futuro: reabrir con el plazo vencido la cerraría al instante.")
            anterior = {"estado": asignacion["estado"], "limite_en": asignacion["limite_en"]}
            asignacion = uow.asignaciones.actualizar(asignacion_id, estado=cat.ACTIVA, cerrada_en=None, limite_en=nuevo)
            self._anotar(uow, asignacion, "evaluacion.asignacion.reabierta", anterior, {"estado": cat.ACTIVA, "limite_en": nuevo}, actor)
            self.motor.avisar(uow, asignacion)
            return vista_asignacion(asignacion)


class ConfigurarPlazo(_Docente):
    """FUN-106: la fecha límite (y la gracia). El plazo sigue siendo el que era; endurecerlo es FUN-107."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_DEADLINE_SET, asignacion)
            if asignacion["estado"] in cat.CON_CIERRE:
                raise TransicionInvalida("La evaluación ya cerró: reábrela antes de cambiar su plazo.", estado=asignacion["estado"], destino=cat.ACTIVA)
            campos: dict = {}
            if "limite_en" in datos:
                _, limite, _ = asig_dom.validar_plazo(asignacion["plazo"], datos.get("limite_en"), asignacion.get("abre_en"), ahora)
                if limite is not None and limite <= ahora and asignacion["plazo"] == cat.ENDURECIDO:
                    raise DatosInvalidos("Con plazo endurecido la fecha límite debe estar en el futuro: cerraría la evaluación ahora.")
                campos["limite_en"] = limite
            if "gracia_min" in datos or "gracia_ms" in datos:
                campos["gracia_ms"] = asig_dom.validar_gracia_ms(datos.get("gracia_min"), datos.get("gracia_ms"), asignacion["gracia_ms"])
            if not campos:
                raise DatosInvalidos("No hay nada que cambiar: manda `limite_en` y/o `gracia_min`.")
            anterior = {k: asignacion[k] for k in campos}
            asignacion = uow.asignaciones.actualizar(asignacion_id, **campos)
            self.motor.publicar(uow, "Asignacion", asignacion_id, cat.EV_PLAZO_CONFIGURADO, {
                "asignacion_id": asignacion_id, "limite_en": asignacion["limite_en"], "plazo": asignacion["plazo"],
                "gracia_ms": asignacion["gracia_ms"]}, ahora)
            self._anotar(uow, asignacion, "evaluacion.plazo.configurado", anterior, campos, actor)
            return vista_asignacion(self.motor.asegurar_asignacion(uow, asignacion, ahora))


class EndurecerPlazo(_Docente):
    """FUN-107: al vencer, la asignación cierra. Exige un plazo blando VIGENTE (con fecha en el futuro)."""

    def ejecutar(self, actor: Actor, asignacion_id: str, limite_en=None) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_DEADLINE_ENFORCE, asignacion)
            if asignacion["estado"] not in cat.ABIERTAS or asignacion["plazo"] != cat.BLANDO:
                raise TransicionInvalida("Sólo se endurece una evaluación abierta con plazo blando.", estado=asignacion["estado"], plazo=asignacion["plazo"])
            nuevo = asig_dom.validar_limite_futuro(limite_en, ahora) if limite_en not in (None, "", 0) else asignacion.get("limite_en")
            if nuevo is None or nuevo <= ahora:
                raise TransicionInvalida("Endurecer exige un plazo blando vigente: fija `limite_en` en el futuro.", estado=asignacion["estado"])
            anterior = {"plazo": asignacion["plazo"], "limite_en": asignacion["limite_en"], "estado": asignacion["estado"]}
            campos = {"plazo": cat.ENDURECIDO, "limite_en": nuevo}
            if asignacion["estado"] == cat.ACTIVA_FUERA_DE_PLAZO:
                campos["estado"] = cat.ACTIVA
            asignacion = uow.asignaciones.actualizar(asignacion_id, **campos)
            self.motor.publicar(uow, "Asignacion", asignacion_id, cat.EV_PLAZO_ENDURECIDO, {
                "asignacion_id": asignacion_id, "limite_en": nuevo, "gracia_ms": asignacion["gracia_ms"]}, ahora)
            self._anotar(uow, asignacion, "evaluacion.plazo.endurecido", anterior,
                         {"plazo": cat.ENDURECIDO, "limite_en": nuevo, "estado": asignacion["estado"]}, actor)
            self.motor.avisar(uow, asignacion)
            return vista_asignacion(asignacion)


class DefinirNivel(_Docente):
    """FUN-105: fija el nivel mínimo de modo examen. Precondición: la evaluación no tiene intentos abiertos."""

    def ejecutar(self, actor: Actor, asignacion_id: str, nivel) -> dict:
        nivel = bloqueo.validar_nivel(nivel)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_EXAM_MODE_SET, asignacion)
            if asignacion["estado"] in cat.CON_CIERRE:
                raise TransicionInvalida("La evaluación ya cerró.", estado=asignacion["estado"], destino=cat.ACTIVA)
            abiertos = [i for i in uow.intentos.de_asignacion(asignacion_id, ABIERTOS)]
            if abiertos:
                raise IntentosAbiertos("Hay intentos abiertos: durante el examen el nivel sólo se puede bajar (degradar).", abiertos=len(abiertos))
            anterior = {"nivel_declarado": asignacion["nivel_declarado"], "nivel_examen": asignacion["nivel_examen"]}
            asignacion = uow.asignaciones.actualizar(asignacion_id, nivel_declarado=nivel, nivel_examen=nivel)
            self.motor.publicar(uow, "Asignacion", asignacion_id, cat.EV_NIVEL_DEFINIDO, {
                "asignacion_id": asignacion_id, "nivel_examen": nivel}, ahora)
            self._anotar(uow, asignacion, "evaluacion.nivel.definido", anterior, {"nivel_declarado": nivel, "nivel_examen": nivel}, actor)
            self.motor.avisar(uow, asignacion)
            return vista_asignacion(asignacion)


class DegradarNivel(_Docente):
    """FUN-118: baja el nivel de una evaluación EN CURSO (nunca sube). Cada intento vivo cuyo nivel efectivo era mayor pasa al nuevo y deja un
    incidente `degradacion`; el plan de bloqueo cambia en su siguiente latido y la tableta suelta lo que ya no se exige."""

    def ejecutar(self, actor: Actor, asignacion_id: str, nivel, motivo: str = "") -> dict:
        nivel = bloqueo.validar_nivel(nivel)
        motivo = str(motivo or "").strip()
        if len(motivo) < 3:
            raise DatosInvalidos("Degradar el nivel exige un motivo: queda en el expediente de cada intento afectado.")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_DOWNGRADE, asignacion)
            if asignacion["estado"] not in cat.ABIERTAS:
                raise TransicionInvalida("Sólo se degrada una evaluación en curso.", estado=asignacion["estado"], destino=asignacion["estado"])
            vigente = asignacion["nivel_examen"]
            bloqueo.validar_degradacion(vigente, nivel)
            asignacion = uow.asignaciones.actualizar(asignacion_id, nivel_examen=nivel)
            afectados = 0
            for it in uow.intentos.de_asignacion(asignacion_id, cat.VIVOS):
                if bloqueo.rango(it["nivel_efectivo"]) > bloqueo.rango(nivel):
                    previo = it["nivel_efectivo"]
                    it = uow.intentos.actualizar(it["id"], nivel_efectivo=nivel)
                    if it["estado"] != cat.NO_INICIADO:
                        self.motor.incidente(uow, it, "degradacion", ahora, detalle={"de": previo, "a": nivel, "por": self._actor_id(actor),
                                                                                      "motivo": motivo}, actor=self._actor_id(actor), asignacion=asignacion)
                    afectados += 1
            self.motor.publicar(uow, "Asignacion", asignacion_id, cat.EV_NIVEL_DEGRADADO, {
                "asignacion_id": asignacion_id, "de": vigente, "a": nivel, "afectados": afectados, "por": self._actor_id(actor)}, ahora)
            self._anotar(uow, asignacion, "evaluacion.nivel.degradado", {"nivel_examen": vigente},
                         {"nivel_examen": nivel, "afectados": afectados}, actor, motivo=motivo)
            self.motor.avisar(uow, asignacion)
            return {**vista_asignacion(asignacion), "afectados": afectados}


class LiberarResultados(_Docente):
    """DEC-032: desde aquí el alumno ve su nota (si la asignación no es `nunca`). Idempotente: la primera liberación manda."""

    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_RESULTS_VIEW, asignacion)
            abiertos = uow.intentos.de_asignacion(asignacion_id, ABIERTOS)
            if abiertos:
                raise IntentosAbiertos("Aún hay alumnos presentando el examen: libera los resultados cuando todos hayan entregado.", abiertos=len(abiertos))
            if asignacion.get("liberados_en") is None:
                asignacion = uow.asignaciones.actualizar(asignacion_id, liberados_en=ahora)
                self.motor.publicar(uow, "Asignacion", asignacion_id, cat.EV_RESULTADOS_LIBERADOS, {
                    "asignacion_id": asignacion_id, "liberados_en": ahora}, ahora)
                self._anotar(uow, asignacion, "evaluacion.resultados.liberados", {"liberados_en": None}, {"liberados_en": ahora}, actor)
                self.motor.avisar(uow, asignacion)
            return vista_asignacion(asignacion)


# ======================================================================================= consultas

class ListarAsignaciones(_Docente):
    def ejecutar(self, actor: Actor, *, estado: str | None = None, grupo_id: str | None = None, sesion_id: str | None = None,
                 profesor_id: str | None = None) -> list[dict]:
        from .panel import totales_de

        self._autorizar(actor, cat.P_READ)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            filas = uow.asignaciones.listar(estados=(estado,) if estado else None, grupo_id=grupo_id or None, sesion_id=sesion_id or None,
                                            profesor_id=profesor_id or None)
            salida = []
            for fila in filas:
                fila = self.motor.asegurar_asignacion(uow, fila, ahora)
                salida.append({**vista_asignacion(fila), "totales": totales_de(uow, fila)})
            return salida


class VerAsignacion(_Docente):
    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        from .panel import totales_de

        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self._autorizar(actor, cat.P_READ, asignacion)
            return {**vista_asignacion(asignacion), "totales": totales_de(uow, asignacion)}


# ================================================================== FUN-103 y FUN-104 (son de la biblioteca)

class RechazarAdministracion(_CasoDeUso):
    """FUN-103 (crear una evaluación con banco) y FUN-104 (añadir un reactivo) NO ocurren en el LMS: son de AVACOM Biblioteca (artículo 14, 14.2). Se rechaza
    con una explicación que nombra al dueño y el intento queda en la bitácora; el asiento se escribe ANTES de rechazar para que no se revierta con el error."""

    def ejecutar(self, actor: Actor, operacion: str) -> None:
        from ..dominio.errores import AdministracionNoPermitida

        with self.s.uow() as uow:
            uow.auditoria.registrar(actor.id or "cliente", "administracion.rechazada", "", "", nuevo={"operacion": operacion, "modulo": "MOD-010"})
        raise AdministracionNoPermitida(
            f"«{operacion}» se hace en AVACOM Biblioteca, dueña del curso y de sus exámenes (artículo 14). Aquí sólo se asigna un examen ya publicado.",
            operacion=operacion, dueno="AVACOM Biblioteca")
