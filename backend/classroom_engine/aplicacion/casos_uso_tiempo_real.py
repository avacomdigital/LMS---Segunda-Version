"""
Casos de uso del tiempo real del aula (007-01, 007-02, 007-03, 007-04, 007-13).

Los usa el consumidor WebSocket (`interfaces/websockets.py`) y el programador del nodo
(`infraestructura/programador.py`); ninguno importa Django. Cada uno es una transacción.

  ConectarTiempoReal     valida quién se conecta a una sesión y devuelve el saludo (con el conteo para el profesor)
  LatidoParticipante     el latido de una tableta por el socket; puede traer una declaración de presencia y telemetría
  BarrerPresencia        «conectado» sin latido → «reconectando» → «salió» (FUN-073)
  CerrarInactivas        clase abierta sin actividad durante 120 minutos → cerrada por inactividad (JRN-011)
  DetectarCaida          al arrancar el nodo, las clases abiertas quedan suspendidas para reanudarlas (FUN-076, BR-051)
  SolicitarAyuda …       la mano levantada (007-13)
  ProyectarAlumno        DEC-034: el estado de la proyección de la pantalla de un alumno, con sus salvaguardas
"""
from __future__ import annotations

from ..dominio import sesion as dom
from ..dominio.errores import DatosInvalidos, ParticipanteExpulsado
from .casos_uso import (
    CerrarSesion,
    RegistrarPresencia,
    SuspenderSesion,
    ArchivarSesiones,
    _CasoDeSesion,
)
from .puertos import Actor

SISTEMA = Actor(id=dom.SISTEMA, rotulo="Nodo del aula")


class ConectarTiempoReal(_CasoDeSesion):
    """Se llama al abrir el socket. El profesor recibe además el conteo de participantes: es lo primero que pinta
    el recuadro verde de la pantalla del aula, sin esperar a que cambie nada."""

    def ejecutar(self, sesion_id: str, rol: str, participante_id: str | None = None, persona_autenticada: str | None = None) -> dict:
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            saludo = {
                "sesion": {"id": sesion["id"], "estado": sesion["estado"]},
                "servidor_en": self.s.reloj.ahora_ms(),
                "latido_ms": self.s.config.intervalo_latido_ms,
                "respaldo_ms": self.s.config.intervalo_respaldo_ms,
            }
            if rol == "docente":
                saludo["conteo"] = uow.sesiones.conteo_participantes(sesion_id)
                saludo["capacidad"] = self._capacidad(saludo["conteo"])
                return saludo
            participante = self._participante(uow, sesion, participante_id or "")
            self._persona_propia(persona_autenticada, participante)
            if participante["estado"] in (dom.EXPULSADO, dom.RECHAZADO):
                raise ParticipanteExpulsado(participante_id=participante["id"], estado=participante["estado"])
            saludo["participante"] = {"id": participante["id"], "estado": participante["estado"]}
            return saludo


class LatidoParticipante(_CasoDeSesion):
    """El latido de una tableta por el WebSocket (cada `latido_ms`). Es ligero: no devuelve el estado de la clase.
    Con `estado` declara presencia (conectado al abrir el socket, reconectando al pasar a segundo plano, salió al
    cerrar la app) por la misma regla que la presencia HTTP; sin él sólo cuenta como señal de vida."""

    def ejecutar(self, sesion_id: str, participante_id: str, estado: str | None = None, telemetria: dict | None = None,
                 persona_autenticada: str | None = None) -> dict:
        if estado:
            respuesta = RegistrarPresencia(self.s).ejecutar(sesion_id, participante_id, estado, persona_autenticada=persona_autenticada,
                                                            telemetria=telemetria)
            return {"estado": respuesta["participante"]["estado"], "servidor_en": respuesta["servidor_en"]}
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            participante = self._participante(uow, sesion, participante_id)
            self._persona_propia(persona_autenticada, participante)
            if participante["estado"] in (dom.EXPULSADO, dom.RECHAZADO):
                raise ParticipanteExpulsado(participante_id=participante_id, estado=participante["estado"])
            if participante["estado"] in (dom.SALIO, dom.ESPERANDO):
                # «Salió» se declara o lo decide el barrido; un latido suelto no lo revierte. Los que esperan
                # admisión no cuentan como conectados: sólo se anota que la tableta sigue viva.
                if participante.get("dispositivo_id"):
                    uow.dispositivos.latido(participante["dispositivo_id"], ahora, telemetria)
                uow.sesiones.actualizar_participante(participante_id, ultimo_latido_en=ahora)
                return {"estado": participante["estado"], "servidor_en": ahora}
            participante = self._tocar_latido(uow, sesion, participante, ahora, telemetria)
            return {"estado": participante["estado"], "servidor_en": ahora}


class PerderConexion(_CasoDeSesion):
    """El socket de una tableta se cerró y no volvió a abrirse en unos segundos: pasa a «reconectando». No toca a quien ya
    declaró «salió» ni a quien la clase no admite: una desconexión no revierte una salida ni admite a nadie."""

    def ejecutar(self, sesion_id: str, participante_id: str) -> bool:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = uow.sesiones.sesion(sesion_id)
            participante = uow.sesiones.participante(participante_id)
            if (not sesion or not participante or participante["sesion_id"] != sesion_id
                    or sesion["estado"] != dom.ABIERTA or participante["estado"] != dom.CONECTADO):
                return False
            uow.sesiones.actualizar_participante(participante_id, estado=dom.RECONECTANDO)
            uow.sesiones.registrar_presencia(participante_id, dom.RECONECTANDO, ahora, participante["dispositivo"], "socket cerrado")
            self._publicar(uow, sesion_id, dom.EV_PRESENCIA_REGISTRADA, {
                "participante_id": participante_id, "estado": dom.RECONECTANDO, "instante": ahora, "origen": "nodo"})
            self._difundir(uow, sesion_id, "presencia", conteo=True, participante_id=participante_id, estado=dom.RECONECTANDO)
            return True


class BarrerPresencia(_CasoDeSesion):
    """FUN-073, 007-04. Recorre las clases abiertas: quien no manda latido en `latido_vencido_ms` pasa a «reconectando»
    y quien lleva `ausencia_ms` sin latido pasa a «salió» (cierra su sesión de alumno en la tableta, motivo inactividad).
    Las clases suspendidas no se barren: nadie puede mandar latido mientras el nodo está caído."""

    def ejecutar(self) -> dict:
        with self.s.uow() as uow:
            abiertas = [s["id"] for s in uow.sesiones.sesiones_en_estado(dom.ABIERTA)]
        reconectando = salieron = 0
        for sesion_id in abiertas:
            r, s = self._barrer(sesion_id)
            reconectando += r
            salieron += s
        return {"sesiones": len(abiertas), "reconectando": reconectando, "salieron": salieron}

    def _barrer(self, sesion_id: str) -> tuple[int, int]:
        ahora = self.s.reloj.ahora_ms()
        cfg = self.s.config
        reconectando = salieron = 0
        with self.s.uow() as uow:
            sesion = uow.sesiones.sesion(sesion_id)
            if not sesion or sesion["estado"] != dom.ABIERTA:
                return 0, 0
            for p in uow.sesiones.participantes(sesion_id):
                silencio = ahora - (p["ultimo_latido_en"] or p["ingreso"])
                if p["estado"] == dom.CONECTADO and silencio > cfg.latido_vencido_ms:
                    uow.sesiones.actualizar_participante(p["id"], estado=dom.RECONECTANDO)
                    uow.sesiones.registrar_presencia(p["id"], dom.RECONECTANDO, ahora, p["dispositivo"], "latido vencido")
                    self._publicar(uow, sesion_id, dom.EV_PRESENCIA_REGISTRADA, {
                        "participante_id": p["id"], "estado": dom.RECONECTANDO, "instante": ahora, "origen": "nodo"})
                    self._difundir(uow, sesion_id, "presencia", conteo=True, participante_id=p["id"], estado=dom.RECONECTANDO)
                    reconectando += 1
                elif p["estado"] == dom.RECONECTANDO and silencio > cfg.ausencia_ms:
                    uow.sesiones.actualizar_participante(p["id"], estado=dom.SALIO, salida=ahora)
                    uow.sesiones.registrar_presencia(p["id"], dom.SALIO, ahora, p["dispositivo"], "ausencia prolongada")
                    self._publicar(uow, sesion_id, dom.EV_PRESENCIA_REGISTRADA, {
                        "participante_id": p["id"], "estado": dom.SALIO, "instante": ahora, "origen": "nodo"})
                    if p.get("dim_sesion_alumno_id"):
                        uow.dispositivos.cerrar_sesion_alumno(p["dim_sesion_alumno_id"], ahora, "inactividad")
                    self._difundir(uow, sesion_id, "presencia", conteo=True, participante_id=p["id"], estado=dom.SALIO)
                    salieron += 1
        return reconectando, salieron


class CerrarInactivas(_CasoDeSesion):
    """JRN-011 · 007-03. La clase abierta que lleva `inactividad_ms` (120 minutos) sin nada —ni una acción del profesor,
    ni un latido de tableta, ni una entrega— se cierra sola, conserva todo y queda con origen «inactividad». Las
    suspendidas no caducan (DEC-018): esperan al profesor."""

    def ejecutar(self) -> list[str]:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            inactivas = [s["id"] for s in uow.sesiones.sesiones_en_estado(dom.ABIERTA)
                         if ahora - uow.sesiones.ultima_actividad(s["id"]) > self.s.config.inactividad_ms]
        cerradas = []
        for sesion_id in inactivas:
            CerrarSesion(self.s).ejecutar(SISTEMA, sesion_id, origen="inactividad", forzar=True)
            cerradas.append(sesion_id)
        return cerradas


class DetectarCaida(_CasoDeSesion):
    """FUN-076 · BR-051. Al arrancar el nodo, toda clase que estaba abierta quedó interrumpida: se suspende (mismo
    código, mismo selector, mismos participantes) en el instante de su última señal, y el profesor la reanuda con un
    toque desde «Clase de hoy». Las tabletas siguen intentando reconectarse y vuelven solas."""

    def ejecutar(self) -> list[str]:
        with self.s.uow() as uow:
            abiertas = [(s["id"], uow.sesiones.ultima_actividad(s["id"])) for s in uow.sesiones.sesiones_en_estado(dom.ABIERTA)]
        suspendidas = []
        for sesion_id, ultima in abiertas:
            SuspenderSesion(self.s).ejecutar(SISTEMA, sesion_id, "reinicio", instante=ultima or None)
            suspendidas.append(sesion_id)
        return suspendidas


# ------------------------------------------------------------------ la mano levantada (007-13)

class SolicitarAyuda(_CasoDeSesion):
    """La tableta levanta (o baja) la mano. Sale a la pantalla del profesor junto al nombre; no interrumpe a nadie."""

    def ejecutar(self, sesion_id: str, participante_id: str, activa: bool = True, persona_autenticada: str | None = None) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.exigir_abierta(sesion["estado"], "solicitudes de ayuda")
            participante = self._participante(uow, sesion, participante_id)
            self._persona_propia(persona_autenticada, participante)
            if participante["estado"] not in dom.ADMITIDOS:
                raise DatosInvalidos("Sólo pide ayuda quien está admitido en la clase.", estado=participante["estado"])
            if activa == bool(participante["ayuda_en"]):
                return {"participante_id": participante_id, "ayuda_en": participante["ayuda_en"], "cambio": False}
            participante = uow.sesiones.actualizar_participante(participante_id, ayuda_en=ahora if activa else None)
            self._publicar(uow, sesion_id, dom.EV_AYUDA_SOLICITADA, {"participante_id": participante_id, "activa": activa, "instante": ahora})
            uow.auditoria.registrar(participante["persona_id"], "aula.ayuda.solicitada" if activa else "aula.ayuda.retirada",
                                    "m07_participante", participante_id)
            self._difundir(uow, sesion_id, "ayuda", participante_id=participante_id, activa=activa)
            return {"participante_id": participante_id, "ayuda_en": participante["ayuda_en"], "cambio": True}


class AtenderAyuda(_CasoDeSesion):
    """El profesor baja la mano de un alumno: ya lo atendió."""

    def ejecutar(self, actor: Actor, sesion_id: str, participante_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            self._autorizar(actor, dom.P_MESSAGE_SEND, sesion)
            participante = self._participante(uow, sesion, participante_id)
            if not participante["ayuda_en"]:
                return {"participante_id": participante_id, "ayuda_en": None, "cambio": False}
            uow.sesiones.actualizar_participante(participante_id, ayuda_en=None)
            self._publicar(uow, sesion_id, dom.EV_AYUDA_SOLICITADA, {
                "participante_id": participante_id, "activa": False, "atendida_por": actor.id, "instante": ahora})
            uow.auditoria.registrar(actor.id, "aula.ayuda.atendida", "m07_participante", participante_id,
                                    anterior={"ayuda_en": participante["ayuda_en"]})
            self._difundir(uow, sesion_id, "ayuda", participante_id=participante_id, activa=False)
            return {"participante_id": participante_id, "ayuda_en": None, "cambio": True}


# ------------------------------------------------ proyectar la pantalla de un alumno (DEC-034)

class ProyectarAlumno(_CasoDeSesion):
    """DEC-034: el profesor puede proyectar la pantalla de un alumno de su clase sin pedirle consentimiento, con cuatro
    salvaguardas: (1) el alumno ve un indicador permanente mientras dure (`estado.proyectando`), (2) el inicio y el fin
    quedan en la auditoría con autor y duración, (3) sólo alcanza a participantes admitidos de la sesión en curso y
    (4) no opera durante un examen. Aquí vive el ESTADO de la proyección; la captura de pantalla la aporta el cliente
    cuando exista (P2)."""

    def ejecutar(self, actor: Actor, sesion_id: str, participante_id: str, activa: bool = True) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            self._autorizar(actor, dom.P_PRESENT, sesion)
            dom.exigir_abierta(sesion["estado"], "proyectar la pantalla de un alumno")
            participante = self._participante(uow, sesion, participante_id)
            if activa:
                if participante["estado"] not in dom.ADMITIDOS:
                    raise DatosInvalidos("Sólo se proyecta la pantalla de quien está admitido en la clase.", estado=participante["estado"])
                if any(d.get("objeto_tipo") == "exam" for d in uow.sesiones.distribuciones(sesion_id, abiertas=True)):
                    raise DatosInvalidos("No se proyecta la pantalla de un alumno durante un examen (DEC-034).")
                if participante["proyectado_desde"]:
                    return {"participante_id": participante_id, "proyectando": True, "cambio": False}
                for otro in uow.sesiones.participantes(sesion_id):
                    if otro["proyectado_desde"] and otro["id"] != participante_id:
                        self._terminar(uow, sesion_id, otro, ahora, actor.id)
                uow.sesiones.actualizar_participante(participante_id, proyectado_desde=ahora, proyectado_por=actor.id)
                self._publicar(uow, sesion_id, dom.EV_PROYECCION_ALUMNO, {"participante_id": participante_id, "activa": True, "instante": ahora})
                uow.auditoria.registrar(actor.id, "aula.proyeccion.iniciada", "m07_participante", participante_id,
                                        nuevo={"persona_id": participante["persona_id"]})
                self._difundir(uow, sesion_id, "proyeccion", participante_id=participante_id, activa=True)
                return {"participante_id": participante_id, "proyectando": True, "cambio": True}
            if not participante["proyectado_desde"]:
                return {"participante_id": participante_id, "proyectando": False, "cambio": False}
            self._terminar(uow, sesion_id, participante, ahora, actor.id)
            return {"participante_id": participante_id, "proyectando": False, "cambio": True}

    def _terminar(self, uow, sesion_id: str, participante: dict, ahora: int, actor_id: str) -> None:
        uow.sesiones.actualizar_participante(participante["id"], proyectado_desde=None, proyectado_por="")
        self._publicar(uow, sesion_id, dom.EV_PROYECCION_ALUMNO, {"participante_id": participante["id"], "activa": False, "instante": ahora})
        uow.auditoria.registrar(actor_id, "aula.proyeccion.terminada", "m07_participante", participante["id"],
                                anterior={"desde": participante["proyectado_desde"], "autor": participante["proyectado_por"]},
                                nuevo={"duracion_ms": ahora - participante["proyectado_desde"]})
        self._difundir(uow, sesion_id, "proyeccion", participante_id=participante["id"], activa=False)


# --------------------------------------------------------------- archivado (programador)

class ArchivarCerradas(ArchivarSesiones):
    """Alias explícito para el programador: cerrada → archivada a las 24 h."""
