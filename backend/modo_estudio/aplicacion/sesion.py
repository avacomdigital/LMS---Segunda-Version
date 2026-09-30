"""
La sesión de estudio y las preguntas del menú (FUN-080, FUN-089, FUN-090, 008-01, 008-07; D-15 «identidad declarada»).

  ConsultarEstado     `GET /estado/`: la pregunta del menú de Student. NUNCA falla: dice si el modo de estudio está disponible en esta
                      tableta y, si no, por qué. `disponible` = nodo instalado y tableta registrada, activa y no bloqueada, sea compartida
                      o asignada (D-1 revisada); `descarga_permitida` = sólo el dueño de una tableta asignada se lleva el paquete (BR-054).
  ListarEstudiantes   `GET /estudiantes/`: los nombres para la pantalla «¿Quién eres?»: los grupos con trabajo asignado y sus alumnos activos.
                      Sin sesión ni permiso: es lo que se pregunta ANTES de saber quién es la persona.
  AbrirSesion         `POST /sesion/` (`study.open`): abre la sesión de alumno en MOD-009 (relevo si hay otra) y emite `estudio.sesion.abierta.v1`.
  CerrarSesion        `POST /sesion/cerrar/` (`study.open`): cierra la sesión (motivo `usuario`) y emite `estudio.sesion.cerrada.v1`. Idempotente.
  ReintentarLimpieza  `POST /sesion/limpieza/`: el aparato avisa de que terminó de borrar lo local (FUN-090, BR-053).

El modo de estudio sirve en cualquier tableta (D-15): lo único que niega es el PAQUETE fuera de la tableta de su dueño (BR-054). Ninguno de
estos casos de uso lee la biblioteca.
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from ..dominio.errores import DatosInvalidos, FaltaDispositivo
from .base import Contexto, _CasoDeUso, resolver_contexto
from .puertos import Actor, UnidadDeTrabajo


def _alumno(alumno_id: str, rotulo: str) -> dict | None:
    return {"id": alumno_id, "rotulo": rotulo or None} if alumno_id else None


def _dispositivo(dispositivo: dict | None) -> dict | None:
    if not dispositivo:
        return None
    return {"id": dispositivo["id"], "nombre": dispositivo["nombre"], "identificador_hw": dispositivo["identificador_hw"]}


def _dueno(uow: UnidadDeTrabajo, dispositivo: dict | None) -> dict | None:
    """A quién está asignada la tableta (`{id, rotulo}`), o None si es compartida o no se conoce."""
    if not dispositivo or dispositivo.get("perfil") != cat.ASIGNADO or not dispositivo.get("asignado_a_id"):
        return None
    return _alumno(dispositivo["asignado_a_id"], uow.identidad.rotulo_persona(dispositivo["asignado_a_id"]))


def _aparato_y_motivo(uow: UnidadDeTrabajo, actor: Actor, huella: str) -> tuple[dict | None, str]:
    """La tableta que pregunta y por qué no puede usar el modo de estudio (`""` si puede). Sólo lee: no registra la tableta, que se da a conocer con su
    latido (`POST /api/dispositivos/latido/`); una tableta que el nodo nunca vio es `dispositivo_desconocido`."""
    organizacion = uow.identidad.organizacion_id()
    if not organizacion:
        return None, cat.MOTIVO_NODO_NO_INSTALADO
    dispositivo = None
    if huella:
        dispositivo = uow.dispositivos.por_identificador(organizacion, huella)
    elif actor.autenticado and actor.dispositivo_id:
        dispositivo = uow.dispositivos.por_id(actor.dispositivo_id)
    if dispositivo is None:
        return None, cat.MOTIVO_DISPOSITIVO_DESCONOCIDO
    if not dispositivo["activo"]:
        return dispositivo, cat.MOTIVO_DISPOSITIVO_INACTIVO
    if dispositivo["bloqueado"]:
        return dispositivo, cat.MOTIVO_DISPOSITIVO_BLOQUEADO
    return dispositivo, ""


class ConsultarEstado(_CasoDeUso):
    """`GET /estado/?dispositivo=[&alumno_id=]`. Nunca falla (salvo un error real del nodo): es la pregunta del menú.
    `{disponible, motivo, perfil, alumno{id, rotulo}|null, dueno{id, rotulo}|null, dispositivo{id, nombre, identificador_hw}|null,
    descarga_permitida, servidor_en}`. `motivo`: `""` · nodo_no_instalado · dispositivo_desconocido · dispositivo_bloqueado · dispositivo_inactivo.
    `alumno` es el que se declaró, si existe y está activo (con sesión, el del token); `dueno`, a quien está asignada la tableta."""

    def ejecutar(self, actor: Actor, huella: str = "", alumno_id: str = "") -> dict:
        ahora = self.s.reloj.ahora_ms()
        huella = str(huella or "").strip()
        respuesta = {"disponible": False, "motivo": "", "perfil": "", "alumno": None, "dueno": None, "dispositivo": None,
                     "descarga_permitida": False, "servidor_en": ahora}
        with self.s.uow() as uow:
            dispositivo, motivo = _aparato_y_motivo(uow, actor, huella)
            if motivo == cat.MOTIVO_NODO_NO_INSTALADO:
                return {**respuesta, "motivo": motivo}
            dueno = _dueno(uow, dispositivo)
            declarado = actor.id if actor.autenticado else str(alumno_id or actor.id or "").strip()[:64]
            alumno = None
            if declarado and actor.autenticado:
                alumno = _alumno(declarado, uow.identidad.rotulo_persona(declarado))
            elif declarado:
                activos = uow.identidad.alumnos_activos([declarado])
                alumno = _alumno(declarado, activos[declarado]) if declarado in activos else None
            disponible = motivo == ""
            return {**respuesta, "disponible": disponible, "motivo": motivo, "perfil": (dispositivo or {}).get("perfil") or "",
                    "alumno": alumno, "dueno": dueno, "dispositivo": _dispositivo(dispositivo),
                    # BR-054: se lleva el paquete el dueño de una tableta asignada (no se declaró a nadie: se presume que es él)
                    "descarga_permitida": bool(disponible and dueno and (not declarado or declarado == dueno["id"]))}


class ListarEstudiantes(_CasoDeUso):
    """`GET /estudiantes/?dispositivo=` (sin sesión ni permiso: identidad declarada): los nombres de la pantalla «¿Quién eres?».
    `{disponible, motivo, grupos[{id, codigo, nombre, alumnos[{id, rotulo}]}], dueno{id, rotulo}|null, servidor_en}`. Siempre 200. `grupos` son los
    que tienen al menos una asignación ACTIVA, con sus alumnos ACTIVOS; los destinatarios de una selección sin grupo van en el grupo sintético
    `{id: "", codigo: "", nombre: "Alumnos"}`. Si la tableta no se puede usar, `disponible = false`, el mismo `motivo` de `/estado/` y sin grupos.
    Sólo nombres: ningún otro dato de las personas."""

    GRUPO_SUELTO = {"id": "", "codigo": "", "nombre": "Alumnos"}      # el de los alumnos nombrados sin grupo

    def ejecutar(self, actor: Actor, huella: str = "") -> dict:
        ahora = self.s.reloj.ahora_ms()
        huella = str(huella or "").strip()
        if not huella and not actor.autenticado:
            raise FaltaDispositivo("Falta `dispositivo` (la huella de la tableta): sin sesión no se sabe desde dónde se pregunta.")
        with self.s.uow() as uow:
            dispositivo, motivo = _aparato_y_motivo(uow, actor, huella)
            respuesta = {"disponible": motivo == "", "motivo": motivo, "grupos": [], "dueno": _dueno(uow, dispositivo), "servidor_en": ahora}
            if motivo == "":
                respuesta["grupos"] = self._grupos_con_trabajo(uow)
            return respuesta

    def _grupos_con_trabajo(self, uow: UnidadDeTrabajo) -> list[dict]:
        activas = uow.asignaciones.listar(estado=cat.ACTIVA)
        grupos: list[dict] = []
        for grupo_id in dict.fromkeys(a["grupo_id"] for a in activas if a["grupo_id"]):
            grupo = uow.identidad.grupo(grupo_id)
            alumnos = uow.identidad.alumnos_del_grupo(grupo_id) if grupo and grupo["activo"] else []
            if alumnos:      # un grupo sin alumnos activos no tiene nadie que elegir
                grupos.append({"id": grupo["id"], "codigo": grupo["codigo"], "nombre": grupo["nombre"],
                               "alumnos": [{"id": a["id"], "rotulo": a["rotulo"]} for a in alumnos]})
        grupos.sort(key=lambda g: ((g["nombre"] or "").lower(), (g["codigo"] or "").lower()))
        sueltos = list(dict.fromkeys(i for a in activas if a["alcance"] == cat.SELECCION and not a["grupo_id"]
                                     for i in (a.get("destinatarios") or [])))
        activos = uow.identidad.alumnos_activos(sueltos)
        if activos:
            grupos.append({**self.GRUPO_SUELTO, "alumnos": sorted(({"id": i, "rotulo": r} for i, r in activos.items()),
                                                                   key=lambda a: ((a["rotulo"] or "").lower(), a["id"]))})
        return grupos


class AbrirSesion(_CasoDeUso):
    """FUN-080. Abre la sesión de alumno del aparato en MOD-009: si otra persona la tenía, se relevó (INV-011, DEC-023)."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_OPEN)
        ahora = self.s.reloj.ahora_ms()
        registro = {"nombre": str(datos.get("nombre") or "")[:120], "plataforma": str(datos.get("plataforma") or "").lower(),
                    "version_app": str(datos.get("version_app") or "")[:32]}
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, datos.get("dispositivo"), ahora=ahora, declarado=datos.get("alumno_id") or "",
                                    registrar=True, exigir_aparato=True, registro=registro)
            existente = uow.dispositivos.sesion_abierta_de_alumno(ctx.alumno_id)
            nueva = not (existente and existente["dispositivo_id"] == ctx.dispositivo_id)
            sesion = uow.dispositivos.abrir_sesion_alumno(ctx.alumno_id, ctx.dispositivo_id, ahora, actor=ctx.alumno_id) if nueva else existente
            if nueva:
                self._publicar(uow, "SesionEstudio", sesion["id"], cat.EV_SESION_ABIERTA, {
                    "alumno_id": ctx.alumno_id, "dispositivo_id": ctx.dispositivo_id, "sesion_id": sesion["id"], "perfil": ctx.perfil}, ahora)
            return {"sesion_id": sesion["id"], "alumno": _alumno(ctx.alumno_id, ctx.alumno_rotulo),
                    "dispositivo": _dispositivo(ctx.dispositivo), "perfil": ctx.perfil, "servidor_en": ahora}


class CerrarSesion(_CasoDeUso):
    """FUN-089 · BR-053. Cierra la sesión del alumno en este aparato (motivo `usuario`). El aparato dice cuánto trabajo le queda por
    enviar (`cola_pendiente`) y si terminó de borrar lo local (`limpieza`). Idempotente: sin sesión abierta, no hace nada. Cerrar debe
    poder hacerse siempre: un aparato bloqueado o retirado también cierra."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_OPEN)
        ahora = self.s.reloj.ahora_ms()
        limpieza = str(datos.get("limpieza") or cat.LIMPIEZA_COMPLETA)
        if limpieza not in cat.LIMPIEZAS:
            raise DatosInvalidos(f"`limpieza` es {' o '.join(cat.LIMPIEZAS)}.", limpieza=limpieza)
        cola = datos.get("cola_pendiente")
        cola = int(cola) if isinstance(cola, int) and not isinstance(cola, bool) and cola >= 0 else 0
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, datos.get("dispositivo"), ahora=ahora, declarado=datos.get("alumno_id") or "",
                                    comprobar_uso=False)
            sesion = uow.dispositivos.sesion_abierta_de_alumno(ctx.alumno_id)
            if sesion and (not ctx.dispositivo_id or sesion["dispositivo_id"] == ctx.dispositivo_id):
                uow.dispositivos.cerrar_sesion_alumno(sesion["id"], ahora, "usuario")
                self._publicar(uow, "SesionEstudio", sesion["id"], cat.EV_SESION_CERRADA, {
                    "alumno_id": ctx.alumno_id, "dispositivo_id": sesion["dispositivo_id"], "sesion_id": sesion["id"],
                    "motivo": "usuario", "cola_pendiente": cola, "limpieza": limpieza}, ahora)
            return {"cerrada": True}


class ReintentarLimpieza(_CasoDeUso):
    """FUN-090. El aparato avisa de que terminó (o no) de borrar lo local tras cerrar la sesión. No exige permiso ni identidad: la
    limpieza de un aparato asignado debe poder informarse siempre."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        resultado = str(datos.get("resultado") or "")
        if resultado not in cat.LIMPIEZAS:
            raise DatosInvalidos(f"`resultado` es {' o '.join(cat.LIMPIEZAS)}.", resultado=resultado)
        with self.s.uow() as uow:
            ctx: Contexto = resolver_contexto(uow, actor, datos.get("dispositivo"), ahora=ahora, declarado=datos.get("alumno_id") or "",
                                              comprobar_uso=False, alumno_obligatorio=False)
            self._publicar(uow, "Dispositivo", ctx.dispositivo_id or ctx.huella[:64], cat.EV_LIMPIEZA_REINTENTADA, {
                "alumno_id": ctx.alumno_id, "dispositivo_id": ctx.dispositivo_id, "resultado": resultado}, ahora)
            return {"ok": True}
