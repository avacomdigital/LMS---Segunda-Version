"""
El PIN maestro y los profesores que nacen de él (RB-10…RB-15 de los requisitos de acceso, 2026-10-05).

El PIN maestro es de la INSTITUCIÓN, no de una persona (D-A5): seis dígitos que se configuran en el primer arranque, que el administrador
cambia cuando quiera y que **vencen a los 365 días**. Quien lo conoce puede hacer dos cosas, y sólo dos:

  · crear su propia cuenta de profesor (`RegistrarDocente`, RN-20…RN-23) y
  · restablecer su propia contraseña de profesor (`RestablecerContrasenaDocente`, RN-24, RN-25).

No abre cuentas de administración, de reportes ni de técnico, ni restablece sus contraseñas (RN-12). Y como un millón de combinaciones es
poco, se verifica DENTRO de la operación que autoriza, con bloqueo por equipo y tope global (RN-10, `VerificadorPinMaestro`): no hay un
endpoint que sólo diga «sí/no» (D-A6).

Nada de este archivo importa Django ni DRF.
"""
from __future__ import annotations

from ..dominio import errores
from ..dominio.entidades import MiembroGrupo, Principal
from ..dominio.politicas import ObjetivoOrganizacion, PoliticaPinMaestro
from ..dominio.valores import (
    Alcance,
    DocumentNumber,
    EstadoUsuario,
    Menu,
    MotivoCierre,
    OrigenCuenta,
    PapelGrupo,
    ResultadoIntento,
    TipoIdentificador,
)
from ..dominio.entidades import IntentoAcceso
from .casos_uso import Base, CrearUsuario, VerificadorPinMaestro, _nuevo_id, _texto, crear_version_pin_maestro


def dto_estado_pin(pin, bloqueo, ahora: int) -> dict:
    if pin is None:
        return {"configurado": False, "creado_en": None, "vence_en": None, "dias_restantes": None, "vencido": False, "aviso": False,
                "bloqueado_hasta": None}
    return {"configurado": True, "creado_en": pin.creado_en, "vence_en": pin.vence_en,
            "dias_restantes": PoliticaPinMaestro.dias_restantes(pin.vence_en, ahora),
            "vencido": PoliticaPinMaestro.esta_vencido(pin.vence_en, ahora),
            "aviso": PoliticaPinMaestro.en_aviso(pin.vence_en, ahora),
            "bloqueado_hasta": bloqueo.hasta if bloqueo.bloqueado else None}


class ConsultarEstadoPinMaestro(Base):
    """RB-12: `{configurado, creado_en, vence_en, dias_restantes, vencido, aviso, bloqueado_hasta}`. NUNCA devuelve el PIN ni su huella."""

    def ejecutar(self, principal: Principal) -> dict:
        with self.s.uow() as uow:
            ctx = self.contexto(uow, principal)
            org = self.organizacion(uow)
            self.exigir(ctx, "identity.master_pin.manage", ObjetivoOrganizacion(org.id))
            ahora = self.ahora()
            bloqueo = VerificadorPinMaestro(self.s).estado_de_bloqueo(uow, principal.dispositivo_id, ahora)
            return dto_estado_pin(uow.pines_maestros.activo(org.id), bloqueo, ahora)


class CambiarPinMaestro(Base):
    """RB-11 · RN-06: el administrador lo cambia cuando quiera, con su sesión abierta y sin saber el actual (así puede reemplazarlo si se
    filtró o se perdió). Valida RN-02 y RN-05 (nada de `123456`, y no se repite ninguno de los tres últimos), sustituye la versión anterior
    —que se conserva— y reinicia el reloj de 365 días (RN-07)."""

    def ejecutar(self, principal: Principal, pin_nuevo: str) -> dict:
        with self.s.uow() as uow:
            ctx = self.contexto(uow, principal)
            org = self.organizacion(uow)
            self.exigir(ctx, "identity.master_pin.manage", ObjetivoOrganizacion(org.id))
            pin = PoliticaPinMaestro.exigir_fuerte(pin_nuevo)
            for previo in uow.pines_maestros.ultimos(org.id, PoliticaPinMaestro.ULTIMOS_NO_REUTILIZABLES):
                if self.s.hasher.verificar(previo.hash, pin):
                    raise errores.PinDebil("Ese PIN ya se usó hace poco. Elige uno distinto de los últimos tres.")
            version = crear_version_pin_maestro(self, uow, org, pin, creado_por=principal.usuario_id, motivo="administrador")
            return {"creado_en": version.creado_en, "vence_en": version.vence_en,
                    "dias_restantes": PoliticaPinMaestro.dias_restantes(version.vence_en, self.ahora())}


class RegistrarDocente(Base):
    """RB-13 · RN-20…RN-23: el profesor crea su propio usuario con su documento, su nombre, su contraseña (definitiva, no provisional) y el
    PIN maestro. La cuenta nace ACTIVA con origen `PIN_MAESTRO`: la institución «aprueba» con el PIN; a cambio, la administración ve en una lista
    quién se registró así y puede suspenderlo (RN-22). Elige los grupos que dicta; sin grupo no ve nada (RN-23).

    Sin sesión: lo que autoriza es el PIN. Dos transacciones: la primera verifica el PIN y se confirma aunque falle (el fallo y el bloqueo
    deben quedar escritos); la segunda crea la cuenta y, si algo falla, no deja nada a medias."""

    def ejecutar(self, datos: dict) -> dict:
        try:
            documento = DocumentNumber(TipoIdentificador.DNI, datos.get("documento"))
        except ValueError as error:
            raise errores.DatosInvalidos(str(error))
        nombres = _texto(datos.get("nombres"), "los nombres", 120)
        apellidos = _texto(datos.get("apellidos"), "los apellidos", 120, obligatorio=False)
        secreto = str(datos.get("secreto") or "")
        if not secreto:
            raise errores.DatosInvalidos("Falta la contraseña.")
        grupos_ids = list(dict.fromkeys(str(g).strip() for g in (datos.get("grupos") or []) if str(g).strip()))

        def verificar(uow):
            org = self.organizacion(uow)
            politica = uow.politicas.por_perfil(org.id, Menu.TEACHER)
            if politica is None or not politica.autoregistro:
                raise errores.RegistroCerrado("El registro de profesores está cerrado. Pídele a la administración que te cree el usuario.")
            disp = self.dispositivo_por_identificador(uow, org.id, datos.get("dispositivo"))
            VerificadorPinMaestro(self.s).exigir(uow, org, datos.get("pin_maestro"), disp, "registro_docente")
            return disp.id if disp else None

        disp_id = self.ejecutar_registrando(verificar)
        with self.s.uow() as uow:
            org = self.organizacion(uow)
            rol = uow.roles.por_codigo(org.id, "TEACHER")
            grupos = []
            for grupo_id in grupos_ids:
                grupo = uow.grupos.por_id(grupo_id)
                if grupo is None or grupo.organizacion_id != org.id or not grupo.activo:
                    raise errores.DatosInvalidos("Uno de los grupos que elegiste ya no existe. Vuelve a elegir tus grupos.")
                grupos.append(grupo)
            primer_apellido = apellidos.split()[0] if apellidos else ""
            alias = f"{nombres.split()[0]} {primer_apellido}".strip()[:64]
            entrada = {"rol": "TEACHER", "alias": alias, "persona": {"nombres": nombres, "apellidos": apellidos},
                       "identificadores": [{"tipo": "DNI", "valor": documento.valor, "es_login": True, "principal": True}],
                       "secreto": secreto, "secreto_definitivo": True}
            # No hay quien la cree (creado_por nulo): la contraseña es definitiva y la cuenta nace sin confirmar, para que la administración la revise.
            creado = CrearUsuario(self.s)._crear(uow, org, rol, entrada, creado_por=None, provisional=False,
                                                 origen=OrigenCuenta.PIN_MAESTRO, confirmado=False)
            ahora = self.ahora()
            for grupo in grupos:
                uow.grupos.guardar_miembro(MiembroGrupo(_nuevo_id(), grupo.id, creado["id"], PapelGrupo.DOCENTE, ahora))
            uow.intentos.registrar(IntentoAcceso("", ResultadoIntento.ALTA, "docente_pin_maestro", ahora, creado["id"], disp_id))
            carga = {"dispositivo_id": disp_id, "grupos": [g.id for g in grupos]}
            self.auditar(uow, creado["id"], "identidad.docente.registrado", "m01_usuario", creado["id"], carga)
            self.evento(uow, "usuario", creado["id"], "docente_registrado", carga)
            return {"id": creado["id"], "alias": creado["alias"]}


class RestablecerContrasenaDocente(Base):
    """RB-14 · RN-24 y RN-25: el profesor da su documento, el PIN maestro y su contraseña nueva. Se cierran todas sus sesiones y queda auditado
    quién, desde qué equipo y cuándo.

    · Mientras el PIN no sea válido, la respuesta es la misma exista o no el documento (RN-25): primero se verifica el PIN.
    · Sólo restablece a profesores (RN-12): un documento de administración, reportes o técnico se contesta igual que uno inexistente
      (AC-A10). Una cuenta con cualquier rol vigente que no sea de profesor tampoco se toca, aunque su rol principal sea el de profesor."""

    def ejecutar(self, datos: dict) -> dict:
        documento = str(datos.get("documento") or "").strip()
        nuevo = str(datos.get("secreto_nuevo") or "")
        if not documento:
            raise errores.DatosInvalidos("Falta el documento.")
        if not nuevo:
            raise errores.DatosInvalidos("Falta la contraseña nueva.")

        def verificar(uow):
            org = self.organizacion(uow)
            disp = self.dispositivo_por_identificador(uow, org.id, datos.get("dispositivo"))
            VerificadorPinMaestro(self.s).exigir(uow, org, datos.get("pin_maestro"), disp, "restablecer_docente")
            return disp.id if disp else None

        disp_id = self.ejecutar_registrando(verificar)
        with self.s.uow() as uow:
            como_documento, como_email = DocumentNumber.normalizar_entrada(documento)
            encontrado = uow.usuarios.por_identificador(self.s.cifrador.indice(como_documento))
            if encontrado is None and "@" in documento:
                encontrado = uow.usuarios.por_identificador(self.s.cifrador.indice(como_email))
            ajeno = errores.NoEncontrado("No encontramos un profesor con ese documento. Revisa que esté bien escrito.")
            if encontrado is None:
                raise ajeno
            usuario, _ = encontrado
            roles = [uow.roles.por_id(a.rol_id) for a in self.asignaciones_vigentes(uow, usuario)]
            if usuario.estado is EstadoUsuario.RETIRADO or not roles or any(r is None or r.menu_principal is not Menu.TEACHER for r in roles):
                raise ajeno
            rol = self.rol_de(uow, usuario)
            politica = self.politica_de(uow, usuario, rol)
            self.establecer_credencial(uow, usuario, politica, nuevo, creado_por=None, debe_cambiar=False)
            ahora = self.ahora()
            revocadas = uow.sesiones.revocar_de_usuario(usuario.id, MotivoCierre.CREDENCIAL_RESTABLECIDA_PIN_MAESTRO.value, ahora)
            # Si estaba bloqueada por intentos, recuperar la contraseña también la libera (igual que RestablecerCredencial).
            uow.intentos.registrar(IntentoAcceso("", ResultadoIntento.DESBLOQUEO, "credencial_restablecida_pin_maestro", ahora, usuario.id, disp_id))
            carga = {"dispositivo_id": disp_id, "sesiones_revocadas": revocadas}
            self.auditar(uow, usuario.id, "identidad.docente.contrasena_restablecida", "m01_credencial", usuario.id, carga)
            self.evento(uow, "credencial", usuario.id, "docente_contrasena_restablecida", carga)
            return {"sesiones_revocadas": revocadas}


class ListarDocentesPorPinMaestro(Base):
    """RB-15: las cuentas de profesor que nacieron con el PIN maestro (origen `PIN_MAESTRO`): alias, fecha, equipo y estado, para que la
    administración las revise o las suspenda (RN-22). Para suspender se usa `PATCH /usuarios/{id}/` con `estado: SUSPENDIDO`."""

    def ejecutar(self, principal: Principal, origen: str = OrigenCuenta.PIN_MAESTRO.value) -> list[dict]:
        with self.s.uow() as uow:
            ctx = self.contexto(uow, principal)
            alcance = self.exigir_alcance(ctx, "identity.user.read")
            if alcance is not Alcance.ORGANIZATION:
                raise errores.SinPermiso("La lista de profesores registrados es de la administración.", permiso="identity.user.read",
                                         alcance_requerido=Alcance.ORGANIZATION.value, alcance_concedido=alcance.value)
            filas = uow.usuarios.listar(principal.organizacion_id, Alcance.ORGANIZATION, principal.usuario_id, [], principal.nivel,
                                        None, "TEACHER", None, (origen or OrigenCuenta.PIN_MAESTRO.value).upper())
            salida = []
            for usuario in filas:
                alta = uow.intentos.ultima_alta(usuario.id)
                equipo = uow.dispositivos.por_id(alta.dispositivo_id) if alta and alta.dispositivo_id else None
                grupos = [uow.grupos.por_id(m.grupo_id) for m in uow.grupos.membresias(usuario.id) if m.papel is PapelGrupo.DOCENTE]
                salida.append({"id": usuario.id, "alias": usuario.alias, "estado": usuario.estado.value, "origen": usuario.origen.value,
                               "registrado_en": usuario.creado_en, "confirmado": usuario.confirmado_en is not None,
                               "equipo": equipo.nombre if equipo else None, "equipo_id": equipo.id if equipo else None,
                               "grupos": [{"id": g.id, "nombre": g.nombre} for g in grupos if g]})
            return salida
