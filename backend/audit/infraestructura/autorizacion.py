"""
Autorización de MOD-019 evaluada con la política de MOD-001 (como `AutorizacionAcceso` de Device Manager): los permisos
`audit.read`, `audit.export` y `diagnostics.read` los siembra `acceso.dominio.plantillas` y aquí se piden con SU política,
en el nodo y con su reloj. Toda ruta de auditoría exige sesión: sin principal no hay evaluación (la vista responde 401).

«Autorización de salida» (ESC-03, BR-105): una escalada temporal VIGENTE de `audit.export` (concesión de origen
`adicional`, con motivo y caducidad, concedida por otra identidad). El rol por sí solo no exporta. Al exportar, la
escalada se consume (se revoca) y queda `acceso.escalada.consumida`.
"""
from __future__ import annotations

from ..dominio import errores


def _politica(principal):
    from acceso.aplicacion import casos_uso as acu
    from acceso.infraestructura.contenedor import servicios as servicios_acceso

    s = servicios_acceso()
    return s, acu.Base(s)


class AutorizacionAcceso:
    def concesion(self, principal, permiso: str):
        """(alcance efectivo o None, Concesión o None, decisión transversal o None)."""
        s, base = _politica(principal)
        with s.uow() as uow:
            ctx = base.contexto(uow, principal)
            previa = base.politica.transversal(ctx, permiso)
            if previa is not None:
                return None, None, previa
            return base.politica.alcance_concedido(ctx, permiso), ctx.concesiones.get(permiso), None

    def exigir(self, principal, permiso: str):
        """Lanza SinPermiso (403 `permiso_denegado`) si el actor no tiene el permiso; devuelve la concesión."""
        if principal is None:
            raise errores.SinPermiso("Hace falta iniciar sesión.", permiso=permiso)
        alcance, concesion, previa = self.concesion(principal, permiso)
        if previa is not None:
            raise errores.SinPermiso(previa.motivo if hasattr(previa, "motivo") else f"La función exige {permiso}.", permiso=permiso)
        if alcance is None:
            raise errores.SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)
        return concesion

    def tiene_escalada(self, principal, permiso: str) -> bool:
        """Una escalada temporal (m01_usuario_permiso) VIGENTE para ese permiso, con independencia de lo que diga el rol:
        la escalada es la «autorización» explícita, con motivo y caducidad, aunque el rol ya tuviera el permiso."""
        if principal is None:
            return False
        s, base = _politica(principal)
        with s.uow() as uow:
            ctx = base.contexto(uow, principal)
            if base.politica.transversal(ctx, permiso) is not None:
                return False
            ahora = s.reloj.ahora_ms()
            return any(p.permiso_codigo == permiso and p.vigente(ahora) for p in uow.usuarios.permisos_adicionales(principal.usuario_id))

    def consumir_escalada(self, principal, permiso: str, operacion: str) -> bool:
        """ESC-03: la autorización de salida vale una operación. Revoca la escalada y lo asienta."""
        s, _ = _politica(principal)
        with s.uow() as uow:
            ahora = s.reloj.ahora_ms()
            hubo = False
            for existente in uow.usuarios.permisos_adicionales(principal.usuario_id):
                if existente.permiso_codigo == permiso and existente.vigente(ahora):
                    existente.revocado_en = ahora
                    uow.usuarios.guardar_permiso_adicional(existente)
                    uow.auditoria.registrar(principal.usuario_id, "acceso.escalada.consumida", "m01_usuario_permiso", existente.id,
                                            nuevo={"permiso": permiso, "operacion": operacion, "concedida_por": existente.otorgado_por})
                    hubo = True
            return hubo
