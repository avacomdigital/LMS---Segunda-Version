"""
Adaptadores de los puertos de MOD-007 sobre Django: el cajón de sesiones (ORM sobre
m07_*), la cola de salida, la auditoría (m19 del expediente), la identidad (lectura
de m01_* del módulo de acceso) y la evaluación (lectura de m10_intento).

Los casos de uso reciben y devuelven dicts planos; aquí se traducen a filas.
"""
from __future__ import annotations

from django.db.models import Q

from expediente import servicios as expediente_servicios

from .. import models as m
from ..dominio import sesion as dom
from ..dominio.errores import DatosInvalidos, DispositivoBloqueado, DispositivoInactivo, NoEncontrado, SinPermiso
from ..aplicacion.puertos import Actor

# --------------------------------------------------------------------- filas → dicts

CAMPOS_SESION = (
    "id", "grupo_id", "grupo_rotulo", "profesor_id", "profesor_rotulo", "relevo_de_sesion_id", "via_origen", "plan_id",
    "nodo_ref", "fuente_curso", "curso_ref", "curso_version", "curso_rotulo", "leccion_ref", "leccion_rotulo", "objeto_ref",
    "objeto_rotulo", "codigo_union", "estado", "superficie", "iniciada_en", "suspendida_en", "causa_suspension",
    "finalizada_en", "origen_cierre", "archivada_en", "creado_en", "creado_por",
)
CAMPOS_PARTICIPANTE = (
    "id", "sesion_id", "persona_id", "persona_rotulo", "dispositivo", "dispositivo_id", "dim_sesion_alumno_id", "sesion_usuario_id",
    "estado", "admision_nominal", "ingreso", "salida", "ultimo_latido_en", "admitido_por", "motivo", "creado_en", "creado_por",
)
CAMPOS_SELECTOR = ("id", "sesion_id", "curso_ref", "curso_version", "leccion_ref", "objeto_ref", "objeto_tipo", "unidad_ref",
                   "unidad_indice", "media_ref", "rotulo", "vigente", "declarado_en", "declarado_por", "sustituido_en")
CAMPOS_CONTROL = ("id", "sesion_id", "tipo", "desde", "hasta", "motivo", "creado_por", "cerrado_por")
CAMPOS_DISTRIBUCION = ("id", "sesion_id", "clase", "curso_ref", "leccion_ref", "objeto_ref", "objeto_tipo", "media_ref",
                       "rotulo", "alcance", "destinatarios", "excluidos_bloqueados", "intentos_permitidos", "tiempo_limite_seg",
                       "disponible_estudio", "asignacion_ref", "abierta_en", "cerrada_en", "creado_por")
CAMPOS_AVISO = ("id", "sesion_id", "participante_id", "texto", "enviado_en", "creado_por")
CAMPOS_RESUMEN = ("participantes", "conectados_maximo", "admitidos_nominal", "selectores", "distribuciones", "actividades",
                  "avisos", "pendientes", "duracion_ms", "origen_cierre", "consolidado_en")


def _d(fila, campos) -> dict:
    return {campo: getattr(fila, campo) for campo in campos}


class SesionesDjango:
    """Implementa `RepositorioSesiones`. Nada se borra (CV-05)."""

    # ------------------------------------------------------------- sesiones
    def crear_sesion(self, datos: dict) -> dict:
        return _d(m.SesionDeClase.objects.create(**datos), CAMPOS_SESION)

    def sesion(self, sesion_id: str) -> dict | None:
        fila = m.SesionDeClase.objects.filter(pk=sesion_id).first()
        return _d(fila, CAMPOS_SESION) if fila else None

    def sesion_por_codigo(self, codigo: str) -> dict | None:
        fila = m.SesionDeClase.objects.filter(codigo_union=codigo, estado__in=dom.ACTIVAS).first()
        return _d(fila, CAMPOS_SESION) if fila else None

    def sesiones(self, estado=None, grupo_id=None, profesor_id=None) -> list[dict]:
        filas = m.SesionDeClase.objects.all().order_by("-creado_en")
        if estado:
            filas = filas.filter(estado__in=[e for e in str(estado).split(",") if e])
        if grupo_id:
            filas = filas.filter(grupo_id=grupo_id)
        if profesor_id:
            filas = filas.filter(profesor_id=profesor_id)
        return [_d(f, CAMPOS_SESION) for f in filas[:200]]

    def sesion_abierta_de(self, profesor_id: str) -> dict | None:
        fila = m.SesionDeClase.objects.filter(profesor_id=profesor_id, estado=dom.ABIERTA).first()
        return _d(fila, CAMPOS_SESION) if fila else None

    def sesion_activa_del_grupo(self, grupo_id: str) -> dict | None:
        fila = m.SesionDeClase.objects.filter(grupo_id=grupo_id, estado__in=dom.ACTIVAS).first()
        return _d(fila, CAMPOS_SESION) if fila else None

    def codigo_ocupado(self, codigo: str) -> bool:
        return m.SesionDeClase.objects.filter(codigo_union=codigo, estado__in=dom.ACTIVAS).exists()

    def actualizar_sesion(self, sesion_id: str, **campos) -> dict:
        m.SesionDeClase.objects.filter(pk=sesion_id).update(**campos)
        return self.sesion(sesion_id)

    def cerradas_antes_de(self, momento: int) -> list[dict]:
        filas = m.SesionDeClase.objects.filter(estado=dom.CERRADA, finalizada_en__lte=momento)
        return [_d(f, CAMPOS_SESION) for f in filas]

    # --------------------------------------------------------- participantes
    def participantes(self, sesion_id: str) -> list[dict]:
        return [_d(p, CAMPOS_PARTICIPANTE) for p in m.Participante.objects.filter(sesion_id=sesion_id).order_by("ingreso")]

    def participante(self, participante_id: str) -> dict | None:
        fila = m.Participante.objects.filter(pk=participante_id).first()
        return _d(fila, CAMPOS_PARTICIPANTE) if fila else None

    def participante_de(self, sesion_id: str, persona_id: str) -> dict | None:
        fila = m.Participante.objects.filter(sesion_id=sesion_id, persona_id=persona_id).first()
        return _d(fila, CAMPOS_PARTICIPANTE) if fila else None

    def crear_participante(self, datos: dict) -> dict:
        return _d(m.Participante.objects.create(**datos), CAMPOS_PARTICIPANTE)

    def actualizar_participante(self, participante_id: str, **campos) -> dict:
        m.Participante.objects.filter(pk=participante_id).update(**campos)
        return self.participante(participante_id)

    def registrar_presencia(self, participante_id: str, estado: str, momento: int, dispositivo: str = "", detalle: str = "") -> None:
        m.Presencia.objects.create(participante_id=participante_id, estado=estado, momento=momento,
                                   dispositivo=dispositivo or "", detalle=(detalle or "")[:200])

    def conectados_maximo(self, sesion_id: str) -> int:
        """Cuántas personas llegaron a estar admitidas a la vez, reconstruido de la bitácora de presencia."""
        eventos = m.Presencia.objects.filter(participante__sesion_id=sesion_id).order_by("momento", "id")
        estado_por_participante: dict[str, str] = {}
        maximo = 0
        for ev in eventos:
            estado_por_participante[ev.participante_id] = ev.estado
            actuales = sum(1 for e in estado_por_participante.values() if e in dom.ADMITIDOS)
            maximo = max(maximo, actuales)
        return maximo

    # -------------------------------------------------------------- selector
    def selector_vigente(self, sesion_id: str) -> dict | None:
        fila = m.Selector.objects.filter(sesion_id=sesion_id, vigente=True).first()
        return _d(fila, CAMPOS_SELECTOR) if fila else None

    def declarar_selector(self, sesion_id: str, datos: dict, momento: int) -> dict:
        m.Selector.objects.filter(sesion_id=sesion_id, vigente=True).update(vigente=False, sustituido_en=momento)
        import uuid
        fila = m.Selector.objects.create(id=str(uuid.uuid4()), sesion_id=sesion_id, vigente=True, declarado_en=momento,
                                         **{k: v for k, v in datos.items() if k in CAMPOS_SELECTOR and k not in ("id", "sesion_id", "vigente", "declarado_en", "sustituido_en")})
        return _d(fila, CAMPOS_SELECTOR)

    def total_selectores(self, sesion_id: str) -> int:
        return m.Selector.objects.filter(sesion_id=sesion_id).count()

    # -------------------------------------------------------------- controles
    def controles_abiertos(self, sesion_id: str) -> list[dict]:
        return [_d(c, CAMPOS_CONTROL) for c in m.Control.objects.filter(sesion_id=sesion_id, hasta__isnull=True)]

    def abrir_control(self, sesion_id: str, tipo: str, momento: int, actor: str, motivo: str = "") -> dict:
        import uuid
        fila = m.Control.objects.create(id=str(uuid.uuid4()), sesion_id=sesion_id, tipo=tipo, desde=momento,
                                        creado_por=actor, motivo=(motivo or "")[:200])
        return _d(fila, CAMPOS_CONTROL)

    def cerrar_control(self, sesion_id: str, tipo: str, momento: int, actor: str) -> dict | None:
        fila = m.Control.objects.filter(sesion_id=sesion_id, tipo=tipo, hasta__isnull=True).first()
        if not fila:
            return None
        fila.hasta = momento
        fila.cerrado_por = actor
        fila.save(update_fields=["hasta", "cerrado_por"])
        return _d(fila, CAMPOS_CONTROL)

    def cerrar_controles(self, sesion_id: str, momento: int, actor: str) -> int:
        return m.Control.objects.filter(sesion_id=sesion_id, hasta__isnull=True).update(hasta=momento, cerrado_por=actor)

    # --------------------------------------------------------- distribuciones
    def _distribucion(self, fila: m.Distribucion) -> dict:
        entregas = list(fila.entregas.all())
        return {
            **_d(fila, CAMPOS_DISTRIBUCION),
            "abierta": fila.cerrada_en is None,
            "entregas": {
                "total": len(entregas),
                "entregadas": sum(1 for e in entregas if e.estado == dom.ENTREGADO),
                "pendientes": sum(1 for e in entregas if e.estado == dom.PENDIENTE),
                "fallidas": sum(1 for e in entregas if e.estado == dom.FALLIDO),
                "detalle": [{"participante_id": e.participante_id, "estado": e.estado, "confirmada_en": e.confirmada_en,
                             "intentos": e.intentos} for e in entregas],
            },
        }

    def distribuciones(self, sesion_id: str, abiertas: bool | None = None) -> list[dict]:
        filas = m.Distribucion.objects.filter(sesion_id=sesion_id).order_by("abierta_en").prefetch_related("entregas")
        if abiertas is True:
            filas = filas.filter(cerrada_en__isnull=True)
        elif abiertas is False:
            filas = filas.filter(cerrada_en__isnull=False)
        return [self._distribucion(f) for f in filas]

    def distribucion(self, distribucion_id: str) -> dict | None:
        fila = m.Distribucion.objects.filter(pk=distribucion_id).prefetch_related("entregas").first()
        return self._distribucion(fila) if fila else None

    def crear_distribucion(self, datos: dict, participantes: list[str]) -> dict:
        fila = m.Distribucion.objects.create(**{k: v for k, v in datos.items() if k in CAMPOS_DISTRIBUCION})
        m.DistribucionEntrega.objects.bulk_create([
            m.DistribucionEntrega(distribucion=fila, participante_id=pid, estado=dom.PENDIENTE) for pid in participantes
        ])
        return self.distribucion(fila.id)

    def confirmar_entrega(self, distribucion_id: str, participante_id: str, momento: int, estado: str) -> dict:
        entrega, _ = m.DistribucionEntrega.objects.get_or_create(distribucion_id=distribucion_id, participante_id=participante_id)
        entrega.estado = estado
        entrega.intentos += 1
        entrega.confirmada_en = momento if estado == dom.ENTREGADO else entrega.confirmada_en
        entrega.save(update_fields=["estado", "intentos", "confirmada_en"])
        return {"distribucion_id": distribucion_id, "participante_id": participante_id, "estado": entrega.estado,
                "confirmada_en": entrega.confirmada_en, "intentos": entrega.intentos}

    def cerrar_distribucion(self, distribucion_id: str, momento: int) -> dict:
        m.Distribucion.objects.filter(pk=distribucion_id, cerrada_en__isnull=True).update(cerrada_en=momento)
        return self.distribucion(distribucion_id)

    def entregas_pendientes_de(self, sesion_id: str, participante_id: str) -> list[dict]:
        filas = (m.DistribucionEntrega.objects.filter(participante_id=participante_id, distribucion__sesion_id=sesion_id,
                                                      distribucion__cerrada_en__isnull=True)
                 .select_related("distribucion").order_by("distribucion__abierta_en"))
        return [{**_d(e.distribucion, CAMPOS_DISTRIBUCION), "entrega": e.estado, "confirmada_en": e.confirmada_en} for e in filas]

    # ------------------------------------------------------- avisos y resumen
    def crear_aviso(self, datos: dict) -> dict:
        return _d(m.Aviso.objects.create(**datos), CAMPOS_AVISO)

    def avisos(self, sesion_id: str, participante_id: str | None = None, desde: int | None = None, limite: int = 20) -> list[dict]:
        filas = m.Aviso.objects.filter(sesion_id=sesion_id).order_by("-enviado_en")
        if participante_id:
            filas = filas.filter(Q(participante_id=participante_id) | Q(participante__isnull=True))
        if desde:
            filas = filas.filter(enviado_en__gt=desde)
        return [_d(a, CAMPOS_AVISO) for a in filas[:limite]]

    def guardar_resumen(self, sesion_id: str, resumen: dict) -> dict:
        fila, _ = m.Resumen.objects.update_or_create(sesion_id=sesion_id, defaults={k: v for k, v in resumen.items() if k in CAMPOS_RESUMEN})
        return {"sesion_id": sesion_id, **_d(fila, CAMPOS_RESUMEN)}

    def resumen(self, sesion_id: str) -> dict | None:
        fila = m.Resumen.objects.filter(sesion_id=sesion_id).first()
        return {"sesion_id": sesion_id, **_d(fila, CAMPOS_RESUMEN)} if fila else None


class OutboxDjango:
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None:
        if tipo_evento not in dom.EVENTOS:
            raise ValueError(f"Evento fuera del catálogo de MOD-007: {tipo_evento}")
        m.EventoSalida.objects.create(agregado_tipo=agregado_tipo, agregado_id=agregado_id, tipo_evento=tipo_evento, carga=carga)


class AuditoriaExpediente:
    """m19_auditoria vive en el expediente (MOD-019 aún no tiene módulo propio). Sólo escritura."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None) -> None:
        expediente_servicios.auditar(actor or "sistema", accion, tabla, str(objeto_id or ""), anterior, nuevo)


class IdentidadAcceso:
    """Lee el padrón replicado en el módulo de acceso (m01_grupo, m01_miembro_grupo, m01_usuario).
    Nunca escribe: MOD-007 no es dueño de personas ni de grupos."""

    def rotulo_persona(self, persona_id: str) -> str:
        try:
            from acceso.models import Usuario
            fila = Usuario.objects.filter(pk=persona_id).first()
            return fila.alias if fila else ""
        except Exception:   # el aula no cae porque el módulo de acceso cambie
            return ""

    def rotulo_grupo(self, grupo_id: str) -> str:
        try:
            from acceso.models import Grupo
            fila = Grupo.objects.filter(pk=grupo_id).first()
            return fila.nombre if fila else ""
        except Exception:
            return ""

    def esta_inscrito(self, grupo_id: str, persona_id: str) -> bool | None:
        if not grupo_id:
            return None
        try:
            from acceso.models import Grupo, MiembroGrupo
            if not Grupo.objects.filter(pk=grupo_id).exists():
                return None   # sin padrón no se puede saber: no se bloquea a nadie (Q-34)
            return MiembroGrupo.objects.filter(grupo_id=grupo_id, usuario_id=persona_id, papel="ESTUDIANTE", hasta__isnull=True).exists()
        except Exception:
            return None

    def es_docente_del_grupo(self, grupo_id: str, persona_id: str) -> bool | None:
        if not grupo_id:
            return None
        try:
            from acceso.models import MiembroGrupo
            return MiembroGrupo.objects.filter(grupo_id=grupo_id, usuario_id=persona_id, papel="DOCENTE", hasta__isnull=True).exists()
        except Exception:
            return None


class DispositivosDeviceManager:
    """MOD-009 visto desde el aula: por su interfaz (`device_manager.servicios`), dentro de la transacción del
    caso de uso (BR-004: el aula no escribe m09_*, pide). Sus errores se traducen a los del aula."""

    @staticmethod
    def _traducir(fn, *args, **kwargs):
        from device_manager.dominio import errores as e9
        try:
            return fn(*args, **kwargs)
        except e9.DispositivoBloqueado as error:
            raise DispositivoBloqueado(error.detalle, **error.extra) from error
        except e9.DispositivoInactivo as error:
            raise DispositivoInactivo(error.detalle, **error.extra) from error
        except e9.NoEncontrado as error:
            raise NoEncontrado(error.detalle, **error.extra) from error
        except e9.ErrorDispositivos as error:
            raise DatosInvalidos(error.detalle, **error.extra) from error

    def resolver(self, identificador: str, nombre: str = "", plataforma: str = "", version_app: str = "",
                 momento: int | None = None) -> dict | None:
        from device_manager import servicios
        return self._traducir(servicios.resolver, identificador, nombre=nombre, plataforma=plataforma,
                              version_app=version_app, momento=momento)

    def por_id(self, dispositivo_id: str) -> dict | None:
        from device_manager import servicios
        return servicios.por_id(dispositivo_id)

    def latido(self, dispositivo_id: str, momento: int) -> None:
        from device_manager import servicios
        servicios.latido(dispositivo_id, momento)

    def bloqueados_entre(self, dispositivo_ids: list[str]) -> set[str]:
        from device_manager import servicios
        return servicios.bloqueados_entre(dispositivo_ids)

    def abrir_sesion_alumno(self, alumno_id: str, dispositivo_id: str, momento: int, actor: str = "") -> dict:
        from device_manager import servicios
        return self._traducir(servicios.abrir_sesion_alumno, alumno_id, dispositivo_id, momento, actor)

    def cerrar_sesion_alumno(self, sesion_id: str, momento: int, motivo: str) -> None:
        from device_manager import servicios
        servicios.cerrar_sesion_alumno(sesion_id, momento, motivo)


class EvaluacionExpediente:
    """MOD-010 visto desde el aula. Hoy el expediente no tiene asignaciones: la referencia queda
    vacía y la actividad se rinde con el flujo de intentos existente (Q-49)."""

    def preparar_asignacion(self, sesion_id: str, curso_ref: str, objeto_ref: str, personas: list[str]) -> str:
        return ""

    def intentos_abiertos(self, curso_ref: str, personas: list[str]) -> int:
        from expediente.models import Intento
        if not personas:
            return 0
        return Intento.objects.filter(curso_ref=curso_ref, persona_id__in=personas, estado=Intento.ABIERTO).count()


class AutorizacionPrototipo:
    """Mientras MOD-001 no siembre los permisos `classroom.*`: con sesión, sólo el personal (nivel ≥ 2)
    opera la clase; sin sesión (Q-34 abierta) se permite, igual que en el expediente."""

    def exigir(self, actor: Actor, permiso: str) -> None:
        if permiso not in dom.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-007: {permiso}")
        if actor.autenticado and actor.nivel < 2:
            raise SinPermiso(f"La función exige {permiso}; un estudiante no opera la clase.", permiso=permiso)
