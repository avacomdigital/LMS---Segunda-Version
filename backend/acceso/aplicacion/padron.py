"""
Padrón del aula desde OPS: registrar estudiantes y asociarlos a un grupo (pantalla «Grupos»).

No hay modelo nuevo: el padrón ya es `m01_usuario` + `m01_persona` + `m01_identificador_usuario` + `m01_credencial` (la persona) y
`m01_grupo` + `m01_miembro_grupo` (el grupo y su pertenencia, papel ESTUDIANTE o DOCENTE). Este módulo sólo compone los casos de uso
que ya existen en una API pensada para una pantalla:

  · EstadoPadron          → una sola lectura con los grupos, sus estudiantes y los estudiantes sin grupo.
  · RegistrarGrupo        → CrearGrupo (+ el docente que lo crea queda como DOCENTE del grupo).
  · RegistrarEstudiante   → CrearUsuario(rol STUDENT, grupo_id): persona + identificador + PIN + pertenencia, en una transacción.
  · MatricularEstudiante  → AgregarMiembro (el estudiante ya existe y entra a otro grupo).
  · RetirarEstudiante     → RetirarMiembro.
  · PrepararAulaDePrueba  → InstalarNodo con valores de prueba (sólo prototipo y sólo si el nodo está vacío).

QUIÉN ACTÚA. Con sesión, quien firma el JWT, con SUS permisos (un docente sólo crea estudiantes en sus grupos; sólo la administración
crea grupos). Sin sesión (Q-34 abierta, prototipo, `AVACOM_LMS_EXIGIR_SESION=0`) actúa la administración del aula: se usa a la primera cuenta
ADMIN activa del nodo como actor, de modo que las reglas, la auditoría y los eventos son exactamente los de siempre. Con
`AVACOM_LMS_EXIGIR_SESION=1` esa rama no existe: las vistas ya rechazan lo que no trae sesión.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..dominio import errores
from ..dominio.entidades import Principal
from ..dominio.valores import Alcance, ClaseSesion
from . import casos_uso as cu

ROL_ESTUDIANTE = "STUDENT"


def _periodo_actual() -> str:
    return str(datetime.now(timezone.utc).year)


def _codigo_de(nombre: str) -> str:
    """«Sexto A» → «SEXTO-A» (máx. 32): el código que el docente no tiene que inventar."""
    limpio = "".join(c if c.isalnum() else "-" for c in nombre.strip().upper())
    while "--" in limpio:
        limpio = limpio.replace("--", "-")
    return limpio.strip("-")[:32] or "GRUPO"


class _Padron(cu.Base):
    def actor(self, principal: Principal | None) -> Principal:
        """El actor de la operación: el principal de la sesión o, en prototipo, la administración del aula."""
        if principal is not None:
            return principal
        with self.s.uow() as uow:
            org = self.organizacion(uow)
            rol = uow.roles.por_codigo(org.id, "ADMIN")
            admins = uow.usuarios.listar(org.id, Alcance.ORGANIZATION, "", [], 3, None, "ADMIN", "ACTIVO") if rol else []
            if not admins:
                raise errores.Conflicto("El nodo no tiene una cuenta de administración activa.", codigo="no_instalado")
            return Principal(usuario_id=admins[0].id, organizacion_id=org.id, rol_id=rol.id, rol_codigo=rol.codigo,
                             menu=rol.menu_principal, nivel=rol.nivel, sesion_id="prototipo", clase_sesion=ClaseSesion.NORMAL,
                             debe_cambiar_credencial=False)


class EstadoPadron(_Padron):
    """`{instalado, organizacion, grupos[{…grupo, estudiantes[], docentes}], sin_grupo[]}`. Nodo vacío → `instalado: false` (200, no error)."""

    def ejecutar(self, principal: Principal | None) -> dict:
        with self.s.uow() as uow:
            org = uow.organizaciones.unica()
        if org is None:
            return {"instalado": False, "organizacion": None, "grupos": [], "sin_grupo": []}
        actor = self.actor(principal)
        grupos = []
        con_grupo: set[str] = set()
        for g in cu.ListarGrupos(self.s).ejecutar(actor):
            detalle = cu.VerGrupo(self.s).ejecutar(actor, g["id"])
            miembros = detalle.get("miembros", [])
            estudiantes = [m for m in miembros if m["papel"] == "ESTUDIANTE"]
            con_grupo.update(m["usuario_id"] for m in estudiantes)
            grupos.append({**{k: g[k] for k in ("id", "codigo", "nombre", "periodo", "nivel_clave", "activo")},
                           "estudiantes": [{"id": m["usuario_id"], "alias": m["alias"], "estado": m["estado"],
                                            "provisional": m["provisional"]} for m in estudiantes],
                           "docentes": sum(1 for m in miembros if m["papel"] == "DOCENTE")})
        try:
            todos = cu.ListarUsuarios(self.s).ejecutar(actor, None, ROL_ESTUDIANTE, "ACTIVO")
        except errores.ErrorAcceso:
            todos = []
        sin_grupo = [{"id": u["id"], "alias": u["alias"]} for u in todos if u["id"] not in con_grupo]
        return {"instalado": True, "organizacion": {"codigo": org.codigo, "nombre": org.nombre}, "grupos": grupos, "sin_grupo": sin_grupo}


class RegistrarGrupo(_Padron):
    def ejecutar(self, principal: Principal | None, datos: dict) -> dict:
        actor = self.actor(principal)
        nombre = str(datos.get("nombre") or "").strip()
        entrada = {"codigo": str(datos.get("codigo") or "").strip() or _codigo_de(nombre), "nombre": nombre,
                   "periodo": str(datos.get("periodo") or "").strip() or _periodo_actual(),
                   "nivel_clave": datos.get("nivel_clave") or None}
        return cu.CrearGrupo(self.s).ejecutar(actor, entrada)


class RegistrarEstudiante(_Padron):
    """Persona + identificador + PIN + pertenencia al grupo, en una sola transacción (`CrearUsuario`). Si no se da documento el nodo emite una
    clave de instalación; si no se da PIN lo genera según el reglamento del perfil y se devuelve UNA vez en `secreto_inicial`."""

    def ejecutar(self, principal: Principal | None, datos: dict) -> dict:
        actor = self.actor(principal)
        nombres = str(datos.get("nombres") or "").strip()
        apellidos = str(datos.get("apellidos") or "").strip()
        if not nombres:
            raise errores.DatosInvalidos("Faltan los nombres del estudiante.")
        if not str(datos.get("grupo_id") or "").strip():
            raise errores.DatosInvalidos("Elige el grupo del estudiante.")
        documento = str(datos.get("documento") or "").strip()
        entrada = {
            "rol": ROL_ESTUDIANTE, "alias": f"{nombres} {apellidos}".strip()[:64],
            "persona": {"nombres": nombres, "apellidos": apellidos},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": documento, "es_login": True}] if documento else [],
            "secreto": str(datos.get("pin") or ""), "secreto_definitivo": bool(datos.get("pin")),
            "grupo_id": str(datos["grupo_id"]).strip(),
        }
        usuario = cu.CrearUsuario(self.s).ejecutar(actor, entrada)
        identificadores = usuario.get("identificadores") or []
        principal_id = next((i for i in identificadores if i.get("principal")), identificadores[0] if identificadores else {})
        salida = {"id": usuario["id"], "alias": usuario["alias"], "grupo_id": entrada["grupo_id"],
                  "identificador": principal_id.get("valor") or ""}
        if "secreto_inicial" in usuario:
            salida["secreto_inicial"] = usuario["secreto_inicial"]
        return salida


class MatricularEstudiante(_Padron):
    def ejecutar(self, principal: Principal | None, grupo_id: str, usuario_id: str) -> dict:
        return cu.AgregarMiembro(self.s).ejecutar(self.actor(principal), grupo_id, usuario_id, "ESTUDIANTE")


class RetirarEstudiante(_Padron):
    def ejecutar(self, principal: Principal | None, grupo_id: str, usuario_id: str) -> None:
        cu.RetirarMiembro(self.s).ejecutar(self.actor(principal), grupo_id, usuario_id)


class PrepararAulaDePrueba(cu.Base):
    """El «día cero» mínimo para probar sin pasar por el instalador: organización de prueba y una cuenta de administración (con la clave
    generada, que NO se devuelve: nadie entra con ella; el aula de prueba no exige sesión). Sólo con el nodo vacío; si ya está instalado es 409."""

    def ejecutar(self) -> dict:
        salida = cu.InstalarNodo(self.s).ejecutar(
            {"codigo": "AULA-PRUEBA", "nombre": "Aula de prueba", "pais": "CO", "idioma": "es", "locale": "es-CO"},
            {"alias": "Administración", "nombres": "Administración", "apellidos": "del aula de prueba", "dni": "ADMIN-PRUEBA"})
        return {"organizacion": salida["organizacion"]}
