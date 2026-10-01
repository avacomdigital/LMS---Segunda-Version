"""
El intento, desde la tableta y desde el profesor (FUN-109, FUN-114; PAN-061, PAN-120…123; CAP-063, CAP-064):

  AbrirIntento        FUN-109: abre (o reanuda) el intento del alumno. Compara el nivel con la capacidad DECLARADA de la tableta (BR-075): si no
                      alcanza, el intento NO se abre solo y espera la decisión del profesor (BR-076). Idempotente: devuelve el intento vivo.
  EstadoDelIntento    el sondeo de la tableta (`GET /estado/`)
  Latido              el punto de recuperación de 5 s (INV-010): prueba de vida, pregunta actual y reconciliación del reloj
  PreguntasDelIntento el examen DE ESTE ALUMNO, sin claves, en el orden de su armado
  MedioDelIntento     los bytes de un medio de una pregunta de ESTE examen
  EntregarIntento     FUN-114: entregar y cerrar
  ReactivarIntento    PAN-061: sólo el profesor reanuda a un alumno suspendido (salvo reactivación automática de la asignación)
  ReactivarTodos      reactiva a todos los suspendidos y dice a cuántos afecta
  CerrarIntento       «cierre forzado» de un intento suspendido
  AnularIntento       la ÚNICA flecha hacia `anulado` (INV-018): una persona, con motivo

Los incidentes NUNCA cambian el estado del intento (BR-077). Ninguna función de este archivo anula por su cuenta.
"""
from __future__ import annotations

from ..dominio import armado as armado_dom
from ..dominio import asignacion as asig_dom
from ..dominio import bloqueo
from ..dominio import catalogos as cat
from ..dominio import intento as int_dom
from ..dominio.errores import (
    AdmisionRechazada,
    AsignacionNoAbierta,
    ConfirmacionRequerida,
    DatosInvalidos,
    FuenteNoDisponible,
    IntentosAgotados,
    NoEncontrado,
    TransicionInvalida,
    VersionNoDisponible,
)
from .alumno import _Alumno
from .base import Contexto, _CasoDeUso, asignacion_del_alumno, nuevo_id
from .motor import Motor
from .puertos import Actor, Bytes, UnidadDeTrabajo
from .respuestas import EnviarRespuestas

SISTEMA = cat.SISTEMA


# ============================================================================================ abrir

class AbrirIntento(_Alumno):
    """`datos`: `{dispositivo, alumno_id, nombre?, plataforma?, version_app?, capacidad_control?}`. Devuelve `(cuerpo, http)`:
    201 abierto · 200 ya había uno vivo (se reanuda) · 202 espera la decisión del profesor."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict) -> tuple[dict, int]:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora, registrar=True, exigir_aparato=True)
            self.s.autorizacion.exigir(actor, cat.P_ATTEMPT_START)
            asignacion = asignacion_del_alumno(uow, ctx, asignacion_id)
            asignacion = self.motor.asegurar_asignacion(uow, asignacion, ahora)
            propios = uow.intentos.del_alumno(asignacion_id, ctx.alumno_id)
            vivo = next((i for i in propios if i["estado"] in cat.VIVOS), None)
            if vivo is not None and vivo["estado"] != cat.NO_INICIADO:
                return self._reanudar(uow, ctx, asignacion, vivo, ahora)
            if not asig_dom.abierta(asignacion["estado"]):
                raise AsignacionNoAbierta(f"La evaluación está «{asignacion['estado']}»: todavía no recibe intentos o ya cerró.",
                                          motivo=asignacion["estado"], asignacion_id=asignacion_id)
            usados = sum(1 for i in propios if i["estado"] not in (cat.NO_INICIADO, cat.ANULADO))
            permitidos = asignacion.get("intentos_permitidos")
            if vivo is None and permitidos is not None and usados >= permitidos:
                raise IntentosAgotados(f"La evaluación admite {permitidos} intento(s) y ya se usaron.", intentos_permitidos=permitidos,
                                       intentos_usados=usados)
            nivel, admision, veredicto = self._evaluar_nivel(uow, ctx, asignacion, asignacion["nivel_examen"], ahora)
            if veredicto == "rechazado":
                raise AdmisionRechazada(cat.MENSAJE_RECHAZADA, admision_id=admision["id"], motivo=admision.get("motivo", ""))
            if veredicto == "espera":
                espera = vivo or self._crear_en_espera(uow, ctx, asignacion, propios, asignacion["nivel_examen"], ahora)
                return {"intento": {"id": espera["id"], "estado": cat.NO_INICIADO, "numero": espera["numero"]},
                        "admision": self._vista_admision(admision), "mensaje": {"codigo": "espera_admision", "texto": cat.MENSAJE_EN_ESPERA},
                        "condiciones": bloqueo.condiciones(asignacion["nivel_examen"]), "servidor_en": ahora}, 202
            return self._abrir(uow, ctx, asignacion, propios, vivo, nivel, admision, ahora), 201

    # ------------------------------------------------------------------------- nivel contra capacidad (BR-075)

    def _evaluar_nivel(self, uow: UnidadDeTrabajo, ctx: Contexto, asignacion: dict, requerido: str, ahora: int) -> tuple[str | None, dict | None, str]:
        """(nivel con el que correrá, admisión, veredicto) donde veredicto es `alcanza` · `admitido` · `espera` · `rechazado`."""
        if bloqueo.alcanza(ctx.capacidad, requerido):
            return requerido, None, "alcanza"
        admision = uow.admisiones.de_terna(asignacion["id"], ctx.alumno_id, ctx.dispositivo_id)
        if admision is None:
            admision = uow.admisiones.crear({
                "id": nuevo_id(), "asignacion_id": asignacion["id"], "alumno_id": ctx.alumno_id, "alumno_rotulo": ctx.alumno_rotulo,
                "dispositivo_id": ctx.dispositivo_id, "dispositivo_rotulo": (ctx.dispositivo or {}).get("nombre", ""),
                "nivel_exigido": requerido, "nivel_alcanzado": ctx.capacidad, "estado": cat.EN_ESPERA, "nivel_admitido": "", "motivo": "",
                "solicitada_en": ahora, "decidido_por": "", "decidido_en": None})
            self.motor.publicar(uow, "Admision", admision["id"], cat.EV_ADMISION_SOLICITADA, {
                "admision_id": admision["id"], "asignacion_id": asignacion["id"], "alumno_id": ctx.alumno_id, "dispositivo_id": ctx.dispositivo_id,
                "nivel_exigido": requerido, "nivel_alcanzado": ctx.capacidad}, ahora)
            self.motor.avisar(uow, asignacion, "evaluacion_panel", admision_id=admision["id"])
            return None, admision, "espera"
        if admision["estado"] == cat.ADMITIDO:
            admitido = admision["nivel_admitido"]
            return (admitido if bloqueo.es_menor(admitido, requerido) else requerido), admision, "admitido"
        if admision["estado"] == cat.RECHAZADO:
            return None, admision, "rechazado"
        if admision["nivel_exigido"] != requerido or admision["nivel_alcanzado"] != ctx.capacidad:      # la tableta o el nivel cambiaron
            admision = uow.admisiones.actualizar(admision["id"], nivel_exigido=requerido, nivel_alcanzado=ctx.capacidad)
        return None, admision, "espera"

    @staticmethod
    def _vista_admision(a: dict) -> dict:
        return {"id": a["id"], "estado": a["estado"], "nivel_exigido": a["nivel_exigido"], "nivel_alcanzado": a["nivel_alcanzado"],
                "nivel_admitido": a.get("nivel_admitido", ""), "motivo": a.get("motivo", "")}

    # --------------------------------------------------------------------------------------- abrir uno nuevo

    def _crear_en_espera(self, uow: UnidadDeTrabajo, ctx: Contexto, asignacion: dict, propios: list[dict], nivel: str, ahora: int) -> dict:
        """El intento `no_iniciado` que reserva el lugar mientras el profesor decide: nace sin examen armado y con el reloj detenido."""
        numero = max([i["numero"] for i in propios] or [0]) + 1
        return uow.intentos.crear({**self._base(asignacion, ctx, numero, ahora), "estado": cat.NO_INICIADO, "nivel_efectivo": nivel,
                                   "dispositivo_id": ctx.dispositivo_id})

    @staticmethod
    def _base(asignacion: dict, ctx: Contexto, numero: int, ahora: int) -> dict:
        return {"id": nuevo_id(), "asignacion_id": asignacion["id"], "alumno_id": ctx.alumno_id, "alumno_rotulo": ctx.alumno_rotulo, "numero": numero,
                "bloqueo": {}, "sesion_ref": "", "sesiones": [], "semilla": "", "curso_version": asignacion["curso_version"], "armado": [],
                "armado_meta": {}, "tiempo_limite_seg": None, "consumido_ms": 0, "reloj_desde": None, "pausas": [], "ultimo_latido_en": None,
                "pregunta_actual": "", "respuestas": [], "secuencia_maxima": 0, "sin_calificar": 0, "requiere_revision": False,
                "calificacion_pendiente": False, "fuera_de_plazo": False, "origen_entrega": "", "envio_tardio": "", "respuestas_pendientes": [],
                "decision_envio": {}, "creado_en": ahora}

    def _abrir(self, uow: UnidadDeTrabajo, ctx: Contexto, asignacion: dict, propios: list[dict], espera: dict | None, nivel: str,
               admision: dict | None, ahora: int) -> dict:
        """FUN-109: arma el examen de ESTE alumno, congela la versión y empieza su reloj. `espera` es el `no_iniciado` que se reutiliza."""
        ficha = self.s.contenido.examen(asignacion["fuente_curso"], asignacion["curso_ref"], asignacion["objeto_ref"])
        if asignacion["curso_version"] and ficha.get("curso_version") and ficha["curso_version"] != asignacion["curso_version"]:
            raise VersionNoDisponible(
                f"El curso cambió de versión ({asignacion['curso_version']} → {ficha['curso_version']}) desde que se asignó el examen: tu profesor debe volver a asignarlo.",
                asignada=asignacion["curso_version"], instalada=ficha["curso_version"])
        numero = espera["numero"] if espera else max([i["numero"] for i in propios] or [0]) + 1
        semilla = armado_dom.semilla_del_intento(asignacion["id"], ctx.alumno_id, numero)
        ajustes = asignacion.get("ajustes") or {}
        armado = armado_dom.armar(ficha["pool"], estrategia=asignacion["estrategia"] or armado_dom.FIXED, cantidad=asignacion["preguntas_por_alumno"],
                                  tolerancia_dificultad_pct=ajustes.get("tolerancia_dificultad_pct"),
                                  tolerancia_tiempo_pct=ajustes.get("tolerancia_tiempo_pct"),
                                  cubrir_temas=bool(ajustes.get("cubrir_todos_los_temas")), semilla=semilla, intentos=self.s.config.armado_intentos)
        sesion = uow.dispositivos.abrir_sesion_alumno(ctx.alumno_id, ctx.dispositivo_id, ahora, actor=ctx.alumno_id)
        fuera = asignacion["estado"] == cat.ACTIVA_FUERA_DE_PLAZO
        apertura = int_dom.abrir({"estado": cat.NO_INICIADO}, ahora, fuera_de_plazo=fuera)
        campos = {**apertura, "nivel_efectivo": nivel, "dispositivo_id": ctx.dispositivo_id, "sesion_ref": sesion["id"],
                  "sesiones": [{"sesion_ref": sesion["id"], "orden": int(sesion.get("iniciada_en") or ahora), "dispositivo_id": ctx.dispositivo_id,
                                "desde": ahora, "hasta": None}],
                  "semilla": semilla, "curso_version": asignacion["curso_version"] or ficha.get("curso_version", ""), "armado": armado.refs,
                  "armado_meta": armado.meta(), "tiempo_limite_seg": self._limite(asignacion, ajustes, armado),
                  "pregunta_actual": armado.refs[0] if armado.refs else ""}
        if espera:
            fila = uow.intentos.actualizar(espera["id"], **campos)
        else:
            fila = uow.intentos.crear({**self._base(asignacion, ctx, numero, ahora), **campos})
        self.motor.publicar(uow, "Intento", fila["id"], cat.EV_INTENTO_ABIERTO, {
            "intento_id": fila["id"], "asignacion_id": asignacion["id"], "curso_ref": asignacion["curso_ref"], "version": fila["curso_version"],
            "alumno_id": ctx.alumno_id, "grupo_id": asignacion["grupo_id"], "dispositivo_id": ctx.dispositivo_id,
            "nivel_examen_efectivo": nivel, "numero": numero}, ahora)
        uow.auditoria.registrar(ctx.alumno_id, cat.A_INTENTO_ABIERTO, "m10_intento_formal", fila["id"],
                                nuevo={"estado": fila["estado"], "numero": numero, "nivel_efectivo": nivel, "preguntas": len(armado.refs)},
                                dispositivo_id=ctx.dispositivo_id or None)
        self.motor.avisar(uow, asignacion, "evaluacion_panel", intento_id=fila["id"])
        return self._cuerpo_de_apertura(fila, asignacion, ctx, ahora, reanudado=False)

    @staticmethod
    def _limite(asignacion: dict, ajustes: dict, armado: armado_dom.Armado) -> int | None:
        if asignacion["tiempo_modo"] == cat.SIN_LIMITE:
            return None
        if asignacion["tiempo_modo"] == cat.TIEMPO_FIJO:
            return asignacion["tiempo_limite_seg"]
        tiempo = ajustes.get("tiempo") or {}
        return armado_dom.limite_en_segundos(tiempo.get("politica"), estimado_seg=armado.tiempo_total_seg, fijo_seg=tiempo.get("fijo_seg"),
                                             extra_pct=tiempo.get("extra_pct"))

    def _cuerpo_de_apertura(self, intento: dict, asignacion: dict, ctx: Contexto, ahora: int, *, reanudado: bool) -> dict:
        estado = self.motor.estado_del_intento(intento, asignacion, ctx.capacidad, ahora)
        return {"intento": estado["intento"], "reloj": estado["reloj"], "plan_bloqueo": estado["plan_bloqueo"],
                "condiciones": bloqueo.condiciones(intento["nivel_efectivo"]), "preguntas_total": len(intento["armado"]),
                "espera_reactivacion": estado["espera_reactivacion"], "mensaje": estado["mensaje"], "reanudado": reanudado,
                "latido_seg": estado["latido_seg"], "servidor_en": ahora}

    # ------------------------------------------------------------------------------ reanudar (y cambiar de tableta)

    def _reanudar(self, uow: UnidadDeTrabajo, ctx: Contexto, asignacion: dict, vivo: dict, ahora: int) -> tuple[dict, int]:
        vivo = self.motor.asegurar_intento(uow, vivo, asignacion, ahora)
        if vivo["estado"] not in cat.VIVOS:                         # el tiempo se agotó mientras tanto
            return self._cuerpo_de_apertura(vivo, asignacion, ctx, ahora, reanudado=True), 200
        cambia_de_tableta = ctx.dispositivo_id != vivo["dispositivo_id"]
        cambia_sesion = False
        campos: dict = {}
        if cambia_de_tableta:
            requerido = bloqueo.es_menor(vivo["nivel_efectivo"], asignacion["nivel_examen"]) and vivo["nivel_efectivo"] or asignacion["nivel_examen"]
            nivel, admision, veredicto = self._evaluar_nivel(uow, ctx, asignacion, requerido, ahora)
            if veredicto == "rechazado":
                raise AdmisionRechazada(cat.MENSAJE_RECHAZADA, admision_id=admision["id"], motivo=admision.get("motivo", ""))
            if veredicto == "espera":
                return {"intento": {"id": vivo["id"], "estado": vivo["estado"], "numero": vivo["numero"]}, "admision": self._vista_admision(admision),
                        "mensaje": {"codigo": "espera_admision", "texto": cat.MENSAJE_EN_ESPERA}, "servidor_en": ahora}, 202
            if bloqueo.es_menor(nivel, vivo["nivel_efectivo"]):
                campos["nivel_efectivo"] = nivel
            cambia_sesion = True
        sesion = uow.dispositivos.abrir_sesion_alumno(ctx.alumno_id, ctx.dispositivo_id, ahora, actor=ctx.alumno_id)
        if cambia_de_tableta or sesion["id"] != vivo["sesion_ref"]:
            sesiones = [dict(s) for s in vivo.get("sesiones") or []]
            for previa in reversed(sesiones):
                if previa.get("hasta") is None:
                    previa["hasta"] = ahora
                    break
            sesiones.append({"sesion_ref": sesion["id"], "orden": int(sesion.get("iniciada_en") or ahora), "dispositivo_id": ctx.dispositivo_id,
                             "desde": ahora, "hasta": None})
            campos.update(sesiones=sesiones, sesion_ref=sesion["id"], dispositivo_id=ctx.dispositivo_id)
            cambia_sesion = True
        if cambia_sesion and vivo["estado"] in cat.CORRIENDO:
            campos["ultimo_latido_en"] = ahora
        if campos:
            anterior_dispositivo = vivo["dispositivo_id"]
            vivo = uow.intentos.actualizar(vivo["id"], **campos)
            if cambia_de_tableta:
                self.motor.incidente(uow, vivo, "cambio_de_dispositivo", ahora, detalle={"de": anterior_dispositivo, "a": ctx.dispositivo_id},
                                     dispositivo_id=ctx.dispositivo_id, asignacion=asignacion)
        return self._cuerpo_de_apertura(vivo, asignacion, ctx, ahora, reanudado=True), 200


# ===================================================================================== estado y latido

class EstadoDelIntento(_Alumno):
    def ejecutar(self, actor: Actor, intento_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            intento, asignacion = self.cargar(uow, ctx, intento_id, ahora)
            return self.motor.estado_del_intento(intento, asignacion, ctx.capacidad, ahora, sesion_activa=self.es_la_tableta_actual(ctx, intento))


class Latido(_Alumno):
    """El punto de recuperación de 5 s (INV-010). Va PRIMERO `cargar` (que detecta el silencio anterior y pausa), DESPUÉS se registra el latido: así
    una desconexión larga no se borra con el primer paquete que llega. Responde igual que `GET /estado/`: el latido es también el sondeo.
    `datos`: `{dispositivo, alumno_id, pregunta_actual?, transcurrido_ms?, hora_tableta_ms?, capacidad_control?, bateria_pct?, espacio_libre_mb?}`."""

    def ejecutar(self, actor: Actor, intento_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            intento, asignacion = self.cargar(uow, ctx, intento_id, ahora)
            actual = self.es_la_tableta_actual(ctx, intento)
            if intento["estado"] in cat.ACEPTAN_RESPUESTAS and actual:
                declarada = bloqueo.validar_capacidad(datos["capacidad_control"]) if datos.get("capacidad_control") not in (None, "") else None
                if ctx.dispositivo_id:
                    uow.dispositivos.latido(ctx.dispositivo_id, ahora, capacidad_control=declarada, telemetria={
                        "espacio_libre_mb": datos.get("espacio_libre_mb"), "bateria_pct": datos.get("bateria_pct")})
                    if declarada:
                        ctx = Contexto(ctx.actor, ctx.alumno_id, ctx.alumno_rotulo, ctx.huella, {**(ctx.dispositivo or {}), "capacidad_control": declarada},
                                       ctx.organizacion_id)
                campos: dict = {"ultimo_latido_en": ahora}
                pregunta = str(datos.get("pregunta_actual") or "")
                if pregunta and pregunta in intento["armado"]:
                    campos["pregunta_actual"] = pregunta
                campos.update(int_dom.reconciliar_reloj(intento, ahora, datos.get("transcurrido_ms")))
                suspendido = intento["estado"] in cat.SUSPENDIDOS
                previo = intento
                intento = uow.intentos.actualizar(intento["id"], **campos)
                self._reloj_desfasado(uow, intento, asignacion, datos, ahora)
                if suspendido:
                    intento = self._volver(uow, intento, previo, asignacion, ahora)
            return self.motor.estado_del_intento(intento, asignacion, ctx.capacidad, ahora, sesion_activa=actual)

    def _volver(self, uow: UnidadDeTrabajo, intento: dict, previo: dict, asignacion: dict, ahora: int) -> dict:
        """La tableta de un intento suspendido volvió a dar señal. Con reactivación automática el intento sigue solo (el reloj continúa desde lo
        congelado); con reactivación del profesor queda esperándolo (`restaurando` pasa a `pausado_desconexion`)."""
        if asignacion["reactivacion"] == cat.REACTIVA_AUTOMATICA:
            return reactivar(self.motor, uow, intento, asignacion, ahora, SISTEMA)
        if intento["estado"] == cat.RESTAURANDO:
            return uow.intentos.actualizar(intento["id"], **int_dom.pasar_a_pausado(intento))
        return intento

    def _reloj_desfasado(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, datos: dict, ahora: int) -> None:
        """INV-017: si el reloj de la tableta está lejos del del nodo se deja constancia (una vez cada diez minutos). Nunca decide nada."""
        hora = datos.get("hora_tableta_ms")
        if isinstance(hora, bool) or hora in (None, ""):
            return
        try:
            desfase = abs(int(hora) - ahora)
        except (TypeError, ValueError):
            return
        if desfase > self.s.config.desfase_reloj_ms:
            self.motor.incidente(uow, intento, "reloj_desfasado", ahora, detalle={"desfase_ms": desfase},
                                 ref_cliente=f"reloj:{intento['id'][:8]}:{ahora // 600_000}", asignacion=asignacion)


def reactivar(motor: Motor, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, ahora: int, por: str, *, desde_pregunta: str = "") -> dict:
    """PAN-061: `pausado_desconexion | restaurando → en_curso`. El reloj continúa desde el valor congelado. Idempotente: reactivar un intento que
    ya corre no hace nada."""
    if intento["estado"] in cat.CORRIENDO:
        return intento
    pausa = int_dom.pausa_abierta(intento) or {}
    cambios = int_dom.reactivar(intento, ahora, por)
    if desde_pregunta and desde_pregunta in intento["armado"]:
        cambios["pregunta_actual"] = desde_pregunta
    anterior = intento["estado"]
    intento = uow.intentos.actualizar(intento["id"], **cambios)
    reloj = int_dom.reloj(intento, ahora)
    if por == SISTEMA:
        motor.incidente(uow, intento, "reconexion", ahora, detalle={"pausa_ms": ahora - int(pausa.get("desde") or ahora)}, asignacion=asignacion)
    else:
        motor.incidente(uow, intento, "reactivado", ahora, detalle={"por": por, "restante_ms": reloj["restante_ms"],
                                                                      "desde_pregunta": intento.get("pregunta_actual") or ""},
                        actor=por, asignacion=asignacion)
    motor.publicar(uow, "Intento", intento["id"], cat.EV_INTENTO_REACTIVADO, {
        "intento_id": intento["id"], "asignacion_id": intento["asignacion_id"], "alumno_id": intento["alumno_id"], "por": por,
        "restante_ms": reloj["restante_ms"]}, ahora)
    uow.auditoria.registrar(por, "evaluacion.intento.reactivado", "m10_intento_formal", intento["id"], anterior={"estado": anterior},
                            nuevo={"estado": intento["estado"], "restante_ms": reloj["restante_ms"]}, dispositivo_id=intento.get("dispositivo_id") or None)
    motor.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
    return intento


# ======================================================================================== preguntas

class PreguntasDelIntento(_Alumno):
    """El examen DE ESTE ALUMNO, sin ninguna clave, en el orden de su armado. Sólo mientras el intento admite respuestas (una tableta que vuelve debe
    poder reabrir su examen) y sólo a las tabletas que han participado en él."""

    def ejecutar(self, actor: Actor, intento_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            intento, asignacion = self.cargar(uow, ctx, intento_id, ahora)
            if intento["estado"] not in cat.ACEPTAN_RESPUESTAS:
                raise TransicionInvalida(f"El intento está «{intento['estado']}»: ya no se muestran sus preguntas.", estado=intento["estado"])
            self.sesion_de(ctx, intento)
            vista = self.s.contenido.preguntas(asignacion["fuente_curso"], asignacion["curso_ref"], intento["curso_version"], asignacion["objeto_ref"],
                                               list(intento["armado"]), intento["semilla"], intento_id=intento["id"], dispositivo=ctx.huella,
                                               alumno_id=ctx.alumno_id)
            respondidas = {r["pregunta_ref"]: {"respuesta": r["respuesta"], "secuencia": r["secuencia"]} for r in intento["respuestas"]}
            return {"intento_id": intento["id"], "titulo": vista.get("titulo") or asignacion["titulo"], "instrucciones": vista.get("instrucciones"),
                    "instrucciones_tramos": vista.get("instrucciones_tramos"), "version": vista.get("version") or intento["curso_version"],
                    "navegacion_atras": bool(asignacion.get("permite_retroceso", True)), "preguntas": vista["preguntas"], "respondidas": respondidas,
                    "pregunta_actual": intento.get("pregunta_actual") or "", "servidor_en": ahora}


class MedioDelIntento(_Alumno):
    """Los bytes de un medio, sólo si pertenece a una pregunta de ESTE examen (un alumno no lee los demás medios del curso durante el examen)."""

    def ejecutar(self, actor: Actor, intento_id: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str, datos: dict) -> Bytes:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            intento, asignacion = self.cargar(uow, ctx, intento_id, ahora)
            if intento["estado"] not in cat.ACEPTAN_RESPUESTAS:
                raise TransicionInvalida("El intento ya no está en curso.", estado=intento["estado"])
            self.sesion_de(ctx, intento)
            fuente, curso, version, objeto = asignacion["fuente_curso"], asignacion["curso_ref"], intento["curso_version"], asignacion["objeto_ref"]
            permitidos = self.s.contenido.medios_de(fuente, curso, version, objeto, list(intento["armado"]), intento["semilla"])
        if media_ref not in permitidos:
            raise NoEncontrado("Ese medio no es de tu examen.", media_ref=media_ref)
        return self.s.contenido.abrir_medio(fuente, curso, media_ref, ruta, rango, metodo)


# ======================================================================================== entregar

class EntregarIntento(_Alumno):
    """FUN-114. `datos`: `{dispositivo, alumno_id, confirmar?, respuestas?, transcurrido_ms?}`. Idempotente: entregar dos veces devuelve lo mismo.
    Con reactivos sin responder hace falta `confirmar = true` (la tableta ya le mostró «Te faltan N»)."""

    def ejecutar(self, actor: Actor, intento_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            self.s.autorizacion.exigir(actor, cat.P_ATTEMPT_SUBMIT)
            intento, asignacion = self.cargar(uow, ctx, intento_id, ahora)
            if intento["estado"] in cat.ENTREGADOS or intento["estado"] == cat.ANULADO:
                return self._cuerpo(intento, asignacion, ahora)
            if intento["estado"] in cat.SUSPENDIDOS:
                raise TransicionInvalida(cat.MENSAJE_SUSPENDIDO, estado=intento["estado"], destino=cat.ENTREGADO)
            if intento["estado"] not in cat.CORRIENDO:
                raise TransicionInvalida(f"El intento está «{intento['estado']}»: no se entrega.", estado=intento["estado"], destino=cat.ENTREGADO)
            sesion = self.sesion_de(ctx, intento)
            if datos.get("respuestas"):
                EnviarRespuestas(self.s).integrar(uow, intento, asignacion, sesion, datos, ahora, permitir_vacio=True)
                intento = uow.intentos.por_id(intento["id"])
            campos = int_dom.reconciliar_reloj(intento, ahora, datos.get("transcurrido_ms"))
            if campos:
                intento = uow.intentos.actualizar(intento["id"], **campos)
            faltan = [ref for ref in intento["armado"] if ref not in {r["pregunta_ref"] for r in intento["respuestas"]}]
            if faltan and not bool(datos.get("confirmar")):
                raise ConfirmacionRequerida(f"Te faltan {len(faltan)} pregunta(s) por responder: confirma la entrega para continuar.", faltan=faltan)
            intento = self.motor.entregar(uow, intento, asignacion, ahora, cat.O_ALUMNO, actor=ctx.alumno_id)
            return self._cuerpo(intento, asignacion, ahora)

    def _cuerpo(self, intento: dict, asignacion: dict, ahora: int) -> dict:
        """PAN-123: confirmación de la entrega y qué sigue. NUNCA dice «calificado» mientras quede un reactivo por revisar."""
        if intento["estado"] == cat.EN_REVISION or intento.get("requiere_revision"):
            que_sigue = "en_revision"
        elif asignacion["resultados"] == cat.NUNCA:
            que_sigue = "sin_resultado"
        elif asignacion["resultados"] == cat.AL_ENTREGAR and intento["estado"] == cat.CALIFICADO:
            que_sigue = "resultado_al_liberar" if not self.motor.resultado_disponible(asignacion, intento) else "sin_resultado"
        else:
            que_sigue = "resultado_al_liberar"
        return {"intento": {"id": intento["id"], "asignacion_id": intento["asignacion_id"], "estado": intento["estado"], "numero": intento["numero"],
                            "respondidas": len(intento["respuestas"]), "total": len(intento["armado"]), "fuera_de_plazo": bool(intento.get("fuera_de_plazo"))},
                "entregado_en": intento.get("entregado_en"), "origen_entrega": intento.get("origen_entrega") or "",
                "que_sigue": {"codigo": que_sigue, "texto": cat.QUE_SIGUE[que_sigue]},
                "resultado_disponible": self.motor.resultado_disponible(asignacion, intento), "servidor_en": ahora}


# ========================================================================= el profesor sobre el intento

class _Docente(_CasoDeUso):
    def __init__(self, servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)

    def _intento(self, uow: UnidadDeTrabajo, intento_id: str, ahora: int) -> tuple[dict, dict]:
        intento = uow.intentos.por_id(intento_id) if intento_id else None
        if intento is None:
            raise NoEncontrado("No existe ese intento.", intento_id=intento_id)
        asignacion = self.motor.asegurar_asignacion(uow, uow.asignaciones.por_id(intento["asignacion_id"]), ahora)
        intento = self.motor.asegurar_intento(uow, uow.intentos.por_id(intento_id), asignacion, ahora)
        return intento, asignacion


class ReactivarIntento(_Docente):
    """PAN-061. Sólo de `pausado_desconexion` o `restaurando`. Devuelve el tiempo que le queda y desde qué pregunta continúa."""

    def ejecutar(self, actor: Actor, intento_id: str, desde_pregunta: str = "") -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento, asignacion = self._intento(uow, intento_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_REACTIVATE, asignacion)
            if intento["estado"] not in cat.SUSPENDIDOS + cat.CORRIENDO:
                raise TransicionInvalida(f"El intento está «{intento['estado']}»: sólo se reactiva uno suspendido.", estado=intento["estado"],
                                         destino=cat.EN_CURSO)
            intento = reactivar(self.motor, uow, intento, asignacion, ahora, actor.id or "docente", desde_pregunta=str(desde_pregunta or ""))
            reloj = int_dom.reloj(intento, ahora)
            return {"intento_id": intento["id"], "estado": intento["estado"], "restante_ms": reloj["restante_ms"],
                    "desde_pregunta": intento.get("pregunta_actual") or "", "servidor_en": ahora}


class ReactivarTodos(_Docente):
    """Guion paso 12: reactiva a todos los suspendidos de la asignación y dice a cuántos afecta (el profesor ve el número antes de confirmar)."""

    def ejecutar(self, actor: Actor, asignacion_id: str, *, solo_contar: bool = False) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = uow.asignaciones.por_id(asignacion_id) if asignacion_id else None
            if asignacion is None:
                raise NoEncontrado("No existe esa evaluación.", asignacion_id=asignacion_id)
            asignacion = self.motor.asegurar_asignacion(uow, asignacion, ahora)
            self.s.autorizacion.exigir(actor, cat.P_REACTIVATE, asignacion)
            suspendidos = []
            for it in uow.intentos.de_asignacion(asignacion_id, cat.CORRIENDO + cat.SUSPENDIDOS):
                it = self.motor.asegurar_intento(uow, it, asignacion, ahora)
                if it["estado"] in cat.SUSPENDIDOS:
                    suspendidos.append(it)
            if solo_contar:
                return {"suspendidos": len(suspendidos), "reactivados": 0, "servidor_en": ahora}
            for it in suspendidos:
                reactivar(self.motor, uow, it, asignacion, ahora, actor.id or "docente")
            return {"suspendidos": len(suspendidos), "reactivados": len(suspendidos), "servidor_en": ahora}


class CerrarIntento(_Docente):
    """«Cierre forzado» (`pausado_desconexion | restaurando → entregado`): el profesor entrega lo que hay de un alumno que no volverá."""

    def ejecutar(self, actor: Actor, intento_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento, asignacion = self._intento(uow, intento_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_REACTIVATE, asignacion)
            if intento["estado"] in cat.ENTREGADOS:
                return {"intento_id": intento["id"], "estado": intento["estado"], "servidor_en": ahora}
            if intento["estado"] not in cat.SUSPENDIDOS:
                raise TransicionInvalida(f"Sólo se cierra a la fuerza un intento suspendido; éste está «{intento['estado']}».", estado=intento["estado"],
                                         destino=cat.ENTREGADO)
            intento = self.motor.entregar(uow, intento, asignacion, ahora, cat.O_PROFESOR, actor=actor.id or "docente")
            return {"intento_id": intento["id"], "estado": intento["estado"], "origen_entrega": cat.O_PROFESOR, "servidor_en": ahora}


class AnularIntento(_Docente):
    """La ÚNICA flecha hacia `anulado` (INV-018): una persona, con motivo y nombre. La interfaz muestra siempre quién lo hizo."""

    def ejecutar(self, actor: Actor, intento_id: str, motivo: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento, asignacion = self._intento(uow, intento_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_VOID, asignacion)
            cambios = int_dom.anular(intento, actor.id, motivo, ahora)
            anterior = intento["estado"]
            intento = uow.intentos.actualizar(intento["id"], **cambios)
            self.motor.publicar(uow, "Intento", intento["id"], cat.EV_INTENTO_ANULADO, {
                "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"], "anulado_por": intento["anulado_por"]}, ahora)
            uow.auditoria.registrar(actor.id, cat.A_INTENTO_ANULADO, "m10_intento_formal", intento["id"], anterior={"estado": anterior},
                                    nuevo={"estado": cat.ANULADO, "anulado_por": intento["anulado_por"]}, motivo=intento["motivo_anulacion"])
            self.motor.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
            return {"intento_id": intento["id"], "estado": intento["estado"], "anulado_por": intento["anulado_por"], "anulado_en": intento["anulado_en"],
                    "motivo": intento["motivo_anulacion"]}
