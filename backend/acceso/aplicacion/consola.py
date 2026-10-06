"""
Lo que el TÉCNICO hace desde la consola del equipo (RB-43 y RB-44), sin sesión: quien tiene acceso al equipo tiene la autoridad física de repararlo.

  · El PIN maestro se puede REEMPLAZAR, no recuperar (RN-04): si el administrador lo perdió o se filtró y no puede entrar a cambiarlo, el técnico fija
    uno nuevo. Quedan los mismos asientos que un cambio normal, con `actor = sistema` y `motivo = consola`.
  · La contraseña del administrador no se restablece con el PIN maestro (RN-12) ni la restablece nadie desde una pantalla: si se perdió, sólo este
    camino (PA-07). Queda como provisional (debe cambiarla al entrar) y se cierran sus sesiones.

Nada de este archivo importa Django ni DRF: el comando de Django (`management/commands/`) sólo lee la entrada y llama aquí.
"""
from __future__ import annotations

from ..dominio import errores
from ..dominio.entidades import IntentoAcceso
from ..dominio.politicas import PoliticaPinMaestro
from ..dominio.valores import DocumentNumber, EstadoUsuario, Menu, MotivoCierre, ResultadoIntento
from .casos_uso import Base, VerificadorPinMaestro, crear_version_pin_maestro
from .pin_maestro import dto_estado_pin


class EstadoPinMaestroDeConsola(Base):
    def ejecutar(self) -> dict:
        with self.s.uow() as uow:
            org = self.organizacion(uow)
            ahora = self.ahora()
            bloqueo = VerificadorPinMaestro(self.s).estado_de_bloqueo(uow, None, ahora)
            return dto_estado_pin(uow.pines_maestros.activo(org.id), bloqueo, ahora)


class CambiarPinMaestroDeConsola(Base):
    """Mismas reglas que el cambio del administrador (RN-02, RN-05): seis dígitos, nada trivial y ninguno de los tres últimos."""

    def ejecutar(self, pin_nuevo: str) -> dict:
        with self.s.uow() as uow:
            org = self.organizacion(uow)
            pin = PoliticaPinMaestro.exigir_fuerte(pin_nuevo)
            for previo in uow.pines_maestros.ultimos(org.id, PoliticaPinMaestro.ULTIMOS_NO_REUTILIZABLES):
                if self.s.hasher.verificar(previo.hash, pin):
                    raise errores.PinDebil("Ese PIN ya se usó hace poco. Elige uno distinto de los últimos tres.")
            version = crear_version_pin_maestro(self, uow, org, pin, creado_por=None, motivo="consola")
            return {"creado_en": version.creado_en, "vence_en": version.vence_en,
                    "dias_restantes": PoliticaPinMaestro.dias_restantes(version.vence_en, self.ahora())}


class RestablecerAdministradorDeConsola(Base):
    """RB-44: restablece la contraseña de una cuenta de administración desde la consola. Sólo cuentas cuyo rol vigente sea el de administración."""

    def ejecutar(self, documento: str, secreto: str | None = None) -> dict:
        documento = str(documento or "").strip()
        if not documento:
            raise errores.DatosInvalidos("Falta el documento del administrador.")
        with self.s.uow() as uow:
            como_documento, como_email = DocumentNumber.normalizar_entrada(documento)
            encontrado = uow.usuarios.por_identificador(self.s.cifrador.indice(como_documento))
            if encontrado is None and "@" in documento:
                encontrado = uow.usuarios.por_identificador(self.s.cifrador.indice(como_email))
            if encontrado is None:
                raise errores.NoEncontrado("No hay una cuenta con ese documento.")
            usuario, _ = encontrado
            roles = [uow.roles.por_id(a.rol_id) for a in self.asignaciones_vigentes(uow, usuario)]
            if not any(r is not None and r.menu_principal is Menu.ADMIN for r in roles):
                raise errores.NoEncontrado("Esa cuenta no es de administración. Los profesores restablecen su contraseña con el PIN maestro; "
                                           "los alumnos, con su profesor.")
            if usuario.estado is EstadoUsuario.RETIRADO:
                raise errores.Conflicto("La cuenta está dada de baja (BR-025).")
            rol = next(r for r in roles if r is not None and r.menu_principal is Menu.ADMIN)
            politica = self.politica_de(uow, usuario, rol)
            provisional = str(secreto or "") or self.generar_secreto(politica)
            self.establecer_credencial(uow, usuario, politica, provisional, creado_por=None, debe_cambiar=True)
            ahora = self.ahora()
            revocadas = uow.sesiones.revocar_de_usuario(usuario.id, MotivoCierre.CREDENCIAL_RESTABLECIDA.value, ahora)
            uow.intentos.registrar(IntentoAcceso("", ResultadoIntento.DESBLOQUEO, "credencial_restablecida_consola", ahora, usuario.id))
            if usuario.estado is EstadoUsuario.BLOQUEADO:
                usuario.estado = EstadoUsuario.ACTIVO
                usuario.actualizado_en = ahora
                uow.usuarios.guardar(usuario)
            carga = {"sesiones_revocadas": revocadas, "via": "consola", "tipo": politica.tipo_secreto.value}
            self.auditar(uow, "sistema", "identidad.credencial.restablecida", "m01_credencial", usuario.id, carga)
            self.evento(uow, "credencial", usuario.id, "credencial_restablecida", {"via": "consola"})
            return {"usuario_id": usuario.id, "alias": usuario.alias, "secreto_provisional": provisional, "debe_cambiar": True,
                    "sesiones_revocadas": revocadas}
