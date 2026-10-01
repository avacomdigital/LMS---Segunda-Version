"""
Adaptadores de los puertos de MOD-009 sobre Django: el inventario y la sesión de alumno (ORM sobre
m09_*), la cola de salida, la auditoría (m19 del expediente), la organización y las sesiones de
login (lectura y cierre por los casos de uso de `acceso`, nunca por su ORM) y la autorización
(las políticas de MOD-001 cuando hay sesión; sin sesión, Q-04, se permite como en el aula).
"""
from __future__ import annotations

from expediente import servicios as expediente_servicios

from .. import models as m
from ..aplicacion.puertos import Actor
from ..dominio import dispositivo as dom
from ..dominio.errores import SinPermiso

CAMPOS_DISPOSITIVO = ("id", "organizacion_id", "identificador_hw", "nombre", "tipo", "plataforma", "version_app",
                      "activo", "bloqueado", "registrado_en", "ultimo_latido_en", "espacio_libre_mb", "bateria_pct",
                      "perfil", "asignado_a_id", "asignado_en", "capacidad_control", "capacidad_detalle", "capacidad_declarada_en")
CAMPOS_SESION = ("id", "alumno_id", "dispositivo_id", "iniciada_en", "finalizada_en", "motivo_cierre")


def _d(fila, campos) -> dict:
    return {campo: getattr(fila, campo) for campo in campos}


class DispositivosDjango:
    def crear(self, datos: dict) -> dict:
        return _d(m.Dispositivo.objects.create(**{k: v for k, v in datos.items() if k in CAMPOS_DISPOSITIVO}), CAMPOS_DISPOSITIVO)

    def por_id(self, dispositivo_id: str) -> dict | None:
        fila = m.Dispositivo.objects.filter(pk=dispositivo_id).first()
        return _d(fila, CAMPOS_DISPOSITIVO) if fila else None

    def por_identificador(self, organizacion_id: str, identificador_hw: str) -> dict | None:
        fila = m.Dispositivo.objects.filter(organizacion_id=organizacion_id, identificador_hw=identificador_hw).first()
        return _d(fila, CAMPOS_DISPOSITIVO) if fila else None

    def listar(self, organizacion_id: str, solo_activos: bool = True) -> list[dict]:
        filas = m.Dispositivo.objects.filter(organizacion_id=organizacion_id)
        if solo_activos:
            filas = filas.filter(activo=True)
        return [_d(f, CAMPOS_DISPOSITIVO) for f in filas.order_by("nombre", "identificador_hw")]

    def actualizar(self, dispositivo_id: str, **campos) -> dict:
        m.Dispositivo.objects.filter(pk=dispositivo_id).update(**campos)
        return self.por_id(dispositivo_id)

    def bloqueados_entre(self, dispositivo_ids: list[str]) -> set[str]:
        ids = [i for i in dispositivo_ids if i]
        if not ids:
            return set()
        return set(m.Dispositivo.objects.filter(pk__in=ids).filter(bloqueado=True).values_list("id", flat=True)) | \
            set(m.Dispositivo.objects.filter(pk__in=ids, activo=False).values_list("id", flat=True))

    def asignados_a(self, alumno_ids: list[str]) -> dict[str, dict]:
        ids = [i for i in alumno_ids if i]
        if not ids:
            return {}
        filas = m.Dispositivo.objects.filter(perfil=dom.ASIGNADO, asignado_a_id__in=ids, activo=True).order_by("asignado_en", "id")
        return {f.asignado_a_id: _d(f, CAMPOS_DISPOSITIVO) for f in filas}   # con varios, el más reciente gana


class SesionesAlumnoDjango:
    def sesion(self, sesion_id: str) -> dict | None:
        fila = m.DimSesionAlumno.objects.filter(pk=sesion_id).first()
        return _d(fila, CAMPOS_SESION) if fila else None

    def abierta_de_alumno(self, alumno_id: str) -> dict | None:
        fila = m.DimSesionAlumno.objects.filter(alumno_id=alumno_id, finalizada_en__isnull=True).first()
        return _d(fila, CAMPOS_SESION) if fila else None

    def abierta_en_dispositivo(self, dispositivo_id: str) -> dict | None:
        fila = m.DimSesionAlumno.objects.filter(dispositivo_id=dispositivo_id, finalizada_en__isnull=True).first()
        return _d(fila, CAMPOS_SESION) if fila else None

    def abiertas_por_dispositivo(self, dispositivo_ids: list[str]) -> dict[str, dict]:
        filas = m.DimSesionAlumno.objects.filter(dispositivo_id__in=dispositivo_ids, finalizada_en__isnull=True)
        return {f.dispositivo_id: _d(f, CAMPOS_SESION) for f in filas}

    def crear(self, datos: dict) -> dict:
        return _d(m.DimSesionAlumno.objects.create(**{k: v for k, v in datos.items() if k in CAMPOS_SESION}), CAMPOS_SESION)

    def cerrar(self, sesion_id: str, momento: int, motivo: str) -> dict | None:
        m.DimSesionAlumno.objects.filter(pk=sesion_id, finalizada_en__isnull=True).update(finalizada_en=momento, motivo_cierre=motivo)
        return self.sesion(sesion_id)


class OutboxDjango:
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None:
        if tipo_evento not in dom.EVENTOS:
            raise ValueError(f"Evento fuera del catálogo de MOD-009: {tipo_evento}")
        m.EventoSalida.objects.create(agregado_tipo=agregado_tipo, agregado_id=agregado_id, tipo_evento=tipo_evento, carga=carga)


class AuditoriaExpediente:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`, app `audit`) dentro de la transacción del caso de uso.
    El nombre se conserva por compatibilidad con el contenedor."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or "sistema", accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)


class OrganizacionesAcceso:
    """El nodo tiene una sola organización y la instala MOD-001. Sólo lectura."""

    def unica_id(self) -> str | None:
        from acceso.models import Organizacion
        fila = Organizacion.objects.order_by("creado_en").first()
        return fila.id if fila else None


class SesionesUsuarioAcceso:
    """Cierra las sesiones de login del dispositivo por los casos de uso de `acceso` (su outbox y su
    auditoría), nunca escribiendo m01_sesion desde aquí (BR-004)."""

    def cerrar_en_dispositivo(self, dispositivo_id: str, momento: int, actor: str) -> int:
        from acceso.aplicacion import casos_uso as acu
        from acceso.dominio.valores import MotivoCierre
        from acceso.infraestructura.contenedor import servicios as servicios_acceso

        s = servicios_acceso()
        base = acu.Base(s)
        cerradas = 0
        with s.uow() as uow:
            for sesion in uow.sesiones.abiertas_en_dispositivo(dispositivo_id, momento):
                base.cerrar_sesion(uow, sesion, MotivoCierre.DISPOSITIVO_BAJA, actor_id=actor or None)
                cerradas += 1
        return cerradas


class AlumnosAcceso:
    """Lee `m01_usuario` del módulo de acceso: quién existe y cómo se llama (el alias). Nunca escribe: MOD-009 no es dueño
    de personas. Sin organización instalada no se puede saber si alguien existe (Q-34): se devuelve None y no se bloquea."""

    def existe(self, alumno_id: str) -> bool | None:
        from acceso.models import Organizacion, Usuario
        if not Organizacion.objects.exists():
            return None
        return Usuario.objects.filter(pk=alumno_id).exists()

    def rotulos(self, alumno_ids: list[str]) -> dict[str, str]:
        ids = [i for i in alumno_ids if i]
        if not ids:
            return {}
        from acceso.models import Usuario
        return dict(Usuario.objects.filter(pk__in=ids).values_list("id", "alias"))


class PaquetesEstudioPerezoso:
    """MOD-008 visto desde el inventario (FUN-093). `modo_estudio` se importa al preguntar y no al cargar: este módulo no
    depende de él ni en el arranque ni en las migraciones. Si el modo de estudio no está instalado no hay paquetes."""

    def activos_en(self, dispositivo_id: str) -> int:
        try:
            from modo_estudio import servicios as estudio
        except ImportError:
            return 0
        return estudio.paquetes_activos_en(dispositivo_id)


class AutorizacionAcceso:
    """Traduce los permisos `device.*` a los que siembra MOD-001. Sin sesión (Q-04 abierta) se permite,
    igual que en el expediente y en el aula; con sesión de alumno se niega siempre (nivel 1)."""

    EQUIVALENCIAS = {
        dom.P_REGISTER: (),
        dom.P_READ: ("identity.device.manage", "identity.exam_access.grant"),
        dom.P_UPDATE: ("identity.device.manage",),
        dom.P_BLOCK: ("identity.device.manage", "identity.exam_access.grant"),
        # FUN-092 y FUN-093: asignar y liberar el equipo de una persona es administración de dispositivos (técnico y administrador).
        dom.P_ASSIGN: ("identity.device.manage",),
        dom.P_RELEASE: ("identity.device.manage",),
    }

    def exigir(self, actor: Actor, permiso: str) -> None:
        if permiso not in dom.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-009: {permiso}")
        equivalentes = self.EQUIVALENCIAS[permiso]
        if not equivalentes or not actor.autenticado or actor.principal is None:
            return
        if actor.nivel < 2:
            raise SinPermiso(f"La función exige {permiso}; un estudiante no administra dispositivos.", permiso=permiso)
        from acceso.aplicacion import casos_uso as acu
        from acceso.infraestructura.contenedor import servicios as servicios_acceso

        s = servicios_acceso()
        base = acu.Base(s)
        with s.uow() as uow:
            ctx = base.contexto(uow, actor.principal)
            for codigo in equivalentes:
                previa = base.politica.transversal(ctx, codigo)
                if previa is not None:
                    previa.exigir()
                if base.politica.alcance_concedido(ctx, codigo) is not None:
                    return
        raise SinPermiso(f"La función exige {permiso}.", permiso=permiso)
