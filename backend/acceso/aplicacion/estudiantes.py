"""
Cómo entra un alumno a la tableta del aula (RB-16…RB-20 de los requisitos de acceso, 2026-10-05).

No hay internet: el alumno no recibe un correo ni un código. Se identifica con lo que tiene a la mano en la tableta:

  1. Elige su grupo y toca su NOMBRE en la lista (`ListarGruposDelAula`, `ListarEstudiantesDelGrupo`; PAN-002). La lista sólo lleva el alias
     (nombre + inicial): nunca documento ni otros datos (D-A8).
  2. Marca su PIN (el login por `usuario_id`, `AutenticarUsuario`). Si todavía no tiene PIN lo elige ahí mismo (`EstablecerPinAlumno`, RN-35).
  3. Si no está en la lista, se crea su propio usuario con grupo, nombre y PIN (`RegistrarEstudiante`, RN-30). El profesor puede confirmarlo después.
  4. Si olvidó su PIN, entra como VISITANTE en dos toques, sin profesor (`AbrirSesionVisitante`, RN-40…47): una cuenta efímera con permisos mínimos
     que se retira al cerrar. Así «olvidé mi clave» no sirve para frenar la clase, y lo que hace un visitante no entra al expediente de nadie.

Todo esto va SIN sesión, pero sólo desde una tableta registrada en el inventario de MOD-009 (BR-056).
"""
from __future__ import annotations

from ..dominio import errores
from ..dominio.entidades import Dispositivo, Identificador, IntentoAcceso, Organizacion, Persona, PoliticaCredencial, Principal, Usuario, UsuarioRol
from ..dominio.politicas import politica_aplicable
from ..dominio.valores import (
    Alcance,
    ClaseSesion,
    CountryCode,
    DocumentNumber,
    EstadoUsuario,
    Menu,
    MotivoCierre,
    NivelEducativo,
    OrigenCuenta,
    ResultadoIntento,
    TipoIdentificador,
    TipoSecreto,
    UserId,
    alias_clave,
    sugerir_alias,
)
from ..dominio import plantillas
from .casos_uso import DIA_MS, HORA_MS, Base, CrearUsuario, _nuevo_id, _texto
from .puertos import UnidadDeTrabajo


class _Aula(Base):
    """Lo que comparten los casos de uso de la tableta: reconocer la tableta y el reglamento que manda sobre un grupo."""

    def tableta(self, uow: UnidadDeTrabajo, org: Organizacion, identificador: str | None, dispositivo_id: str | None = None) -> Dispositivo:
        """BR-056: sólo desde un equipo registrado. Se reconoce por su huella (la misma del login) o, si no la trae, por el id que el aparato
        aprendió del nodo (`X-Avacom-Dispositivo`)."""
        disp = self.dispositivo_por_identificador(uow, org.id, identificador)
        if disp is None and dispositivo_id:
            candidato = uow.dispositivos.por_id(str(dispositivo_id))
            if candidato is not None and candidato.organizacion_id == org.id and candidato.activo:
                if candidato.bloqueado:
                    raise errores.DispositivoBloqueado(dispositivo=candidato.nombre)
                disp = candidato
        if disp is None:
            raise errores.DispositivoNoAutorizado("Esta tableta no está registrada en el aula. Pídele ayuda al profesor.")
        return disp

    def politica_de_grupo(self, uow: UnidadDeTrabajo, org: Organizacion, grupo) -> PoliticaCredencial:
        """Qué reglamento manda sobre los alumnos de un grupo: el propio del grupo, si lo tiene; si no el de su nivel (BR-024: preescolar con
        avatar) y si no el de los estudiantes (BR-023)."""
        del_perfil = uow.politicas.por_perfil(org.id, Menu.STUDENT)
        if del_perfil is None:
            raise errores.Conflicto("La organización no tiene política de credenciales para los estudiantes.")
        del_grupo = uow.politicas.por_id(grupo.politica_credencial_id) if grupo.politica_credencial_id else None
        del_nivel = uow.politicas.por_nivel(org.id, Menu.STUDENT, grupo.nivel_clave) if grupo.nivel_clave else None
        return politica_aplicable(del_perfil, del_grupo, del_nivel)

    def registro_abierto(self, uow: UnidadDeTrabajo, org: Organizacion) -> bool:
        """RN-37: el registro propio es un interruptor por perfil; lo apaga la administración y sólo queda el padrón o el alta del profesor."""
        general = uow.politicas.por_perfil(org.id, Menu.STUDENT)
        return bool(general and general.autoregistro)

    def grupo_activo(self, uow: UnidadDeTrabajo, org: Organizacion, grupo_id: str):
        grupo = uow.grupos.por_id(str(grupo_id or "").strip())
        if grupo is None or grupo.organizacion_id != org.id or not grupo.activo:
            raise errores.NoEncontrado("No encontramos ese grupo. Vuelve a elegirlo en la lista.")
        return grupo


class ListarGruposDelAula(_Aula):
    """RB-16 (1/2): los grupos que la tableta ofrece para elegir. Con `para_docente`, todos los activos: el profesor elige entre los grupos que
    dicta al crear su usuario. Para el alumno, sólo los que ya tienen alumnos o los que dejan registrarse."""

    def ejecutar(self, dispositivo: str | None, dispositivo_id: str | None = None, para_docente: bool = False) -> list[dict]:
        with self.s.uow() as uow:
            org = self.organizacion(uow)
            self.tableta(uow, org, dispositivo, dispositivo_id)
            abierto = self.registro_abierto(uow, org)
            salida = []
            for grupo in uow.grupos.listar(org.id):
                if not grupo.activo:
                    continue
                alumnos = uow.grupos.estudiantes_activos(grupo.id)
                if not para_docente and not alumnos and not abierto:
                    continue
                politica = self.politica_de_grupo(uow, org, grupo)
                salida.append({"id": grupo.id, "codigo": grupo.codigo, "nombre": grupo.nombre, "nivel_clave": grupo.nivel_clave,
                               "tipo_secreto": politica.tipo_secreto.value, "longitud_pin": politica.longitud_minima,
                               "alumnos": len(alumnos), "registro_abierto": abierto})
            return salida


class ListarEstudiantesDelGrupo(_Aula):
    """RB-16 (2/2): `[{id, alias, pin_pendiente}]` de los alumnos activos del grupo. Nada más: ni documento, ni apellidos, ni estado."""

    def ejecutar(self, grupo_id: str, dispositivo: str | None, dispositivo_id: str | None = None) -> list[dict]:
        with self.s.uow() as uow:
            org = self.organizacion(uow)
            self.tableta(uow, org, dispositivo, dispositivo_id)
            grupo = self.grupo_activo(uow, org, grupo_id)
            return [{"id": u.id, "alias": u.alias, "pin_pendiente": not con_pin}
                    for u, con_pin in uow.grupos.estudiantes_activos(grupo.id)]


class RegistrarEstudiante(_Aula):
    """RB-17 · RN-30, RN-31, RN-34, RN-37: el alumno crea su propio usuario con grupo, nombre y PIN; no necesita documento ni código.

    · La cuenta nace con origen `AUTOALTA_ALUMNO` y «sin confirmar»: el profesor puede confirmarla o vincularla con el padrón (JRN-007).
    · El alias (nombre + inicial) es único dentro del grupo, sin distinguir mayúsculas ni tildes; si ya existe se sugiere una letra más en vez de
      rechazar sin salida (RN-34).
    · El PIN lo valida el reglamento del grupo (4 a 6 dígitos, sin reglas de complejidad: `1234` vale); el nodo emite la clave de instalación (DEC-049).
    · Tope de 5 altas por tableta y hora, y se apaga con la política `autoregistro` (R-4, RN-37)."""

    def ejecutar(self, datos: dict) -> dict:
        nombres = _texto(datos.get("nombres"), "el nombre", 120)
        apellidos = _texto(datos.get("apellidos"), "el apellido", 120, obligatorio=False)
        alias_pedido = _texto(datos.get("alias"), "el alias", 64, obligatorio=False)
        pin = str(datos.get("pin") or "")
        if not pin:
            raise errores.DatosInvalidos("Falta el PIN.")
        with self.s.uow() as uow:
            org = self.organizacion(uow)
            disp = self.tableta(uow, org, datos.get("dispositivo"), datos.get("dispositivo_id"))
            if not self.registro_abierto(uow, org):
                raise errores.RegistroCerrado("Crear un usuario nuevo está apagado. Pídele al profesor que te anote en el grupo.")
            ahora = self.ahora()
            if uow.intentos.altas_recientes(disp.id, ahora - HORA_MS) >= plantillas.ALTAS_MAXIMAS_POR_TABLETA_Y_HORA:
                raise errores.RegistroCerrado("Esta tableta creó varios usuarios hace poco. Pídele ayuda al profesor.", motivo="tope_por_tableta")
            grupo = self.grupo_activo(uow, org, datos.get("grupo_id"))
            primer_nombre = nombres.split()[0]
            alias = alias_pedido or (f"{primer_nombre} {apellidos[0].upper()}." if apellidos else primer_nombre)
            ocupados = {alias_clave(u.alias) for u, _ in uow.grupos.estudiantes_activos(grupo.id)}
            if alias_clave(alias) in ocupados:
                sugerencia = sugerir_alias(primer_nombre, apellidos, ocupados)
                texto = f"Ya hay alguien llamado {alias} en este grupo. "
                texto += f"Añade una letra: {sugerencia}{'' if sugerencia.endswith('.') else '.'}" if sugerencia else "Añade una letra o tu apellido."
                raise errores.AliasDuplicado(texto, alias=alias, sugerencia=sugerencia)
            rol = uow.roles.por_codigo(org.id, "STUDENT")
            entrada = {"rol": "STUDENT", "alias": alias, "persona": {"nombres": nombres, "apellidos": apellidos},
                       "identificadores": [], "secreto": pin, "secreto_definitivo": True}
            creado = CrearUsuario(self.s)._crear(uow, org, rol, entrada, creado_por=None, provisional=False, grupo=grupo,
                                                 origen=OrigenCuenta.AUTOALTA_ALUMNO, confirmado=False)
            uow.intentos.registrar(IntentoAcceso("", ResultadoIntento.ALTA, "autoalta_alumno", ahora, creado["id"], disp.id))
            carga = {"grupo_id": grupo.id, "dispositivo_id": disp.id}
            self.auditar(uow, creado["id"], "identidad.estudiante.registrado", "m01_usuario", creado["id"], carga)
            self.evento(uow, "usuario", creado["id"], "estudiante_registrado", carga)
            return {"id": creado["id"], "alias": creado["alias"]}


class EstablecerPinAlumno(_Aula):
    """RB-18 · RN-35: el alumno cuya cuenta está en «PIN pendiente» (alta por padrón o PIN restablecido) elige su PIN tocando su nombre.

    Sólo funciona si la cuenta NO tiene credencial: con una vigente no hay nada que establecer (el PIN se cambia con la sesión abierta, RN-36).
    Es el riesgo R-3 asumido: sin sistema central no hay verificación de identidad; el profesor lo corrige con «PIN pendiente» y queda auditado."""

    def ejecutar(self, usuario_id: str, pin: str, dispositivo: str | None, dispositivo_id: str | None = None) -> dict:
        if not str(pin or ""):
            raise errores.DatosInvalidos("Falta el PIN.")
        with self.s.uow() as uow:
            org = self.organizacion(uow)
            disp = self.tableta(uow, org, dispositivo, dispositivo_id)
            usuario = uow.usuarios.por_id(str(usuario_id or "").strip())
            ajeno = errores.NoEncontrado("No encontramos ese nombre. Vuelve a elegirlo en la lista.")
            if usuario is None or usuario.organizacion_id != org.id or not usuario.activo:
                raise ajeno
            rol = self.rol_de(uow, usuario)
            if rol.menu_principal is not Menu.STUDENT:
                raise ajeno
            if uow.credenciales.activa(usuario.id) is not None:
                raise errores.Conflicto("Ese nombre ya tiene PIN: escríbelo para entrar.", codigo="pin_ya_establecido")
            politica = self.politica_de(uow, usuario, rol)
            self.establecer_credencial(uow, usuario, politica, str(pin), creado_por=usuario.id, debe_cambiar=False, revisar_historial=False)
            carga = {"dispositivo_id": disp.id}
            self.auditar(uow, usuario.id, "identidad.estudiante.pin_establecido", "m01_credencial", usuario.id, carga)
            self.evento(uow, "credencial", usuario.id, "estudiante_pin_establecido", carga)
            return {"id": usuario.id, "alias": usuario.alias}


class AbrirSesionVisitante(_Aula):
    """RB-19 · RN-40…RN-47: entrar como visitante, sin profesor, PIN ni código. Cada visita es una CUENTA EFÍMERA «Visitante · <tableta>» con rol
    `STUDENT`, `provisional` y origen `VISITANTE`, y una sesión de clase `VISITANTE` que sólo puede leer lecciones y seguir la clase (RN-42,
    RN-43). Como son cuentas distintas, la sesión única no hace que un visitante cierre a otro (RN-45); entrar en la tableta sí cierra la sesión de
    quien estaba antes en ella (INV-011).

    Se retira al cerrar la sesión y a las 24 h; nunca se borra (CV-05). Entrar como visitante NUNCA se bloquea (RN-33). La política `visitante`
    de la institución lo apaga (RN-47)."""

    def ejecutar(self, dispositivo: str | None, dispositivo_id: str | None = None, grupo_id: str | None = None) -> dict:
        with self.s.uow() as uow:
            org = self.organizacion(uow)
            if not org.visitante:
                raise errores.VisitanteNoPermitido("Hoy no se puede entrar como visitante. Pídele ayuda al profesor.")
            disp = self.tableta(uow, org, dispositivo, dispositivo_id)
            grupo = self.grupo_activo(uow, org, grupo_id) if str(grupo_id or "").strip() else None
            ahora = self.ahora()
            self._retirar_vencidas(uow, org, ahora)
            rol = uow.roles.por_codigo(org.id, "STUDENT")
            politica = uow.politicas.por_perfil(org.id, Menu.STUDENT)
            alias = f"Visitante · {disp.nombre}"[:64]
            usuario = Usuario(id=str(UserId.nuevo()), organizacion_id=org.id, rol_id=rol.id, estado=EstadoUsuario.ACTIVO, alias=alias,
                              idioma=org.idioma, creado_en=ahora, actualizado_en=ahora, provisional=True, origen=OrigenCuenta.VISITANTE)
            uow.usuarios.guardar(usuario)
            uow.usuarios.guardar_persona(Persona(usuario.id, alias, "", org.pais, actualizado_en=ahora))
            clave = f"{org.codigo}-V{self.s.azar.pin(8)}"
            while uow.usuarios.existe_identificador(self.s.cifrador.indice(DocumentNumber(TipoIdentificador.CLAVE_INSTALACION, clave).normalizado)):
                clave = f"{org.codigo}-V{self.s.azar.pin(8)}"
            # DEC-049: nunca existe una persona sin identificador externo; éste no sirve para entrar (`es_login` falso): la visita no tiene clave.
            uow.usuarios.reemplazar_identificadores(usuario.id, [Identificador(_nuevo_id(), usuario.id, TipoIdentificador.CLAVE_INSTALACION, clave,
                                                                               False, ahora, emisor=org.codigo, principal=True)])
            uow.usuarios.guardar_asignacion(UsuarioRol(_nuevo_id(), usuario.id, rol.id, Alcance.ORGANIZATION, ahora))
            salida = self.abrir_sesion(uow, usuario, rol, politica, disp, ClaseSesion.VISITANTE, False)
            salida["roles_disponibles"] = [rol.codigo]
            carga = {"dispositivo_id": disp.id, "grupo_id": grupo.id if grupo else None}
            self.auditar(uow, usuario.id, "identidad.sesion.visitante_abierta", "m01_sesion", salida["sesion_id"], carga)
            self.evento(uow, "sesion", salida["sesion_id"], "sesion_visitante_abierta", {**carga, "usuario_id": usuario.id})
            return salida

    def _retirar_vencidas(self, uow: UnidadDeTrabajo, org: Organizacion, ahora: int) -> None:
        """RN-45: las visitas de hace más de 24 h se retiran (y sus sesiones se cierran) la próxima vez que alguien entra como visitante."""
        for vieja in uow.usuarios.visitantes_activos(org.id, ahora - plantillas.HORAS_VIDA_VISITANTE * HORA_MS):
            uow.sesiones.revocar_de_usuario(vieja.id, MotivoCierre.VISITA_RETIRADA.value, ahora)
            self.retirar_visita(uow, vieja.id)


class ConfirmarEstudiante(Base):
    """RB-20: el profesor marca como «confirmado» a un alumno que se registró solo (o a un profesor que entró con el PIN): alguien de la institución
    respalda que es quien dice ser. Idempotente."""

    def ejecutar(self, principal: Principal, usuario_id: str) -> dict:
        with self.s.uow() as uow:
            ctx = self.contexto(uow, principal)
            usuario, _ = self.usuario_objetivo(uow, ctx, usuario_id, "identity.user.update")
            if usuario.confirmado_en is None:
                ahora = self.ahora()
                usuario.confirmado_en = ahora
                usuario.actualizado_en = ahora
                uow.usuarios.guardar(usuario)
                self.auditar(uow, principal.usuario_id, "identidad.usuario.confirmado", "m01_usuario", usuario.id, {"origen": usuario.origen.value})
                self.evento(uow, "usuario", usuario.id, "usuario_confirmado", {"origen": usuario.origen.value})
            return {"id": usuario.id, "confirmado_en": usuario.confirmado_en}


class ListarVisitantes(Base):
    """RN-46: el profesor ve quiénes entraron como visitante (cuántos y desde qué tableta): la rendición de cuentas contra el sabotaje es la tableta,
    no la persona. Una visita no pertenece a ningún grupo, así que se lista por sesión abierta en toda la organización."""

    def ejecutar(self, principal: Principal) -> list[dict]:
        with self.s.uow() as uow:
            ctx = self.contexto(uow, principal)
            alcance = self.exigir_alcance(ctx, "identity.session.read")
            if alcance is Alcance.SELF:
                raise errores.SinPermiso("Las visitas las ve el profesor o la administración.", permiso="identity.session.read")
            ahora = self.ahora()
            salida = []
            for sesion in uow.sesiones.listar(principal.organizacion_id, None, True, ahora):
                if sesion.clase is not ClaseSesion.VISITANTE:
                    continue
                visita = uow.usuarios.por_id(sesion.usuario_id)
                equipo = uow.dispositivos.por_id(sesion.dispositivo_id) if sesion.dispositivo_id else None
                salida.append({"usuario_id": sesion.usuario_id, "alias": visita.alias if visita else "", "sesion_id": sesion.id,
                               "dispositivo_id": sesion.dispositivo_id, "dispositivo": equipo.nombre if equipo else None,
                               "emitida_en": sesion.emitida_en})
            return salida
