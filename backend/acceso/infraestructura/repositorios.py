"""
Repositorios sobre Django ORM. Mapean filas ↔ entidades y cifran/descifran la PII
al cruzar la frontera. Son el único lugar del módulo que conoce `acceso.models`.
"""
from __future__ import annotations

import time
from typing import Iterable

from django.db.models import Q

from .. import models as m
from ..aplicacion.puertos import Cifrador
from ..dominio import entidades as e
from ..dominio.valores import (
    Alcance,
    BloqueoAlcance,
    ClaseSesion,
    EstadoUsuario,
    Menu,
    OrigenCuenta,
    PapelGrupo,
    ResultadoIntento,
    TipoAutorizacion,
    TipoDispositivo,
    TipoIdentificador,
    TipoSecreto,
)
from .invalidacion import invalida

CTX_NOMBRES, CTX_APELLIDOS, CTX_NACIMIENTO, CTX_TELEFONO, CTX_IDENT = (
    "persona.nombres", "persona.apellidos", "persona.fecha_nacimiento", "persona.telefono", "identificador.valor")


def _solo_digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


# ------------------------------------------------------------ organización


class OrganizacionesDjango:
    def unica(self) -> e.Organizacion | None:
        fila = m.Organizacion.objects.order_by("creado_en").first()
        return self._a_entidad(fila) if fila else None

    def guardar(self, o: e.Organizacion) -> None:
        m.Organizacion.objects.update_or_create(id=o.id, defaults=dict(
            codigo=o.codigo, nombre=o.nombre, pais=o.pais, idioma=o.idioma, locale=o.locale,
            zona_horaria=o.zona_horaria, creado_en=o.creado_en, visitante=o.visitante))

    @staticmethod
    def _a_entidad(f: m.Organizacion) -> e.Organizacion:
        return e.Organizacion(f.id, f.codigo, f.nombre, f.pais, f.idioma, f.locale, f.zona_horaria, f.creado_en, f.visitante)


class PoliticasDjango:
    def por_organizacion(self, organizacion_id: str) -> list[e.PoliticaCredencial]:
        return [self._a_entidad(f) for f in m.PoliticaCredencial.objects.filter(organizacion_id=organizacion_id).order_by("perfil")]

    def por_perfil(self, organizacion_id: str, perfil: Menu) -> e.PoliticaCredencial | None:
        f = m.PoliticaCredencial.objects.filter(organizacion_id=organizacion_id, perfil=perfil.value,
                                                nivel_clave__isnull=True).first()
        return self._a_entidad(f) if f else None

    def por_nivel(self, organizacion_id: str, perfil: Menu, nivel_clave: str) -> e.PoliticaCredencial | None:
        f = m.PoliticaCredencial.objects.filter(organizacion_id=organizacion_id, perfil=perfil.value,
                                                nivel_clave=nivel_clave).first()
        return self._a_entidad(f) if f else None

    def por_id(self, politica_id: str) -> e.PoliticaCredencial | None:
        f = m.PoliticaCredencial.objects.filter(id=politica_id).first()
        return self._a_entidad(f) if f else None

    @invalida
    def guardar(self, p: e.PoliticaCredencial) -> None:
        m.PoliticaCredencial.objects.update_or_create(id=p.id, defaults=dict(
            organizacion_id=p.organizacion_id, perfil=p.perfil.value, tipo_identificador=p.tipo_identificador.value,
            tipo_secreto=p.tipo_secreto.value, longitud_minima=p.longitud_minima, exige_mayuscula=p.exige_mayuscula,
            exige_minuscula=p.exige_minuscula, exige_digito=p.exige_digito, exige_simbolo=p.exige_simbolo,
            intentos_maximos=p.intentos_maximos, ventana_intentos_min=p.ventana_intentos_min,
            bloqueo_minutos=p.bloqueo_minutos, duracion_sesion_min=p.duracion_sesion_min,
            vigencia_credencial_dias=p.vigencia_credencial_dias, permite_acceso_temporal=p.permite_acceso_temporal,
            nivel_clave=p.nivel_clave, inactividad_min=p.inactividad_min,
            autoregistro=p.autoregistro, bloqueo_alcance=p.bloqueo_alcance.value,
            creado_en=p.creado_en, actualizado_en=p.actualizado_en))

    @staticmethod
    def _a_entidad(f: m.PoliticaCredencial) -> e.PoliticaCredencial:
        return e.PoliticaCredencial(
            id=f.id, organizacion_id=f.organizacion_id, perfil=Menu(f.perfil),
            tipo_identificador=TipoIdentificador(f.tipo_identificador), tipo_secreto=TipoSecreto(f.tipo_secreto),
            longitud_minima=f.longitud_minima, exige_mayuscula=f.exige_mayuscula, exige_minuscula=f.exige_minuscula,
            exige_digito=f.exige_digito, exige_simbolo=f.exige_simbolo, intentos_maximos=f.intentos_maximos,
            ventana_intentos_min=f.ventana_intentos_min, bloqueo_minutos=f.bloqueo_minutos,
            duracion_sesion_min=f.duracion_sesion_min, vigencia_credencial_dias=f.vigencia_credencial_dias,
            permite_acceso_temporal=f.permite_acceso_temporal, creado_en=f.creado_en, actualizado_en=f.actualizado_en,
            nivel_clave=f.nivel_clave, inactividad_min=f.inactividad_min, autoregistro=f.autoregistro,
            bloqueo_alcance=BloqueoAlcance(f.bloqueo_alcance))


# ------------------------------------------------------------ permisos/roles


class PermisosDjango:
    def listar(self) -> list[e.Permiso]:
        return [self._a_entidad(f) for f in m.Permiso.objects.order_by("modulo", "codigo")]

    def obtener(self, codigo: str) -> e.Permiso | None:
        f = m.Permiso.objects.filter(codigo=codigo).first()
        return self._a_entidad(f) if f else None

    def guardar(self, p: e.Permiso) -> None:
        m.Permiso.objects.update_or_create(codigo=p.codigo, defaults=dict(
            modulo=p.modulo, descripcion=p.descripcion, alcance_maximo=p.alcance_maximo.value))

    @staticmethod
    def _a_entidad(f: m.Permiso) -> e.Permiso:
        return e.Permiso(f.codigo, f.modulo, f.descripcion, Alcance(f.alcance_maximo))


class RolesDjango:
    def por_id(self, rol_id: str) -> e.Rol | None:
        f = m.Rol.objects.filter(id=rol_id).prefetch_related("permisos").first()
        return self._a_entidad(f) if f else None

    def por_codigo(self, organizacion_id: str, codigo: str) -> e.Rol | None:
        consulta = m.Rol.objects.filter(codigo=codigo).prefetch_related("permisos")
        propio = consulta.filter(organizacion_id=organizacion_id).first() if organizacion_id else None
        f = propio or consulta.filter(organizacion__isnull=True).first()
        return self._a_entidad(f) if f else None

    def listar(self, organizacion_id: str) -> list[e.Rol]:
        filas = m.Rol.objects.filter(Q(organizacion__isnull=True) | Q(organizacion_id=organizacion_id)) \
            .prefetch_related("permisos").order_by("-es_sistema", "nivel", "codigo")
        return [self._a_entidad(f) for f in filas]

    @invalida
    def guardar(self, r: e.Rol) -> None:
        fila, _ = m.Rol.objects.update_or_create(id=r.id, defaults=dict(
            organizacion_id=r.organizacion_id, codigo=r.codigo, nombre=r.nombre, menu_principal=r.menu_principal.value,
            nivel=r.nivel, es_sistema=r.es_sistema, creado_en=r.creado_en))
        fila.permisos.all().delete()
        m.RolPermiso.objects.bulk_create([
            m.RolPermiso(rol=fila, permiso_id=p.permiso_codigo, alcance=p.alcance.value) for p in r.permisos])

    @staticmethod
    def _a_entidad(f: m.Rol) -> e.Rol:
        return e.Rol(id=f.id, organizacion_id=f.organizacion_id, codigo=f.codigo, nombre=f.nombre,
                     menu_principal=Menu(f.menu_principal), nivel=f.nivel, es_sistema=f.es_sistema, creado_en=f.creado_en,
                     permisos=[e.RolPermiso(p.permiso_id, Alcance(p.alcance)) for p in f.permisos.all()])


# ----------------------------------------------------------------- usuarios


class UsuariosDjango:
    def __init__(self, cifrador: Cifrador):
        self.c = cifrador

    def por_id(self, usuario_id: str) -> e.Usuario | None:
        f = m.Usuario.objects.filter(id=usuario_id).first()
        return self._a_entidad(f) if f else None

    def por_identificador(self, valor_hmac: str) -> tuple[e.Usuario, e.Identificador] | None:
        f = m.IdentificadorUsuario.objects.filter(valor_hmac=valor_hmac, retirado_en__isnull=True) \
            .select_related("usuario").first()
        if f is None:
            return None
        return self._a_entidad(f.usuario), self._ident(f)

    @invalida
    def guardar(self, u: e.Usuario) -> None:
        m.Usuario.objects.update_or_create(id=u.id, defaults=dict(
            organizacion_id=u.organizacion_id, rol_id=u.rol_id, estado=u.estado.value, alias=u.alias, idioma=u.idioma,
            creado_en=u.creado_en, actualizado_en=u.actualizado_en, creado_por_id=u.creado_por,
            ultimo_acceso_en=u.ultimo_acceso_en, provisional=u.provisional, vinculado_a_id=u.vinculado_a,
            origen=u.origen.value, confirmado_en=u.confirmado_en))

    def asignaciones(self, usuario_id: str) -> list[e.UsuarioRol]:
        return [e.UsuarioRol(f.id, f.usuario_id, f.rol_id, Alcance(f.alcance_tipo), f.desde, f.alcance_id, f.hasta,
                             f.asignado_por_id, f.revocado_en)
                for f in m.UsuarioRol.objects.filter(usuario_id=usuario_id).order_by("desde")]

    @invalida
    def guardar_asignacion(self, a: e.UsuarioRol) -> None:
        m.UsuarioRol.objects.update_or_create(id=a.id, defaults=dict(
            usuario_id=a.usuario_id, rol_id=a.rol_id, alcance_tipo=a.alcance_tipo.value, alcance_id=a.alcance_id,
            desde=a.desde, hasta=a.hasta, asignado_por_id=a.asignado_por, revocado_en=a.revocado_en))

    def persona(self, usuario_id: str) -> e.Persona | None:
        f = m.Persona.objects.filter(usuario_id=usuario_id).first()
        if f is None:
            return None
        return e.Persona(
            usuario_id=f.usuario_id,
            nombres=self.c.descifrar(f.nombres_cifrado, CTX_NOMBRES),
            apellidos=self.c.descifrar(f.apellidos_cifrado, CTX_APELLIDOS) if f.apellidos_cifrado else "",
            pais=f.pais,
            fecha_nacimiento=self.c.descifrar(f.fecha_nacimiento_cifrado, CTX_NACIMIENTO) if f.fecha_nacimiento_cifrado else None,
            telefono=self.c.descifrar(f.telefono_cifrado, CTX_TELEFONO) if f.telefono_cifrado else None,
            actualizado_en=f.actualizado_en)

    def guardar_persona(self, p: e.Persona) -> None:
        m.Persona.objects.update_or_create(usuario_id=p.usuario_id, defaults=dict(
            nombres_cifrado=self.c.cifrar(p.nombres, CTX_NOMBRES),
            apellidos_cifrado=self.c.cifrar(p.apellidos, CTX_APELLIDOS) if p.apellidos else "",
            fecha_nacimiento_cifrado=self.c.cifrar(p.fecha_nacimiento, CTX_NACIMIENTO) if p.fecha_nacimiento else None,
            telefono_cifrado=self.c.cifrar(p.telefono, CTX_TELEFONO) if p.telefono else None,
            telefono_hmac=self.c.indice(_solo_digitos(p.telefono)) if p.telefono else None,
            pais=p.pais, actualizado_en=p.actualizado_en))

    def identificadores(self, usuario_id: str) -> list[e.Identificador]:
        return [self._ident(f) for f in m.IdentificadorUsuario.objects.filter(usuario_id=usuario_id, retirado_en__isnull=True)
                .order_by("-principal", "tipo")]

    def existe_identificador(self, valor_hmac: str, excepto_usuario: str | None = None) -> bool:
        consulta = m.IdentificadorUsuario.objects.filter(valor_hmac=valor_hmac, retirado_en__isnull=True)
        if excepto_usuario:
            consulta = consulta.exclude(usuario_id=excepto_usuario)
        return consulta.exists()

    def reemplazar_identificadores(self, usuario_id: str, identificadores: list[e.Identificador]) -> None:
        """CV-05 (nada se borra): los identificadores que dejan de valer se retiran con fecha; los nuevos se crean."""
        from ..dominio.valores import DocumentNumber  # normalización para el índice ciego
        ahora = int(time.time() * 1000)
        m.IdentificadorUsuario.objects.filter(usuario_id=usuario_id, retirado_en__isnull=True).update(retirado_en=ahora)
        m.IdentificadorUsuario.objects.bulk_create([
            m.IdentificadorUsuario(
                id=i.id, usuario_id=usuario_id, tipo=i.tipo.value,
                valor_cifrado=self.c.cifrar(i.valor, CTX_IDENT),
                valor_hmac=self.c.indice(DocumentNumber(i.tipo, i.valor).normalizado),
                es_login=i.es_login, verificado_en=i.verificado_en, creado_en=i.creado_en,
                emisor=i.emisor, principal=i.principal, retirado_en=None)
            for i in identificadores])

    def permisos_adicionales(self, usuario_id: str) -> list[e.UsuarioPermiso]:
        return [e.UsuarioPermiso(f.id, f.usuario_id, f.permiso_id, Alcance(f.alcance), f.otorgado_por_id, f.motivo,
                                 f.vigente_desde, f.vigente_hasta, f.revocado_en)
                for f in m.UsuarioPermiso.objects.filter(usuario_id=usuario_id).order_by("-vigente_desde")]

    def guardar_permiso_adicional(self, p: e.UsuarioPermiso) -> None:
        m.UsuarioPermiso.objects.update_or_create(id=p.id, defaults=dict(
            usuario_id=p.usuario_id, permiso_id=p.permiso_codigo, alcance=p.alcance.value, otorgado_por_id=p.otorgado_por,
            motivo=p.motivo, vigente_desde=p.vigente_desde, vigente_hasta=p.vigente_hasta, revocado_en=p.revocado_en))

    def listar(self, organizacion_id: str, alcance: Alcance, actor_id: str, grupos_docente: Iterable[str],
               nivel_maximo: int, grupo_id: str | None = None, rol_codigo: str | None = None,
               estado: str | None = None, origen: str | None = None) -> list[e.Usuario]:
        base = m.Usuario.objects.filter(organizacion_id=organizacion_id)
        vigente = Q(membresias__hasta__isnull=True)
        if alcance is Alcance.SELF:
            base = base.filter(id=actor_id)
        elif alcance is Alcance.ASSIGNED_GROUPS:
            base = base.filter(Q(id=actor_id) | (
                Q(membresias__grupo_id__in=list(grupos_docente), membresias__papel=PapelGrupo.ESTUDIANTE.value) & vigente))
        else:
            base = base.filter(Q(id=actor_id) | Q(rol__nivel__lte=nivel_maximo))
        if grupo_id:
            base = base.filter(Q(membresias__grupo_id=grupo_id) & vigente)
        if rol_codigo:
            base = base.filter(rol__codigo=rol_codigo)
        if estado:
            base = base.filter(estado=estado)
        if origen:
            base = base.filter(origen=origen)
        return [self._a_entidad(f) for f in base.distinct().order_by("alias")]

    def visitantes_activos(self, organizacion_id: str, creados_antes_de: int | None = None) -> list[e.Usuario]:
        """Las cuentas efímeras de visita (RN-45) que siguen activas; con `creados_antes_de`, sólo las que ya pasaron su día."""
        consulta = m.Usuario.objects.filter(organizacion_id=organizacion_id, origen=OrigenCuenta.VISITANTE.value,
                                            estado=EstadoUsuario.ACTIVO.value)
        if creados_antes_de is not None:
            consulta = consulta.filter(creado_en__lt=creados_antes_de)
        return [self._a_entidad(f) for f in consulta.order_by("creado_en")]
    def _ident(self, f: m.IdentificadorUsuario) -> e.Identificador:
        return e.Identificador(f.id, f.usuario_id, TipoIdentificador(f.tipo), self.c.descifrar(f.valor_cifrado, CTX_IDENT),
                               f.es_login, f.creado_en, f.verificado_en, f.emisor, f.principal, f.retirado_en)

    @staticmethod
    def _a_entidad(f: m.Usuario) -> e.Usuario:
        return e.Usuario(id=f.id, organizacion_id=f.organizacion_id, rol_id=f.rol_id, estado=EstadoUsuario(f.estado),
                         alias=f.alias, idioma=f.idioma, creado_en=f.creado_en, actualizado_en=f.actualizado_en,
                         creado_por=f.creado_por_id, ultimo_acceso_en=f.ultimo_acceso_en,
                         provisional=f.provisional, vinculado_a=f.vinculado_a_id,
                         origen=OrigenCuenta(f.origen), confirmado_en=f.confirmado_en)


class CredencialesDjango:
    def activa(self, usuario_id: str) -> e.Credencial | None:
        f = m.Credencial.objects.filter(usuario_id=usuario_id, activa=True).first()
        return self._a_entidad(f) if f else None

    def historial(self, usuario_id: str, cantidad: int) -> list[e.Credencial]:
        return [self._a_entidad(f) for f in m.Credencial.objects.filter(usuario_id=usuario_id).order_by("-creado_en")[:cantidad]]

    @invalida
    def guardar(self, c: e.Credencial) -> None:
        m.Credencial.objects.update_or_create(id=c.id, defaults=dict(
            usuario_id=c.usuario_id, tipo=c.tipo.value, hash=c.hash, activa=c.activa, debe_cambiar=c.debe_cambiar,
            creado_en=c.creado_en, expira_en=c.expira_en, sustituida_en=c.sustituida_en, creado_por_id=c.creado_por))

    @invalida
    def desactivar(self, usuario_id: str, ahora: int) -> None:
        m.Credencial.objects.filter(usuario_id=usuario_id, activa=True).update(activa=False, sustituida_en=ahora)

    @staticmethod
    def _a_entidad(f: m.Credencial) -> e.Credencial:
        return e.Credencial(f.id, f.usuario_id, TipoSecreto(f.tipo), f.hash, f.activa, f.debe_cambiar, f.creado_en,
                            f.expira_en, f.sustituida_en, f.creado_por_id)


class PinesMaestrosDjango:
    """Las versiones del PIN maestro de la institución (D-A5). Sólo la huella; nada se borra."""

    def activo(self, organizacion_id: str) -> e.PinMaestro | None:
        f = m.PinMaestro.objects.filter(organizacion_id=organizacion_id, activa=True).first()
        return self._a_entidad(f) if f else None

    def ultimos(self, organizacion_id: str, cantidad: int) -> list[e.PinMaestro]:
        """Las últimas versiones (la vigente incluida), de la más reciente a la más antigua: lo que RN-05 no deja reutilizar."""
        filas = m.PinMaestro.objects.filter(organizacion_id=organizacion_id).order_by("-creado_en")[:cantidad]
        return [self._a_entidad(f) for f in filas]

    def sustituir_activo(self, organizacion_id: str, ahora: int) -> None:
        m.PinMaestro.objects.filter(organizacion_id=organizacion_id, activa=True).update(activa=False, sustituida_en=ahora)

    def guardar(self, p: e.PinMaestro) -> None:
        m.PinMaestro.objects.update_or_create(id=p.id, defaults=dict(
            organizacion_id=p.organizacion_id, hash=p.hash, activa=p.activa, creado_en=p.creado_en,
            creado_por_id=p.creado_por, vence_en=p.vence_en, sustituida_en=p.sustituida_en))

    @staticmethod
    def _a_entidad(f: m.PinMaestro) -> e.PinMaestro:
        return e.PinMaestro(f.id, f.organizacion_id, f.hash, f.activa, f.creado_en, f.vence_en, f.creado_por_id, f.sustituida_en)


# ------------------------------------------------------------------- grupos


class GruposDjango:
    def por_id(self, grupo_id: str) -> e.Grupo | None:
        f = m.Grupo.objects.filter(id=grupo_id).first()
        return self._a_entidad(f) if f else None

    def listar(self, organizacion_id: str, solo_ids: Iterable[str] | None = None) -> list[e.Grupo]:
        consulta = m.Grupo.objects.filter(organizacion_id=organizacion_id)
        if solo_ids is not None:
            consulta = consulta.filter(id__in=list(solo_ids))
        return [self._a_entidad(f) for f in consulta.order_by("periodo", "codigo")]

    @invalida
    def guardar(self, g: e.Grupo) -> None:
        m.Grupo.objects.update_or_create(id=g.id, defaults=dict(
            organizacion_id=g.organizacion_id, codigo=g.codigo, nombre=g.nombre, periodo=g.periodo,
            politica_credencial_id=g.politica_credencial_id, activo=g.activo, creado_en=g.creado_en,
            nivel_clave=g.nivel_clave))

    def ids_grupos_por_nivel(self, organizacion_id: str, nivel_clave: str) -> frozenset[str]:
        return frozenset(m.Grupo.objects.filter(organizacion_id=organizacion_id, nivel_clave=nivel_clave, activo=True)
                         .values_list("id", flat=True))

    def nivel_de_usuario(self, usuario_id: str, ahora: int) -> str | None:
        f = m.MiembroGrupo.objects.filter(
            usuario_id=usuario_id, papel=PapelGrupo.ESTUDIANTE.value, hasta__isnull=True, grupo__activo=True,
            grupo__nivel_clave__isnull=False).select_related("grupo").order_by("desde").first()
        return f.grupo.nivel_clave if f else None

    def estudiantes_activos(self, grupo_id: str) -> list[tuple[e.Usuario, bool]]:
        """Los alumnos vigentes y activos del grupo, con si su cuenta ya tiene PIN (credencial activa): alimenta «toca tu nombre» (RB-16)."""
        filas = m.MiembroGrupo.objects.filter(
            grupo_id=grupo_id, papel=PapelGrupo.ESTUDIANTE.value, hasta__isnull=True, grupo__activo=True,
            usuario__estado=EstadoUsuario.ACTIVO.value).select_related("usuario").order_by("usuario__alias")
        con_credencial = set(m.Credencial.objects.filter(
            usuario_id__in=[f.usuario_id for f in filas], activa=True).values_list("usuario_id", flat=True))
        return [(UsuariosDjango._a_entidad(f.usuario), f.usuario_id in con_credencial) for f in filas]

    def miembros(self, grupo_id: str, vigentes: bool = True) -> list[e.MiembroGrupo]:
        consulta = m.MiembroGrupo.objects.filter(grupo_id=grupo_id)
        if vigentes:
            consulta = consulta.filter(hasta__isnull=True)
        return [self._miembro(f) for f in consulta.order_by("papel", "desde")]

    def membresias(self, usuario_id: str, vigentes: bool = True) -> list[e.MiembroGrupo]:
        consulta = m.MiembroGrupo.objects.filter(usuario_id=usuario_id)
        if vigentes:
            consulta = consulta.filter(hasta__isnull=True)
        return [self._miembro(f) for f in consulta.order_by("desde")]

    @invalida
    def guardar_miembro(self, mg: e.MiembroGrupo) -> None:
        m.MiembroGrupo.objects.update_or_create(id=mg.id, defaults=dict(
            grupo_id=mg.grupo_id, usuario_id=mg.usuario_id, papel=mg.papel.value, desde=mg.desde, hasta=mg.hasta))

    def ids_grupos(self, usuario_id: str, papel: PapelGrupo | None, ahora: int) -> frozenset[str]:
        consulta = m.MiembroGrupo.objects.filter(usuario_id=usuario_id, hasta__isnull=True, grupo__activo=True)
        if papel is not None:
            consulta = consulta.filter(papel=papel.value)
        return frozenset(consulta.values_list("grupo_id", flat=True))

    def politica_de_grupo(self, usuario_id: str, ahora: int) -> e.PoliticaCredencial | None:
        f = m.MiembroGrupo.objects.filter(
            usuario_id=usuario_id, papel=PapelGrupo.ESTUDIANTE.value, hasta__isnull=True, grupo__activo=True,
            grupo__politica_credencial__isnull=False).select_related("grupo__politica_credencial").order_by("desde").first()
        return PoliticasDjango._a_entidad(f.grupo.politica_credencial) if f else None

    @staticmethod
    def _a_entidad(f: m.Grupo) -> e.Grupo:
        return e.Grupo(f.id, f.organizacion_id, f.codigo, f.nombre, f.periodo, f.activo, f.creado_en,
                       f.politica_credencial_id, f.nivel_clave)

    @staticmethod
    def _miembro(f: m.MiembroGrupo) -> e.MiembroGrupo:
        return e.MiembroGrupo(f.id, f.grupo_id, f.usuario_id, PapelGrupo(f.papel), f.desde, f.hasta)


# ------------------------------------------------------------- dispositivos


class DispositivosDjango:
    """El inventario es de MOD-009: se lee y se escribe por su interfaz (`device_manager.servicios`), dentro
    de la transacción del login. Aquí sólo se traduce al vocabulario de este módulo (identificador,
    ultimo_visto_en)."""

    def por_id(self, dispositivo_id: str) -> e.Dispositivo | None:
        from device_manager import servicios as dispositivos
        fila = dispositivos.por_id(dispositivo_id)
        return self._a_entidad(fila) if fila else None

    def por_identificador(self, organizacion_id: str, identificador: str) -> e.Dispositivo | None:
        from device_manager import servicios as dispositivos
        fila = dispositivos.por_identificador(organizacion_id, identificador)
        return self._a_entidad(fila) if fila else None

    def listar(self, organizacion_id: str, solo_activos: bool = True) -> list[e.Dispositivo]:
        from device_manager import servicios as dispositivos
        return [self._a_entidad(f) for f in dispositivos.listar(organizacion_id, solo_activos)]

    @invalida
    def guardar(self, d: e.Dispositivo) -> None:
        """Lo único que el login cambia de un dispositivo: su último latido y, si cambió, su nombre."""
        from device_manager import servicios as dispositivos
        dispositivos.latido(d.id, d.ultimo_visto_en)
        actual = dispositivos.por_id(d.id)
        if actual and d.nombre and actual["nombre"] != d.nombre:
            dispositivos.renombrar(d.id, d.nombre)

    @staticmethod
    def _a_entidad(f: dict) -> e.Dispositivo:
        return e.Dispositivo(f["id"], f["organizacion_id"], f["identificador_hw"], f["nombre"], TipoDispositivo(f["tipo"]),
                             f["activo"], f["registrado_en"], f["ultimo_latido_en"], bloqueado=bool(f.get("bloqueado")))


# ----------------------------------------------------------------- sesiones


class SesionesDjango:
    def por_id(self, sesion_id: str) -> e.Sesion | None:
        f = m.Sesion.objects.filter(id=sesion_id).first()
        return self._a_entidad(f) if f else None

    @invalida
    def guardar(self, s: e.Sesion) -> None:
        m.Sesion.objects.update_or_create(id=s.id, defaults=dict(
            usuario_id=s.usuario_id, dispositivo_id=s.dispositivo_id, clase=s.clase.value, emitida_en=s.emitida_en,
            expira_en=s.expira_en, ultimo_uso_en=s.ultimo_uso_en, revocada_en=s.revocada_en,
            motivo_revocacion=s.motivo_revocacion, evaluacion_ref=s.evaluacion_ref, rol_id=s.rol_id))

    def tocar(self, sesion_id: str, ahora: int) -> None:
        """Sólo el «último uso»: lo que mide la inactividad. No cambia quién es la persona de la sesión, así que NO vacía la caché de pases."""
        m.Sesion.objects.filter(id=sesion_id).update(ultimo_uso_en=ahora)

    def abiertas_de_usuario(self, usuario_id: str, ahora: int) -> list[e.Sesion]:
        filas = m.Sesion.objects.filter(usuario_id=usuario_id, revocada_en__isnull=True, expira_en__gt=ahora)
        return [self._a_entidad(f) for f in filas.order_by("-emitida_en")]

    def abiertas_en_dispositivo(self, dispositivo_id: str, ahora: int) -> list[e.Sesion]:
        filas = m.Sesion.objects.filter(dispositivo_id=dispositivo_id, revocada_en__isnull=True, expira_en__gt=ahora)
        return [self._a_entidad(f) for f in filas.order_by("-emitida_en")]

    def listar(self, organizacion_id: str, usuario_id: str | None, solo_activas: bool, ahora: int,
               usuarios_permitidos: Iterable[str] | None = None) -> list[e.Sesion]:
        consulta = m.Sesion.objects.filter(usuario__organizacion_id=organizacion_id)
        if usuario_id:
            consulta = consulta.filter(usuario_id=usuario_id)
        if usuarios_permitidos is not None:
            consulta = consulta.filter(usuario_id__in=list(usuarios_permitidos))
        if solo_activas:
            consulta = consulta.filter(revocada_en__isnull=True, expira_en__gt=ahora)
        return [self._a_entidad(f) for f in consulta.order_by("-emitida_en")[:500]]

    @invalida
    def revocar_de_usuario(self, usuario_id: str, motivo: str, ahora: int, excepto: str | None = None) -> int:
        consulta = m.Sesion.objects.filter(usuario_id=usuario_id, revocada_en__isnull=True, expira_en__gt=ahora)
        if excepto:
            consulta = consulta.exclude(id=excepto)
        return consulta.update(revocada_en=ahora, motivo_revocacion=motivo)

    @staticmethod
    def _a_entidad(f: m.Sesion) -> e.Sesion:
        return e.Sesion(f.id, f.usuario_id, ClaseSesion(f.clase), f.emitida_en, f.expira_en, f.dispositivo_id,
                        f.ultimo_uso_en, f.revocada_en, f.motivo_revocacion, f.evaluacion_ref, f.rol_id)


class IntentosDjango:
    def registrar(self, i: e.IntentoAcceso) -> None:
        fila = m.IntentoAcceso.objects.create(
            usuario_id=i.usuario_id, identificador_hmac=i.identificador_hmac or "", dispositivo_id=i.dispositivo_id,
            resultado=i.resultado.value, motivo=i.motivo, autorizacion_id=i.autorizacion_id, momento=i.momento)
        i.id = fila.id

    def recientes(self, usuario_id: str, desde: int) -> list[e.IntentoAcceso]:
        filas = m.IntentoAcceso.objects.filter(usuario_id=usuario_id, momento__gte=desde).order_by("-momento", "-id")[:200]
        return [e.IntentoAcceso(f.identificador_hmac, ResultadoIntento(f.resultado), f.motivo, f.momento, f.usuario_id,
                                f.dispositivo_id, f.autorizacion_id, f.id) for f in filas]

    def de_dispositivo(self, dispositivo_id: str, desde: int) -> list[e.IntentoAcceso]:
        """RN-33: los intentos de PIN hechos desde la tableta (de cualquier alumno), del más reciente al más antiguo. Deja fuera los del PIN maestro."""
        filas = m.IntentoAcceso.objects.filter(dispositivo_id=dispositivo_id, momento__gte=desde, usuario__isnull=False) \
            .exclude(motivo__startswith="pin_maestro").exclude(resultado__in=[ResultadoIntento.TEMPORAL_EXITO.value, ResultadoIntento.TEMPORAL_FALLO.value]) \
            .order_by("-momento", "-id")[:200]
        return [self._a_entidad(f) for f in filas]

    def pin_maestro_del_equipo(self, dispositivo_id: str | None, desde: int) -> list[e.IntentoAcceso]:
        """RN-10: los intentos del PIN maestro hechos desde un equipo (o, sin equipo, los que no dijeron cuál), del más reciente al más antiguo."""
        consulta = m.IntentoAcceso.objects.filter(motivo="pin_maestro", momento__gte=desde)
        consulta = consulta.filter(dispositivo_id=dispositivo_id) if dispositivo_id else consulta.filter(dispositivo__isnull=True)
        return [self._a_entidad(f) for f in consulta.order_by("-momento", "-id")[:200]]

    def pin_maestro_fallos_globales(self, desde: int) -> list[int]:
        """RN-10: los momentos de los fallos del PIN maestro en todo el nodo, del más reciente al más antiguo."""
        return list(m.IntentoAcceso.objects.filter(motivo="pin_maestro", resultado=ResultadoIntento.FALLO.value, momento__gte=desde)
                    .order_by("-momento").values_list("momento", flat=True)[:100])

    def altas_recientes(self, dispositivo_id: str, desde: int) -> int:
        """RB-17: cuántas cuentas propias nacieron desde esta tableta desde `desde` (cada alta deja una fila ALTA, que el bloqueo no cuenta como fallo ni acierto)."""
        return m.IntentoAcceso.objects.filter(dispositivo_id=dispositivo_id, resultado=ResultadoIntento.ALTA.value, momento__gte=desde).count()

    def ultima_alta(self, usuario_id: str) -> e.IntentoAcceso | None:
        f = m.IntentoAcceso.objects.filter(usuario_id=usuario_id, resultado=ResultadoIntento.ALTA.value).order_by("-momento", "-id").first()
        return self._a_entidad(f) if f else None

    @staticmethod
    def _a_entidad(f: m.IntentoAcceso) -> e.IntentoAcceso:
        return e.IntentoAcceso(f.identificador_hmac, ResultadoIntento(f.resultado), f.motivo, f.momento, f.usuario_id,
                               f.dispositivo_id, f.autorizacion_id, f.id)

    def fallos_de_autorizacion(self, autorizacion_id: str) -> int:
        return m.IntentoAcceso.objects.filter(autorizacion_id=autorizacion_id, resultado=ResultadoIntento.TEMPORAL_FALLO.value).count()


class AutorizacionesDjango:
    def por_id(self, autorizacion_id: str) -> e.AutorizacionTemporal | None:
        f = m.AutorizacionTemporal.objects.filter(id=autorizacion_id).first()
        return self._a_entidad(f) if f else None

    def guardar(self, a: e.AutorizacionTemporal) -> None:
        m.AutorizacionTemporal.objects.update_or_create(id=a.id, defaults=dict(
            usuario_id=a.usuario_id, otorgada_por_id=a.otorgada_por, tipo=a.tipo.value, dispositivo_id=a.dispositivo_id,
            secreto_hash=a.secreto_hash, evaluacion_ref=a.evaluacion_ref, creada_en=a.creada_en, expira_en=a.expira_en,
            usada_en=a.usada_en, revocada_en=a.revocada_en, sesion_id=a.sesion_id, motivo=a.motivo))

    def canjeables_por_codigo(self, organizacion_id: str, ahora: int) -> list[e.AutorizacionTemporal]:
        filas = m.AutorizacionTemporal.objects.filter(
            usuario__organizacion_id=organizacion_id, tipo=TipoAutorizacion.CODIGO.value, usada_en__isnull=True,
            revocada_en__isnull=True, expira_en__gt=ahora).order_by("-creada_en")[:50]
        return [self._a_entidad(f) for f in filas]

    def listar(self, organizacion_id: str, usuario_id: str | None, solo_vigentes: bool, ahora: int,
               usuarios_permitidos: Iterable[str] | None = None) -> list[e.AutorizacionTemporal]:
        consulta = m.AutorizacionTemporal.objects.filter(usuario__organizacion_id=organizacion_id)
        if usuario_id:
            consulta = consulta.filter(usuario_id=usuario_id)
        if usuarios_permitidos is not None:
            consulta = consulta.filter(usuario_id__in=list(usuarios_permitidos))
        if solo_vigentes:
            consulta = consulta.filter(usada_en__isnull=True, revocada_en__isnull=True, expira_en__gt=ahora)
        return [self._a_entidad(f) for f in consulta.order_by("-creada_en")[:200]]

    @staticmethod
    def _a_entidad(f: m.AutorizacionTemporal) -> e.AutorizacionTemporal:
        return e.AutorizacionTemporal(f.id, f.usuario_id, f.otorgada_por_id, TipoAutorizacion(f.tipo), f.secreto_hash,
                                      f.creada_en, f.expira_en, f.motivo, f.dispositivo_id, f.evaluacion_ref, f.usada_en,
                                      f.revocada_en, f.sesion_id)


# ------------------------------------------------------- outbox y auditoría


class OutboxDjango:
    def publicar(self, ev: e.EventoSalida) -> None:
        fila = m.EventoSalida.objects.create(agregado_tipo=ev.agregado_tipo, agregado_id=ev.agregado_id,
                                             tipo_evento=ev.tipo_evento, carga=ev.carga, creado_en=ev.creado_en)
        ev.id = fila.id

    def ya_publicado(self, agregado_tipo: str, agregado_id: str, tipo_evento: str) -> bool:
        return m.EventoSalida.objects.filter(agregado_tipo=agregado_tipo, agregado_id=agregado_id, tipo_evento=tipo_evento).exists()


class AuditoriaExpediente:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`, app `audit`): misma transacción que el hecho."""

    def registrar(self, actor_id: str, accion: str, tabla: str = "", objeto_id: str = "", nuevo=None, anterior=None, **extra) -> None:
        from audit import servicios as auditoria  # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor_id or "", accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)
