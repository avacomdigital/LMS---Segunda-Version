"""
Catálogo cerrado y versionado de acciones auditables (§3.5 del prompt de MOD-019), como `evento.clave` del v2.

Formato `<dominio>.<objeto>.<verbo>`. Las acciones vigentes de los módulos (identidad.*, aula.*, dispositivos.*,
estudio.*, y las del expediente) se conservan tal como ya están en el código; las nuevas se declaran aquí antes
de que nadie las anexe. Anexar una clave fuera del catálogo falla en pruebas y, en producción, se asienta
`auditoria.accion_desconocida` en vez de perder el hecho.

Algunas familias son abiertas por diseño (el tipo de control o la clase de distribución las decide el aula): se
declaran como PATRONES por prefijo.
"""
from __future__ import annotations

from dataclasses import dataclass

VERSION_CATALOGO = "2026.09.30"

M_ACCESO, M_AULA, M_DISPOSITIVOS, M_ESTUDIO, M_EVALUACION = "acceso", "aula", "dispositivos", "estudio", "evaluacion"
M_AUDITORIA, M_INSTALACION, M_EXPEDIENTE, M_PRUEBAS = "auditoria", "instalacion", "expediente", "pruebas"
MODULOS = (M_ACCESO, M_AULA, M_DISPOSITIVOS, M_ESTUDIO, M_EVALUACION, M_AUDITORIA, M_INSTALACION, M_EXPEDIENTE, M_PRUEBAS)

ETIQUETAS_MODULO = {
    M_ACCESO: "Acceso e identidad", M_AULA: "Aula (clase en vivo)", M_DISPOSITIVOS: "Dispositivos", M_ESTUDIO: "Modo estudio",
    M_EVALUACION: "Evaluaciones", M_AUDITORIA: "Auditoría", M_INSTALACION: "Instalación", M_EXPEDIENTE: "Expediente",
    M_PRUEBAS: "Pruebas",
}


@dataclass(frozen=True)
class Accion:
    clave: str
    modulo: str
    etiqueta: str
    exige_motivo: bool = False
    sensible: bool = False           # toca datos personales o resultados: su detalle se enmascara sin escalada (BR-131)
    evento_origen: str | None = None  # el evento de cola del que deriva (019-09), si existe


def _a(clave: str, modulo: str, etiqueta: str, exige_motivo: bool = False, sensible: bool = False, evento_origen: str | None = None) -> Accion:
    return Accion(clave, modulo, etiqueta, exige_motivo, sensible, evento_origen)


_LISTA: tuple[Accion, ...] = (
    # ---- acceso (MOD-001): las vigentes en `acceso/aplicacion/casos_uso.py` ----
    _a("identidad.usuario.creado", M_ACCESO, "Usuario creado", sensible=True, evento_origen="identidad.usuario.creado.v1"),
    _a("identidad.usuario.actualizado", M_ACCESO, "Usuario actualizado", sensible=True, evento_origen="identidad.usuario.actualizado.v1"),
    _a("identidad.usuarios.importados", M_ACCESO, "Usuarios importados", sensible=True, evento_origen="identidad.usuarios.importados.v1"),
    _a("identidad.usuario.vinculado", M_ACCESO, "Usuario vinculado", sensible=True, evento_origen="identidad.usuario.vinculado.v1"),
    _a("identidad.rol.asignado", M_ACCESO, "Rol asignado", evento_origen="identidad.rol.asignado.v1"),
    _a("identidad.rol.revocado", M_ACCESO, "Rol revocado", evento_origen="identidad.rol.revocado.v1"),
    _a("identidad.rol.creado", M_ACCESO, "Rol creado", evento_origen="identidad.rol.creado.v1"),
    _a("identidad.sesion.abierta", M_ACCESO, "Sesión abierta", evento_origen="identidad.sesion.abierta.v1"),
    _a("identidad.sesion.cerrada", M_ACCESO, "Sesión cerrada", evento_origen="identidad.sesion.cerrada.v1"),
    _a("identidad.sesiones.revocadas", M_ACCESO, "Sesiones revocadas", evento_origen="identidad.sesiones.revocadas.v1"),
    _a("identidad.credencial.restablecida", M_ACCESO, "Credencial restablecida", evento_origen="identidad.credencial.restablecida.v1"),
    _a("identidad.credencial.cambiada", M_ACCESO, "Credencial cambiada", evento_origen="identidad.credencial.cambiada.v1"),
    _a("identidad.cuenta.bloqueada", M_ACCESO, "Cuenta bloqueada", evento_origen="identidad.cuenta.bloqueada.v1"),
    _a("identidad.cuenta.desbloqueada", M_ACCESO, "Cuenta desbloqueada", evento_origen="identidad.cuenta.desbloqueada.v1"),
    _a("identidad.escalada.concedida", M_ACCESO, "Escalada temporal concedida", exige_motivo=False, evento_origen="identidad.escalada.concedida.v1"),
    _a("identidad.escalada.revocada", M_ACCESO, "Escalada temporal revocada", evento_origen="identidad.escalada.revocada.v1"),
    _a("identidad.acceso_temporal.otorgado", M_ACCESO, "Acceso temporal a examen otorgado", evento_origen="identidad.acceso_temporal.otorgado.v1"),
    _a("identidad.acceso_temporal.canjeado", M_ACCESO, "Acceso temporal canjeado", evento_origen="identidad.acceso_temporal.canjeado.v1"),
    _a("identidad.acceso_temporal.revocado", M_ACCESO, "Acceso temporal revocado", evento_origen="identidad.acceso_temporal.revocado.v1"),
    _a("identidad.politica.configurada", M_ACCESO, "Política de credenciales configurada", evento_origen="identidad.politica.configurada.v1"),
    _a("identidad.grupo.creado", M_ACCESO, "Grupo creado", evento_origen="identidad.grupo.creado.v1"),
    _a("identidad.grupo.actualizado", M_ACCESO, "Grupo actualizado", evento_origen="identidad.grupo.actualizado.v1"),
    _a("identidad.grupo.miembro_agregado", M_ACCESO, "Miembro agregado al grupo", evento_origen="identidad.grupo.miembro_agregado.v1"),
    _a("identidad.grupo.miembro_retirado", M_ACCESO, "Miembro retirado del grupo", evento_origen="identidad.grupo.miembro_retirado.v1"),
    _a("identidad.instalacion", M_ACCESO, "Nodo instalado (organización y administrador)", evento_origen="identidad.organizacion.instalada.v1"),
    # nuevas (019-08, 019-10)
    _a("acceso.denegado", M_ACCESO, "Acceso denegado"),
    _a("acceso.dato_personal.consultado", M_ACCESO, "Dato personal de menor consultado", sensible=True),
    _a("acceso.escalada.consumida", M_ACCESO, "Escalada consumida por una operación"),
    _a("acceso.escalada.vencida", M_ACCESO, "Escalada vencida"),
    # ---- aula (MOD-007 · Classroom Engine, prioridad) ----
    _a("aula.sesion.iniciada", M_AULA, "Clase iniciada"),
    _a("aula.sesion.archivada", M_AULA, "Clase archivada"),
    _a("aula.sesion.suspendida", M_AULA, "Clase suspendida"),
    _a("aula.sesion.reanudada", M_AULA, "Clase reanudada"),
    _a("aula.sesion.finalizada", M_AULA, "Clase finalizada"),
    _a("aula.sesion.anclada", M_AULA, "Clase anclada a la tableta"),
    _a("aula.participante.ingreso", M_AULA, "Participante ingresó"),
    _a("aula.participante.admitido", M_AULA, "Participante admitido"),
    _a("aula.participante.rechazado", M_AULA, "Participante rechazado"),
    _a("aula.participante.expulsado", M_AULA, "Participante expulsado"),
    _a("aula.selector.declarado", M_AULA, "Selector de la clase declarado"),
    _a("aula.distribucion.cerrada", M_AULA, "Actividad cerrada"),
    _a("aula.distribucion.estudio", M_AULA, "Lección enviada al modo estudio"),
    _a("aula.resultados.mostrados", M_AULA, "Resultados mostrados"),
    _a("aula.codigo.rotado", M_AULA, "Código de unión rotado"),
    _a("aula.proyeccion.iniciada", M_AULA, "Proyección de una pantalla iniciada", sensible=True),
    _a("aula.proyeccion.terminada", M_AULA, "Proyección de una pantalla terminada"),
    _a("aula.ayuda.solicitada", M_AULA, "Ayuda solicitada"),
    _a("aula.ayuda.atendida", M_AULA, "Ayuda atendida"),
    _a("aula.ayuda.retirada", M_AULA, "Ayuda retirada"),
    # nuevas (019-08)
    _a("aula.aviso.enviado", M_AULA, "Aviso enviado"),
    _a("aula.presencia.perdida", M_AULA, "Presencia perdida (transición)"),
    _a("aula.presencia.recuperada", M_AULA, "Presencia recuperada (transición)"),
    _a("aula.nivel.excepcion", M_AULA, "Excepción de nivel de control"),
    _a("aula.denegado", M_AULA, "Operación del aula denegada"),
    # ---- dispositivos (MOD-009) ----
    _a("dispositivos.registrado", M_DISPOSITIVOS, "Equipo registrado"),
    _a("dispositivos.actualizado", M_DISPOSITIVOS, "Equipo actualizado"),
    _a("dispositivos.bloqueado", M_DISPOSITIVOS, "Equipo bloqueado"),
    _a("dispositivos.desbloqueado", M_DISPOSITIVOS, "Equipo desbloqueado"),
    _a("dispositivos.asignado", M_DISPOSITIVOS, "Equipo asignado a una persona"),
    _a("dispositivos.liberado", M_DISPOSITIVOS, "Equipo liberado"),
    _a("dispositivos.borrado_remoto", M_DISPOSITIVOS, "Borrado remoto ordenado", exige_motivo=True),
    _a("dispositivos.limpieza_registrada", M_DISPOSITIVOS, "Limpieza del equipo registrada"),
    # ---- estudio (MOD-008) ----
    _a("estudio.asignacion.creada", M_ESTUDIO, "Asignación creada"),
    _a("estudio.asignacion.actualizada", M_ESTUDIO, "Asignación actualizada"),
    _a("estudio.asignacion.cerrada", M_ESTUDIO, "Asignación cerrada"),
    _a("estudio.asignacion.estructura_refrescada", M_ESTUDIO, "Estructura de la asignación refrescada"),
    _a("estudio.leccion.completada", M_ESTUDIO, "Lección completada"),
    _a("estudio.paquete.descargado", M_ESTUDIO, "Paquete de estudio descargado"),
    _a("estudio.paquete.denegado", M_ESTUDIO, "Paquete de estudio denegado"),
    _a("estudio.entrega.integrada", M_ESTUDIO, "Entrega integrada al expediente"),
    # ---- evaluación (MOD-010/011: el punto de llamada se conecta cuando nazcan sus tablas) ----
    _a("evaluacion.iniciada", M_EVALUACION, "Evaluación iniciada"),
    _a("evaluacion.enviada", M_EVALUACION, "Evaluación enviada"),
    _a("evaluacion.anulada", M_EVALUACION, "Evaluación anulada", exige_motivo=True, sensible=True),
    _a("calificacion.modificada", M_EVALUACION, "Calificación modificada", exige_motivo=True, sensible=True),
    _a("calificacion.reabierta", M_EVALUACION, "Calificación reabierta", exige_motivo=True, sensible=True),
    _a("calificacion.correccion_posterior_cierre", M_EVALUACION, "Corrección posterior al cierre", exige_motivo=True, sensible=True),
    # ---- expediente (lo que hoy escribe `expediente/servicios.py`) ----
    _a("inscripcion.creada", M_EXPEDIENTE, "Inscripción creada"),
    _a("inscripcion.retirada", M_EXPEDIENTE, "Inscripción retirada"),
    _a("progreso.actualizado", M_EXPEDIENTE, "Progreso actualizado"),
    _a("apertura.registrada", M_EXPEDIENTE, "Apertura de material registrada"),
    _a("intento.iniciado", M_EXPEDIENTE, "Intento iniciado"),
    _a("intento.finalizado", M_EXPEDIENTE, "Intento finalizado", sensible=True),
    _a("disponibilidad.desaparecio", M_EXPEDIENTE, "Elemento del curso desapareció"),
    _a("disponibilidad.reaparecio", M_EXPEDIENTE, "Elemento del curso reapareció"),
    _a("administracion.rechazada", M_EXPEDIENTE, "Administración de cursos rechazada"),
    # ---- auditoría (los cinco eventos de 019-09 y los propios) ----
    _a("auditoria.bitacora_abierta", M_AUDITORIA, "Bitácora abierta (génesis)"),
    _a("auditoria.cadena_migrada", M_AUDITORIA, "Cadena creada a partir del historial"),
    _a("auditoria.registro_creado", M_AUDITORIA, "Asiento creado"),
    _a("auditoria.cadena_verificada", M_AUDITORIA, "Cadena verificada", evento_origen="auditoria.cadena_verificada.v1"),
    _a("auditoria.salto_detectado", M_AUDITORIA, "Salto detectado en la cadena", evento_origen="auditoria.salto_detectado.v1"),
    _a("auditoria.bitacora_rotada", M_AUDITORIA, "Bitácora rotada", evento_origen="auditoria.bitacora_rotada.v1"),
    _a("auditoria.tramo_exportado", M_AUDITORIA, "Tramo exportado", exige_motivo=True, evento_origen="auditoria.tramo_exportado.v1"),
    _a("auditoria.alteracion_intentada", M_AUDITORIA, "Intento de alterar la bitácora"),
    _a("auditoria.consulta_realizada", M_AUDITORIA, "Consulta de la bitácora"),
    _a("auditoria.exportacion_denegada", M_AUDITORIA, "Exportación denegada"),
    _a("auditoria.violacion_inv003", M_AUDITORIA, "Escritura desde un módulo no declarado"),
    _a("auditoria.restauracion_registrada", M_AUDITORIA, "Restauración de respaldo registrada"),
    _a("auditoria.accion_desconocida", M_AUDITORIA, "Acción fuera del catálogo"),
    # ---- instalación ----
    _a("instalacion.organizacion_creada", M_INSTALACION, "Organización creada"),
    _a("instalacion.licencia_activada", M_INSTALACION, "Licencia activada"),
    _a("instalacion.migracion_aplicada", M_INSTALACION, "Migración aplicada"),
)

ACCIONES: dict[str, Accion] = {a.clave: a for a in _LISTA}

# Familias abiertas: (prefijo, módulo, etiqueta). `aula.control.<tipo>`, `aula.distribucion.<clase>`, `aula.envio.<decisión>`,
# `estudio.envio.<decisión>`; `prueba.*` es sólo para las pruebas automáticas del backend.
PATRONES: tuple[tuple[str, str, str], ...] = (
    ("aula.control.", M_AULA, "Control de la clase"),
    ("aula.distribucion.", M_AULA, "Actividad distribuida"),
    ("aula.envio.", M_AULA, "Entrega recibida"),
    ("estudio.envio.", M_ESTUDIO, "Entrega de estudio recibida"),
    ("prueba.", M_PRUEBAS, "Acción de prueba"),
)


def resolver(clave: str) -> Accion | None:
    """La definición de la acción, o None si no está en el catálogo (ni por clave ni por patrón)."""
    accion = ACCIONES.get(clave)
    if accion is not None:
        return accion
    for prefijo, modulo, etiqueta in PATRONES:
        if clave.startswith(prefijo) and len(clave) > len(prefijo):
            return Accion(clave, modulo, f"{etiqueta}: {clave[len(prefijo):]}")
    return None


def modulo_de(clave: str) -> str:
    """El módulo de una acción por su prefijo, aun si no está en el catálogo (para la migración y lo desconocido)."""
    accion = resolver(clave)
    if accion is not None:
        return accion.modulo
    prefijo = clave.split(".", 1)[0]
    return {"identidad": M_ACCESO, "identity": M_ACCESO, "acceso": M_ACCESO, "aula": M_AULA, "dispositivos": M_DISPOSITIVOS,
            "estudio": M_ESTUDIO, "evaluacion": M_EVALUACION, "calificacion": M_EVALUACION, "auditoria": M_AUDITORIA,
            "instalacion": M_INSTALACION, "prueba": M_PRUEBAS}.get(prefijo, M_EXPEDIENTE)


def como_lista() -> list[dict]:
    """El catálogo para `GET /api/auditoria/catalogo/` (alimenta los filtros de OPS)."""
    return [{"clave": a.clave, "modulo": a.modulo, "etiqueta": a.etiqueta, "exige_motivo": a.exige_motivo,
             "sensible": a.sensible, "evento_origen": a.evento_origen} for a in _LISTA] + [
        {"clave": f"{prefijo}*", "modulo": modulo, "etiqueta": etiqueta, "exige_motivo": False, "sensible": False, "evento_origen": None}
        for prefijo, modulo, etiqueta in PATRONES if modulo != M_PRUEBAS]
