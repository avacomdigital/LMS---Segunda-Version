"""
Casos de uso de MOD-007 · Classroom Engine.

Dos familias:
  1. Consumo del curso para el aula (ConsultarCursos, ConsultarCurso, ConsultarLeccion,
     ConsultarObjeto, AbrirMedio): leen la fuente EN VIVO, normalizan y no escriben nada.
  2. La sesión de clase (IniciarSesion … CerrarSesion): lo único que MOD-007 escribe.

Cada caso de uso es una transacción (una Unidad de Trabajo): el hecho, su asiento de
auditoría y su evento `aula.*.v1` en la cola de salida se confirman juntos o no se
confirman. Ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from ..dominio import catalogos as cat
from ..dominio import curso as cur
from ..dominio import respuestas as resp
from ..dominio import sesion as dom
from ..dominio.errores import (
    ActividadesAbiertas,
    CodigoInvalido,
    CursoNoEncontrado,
    DatosInvalidos,
    DispositivoBloqueado,
    GrupoConSesionActiva,
    NoEncontrado,
    ParticipanteExpulsado,
    SesionActivaExistente,
    SinParticipantesAdmitidos,
)
from .puertos import Actor, Autorizacion, Bytes, FuenteDeCursos, Reloj, UnidadDeTrabajo

UrlMedioDeFuente = Callable[[str, str, str, str | None], str]
"""(fuente, curso_ref, media_ref, ruta) → ruta HTTP del medio en este backend."""


@dataclass
class Servicios:
    """Lo que el composition root entrega a todos los casos de uso."""

    uow: Callable[[], UnidadDeTrabajo]
    fuente: Callable[..., FuenteDeCursos]      # (nombre | None, curso_ref='') → fuente
    reloj: Reloj
    autorizacion: Autorizacion
    url_medio: UrlMedioDeFuente


def _id() -> str:
    return str(uuid.uuid4())


class _CasoDeUso:
    def __init__(self, servicios: Servicios):
        self.s = servicios

    # ------------------------------------------------------------ el curso, en vivo
    def _vista(self, fuente_nombre: str | None, curso_ref: str, rol: str, version: str | None = None,
               semilla: str | None = None) -> tuple[dict, str]:
        """`version` exige esa versión del curso (la clase en vivo siempre ve la instalada, artículo
        14.3). `semilla` fija el barajado de las opciones: la misma para toda la clase."""
        fuente = self.s.fuente(fuente_nombre, curso_ref)
        crudo = fuente.curso(curso_ref, version=version or None, rol=rol if rol in cat.ROLES else "estudiante", semilla=semilla or None)
        # Las URL de los medios llevan la referencia REAL del curso, aunque se haya pedido por un alias.
        ref_real = str(crudo.get("id") or crudo.get("curso_ref") or curso_ref)
        vista = cur.normalizar(
            crudo, rol=rol, fuente=fuente.nombre,
            url_medio=lambda media_ref, ruta: self.s.url_medio(fuente.nombre, ref_real, media_ref, ruta),
        )
        return vista, fuente.nombre


# ======================================================================== curso

class ConsultarCursos(_CasoDeUso):
    """Los cursos ofrecidos, agrupados por asignatura para el panel de navegación."""

    def ejecutar(self, fuente_nombre: str | None = None) -> dict:
        fuente = self.s.fuente(fuente_nombre)
        resumenes = []
        for crudo in fuente.cursos():
            if cur.es_manifiesto(crudo):
                ref = str(crudo.get("id", ""))
                resumenes.append(cur.resumen_de(crudo, fuente.nombre,
                                                lambda m, r, ref=ref: self.s.url_medio(fuente.nombre, ref, m, r)))
            else:
                resumenes.append(cur.resumen_contrato1(crudo, fuente.nombre))
        return {
            "fuente": fuente.nombre,
            "disponible": True,
            "asignaturas": cur.agrupar_por_asignatura(resumenes),
            "cursos": resumenes,
        }


class ConsultarCurso(_CasoDeUso):
    """La vista de aula completa de un curso, para el rol indicado. No escribe."""

    def ejecutar(self, curso_ref: str, rol: str = "estudiante", fuente_nombre: str | None = None, version: str | None = None,
                 semilla: str | None = None) -> dict:
        vista, _ = self._vista(fuente_nombre, curso_ref, rol, version, semilla)
        return vista


class ConsultarLeccion(_CasoDeUso):
    """Una lección con sus objetos: la carga que baja una tableta al seguir la clase."""

    def ejecutar(self, curso_ref: str, leccion_ref: str, rol: str = "estudiante", fuente_nombre: str | None = None,
                 version: str | None = None, semilla: str | None = None) -> dict:
        vista, _ = self._vista(fuente_nombre, curso_ref, rol, version, semilla)
        hallado = cur.localizar(vista, leccion_ref=leccion_ref)
        return {"curso": _ficha(vista), "leccion": hallado["leccion"]}


class ConsultarObjeto(_CasoDeUso):
    """Un objeto (presentación, lectura, laboratorio o actividad) con su lección de contexto."""

    def ejecutar(self, curso_ref: str, objeto_ref: str, rol: str = "estudiante", fuente_nombre: str | None = None,
                 version: str | None = None, semilla: str | None = None) -> dict:
        vista, _ = self._vista(fuente_nombre, curso_ref, rol, version, semilla)
        hallado = cur.localizar(vista, objeto_ref=objeto_ref)
        leccion = dict(hallado["leccion"])
        leccion.pop("objetos", None)
        return {"curso": _ficha(vista), "leccion": leccion, "objeto": hallado["objeto"]}


class AbrirMedio(_CasoDeUso):
    """Los bytes de un medio (o de un archivo interno de una simulación). Paso a través."""

    def ejecutar(self, curso_ref: str, media_ref: str, ruta: str | None = None, rango: str | None = None,
                 metodo: str = "GET", fuente_nombre: str | None = None) -> Bytes:
        return self.s.fuente(fuente_nombre, curso_ref).medio(curso_ref, media_ref, ruta, rango, metodo)


class EstadoFuente(_CasoDeUso):
    """¿Hay contenido? Nunca lanza: la ausencia de la biblioteca es un estado normal del aula."""

    def ejecutar(self, fuente_nombre: str | None = None) -> dict:
        fuente = self.s.fuente(fuente_nombre)
        return {"fuente": fuente.nombre, **fuente.estado()}


class EvaluarRespuesta(_CasoDeUso):
    """§5 del mapeo: la clave se compara DONDE VIVE. El aula valida la forma de la respuesta
    contra la pregunta tal como la vio el alumno, la reenvía con la versión del curso y
    devuelve el veredicto traducido. No escribe: el intento y la nota son de MOD-010 (Q-48)."""

    LOTE_MAXIMO = 200

    def ejecutar(self, curso_ref: str, datos: dict, fuente_nombre: str | None = None) -> dict:
        version = str(datos.get("version") or "")
        items = datos.get("items")
        if items is None:
            items = [{"objeto_ref": datos.get("objeto_ref"), "pregunta_ref": datos.get("pregunta_ref"), "respuesta": datos.get("respuesta")}]
            lote = False
        else:
            lote = True
        if not isinstance(items, list) or not items:
            raise DatosInvalidos("`items` debe ser una lista con al menos una respuesta.")
        if len(items) > self.LOTE_MAXIMO:
            raise DatosInvalidos(f"Un lote admite hasta {self.LOTE_MAXIMO} respuestas.", items=len(items))

        fuente = self.s.fuente(fuente_nombre, curso_ref)
        # La pregunta se valida contra el curso tal como lo vio el alumno y con su perfil: así ninguna
        # clave transita por aquí ni por accidente. La biblioteca sólo sirve el esquema de la versión
        # instalada; si el intento es de una versión archivada, la forma la valida ella (conserva las claves).
        vista: dict | None
        try:
            vista, _ = self._vista(fuente.nombre, curso_ref, "estudiante", version or None)
        except CursoNoEncontrado as error:
            if not version or error.extra.get("codigo_biblioteca") != "version_not_available":
                raise
            vista = None
        if vista is not None:
            version = version or str(vista.get("version") or "")
        if not version:
            raise DatosInvalidos("No se pudo determinar la versión del curso; `/v2/evaluate` la exige.")
        ref_real = str((vista or {}).get("curso_ref") or curso_ref)

        preparados = []
        for item in items:
            if not isinstance(item, dict):
                raise DatosInvalidos("Cada respuesta debe ser un objeto {objeto_ref, pregunta_ref, respuesta}.")
            objeto_ref = str(item.get("objeto_ref") or "")
            pregunta_ref = str(item.get("pregunta_ref") or "")
            if not objeto_ref or not pregunta_ref:
                raise DatosInvalidos("Cada respuesta exige objeto_ref y pregunta_ref.")
            respuesta = item.get("respuesta")
            if vista is None:
                if not isinstance(respuesta, dict) or not respuesta:
                    raise DatosInvalidos("`respuesta` debe ser un objeto con la forma del tipo de pregunta.", pregunta_ref=pregunta_ref)
                preparados.append({"objectId": objeto_ref, "questionId": pregunta_ref, "response": dict(respuesta)})
                continue
            objeto = cur.localizar(vista, objeto_ref=objeto_ref)["objeto"]
            if objeto["fuera_de_alcance"]:
                raise DatosInvalidos(f"El objeto «{objeto_ref}» es de {objeto['modulo']}: el aula no lo califica.")
            pregunta = cur.localizar(vista, objeto_ref=objeto_ref, unidad_ref=pregunta_ref)["unidad"]
            if not pregunta or "pregunta_ref" not in pregunta:
                raise DatosInvalidos(f"«{pregunta_ref}» no es una pregunta del objeto «{objeto_ref}».", pregunta_ref=pregunta_ref)
            preparados.append({"objectId": objeto_ref, "questionId": pregunta_ref, "response": resp.validar_respuesta(pregunta, respuesta)})

        if lote:
            crudos = fuente.evaluar_lote(ref_real, version, preparados)
            por_pregunta = {str(c.get("questionId") or ""): c for c in crudos}
            veredictos = [resp.veredicto(por_pregunta.get(p["questionId"], crudos[i] if i < len(crudos) else {}), p["questionId"])
                          for i, p in enumerate(preparados)]
            return {"fuente": fuente.nombre, "curso_ref": ref_real, "version": version, "veredictos": veredictos,
                    "pendientes": sum(1 for v in veredictos if v["pendiente"])}
        p = preparados[0]
        crudo = fuente.evaluar(ref_real, version, p["objectId"], p["questionId"], p["response"])
        return {"fuente": fuente.nombre, "curso_ref": ref_real, "version": version, "objeto_ref": p["objectId"],
                **resp.veredicto(crudo, p["questionId"])}


def _ficha(vista: dict) -> dict:
    """La cabecera del curso sin estructura."""
    return {k: vista.get(k) for k in ("fuente", "esquema", "curso_ref", "version", "titulo", "subtitulo", "idioma",
                                       "clasificacion", "duracion_estimada_min", "modos", "portada_url")}


# ====================================================================== sesión

class _CasoDeSesion(_CasoDeUso):
    def _sesion(self, uow: UnidadDeTrabajo, sesion_id: str) -> dict:
        sesion = uow.sesiones.sesion(sesion_id)
        if not sesion:
            raise NoEncontrado(f"No existe la sesión de clase «{sesion_id}».", sesion_id=sesion_id)
        return sesion

    def _participante(self, uow: UnidadDeTrabajo, sesion: dict, participante_id: str) -> dict:
        participante = uow.sesiones.participante(participante_id)
        if not participante or participante["sesion_id"] != sesion["id"]:
            raise NoEncontrado(f"No existe el participante «{participante_id}» en esta sesión.", participante_id=participante_id)
        return participante

    def _admitidos(self, uow: UnidadDeTrabajo, sesion_id: str) -> list[dict]:
        return [p for p in uow.sesiones.participantes(sesion_id) if p["estado"] in dom.ADMITIDOS]

    def _con_bloqueo(self, uow: UnidadDeTrabajo, participantes: list[dict]) -> list[dict]:
        """Marca a cada participante si su tableta está bloqueada o retirada (MOD-009): el profesor lo ve en la
        lista y el lanzamiento la deja fuera."""
        bloqueados = uow.dispositivos.bloqueados_entre([p["dispositivo_id"] for p in participantes if p.get("dispositivo_id")])
        for p in participantes:
            p["dispositivo_bloqueado"] = bool(p.get("dispositivo_id")) and p["dispositivo_id"] in bloqueados
        return participantes

    def _detalle(self, uow: UnidadDeTrabajo, sesion: dict) -> dict:
        """Lo que ve el profesor (PAN-001 / PAN-022)."""
        participantes = self._con_bloqueo(uow, uow.sesiones.participantes(sesion["id"]))
        controles = uow.sesiones.controles_abiertos(sesion["id"])
        distribuciones = uow.sesiones.distribuciones(sesion["id"])
        return {
            **sesion,
            "activa": sesion["estado"] in dom.ACTIVAS,
            "selector": uow.sesiones.selector_vigente(sesion["id"]),
            "seguimiento": any(c["tipo"] == dom.SEGUIMIENTO for c in controles),
            "pantallas_bloqueadas": any(c["tipo"] == dom.BLOQUEO for c in controles),
            "controles": controles,
            "participantes": participantes,
            "conteo": {
                "total": len(participantes),
                "conectados": sum(1 for p in participantes if p["estado"] == dom.CONECTADO),
                "reconectando": sum(1 for p in participantes if p["estado"] == dom.RECONECTANDO),
                "esperando": sum(1 for p in participantes if p["estado"] == dom.ESPERANDO),
                "salieron": sum(1 for p in participantes if p["estado"] == dom.SALIO),
            },
            "distribuciones": distribuciones,
            "avisos": uow.sesiones.avisos(sesion["id"]),
            "resumen": uow.sesiones.resumen(sesion["id"]),
            "servidor_en": self.s.reloj.ahora_ms(),
        }

    def _estado_tableta(self, uow: UnidadDeTrabajo, sesion: dict, participante: dict | None, desde: int | None = None) -> dict:
        """Lo que sigue una tableta (PAN-102): selector vigente, controles, lo que le toca hacer y avisos.
        Sin código de unión ni lista de participantes: eso es de la superficie del aula."""
        controles = uow.sesiones.controles_abiertos(sesion["id"])
        pid = participante["id"] if participante else None
        if participante:
            participante = self._con_bloqueo(uow, [participante])[0]
        return {
            "sesion": {k: sesion[k] for k in ("id", "estado", "fuente_curso", "curso_ref", "curso_version", "curso_rotulo",
                                               "leccion_ref", "leccion_rotulo", "grupo_rotulo", "profesor_rotulo")},
            "activa": sesion["estado"] in dom.ACTIVAS,
            "participante": participante,
            "selector": uow.sesiones.selector_vigente(sesion["id"]),
            "seguimiento": any(c["tipo"] == dom.SEGUIMIENTO for c in controles),
            "pantallas_bloqueadas": any(c["tipo"] == dom.BLOQUEO for c in controles),
            "pendientes": uow.sesiones.entregas_pendientes_de(sesion["id"], pid) if pid else [],
            "avisos": uow.sesiones.avisos(sesion["id"], participante_id=pid, desde=desde),
            "servidor_en": self.s.reloj.ahora_ms(),
            "intervalo_sondeo_ms": 2000,   # BR-049: el cambio de selector llega en 3 s como máximo
        }

    def _equipo(self, uow: UnidadDeTrabajo, datos: dict, dispositivo: str, persona_id: str, ahora: int) -> dict:
        """MOD-009: reconoce la tableta por su huella (la registra la primera vez) y abre, o reutiliza, la sesión
        de alumno en ella (Dim Sesión Alumno). Una tableta bloqueada o retirada no entra. Sin huella no hay
        equipo: la participación sigue siendo válida (Q-04, prototipo)."""
        if not dispositivo:
            return {}
        equipo = uow.dispositivos.resolver(
            dispositivo, nombre=str(datos.get("dispositivo_nombre") or dispositivo)[:120],
            plataforma=str(datos.get("plataforma") or "").lower(), version_app=str(datos.get("version_app") or ""), momento=ahora)
        if not equipo:
            return {}
        sesion_alumno = uow.dispositivos.abrir_sesion_alumno(persona_id, equipo["id"], ahora, actor=persona_id)
        return {"dispositivo_id": equipo["id"], "dim_sesion_alumno_id": sesion_alumno["id"]}

    def _publicar(self, uow: UnidadDeTrabajo, sesion_id: str, evento: str, carga: dict) -> None:
        uow.outbox.publicar("SesionDeClase", sesion_id, evento, {"sesion_id": sesion_id, **carga})


class IniciarSesion(_CasoDeSesion):
    """FUN-064 · BR-044/045/046 · DEC-035. Cualquiera de las cuatro vías produce la misma sesión."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_START)
        via = dom.ViaDeInicio(
            via=str(datos.get("via") or datos.get("via_origen") or ""),
            curso_ref=str(datos.get("curso_ref") or ""),
            leccion_ref=str(datos.get("leccion_ref") or ""),
            objeto_ref=str(datos.get("objeto_ref") or ""),
            nodo_ref=str(datos.get("nodo_ref") or ""),
        )
        via.validar()
        grupo_id = str(datos.get("grupo_id") or "")
        ahora = self.s.reloj.ahora_ms()

        with self.s.uow() as uow:
            abierta = uow.sesiones.sesion_abierta_de(actor.id)
            if abierta:
                raise SesionActivaExistente(sesion_id=abierta["id"], codigo_union=abierta["codigo_union"])
            if grupo_id:
                del_grupo = uow.sesiones.sesion_activa_del_grupo(grupo_id)
                if del_grupo:
                    raise GrupoConSesionActiva(sesion_id=del_grupo["id"], profesor_id=del_grupo["profesor_id"])

            fuente_nombre = None
            curso = {"curso_ref": via.curso_ref, "curso_version": "", "curso_rotulo": "", "leccion_ref": via.leccion_ref,
                     "leccion_rotulo": "", "objeto_ref": via.objeto_ref, "objeto_rotulo": ""}
            selector_inicial: dict | None = None
            if via.necesita_curso:
                vista, fuente_nombre = self._vista(datos.get("fuente"), via.curso_ref, "docente")
                curso["curso_version"] = vista.get("version", "")
                curso["curso_rotulo"] = vista.get("titulo", "")
                hallado = cur.localizar(vista, leccion_ref=via.leccion_ref, objeto_ref=via.objeto_ref)
                if hallado["leccion"]:
                    curso["leccion_ref"] = hallado["leccion"]["leccion_ref"]
                    curso["leccion_rotulo"] = hallado["leccion"]["titulo"]
                if hallado["objeto"]:
                    if hallado["objeto"]["fuera_de_alcance"]:
                        raise DatosInvalidos(f"El objeto «{via.objeto_ref}» es de {hallado['objeto']['modulo']}: "
                                             "el aula no lo proyecta ni lo lanza.")
                    curso["objeto_rotulo"] = hallado["objeto"]["titulo"]
                    inicial = hallado
                else:
                    inicial = cur.primer_objeto(vista, via.leccion_ref)
                if inicial and inicial.get("objeto"):
                    selector_inicial = _selector_de(inicial, vista)

            sesion = uow.sesiones.crear_sesion({
                "id": _id(),
                "grupo_id": grupo_id,
                "grupo_rotulo": uow.identidad.rotulo_grupo(grupo_id) if grupo_id else "",
                "profesor_id": actor.id,
                "profesor_rotulo": actor.rotulo or uow.identidad.rotulo_persona(actor.id),
                "via_origen": via.via,
                "plan_id": str(datos.get("plan_id") or ""),
                "nodo_ref": via.nodo_ref,
                "fuente_curso": fuente_nombre or "",
                **curso,
                "codigo_union": dom.generar_codigo(uow.sesiones.codigo_ocupado),
                "estado": dom.ABIERTA,
                "superficie": str(datos.get("superficie") or actor.dispositivo or ""),
                "iniciada_en": ahora,
                "creado_en": ahora,
                "creado_por": actor.id,
            })
            # Por defecto los alumnos siguen al profesor (BR-050); liberar el seguimiento es una orden explícita.
            uow.sesiones.abrir_control(sesion["id"], dom.SEGUIMIENTO, ahora, actor.id, "inicio de la sesión")
            if selector_inicial:
                uow.sesiones.declarar_selector(sesion["id"], {**selector_inicial, "declarado_por": actor.id}, ahora)

            self._publicar(uow, sesion["id"], dom.EV_SESION_INICIADA, {
                "grupo_id": grupo_id, "plan_id": sesion["plan_id"], "profesor_id": actor.id, "via_origen": via.via,
                "curso_ref": curso["curso_ref"], "leccion_ref": curso["leccion_ref"], "superficie": sesion["superficie"],
                "instante": ahora,
            })
            self._publicar(uow, sesion["id"], dom.EV_CODIGO_GENERADO, {"codigo_union": sesion["codigo_union"], "instante": ahora})
            if selector_inicial:
                self._publicar(uow, sesion["id"], dom.EV_RECURSO_PROYECTADO, {**selector_inicial, "instante": ahora, "inicial": True})
            uow.auditoria.registrar(actor.id, "aula.sesion.iniciada", "m07_sesion", sesion["id"],
                                    nuevo={"via": via.via, "curso_ref": curso["curso_ref"], "grupo_id": grupo_id})
            return self._detalle(uow, sesion)


def _selector_de(hallado: dict, vista: dict, unidad_ref: str = "") -> dict:
    objeto = hallado["objeto"]
    leccion = hallado.get("leccion") or {}
    unidad = hallado.get("unidad")
    return {
        "curso_ref": vista.get("curso_ref", ""),
        "curso_version": vista.get("version", ""),
        "leccion_ref": leccion.get("leccion_ref", ""),
        "objeto_ref": objeto["objeto_ref"],
        "objeto_tipo": objeto["tipo"],
        "unidad_ref": (unidad or {}).get("unidad_ref") or (unidad or {}).get("pregunta_ref") or unidad_ref,
        "unidad_indice": (unidad or {}).get("indice"),
        "media_ref": "",
        "rotulo": (unidad or {}).get("titulo") or objeto["titulo"],
    }


class VerSesion(_CasoDeSesion):
    def ejecutar(self, sesion_id: str) -> dict:
        with self.s.uow() as uow:
            return self._detalle(uow, self._sesion(uow, sesion_id))


class ListarSesiones(_CasoDeSesion):
    """Lista las sesiones y, de paso, archiva las cerradas hace más de veinticuatro horas."""

    def ejecutar(self, estado: str | None = None, grupo_id: str | None = None, profesor_id: str | None = None) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            archivadas = ArchivarSesiones(self.s)._archivar(uow, ahora)
            filas = uow.sesiones.sesiones(estado=estado, grupo_id=grupo_id, profesor_id=profesor_id)
            return {"sesiones": filas, "archivadas_ahora": archivadas, "servidor_en": ahora}


class ArchivarSesiones(_CasoDeSesion):
    """Sección H: cerrada → archivada a las veinticuatro horas. Acción del sistema."""

    def ejecutar(self) -> int:
        with self.s.uow() as uow:
            return self._archivar(uow, self.s.reloj.ahora_ms())

    def _archivar(self, uow: UnidadDeTrabajo, ahora: int) -> int:
        cuantas = 0
        for sesion in uow.sesiones.cerradas_antes_de(ahora - dom.ARCHIVO_TRAS_MS):
            dom.comprobar_transicion(sesion["estado"], dom.ARCHIVADA)
            uow.sesiones.actualizar_sesion(sesion["id"], estado=dom.ARCHIVADA, archivada_en=ahora)
            uow.auditoria.registrar("sistema", "aula.sesion.archivada", "m07_sesion", sesion["id"])
            cuantas += 1
        return cuantas


class UnirseASesion(_CasoDeSesion):
    """JRN-007 · FUN-067 · FUN-077 · BR-047. La tableta presenta el código; si ya participó, se readmite sin duplicar.
    Antes de entrar, MOD-009 reconoce la tableta y abre en ella la sesión de alumno: una tableta bloqueada o
    retirada no entra (403 dispositivo_bloqueado / dispositivo_inactivo), regla del equipo y no de la persona."""

    def ejecutar(self, datos: dict) -> dict:
        codigo = str(datos.get("codigo_union") or datos.get("codigo") or "").strip()
        persona_id = str(datos.get("persona_id") or "").strip()
        if not codigo or not persona_id:
            raise DatosInvalidos("Faltan codigo_union y persona_id.")
        dispositivo = str(datos.get("dispositivo") or "")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = uow.sesiones.sesion_por_codigo(codigo)
            if not sesion:
                raise CodigoInvalido(f"No hay ninguna clase abierta con el código {codigo}.", codigo_union=codigo)
            existente = None
            if datos.get("participante_id"):
                existente = uow.sesiones.participante(str(datos["participante_id"]))
                if existente and existente["sesion_id"] != sesion["id"]:
                    existente = None
            existente = existente or uow.sesiones.participante_de(sesion["id"], persona_id)

            if existente and existente["estado"] in (dom.EXPULSADO, dom.RECHAZADO):
                raise ParticipanteExpulsado(
                    f"El participante fue {existente['estado']}; el profesor puede readmitirlo desde su panel.",
                    participante_id=existente["id"], estado=existente["estado"])
            equipo = self._equipo(uow, datos, dispositivo, persona_id, ahora)

            if existente:
                if existente["estado"] == dom.ESPERANDO:
                    participante = uow.sesiones.actualizar_participante(existente["id"], ultimo_latido_en=ahora,
                                                                        dispositivo=dispositivo or existente["dispositivo"], **equipo)
                    return {**self._estado_tableta(uow, sesion, participante), "nuevo": False, "en_espera": True}
                nuevo_estado = dom.CONECTADO if sesion["estado"] == dom.ABIERTA else dom.RECONECTANDO
                participante = uow.sesiones.actualizar_participante(
                    existente["id"], estado=nuevo_estado, salida=None, ultimo_latido_en=ahora,
                    dispositivo=dispositivo or existente["dispositivo"],
                    sesion_usuario_id=str(datos.get("sesion_usuario_id") or existente["sesion_usuario_id"]), **equipo)
                uow.sesiones.registrar_presencia(participante["id"], nuevo_estado, ahora, dispositivo, "readmisión")
                self._publicar(uow, sesion["id"], dom.EV_DISPOSITIVO_READMITIDO, {
                    "participante_id": participante["id"], "persona_id": persona_id, "dispositivo": dispositivo, "instante": ahora})
                return {**self._estado_tableta(uow, sesion, participante), "nuevo": False, "en_espera": False}

            # Participante nuevo: BR-047 decide si entra directo o queda en la lista de espera.
            inscrito = uow.identidad.esta_inscrito(sesion["grupo_id"], persona_id) if sesion["grupo_id"] else None
            estado = dom.CONECTADO if inscrito in (True, None) else dom.ESPERANDO
            if estado == dom.CONECTADO and sesion["estado"] != dom.ABIERTA:
                estado = dom.RECONECTANDO
            participante = uow.sesiones.crear_participante({
                "id": _id(), "sesion_id": sesion["id"], "persona_id": persona_id,
                "persona_rotulo": str(datos.get("persona_rotulo") or "") or uow.identidad.rotulo_persona(persona_id),
                "dispositivo": dispositivo, "sesion_usuario_id": str(datos.get("sesion_usuario_id") or ""),
                "estado": estado, "admision_nominal": False, "ingreso": ahora,
                "ultimo_latido_en": ahora, "creado_en": ahora, "creado_por": persona_id, **equipo,
            })
            uow.sesiones.registrar_presencia(participante["id"], estado, ahora, dispositivo, "ingreso")
            if estado != dom.ESPERANDO:
                self._publicar(uow, sesion["id"], dom.EV_DISPOSITIVO_ADMITIDO, {
                    "participante_id": participante["id"], "persona_id": persona_id, "dispositivo": dispositivo,
                    "inscrito": inscrito, "instante": ahora})
                self._publicar(uow, sesion["id"], dom.EV_PRESENCIA_REGISTRADA, {
                    "participante_id": participante["id"], "estado": estado, "instante": ahora})
            uow.auditoria.registrar(persona_id, "aula.participante.ingreso", "m07_participante", participante["id"],
                                    nuevo={"estado": estado, "sesion_id": sesion["id"]})
            return {**self._estado_tableta(uow, sesion, participante), "nuevo": True, "en_espera": estado == dom.ESPERANDO}


class AdmitirParticipante(_CasoDeSesion):
    """FUN-067 y BR-048 (readmisión manual). Un invitado admitido por su nombre queda como admisión nominal."""

    def ejecutar(self, actor: Actor, sesion_id: str, participante_id: str) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_DEVICE_ADMIT)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.exigir_abierta(sesion["estado"], "admitir participantes")
            participante = self._participante(uow, sesion, participante_id)
            if participante["estado"] in dom.ADMITIDOS:
                return participante
            if participante.get("dispositivo_id") and participante["dispositivo_id"] in uow.dispositivos.bloqueados_entre([participante["dispositivo_id"]]):
                raise DispositivoBloqueado(f"La tableta «{participante['dispositivo']}» está bloqueada; desbloquéala antes de admitir.",
                                           participante_id=participante_id, dispositivo_id=participante["dispositivo_id"])
            inscrito = uow.identidad.esta_inscrito(sesion["grupo_id"], participante["persona_id"]) if sesion["grupo_id"] else None
            readmision = participante["estado"] in (dom.EXPULSADO, dom.RECHAZADO, dom.SALIO)
            participante = uow.sesiones.actualizar_participante(
                participante_id, estado=dom.CONECTADO, salida=None, admitido_por=actor.id, ultimo_latido_en=ahora,
                admision_nominal=(inscrito is not True))
            uow.sesiones.registrar_presencia(participante_id, dom.CONECTADO, ahora, participante["dispositivo"], "admitido por el profesor")
            evento = dom.EV_DISPOSITIVO_READMITIDO if readmision else dom.EV_DISPOSITIVO_ADMITIDO
            self._publicar(uow, sesion_id, evento, {"participante_id": participante_id, "persona_id": participante["persona_id"],
                                                    "admision_nominal": participante["admision_nominal"], "instante": ahora})
            uow.auditoria.registrar(actor.id, "aula.participante.admitido", "m07_participante", participante_id,
                                    nuevo={"admision_nominal": participante["admision_nominal"]})
            return participante


class RechazarParticipante(_CasoDeSesion):
    """FUN-068: sólo se rechaza a quien está en la lista de espera."""

    def ejecutar(self, actor: Actor, sesion_id: str, participante_id: str, motivo: str = "") -> dict:
        self.s.autorizacion.exigir(actor, dom.P_DEVICE_ADMIT)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            participante = self._participante(uow, sesion, participante_id)
            if participante["estado"] != dom.ESPERANDO:
                raise DatosInvalidos("Sólo se rechaza a un participante en la lista de espera.", estado=participante["estado"])
            participante = uow.sesiones.actualizar_participante(participante_id, estado=dom.RECHAZADO, salida=ahora, motivo=motivo[:200])
            uow.sesiones.registrar_presencia(participante_id, dom.RECHAZADO, ahora, participante["dispositivo"], motivo)
            self._publicar(uow, sesion_id, dom.EV_DISPOSITIVO_RECHAZADO, {"participante_id": participante_id, "instante": ahora})
            uow.auditoria.registrar(actor.id, "aula.participante.rechazado", "m07_participante", participante_id, nuevo={"motivo": motivo})
            return participante


class ExpulsarParticipante(_CasoDeSesion):
    """FUN-078 · BR-048: la expulsión no borra respuestas (MOD-010 no se toca)."""

    def ejecutar(self, actor: Actor, sesion_id: str, participante_id: str, motivo: str = "") -> dict:
        self.s.autorizacion.exigir(actor, dom.P_DEVICE_REMOVE)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            participante = self._participante(uow, sesion, participante_id)
            if participante["estado"] in (dom.EXPULSADO, dom.RECHAZADO):
                return participante
            participante = uow.sesiones.actualizar_participante(participante_id, estado=dom.EXPULSADO, salida=ahora, motivo=motivo[:200])
            uow.sesiones.registrar_presencia(participante_id, dom.EXPULSADO, ahora, participante["dispositivo"], motivo)
            self._publicar(uow, sesion_id, dom.EV_DISPOSITIVO_EXPULSADO, {"participante_id": participante_id,
                                                                          "persona_id": participante["persona_id"], "instante": ahora})
            uow.auditoria.registrar(actor.id, "aula.participante.expulsado", "m07_participante", participante_id, nuevo={"motivo": motivo})
            return participante


class RegistrarPresencia(_CasoDeSesion):
    """FUN-073. La tableta declara conectado / reconectando / salio; el nodo pone la hora (BR-062).
    Devuelve el estado que la tableta debe pintar (foco, controles, pendientes, avisos)."""

    def ejecutar(self, sesion_id: str, participante_id: str, estado: str | None = None, dispositivo: str = "",
                 desde: int | None = None) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            participante = self._participante(uow, sesion, participante_id)
            if participante["estado"] in (dom.EXPULSADO, dom.RECHAZADO):
                raise ParticipanteExpulsado(participante_id=participante_id, estado=participante["estado"])
            campos: dict = {"ultimo_latido_en": ahora}
            if dispositivo:
                campos["dispositivo"] = dispositivo
            if participante.get("dispositivo_id"):
                uow.dispositivos.latido(participante["dispositivo_id"], ahora)
            if estado and participante["estado"] != dom.ESPERANDO:
                if estado not in dom.PRESENCIA_DECLARABLE:
                    raise DatosInvalidos(f"Una tableta sólo declara {', '.join(dom.PRESENCIA_DECLARABLE)}.", estado=estado)
                if sesion["estado"] != dom.ABIERTA and estado == dom.CONECTADO:
                    estado = dom.RECONECTANDO   # con la sesión suspendida nadie está «conectado» a una clase
                if estado != participante["estado"]:
                    campos["estado"] = estado
                    campos["salida"] = ahora if estado == dom.SALIO else None
                    uow.sesiones.registrar_presencia(participante_id, estado, ahora, dispositivo or participante["dispositivo"])
                    self._publicar(uow, sesion_id, dom.EV_PRESENCIA_REGISTRADA, {
                        "participante_id": participante_id, "estado": estado, "instante": ahora})
                    # La sesión de alumno en la tableta (MOD-009) sigue a la presencia: salir la cierra; volver la reabre.
                    if estado == dom.SALIO and participante.get("dim_sesion_alumno_id"):
                        uow.dispositivos.cerrar_sesion_alumno(participante["dim_sesion_alumno_id"], ahora, "usuario")
                    elif estado in dom.ADMITIDOS and participante["estado"] == dom.SALIO and participante.get("dispositivo_id"):
                        reabierta = uow.dispositivos.abrir_sesion_alumno(participante["persona_id"], participante["dispositivo_id"],
                                                                         ahora, actor=participante["persona_id"])
                        campos["dim_sesion_alumno_id"] = reabierta["id"]
            participante = uow.sesiones.actualizar_participante(participante_id, **campos)
            return self._estado_tableta(uow, sesion, participante, desde)


class EstadoParaTableta(_CasoDeSesion):
    """Sólo lectura de la clase: lo mismo que devuelve la presencia, sin declarar nada. El sondeo cuenta como
    latido de la tableta (MOD-009) para saber qué equipos están vivos."""

    def ejecutar(self, sesion_id: str, participante_id: str | None = None, desde: int | None = None) -> dict:
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            participante = self._participante(uow, sesion, participante_id) if participante_id else None
            if participante and participante.get("dispositivo_id"):
                uow.dispositivos.latido(participante["dispositivo_id"], self.s.reloj.ahora_ms())
            return self._estado_tableta(uow, sesion, participante, desde)


class DeclararSelector(_CasoDeSesion):
    """FUN-069 · BR-049: el selector es lo que el profesor declara que proyecta; se valida contra el curso
    vigente. No es un lanzamiento: no espera confirmación ni genera intentos."""

    def ejecutar(self, actor: Actor, sesion_id: str, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_PRESENT)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.exigir_abierta(sesion["estado"], "cambios de selector")
            selector = dom.Selector(
                curso_ref=str(datos.get("curso_ref") or sesion["curso_ref"] or ""),
                leccion_ref=str(datos.get("leccion_ref") or ""),
                objeto_ref=str(datos.get("objeto_ref") or ""),
                unidad_ref=str(datos.get("unidad_ref") or ""),
                media_ref=str(datos.get("media_ref") or ""),
                rotulo=str(datos.get("rotulo") or "")[:250],
            )
            if not selector.objeto_ref and not selector.media_ref:
                raise DatosInvalidos("El selector exige objeto_ref (y opcionalmente unidad_ref) o media_ref.")
            selector.validar()
            registro: dict
            if selector.objeto_ref:
                vista, _ = self._vista(datos.get("fuente") or sesion["fuente_curso"] or None, selector.curso_ref, "docente")
                hallado = cur.localizar(vista, leccion_ref=selector.leccion_ref, objeto_ref=selector.objeto_ref, unidad_ref=selector.unidad_ref)
                if hallado["objeto"]["fuera_de_alcance"]:
                    raise DatosInvalidos(f"El objeto «{selector.objeto_ref}» es de {hallado['objeto']['modulo']} y no se proyecta desde el aula.")
                registro = _selector_de(hallado, vista, selector.unidad_ref)
            else:
                registro = {"curso_ref": selector.curso_ref, "curso_version": sesion["curso_version"], "leccion_ref": selector.leccion_ref,
                            "objeto_ref": "", "objeto_tipo": "medio", "unidad_ref": "", "unidad_indice": None,
                            "media_ref": selector.media_ref, "rotulo": selector.rotulo}
            registro["declarado_por"] = actor.id
            vigente = uow.sesiones.declarar_selector(sesion_id, registro, ahora)
            self._publicar(uow, sesion_id, dom.EV_RECURSO_PROYECTADO, {**registro, "instante": ahora})
            uow.auditoria.registrar(actor.id, "aula.selector.declarado", "m07_selector", vigente["id"],
                                    nuevo={"objeto_ref": registro["objeto_ref"], "unidad_ref": registro["unidad_ref"], "media_ref": registro["media_ref"]})
            return vigente


class CambiarControl(_CasoDeSesion):
    """FUN-074 (bloqueo de pantallas) y BR-050 (seguimiento). Idempotente: activar lo activo no duplica."""

    def ejecutar(self, actor: Actor, sesion_id: str, tipo: str, activo: bool, motivo: str = "") -> dict:
        self.s.autorizacion.exigir(actor, dom.P_DEVICE_LOCK)
        if tipo not in dom.TIPOS_CONTROL:
            raise DatosInvalidos(f"El control «{tipo}» no existe. Controles: {', '.join(dom.TIPOS_CONTROL)}.")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.exigir_abierta(sesion["estado"], "controles")
            abiertos = {c["tipo"] for c in uow.sesiones.controles_abiertos(sesion_id)}
            cambio = False
            if activo and tipo not in abiertos:
                uow.sesiones.abrir_control(sesion_id, tipo, ahora, actor.id, motivo)
                cambio = True
            elif not activo and tipo in abiertos:
                uow.sesiones.cerrar_control(sesion_id, tipo, ahora, actor.id)
                cambio = True
            if cambio:
                if tipo == dom.BLOQUEO:
                    self._publicar(uow, sesion_id, dom.EV_DISPOSITIVOS_BLOQUEADOS, {"bloqueados": activo, "instante": ahora})
                uow.auditoria.registrar(actor.id, f"aula.control.{tipo}", "m07_control", sesion_id, nuevo={"activo": activo, "motivo": motivo})
            controles = uow.sesiones.controles_abiertos(sesion_id)
            return {"sesion_id": sesion_id, "tipo": tipo, "activo": activo, "cambio": cambio,
                    "seguimiento": any(c["tipo"] == dom.SEGUIMIENTO for c in controles),
                    "pantallas_bloqueadas": any(c["tipo"] == dom.BLOQUEO for c in controles), "controles": controles}


class Distribuir(_CasoDeSesion):
    """CAP-040 · FUN-070 · JRN-008: el lanzamiento. Un recurso o una actividad a todos los admitidos o a una
    selección, con avance de entrega. Las tabletas bloqueadas o retiradas (MOD-009) quedan fuera aunque estén
    en la selección, y constan en `excluidos_bloqueados`."""

    def ejecutar(self, actor: Actor, sesion_id: str, datos: dict) -> dict:
        clase = str(datos.get("clase") or dom.RECURSO)
        if clase not in dom.CLASES_DISTRIBUCION:
            raise DatosInvalidos(f"La clase «{clase}» no existe. Clases: {', '.join(dom.CLASES_DISTRIBUCION)}.")
        self.s.autorizacion.exigir(actor, dom.P_ACTIVITY_LAUNCH if clase == dom.ACTIVIDAD else dom.P_PRESENT)
        alcance = str(datos.get("alcance") or dom.GRUPO)
        if alcance not in dom.ALCANCES:
            raise DatosInvalidos(f"El alcance «{alcance}» no existe.")
        objeto_ref = str(datos.get("objeto_ref") or "")
        media_ref = str(datos.get("media_ref") or "")
        if not objeto_ref and not media_ref:
            raise DatosInvalidos("Una distribución exige objeto_ref o media_ref.")
        intentos_permitidos = dom.validar_regla_entera(datos.get("intentos_permitidos"), "intentos_permitidos")
        tiempo_limite_seg = dom.validar_regla_entera(datos.get("tiempo_limite_seg"), "tiempo_limite_seg")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.exigir_abierta(sesion["estado"], "distribuciones")
            admitidos = self._con_bloqueo(uow, self._admitidos(uow, sesion_id))
            if alcance == dom.SELECCION:
                elegidos = {str(p) for p in (datos.get("participantes") or [])}
                candidatos = [p for p in admitidos if p["id"] in elegidos or p["persona_id"] in elegidos]
            else:
                candidatos = admitidos
            destinatarios = [p for p in candidatos if not p["dispositivo_bloqueado"]]
            excluidos = [p["persona_id"] for p in candidatos if p["dispositivo_bloqueado"]]
            if clase == dom.ACTIVIDAD and not destinatarios:
                raise SinParticipantesAdmitidos(excluidos_bloqueados=excluidos)

            curso_ref = str(datos.get("curso_ref") or sesion["curso_ref"] or "")
            registro = {"id": _id(), "sesion_id": sesion_id, "clase": clase, "curso_ref": curso_ref, "leccion_ref": "",
                        "objeto_ref": objeto_ref, "objeto_tipo": "", "media_ref": media_ref,
                        "rotulo": str(datos.get("rotulo") or "")[:250], "alcance": alcance,
                        "destinatarios": [p["persona_id"] for p in destinatarios], "excluidos_bloqueados": excluidos,
                        "intentos_permitidos": intentos_permitidos, "tiempo_limite_seg": tiempo_limite_seg,
                        "disponible_estudio": bool(datos.get("disponible_estudio")), "asignacion_ref": "",
                        "abierta_en": ahora, "creado_por": actor.id}
            if objeto_ref:
                vista, _ = self._vista(datos.get("fuente") or sesion["fuente_curso"] or None, curso_ref, "docente")
                hallado = cur.localizar(vista, objeto_ref=objeto_ref)
                objeto = hallado["objeto"]
                if objeto["fuera_de_alcance"]:
                    raise DatosInvalidos(f"El objeto «{objeto_ref}» es de {objeto['modulo']}: el aula no lo lanza.")
                if clase == dom.ACTIVIDAD and objeto["tipo"] != "activity":
                    raise DatosInvalidos(f"Sólo se lanza como actividad un objeto de tipo «activity»; «{objeto_ref}» es «{objeto['tipo']}».")
                registro.update(leccion_ref=hallado["leccion"]["leccion_ref"], objeto_tipo=objeto["tipo"],
                                rotulo=registro["rotulo"] or objeto["titulo"], curso_ref=vista.get("curso_ref", curso_ref))
            if clase == dom.ACTIVIDAD:
                registro["asignacion_ref"] = uow.evaluacion.preparar_asignacion(
                    sesion_id, registro["curso_ref"], objeto_ref, [p["persona_id"] for p in destinatarios])
            distribucion = uow.sesiones.crear_distribucion(registro, [p["id"] for p in destinatarios])
            if clase == dom.ACTIVIDAD:
                self._publicar(uow, sesion_id, dom.EV_ACTIVIDAD_LANZADA, {
                    "distribucion_id": distribucion["id"], "curso_ref": registro["curso_ref"], "objeto_ref": objeto_ref,
                    "asignacion_ref": registro["asignacion_ref"], "alcance": alcance, "destinatarios": len(destinatarios),
                    "excluidos_bloqueados": len(excluidos), "intentos_permitidos": intentos_permitidos,
                    "tiempo_limite_seg": tiempo_limite_seg, "instante": ahora})
            uow.auditoria.registrar(actor.id, f"aula.distribucion.{clase}", "m07_distribucion", distribucion["id"],
                                    nuevo={"objeto_ref": objeto_ref, "media_ref": media_ref, "alcance": alcance,
                                           "destinatarios": len(destinatarios), "excluidos_bloqueados": excluidos})
            return distribucion


class ConfirmarEntrega(_CasoDeSesion):
    """La tableta confirma que recibió la distribución (o que falló)."""

    def ejecutar(self, sesion_id: str, distribucion_id: str, participante_id: str, estado: str = dom.ENTREGADO) -> dict:
        if estado not in (dom.ENTREGADO, dom.FALLIDO):
            raise DatosInvalidos("La confirmación es «entregado» o «fallido».")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            distribucion = uow.sesiones.distribucion(distribucion_id)
            if not distribucion or distribucion["sesion_id"] != sesion_id:
                raise NoEncontrado("No existe esa distribución en esta sesión.")
            self._participante(uow, sesion, participante_id)
            return uow.sesiones.confirmar_entrega(distribucion_id, participante_id, ahora, estado)


class CerrarDistribucion(_CasoDeSesion):
    """FUN-071: cerrar la recepción. Las respuestas encoladas se siguen aceptando (BR-052) en MOD-010."""

    def ejecutar(self, actor: Actor, sesion_id: str, distribucion_id: str) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_ACTIVITY_CLOSE)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            self._sesion(uow, sesion_id)
            distribucion = uow.sesiones.distribucion(distribucion_id)
            if not distribucion or distribucion["sesion_id"] != sesion_id:
                raise NoEncontrado("No existe esa distribución en esta sesión.")
            if distribucion["cerrada_en"] is not None:
                return distribucion
            distribucion = uow.sesiones.cerrar_distribucion(distribucion_id, ahora)
            if distribucion["clase"] == dom.ACTIVIDAD:
                self._publicar(uow, sesion_id, dom.EV_ACTIVIDAD_CERRADA, {"distribucion_id": distribucion_id,
                                                                         "asignacion_ref": distribucion["asignacion_ref"], "instante": ahora})
            uow.auditoria.registrar(actor.id, "aula.distribucion.cerrada", "m07_distribucion", distribucion_id)
            return distribucion


class MostrarResultados(_CasoDeSesion):
    """FUN-072: el profesor muestra el panel agregado en la pantalla. Los datos son de MOD-010/011;
    aquí sólo queda constancia del hecho y el conteo de entregas."""

    def ejecutar(self, actor: Actor, sesion_id: str, distribucion_id: str) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_RESULTS_VIEW)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            self._sesion(uow, sesion_id)
            distribucion = uow.sesiones.distribucion(distribucion_id)
            if not distribucion or distribucion["sesion_id"] != sesion_id:
                raise NoEncontrado("No existe esa distribución en esta sesión.")
            self._publicar(uow, sesion_id, dom.EV_RESULTADOS_MOSTRADOS, {"distribucion_id": distribucion_id, "instante": ahora})
            uow.auditoria.registrar(actor.id, "aula.resultados.mostrados", "m07_distribucion", distribucion_id)
            return {"distribucion": distribucion, "mostrado_en": ahora}


class EnviarAviso(_CasoDeSesion):
    """FUN-075: un aviso al grupo o a un participante admitido."""

    def ejecutar(self, actor: Actor, sesion_id: str, texto: str, participante_id: str | None = None) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_MESSAGE_SEND)
        texto = (texto or "").strip()
        if not texto:
            raise DatosInvalidos("El aviso no puede estar vacío.")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.exigir_abierta(sesion["estado"], "avisos")
            if participante_id:
                participante = self._participante(uow, sesion, participante_id)
                if participante["estado"] not in dom.ADMITIDOS:
                    raise DatosInvalidos("El destinatario no está admitido en la sesión.", estado=participante["estado"])
            aviso = uow.sesiones.crear_aviso({"id": _id(), "sesion_id": sesion_id, "participante_id": participante_id,
                                              "texto": texto[:300], "enviado_en": ahora, "creado_por": actor.id})
            self._publicar(uow, sesion_id, dom.EV_MENSAJE_ENVIADO, {"aviso_id": aviso["id"], "participante_id": participante_id,
                                                                   "alcance": "participante" if participante_id else "grupo", "instante": ahora})
            return aviso


class RotarCodigo(_CasoDeSesion):
    """FUN-066. El anterior queda en la auditoría; las tabletas ya unidas no se ven afectadas (su llave es el participante)."""

    def ejecutar(self, actor: Actor, sesion_id: str) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_CODE_ROTATE)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.exigir_abierta(sesion["estado"], "rotar el código")
            anterior = sesion["codigo_union"]
            nuevo = dom.generar_codigo(uow.sesiones.codigo_ocupado)
            sesion = uow.sesiones.actualizar_sesion(sesion_id, codigo_union=nuevo)
            self._publicar(uow, sesion_id, dom.EV_CODIGO_ROTADO, {"codigo_union": nuevo, "instante": ahora})
            uow.auditoria.registrar(actor.id, "aula.codigo.rotado", "m07_sesion", sesion_id,
                                    anterior={"codigo_union": anterior}, nuevo={"codigo_union": nuevo})
            return {"sesion_id": sesion_id, "codigo_union": nuevo, "rotado_en": ahora}


class SuspenderSesion(_CasoDeSesion):
    """Caída del equipo del aula (MOD-015 la detecta) o suspensión manual. Conserva código, foco y participantes."""

    def ejecutar(self, actor: Actor, sesion_id: str, causa: str = "manual") -> dict:
        if causa not in dom.CAUSAS_SUSPENSION:
            raise DatosInvalidos(f"Causa desconocida. Causas: {', '.join(dom.CAUSAS_SUSPENSION)}.")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.comprobar_transicion(sesion["estado"], dom.SUSPENDIDA)
            for p in self._admitidos(uow, sesion_id):
                uow.sesiones.actualizar_participante(p["id"], estado=dom.RECONECTANDO)
                uow.sesiones.registrar_presencia(p["id"], dom.RECONECTANDO, ahora, p["dispositivo"], f"suspensión: {causa}")
            sesion = uow.sesiones.actualizar_sesion(sesion_id, estado=dom.SUSPENDIDA, suspendida_en=ahora, causa_suspension=causa)
            uow.auditoria.registrar(actor.id, "aula.sesion.suspendida", "m07_sesion", sesion_id, nuevo={"causa": causa})
            return self._detalle(uow, sesion)


class ReanudarSesion(_CasoDeSesion):
    """FUN-076 · BR-051: mismo foco, mismos participantes, mismo código."""

    def ejecutar(self, actor: Actor, sesion_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.comprobar_transicion(sesion["estado"], dom.ABIERTA)
            corte = sesion["suspendida_en"]
            recuperados = sum(1 for p in uow.sesiones.participantes(sesion_id) if p["estado"] == dom.RECONECTANDO)
            sesion = uow.sesiones.actualizar_sesion(sesion_id, estado=dom.ABIERTA)
            self._publicar(uow, sesion_id, dom.EV_SESION_REANUDADA, {
                "causa": sesion["causa_suspension"], "instante_corte": corte, "instante_reanudacion": ahora,
                "dispositivos_por_recuperar": recuperados, "codigo_union": sesion["codigo_union"]})
            uow.auditoria.registrar(actor.id, "aula.sesion.reanudada", "m07_sesion", sesion_id,
                                    nuevo={"corte": corte, "reanudacion": ahora, "ventana_ms": (ahora - corte) if corte else None})
            return self._detalle(uow, sesion)


class CerrarSesion(_CasoDeSesion):
    """FUN-079 · CAP-045 · BR-052. Consolida el resumen y libera la sala. Una sesión cerrada no se reabre."""

    def ejecutar(self, actor: Actor, sesion_id: str, origen: str = "profesor", forzar: bool = False) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_END)
        if origen not in dom.ORIGENES_CIERRE:
            raise DatosInvalidos(f"Origen de cierre desconocido. Orígenes: {', '.join(dom.ORIGENES_CIERRE)}.")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            dom.comprobar_transicion(sesion["estado"], dom.CERRADA)
            abiertas = [d for d in uow.sesiones.distribuciones(sesion_id, abiertas=True) if d["clase"] == dom.ACTIVIDAD]
            if abiertas and not forzar:
                raise ActividadesAbiertas(f"Hay {len(abiertas)} actividad(es) abierta(s). Ciérralas o envía forzar=true (MSG-016).",
                                          distribuciones=[d["id"] for d in abiertas])
            for d in abiertas:
                uow.sesiones.cerrar_distribucion(d["id"], ahora)
                self._publicar(uow, sesion_id, dom.EV_ACTIVIDAD_CERRADA, {"distribucion_id": d["id"], "asignacion_ref": d["asignacion_ref"],
                                                                         "instante": ahora, "por_cierre_de_sesion": True})
            uow.sesiones.cerrar_controles(sesion_id, ahora, actor.id)
            participantes = uow.sesiones.participantes(sesion_id)
            for p in participantes:
                if p["estado"] in dom.ADMITIDOS:
                    uow.sesiones.actualizar_participante(p["id"], estado=dom.SALIO, salida=ahora)
                    uow.sesiones.registrar_presencia(p["id"], dom.SALIO, ahora, p["dispositivo"], "cierre de la sesión")
                    if p.get("dim_sesion_alumno_id"):
                        uow.dispositivos.cerrar_sesion_alumno(p["dim_sesion_alumno_id"], ahora, "sistema")
            distribuciones = uow.sesiones.distribuciones(sesion_id)
            personas = [p["persona_id"] for p in participantes]
            resumen = dom.ResumenSesion(
                participantes=len(participantes),
                conectados_maximo=uow.sesiones.conectados_maximo(sesion_id),
                admitidos_nominal=sum(1 for p in participantes if p["admision_nominal"]),
                selectores=uow.sesiones.total_selectores(sesion_id),
                distribuciones=len(distribuciones),
                actividades=sum(1 for d in distribuciones if d["clase"] == dom.ACTIVIDAD),
                avisos=len(uow.sesiones.avisos(sesion_id, limite=10_000)),
                pendientes=uow.evaluacion.intentos_abiertos(sesion["curso_ref"], personas) if sesion["curso_ref"] else 0,
                duracion_ms=max(0, ahora - (sesion["iniciada_en"] or ahora)),
                origen_cierre=origen,
                consolidado_en=ahora,
            )
            uow.sesiones.guardar_resumen(sesion_id, resumen.como_dict())
            sesion = uow.sesiones.actualizar_sesion(sesion_id, estado=dom.CERRADA, finalizada_en=ahora, origen_cierre=origen)
            self._publicar(uow, sesion_id, dom.EV_SESION_FINALIZADA, {
                "instante_fin": ahora, "origen_cierre": origen, "actividades_cerradas": len(abiertas),
                "dispositivos_liberados": sum(1 for p in participantes if p["estado"] in dom.ADMITIDOS),
                "presencia_consolidada": resumen.participantes, "pendientes": resumen.pendientes})
            uow.auditoria.registrar(actor.id, "aula.sesion.finalizada", "m07_sesion", sesion_id, nuevo=resumen.como_dict())
            return self._detalle(uow, sesion)
