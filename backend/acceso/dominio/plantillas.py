"""
Plantillas plug-and-play alineadas con MOD-001 · Identity & Access del Documento
Maestro: los cinco roles predefinidos (Administrador, Profesor, Alumno, Reportes,
Técnico AVACOM), el catálogo de permisos con nomenclatura `identity.*` y las
políticas de credencial por defecto. Un colegio que no configure nada funciona con esto.
"""
from __future__ import annotations

from .valores import Alcance, Menu, TipoIdentificador, TipoSecreto

S, G, L, O = Alcance.SELF, Alcance.ASSIGNED_GROUPS, Alcance.LEVEL, Alcance.ORGANIZATION

# (codigo, modulo, descripcion, alcance_maximo, sensible)
# Los del módulo de acceso llevan el prefijo `identity.` que exige el Documento Maestro
# (identity.user.create, identity.role.assign, identity.user.import, identity.password.reset,
# identity.user.unlock, identity.session.revoke). Los demás pertenecen a otros módulos y se
# conservan aquí porque el rol es quien los concede.
PERMISOS: list[tuple[str, str, str, Alcance, bool]] = [
    # --- expediente / contenido / aula (otros módulos) ---
    ("student.progress.read", "expediente", "Ver progreso y notas", O, False),
    ("student.progress.write", "expediente", "Registrar aperturas y avance", S, False),
    ("student.exam.attempt", "expediente", "Rendir evaluaciones", S, False),
    ("results.read", "expediente", "Ver resultados", O, False),
    ("reports.student.view", "reportes", "Ver el informe nominal de un alumno", O, True),
    ("content.read", "contenido", "Ver cursos de la biblioteca", O, False),
    ("content.project", "aula", "Proyectar en la pantalla del aula", G, False),
    ("audit.read", "auditoria", "Leer auditoría", O, True),
    # --- MOD-001 · identity ---
    ("identity.user.read", "acceso", "Ver usuarios y sus datos personales", O, True),
    ("identity.user.create", "acceso", "Crear una cuenta de usuario local (FUN-001)", O, True),
    ("identity.user.import", "acceso", "Importar usuarios desde archivo delimitado (FUN-003)", O, True),
    ("identity.user.update", "acceso", "Editar datos y estado de usuarios", O, True),
    ("identity.user.unlock", "acceso", "Desbloquear una cuenta bloqueada (FUN-008)", O, True),
    ("identity.role.assign", "acceso", "Asignar un rol a un usuario (FUN-002)", O, True),
    ("identity.role.read", "acceso", "Ver roles y catálogo de permisos", O, False),
    ("identity.role.manage", "acceso", "Componer roles personalizados", O, True),
    ("identity.escalation.grant", "acceso", "Conceder una escalada temporal de permisos (BR-101)", O, True),
    ("identity.password.reset", "acceso", "Restablecer la credencial de otra persona (FUN-006)", O, True),
    ("identity.password.change_own", "acceso", "Cambiar la propia credencial", S, False),
    ("identity.exam_access.grant", "acceso", "Autorizar acceso temporal a examen desde el aula (CAP-004)", G, True),
    ("identity.session.read", "acceso", "Ver sesiones", O, False),
    ("identity.session.revoke", "acceso", "Revocar sesiones ajenas (FUN-010)", O, True),
    ("identity.session.revoke_own", "acceso", "Cerrar la propia sesión", S, False),
    ("identity.group.read", "acceso", "Ver grupos", O, False),
    ("identity.group.manage", "acceso", "Crear y editar grupos", O, False),
    ("identity.group.member.manage", "acceso", "Añadir y quitar miembros de grupos", O, False),
    ("identity.policy.manage", "acceso", "Configurar la política de credenciales (BR-023)", O, True),
    ("identity.device.manage", "acceso", "Registrar y dar de baja dispositivos", O, False),
    # --- MOD-007 · Classroom Engine (sección J de su ficha). Los evalúa `classroom_engine.infraestructura.repositorios.AutorizacionAula`.
    ("classroom.start", "aula", "Abrir una sesión de aula sobre un grupo propio y generar su código de unión (FUN-064)", O, False),
    ("classroom.code.rotate", "aula", "Rotar el código de unión de una sesión activa (FUN-066)", O, False),
    ("classroom.device.admit", "aula", "Admitir o rechazar un dispositivo en la sesión (FUN-067, FUN-068)", O, False),
    ("classroom.device.remove", "aula", "Expulsar a un dispositivo de la sesión (FUN-078)", O, False),
    ("classroom.device.lock", "aula", "Bloquear las pantallas del grupo y fijar el seguimiento (FUN-074, BR-050)", O, False),
    ("classroom.present", "aula", "Proyectar un recurso y declarar el selector de la clase (FUN-069, BR-049)", O, False),
    ("classroom.activity.launch", "aula", "Lanzar una actividad a los dispositivos del grupo (FUN-070)", O, False),
    ("classroom.activity.close", "aula", "Cerrar la recepción de respuestas de la actividad en curso (FUN-071)", O, False),
    ("classroom.results.view", "aula", "Ver el panel de resultados agregados de la clase (FUN-072)", O, False),
    ("classroom.message.send", "aula", "Enviar un aviso a un dispositivo o al grupo (FUN-075)", O, False),
    ("classroom.end", "aula", "Finalizar la sesión de clase y consolidar su registro (FUN-079)", O, False),
    # --- MOD-008 · Modo Estudio (sección J de su ficha). Los seis primeros son del alumno sobre lo suyo (SELF); los dos últimos son del
    # proyecto (el Maestro no da permiso a CAP-050/051): el profesor asigna y ve quién completó sobre sus grupos. Los evalúa
    # `modo_estudio.infraestructura.autorizacion.AutorizacionEstudio`.
    ("study.open", "estudio", "Abrir y cerrar la sesión de estudio en una tableta asignada (FUN-080, FUN-089)", S, False),
    ("study.assignment.read", "estudio", "Ver el trabajo pendiente propio con sus fechas límite (FUN-081)", S, False),
    ("study.lesson.open", "estudio", "Abrir una lección asignada y sus medios (FUN-082)", S, False),
    ("study.lesson.complete", "estudio", "Registrar avance por bloques y marcar la lección como completada (FUN-087)", S, False),
    ("study.answer.submit", "estudio", "Practicar con retroalimentación inmediata y reanudar la práctica (FUN-083, FUN-088)", S, False),
    ("study.package.download", "estudio", "Pedir, bajar, confirmar y retirar el paquete de estudio (FUN-084)", S, False),
    ("study.assignment.create", "estudio", "Asignar una lección a un grupo o a alumnos con fecha límite (CAP-050)", O, False),
    ("study.assignment.review", "estudio", "Ver quién completó lo asignado y resolver lo pendiente de decisión (CAP-051, BR-074)", O, False),
]

PERMISOS_POR_CODIGO = {p[0]: p for p in PERMISOS}

# Los seis permisos `study.*` del alumno: sólo el rol STUDENT los tiene. El Maestro es explícito: el administrador «no accede al
# modo de estudio del alumno», así que se excluyen de ADMIN aunque el resto de los permisos se le concedan por defecto.
PERMISOS_DE_ESTUDIO_DEL_ALUMNO = ("study.open", "study.assignment.read", "study.lesson.open", "study.lesson.complete",
                                  "study.answer.submit", "study.package.download")

# Correspondencia con los códigos usados antes de alinear con el Documento Maestro.
# La migración 0003 la aplica sobre las filas existentes.
RENOMBRES_PERMISOS: dict[str, str] = {
    "user.read": "identity.user.read",
    "user.create": "identity.user.create",
    "user.update": "identity.user.update",
    "user.role.assign": "identity.role.assign",
    "user.permission.grant": "identity.escalation.grant",
    "user.unlock": "identity.user.unlock",
    "credential.reset": "identity.password.reset",
    "credential.change_own": "identity.password.change_own",
    "exam.temporary_access.grant": "identity.exam_access.grant",
    "session.read": "identity.session.read",
    "session.revoke": "identity.session.revoke",
    "session.revoke_own": "identity.session.revoke_own",
    "group.read": "identity.group.read",
    "group.manage": "identity.group.manage",
    "group.member.manage": "identity.group.member.manage",
    "role.read": "identity.role.read",
    "role.manage": "identity.role.manage",
    "policy.manage": "identity.policy.manage",
    "device.manage": "identity.device.manage",
}

_TODOS_ORG = {codigo: (O if maximo is O else maximo) for codigo, _, _, maximo, _ in PERMISOS}

# codigo -> (nombre, menu, nivel, {permiso: alcance})
# Los cinco roles del Documento Maestro. Nivel: 1 alumno · 2 personal docente y de apoyo · 3 administración.
ROLES_SISTEMA: dict[str, tuple[str, Menu, int, dict[str, Alcance]]] = {
    "STUDENT": ("Alumno", Menu.STUDENT, 1, {
        "student.progress.read": S, "student.progress.write": S, "student.exam.attempt": S,
        "results.read": S, "content.read": S, "identity.user.read": S, "identity.password.change_own": S,
        "identity.session.read": S, "identity.session.revoke_own": S, "identity.group.read": S,
        # El modo de estudio es del alumno y sólo sobre lo suyo.
        **{c: S for c in PERMISOS_DE_ESTUDIO_DEL_ALUMNO},
    }),
    "TEACHER": ("Profesor", Menu.TEACHER, 2, {
        "student.progress.read": G, "results.read": G, "reports.student.view": G, "content.read": O, "content.project": G,
        "identity.user.read": G, "identity.user.create": G, "identity.user.update": G, "identity.user.unlock": G,
        "identity.password.reset": G, "identity.password.change_own": S, "identity.exam_access.grant": G,
        "identity.session.read": G, "identity.session.revoke": G, "identity.session.revoke_own": S,
        "identity.group.read": G, "identity.group.member.manage": G, "identity.role.read": O,
        # La clase la opera su profesor titular sobre sus grupos; la titularidad la comprueba el aula sesión por sesión.
        "classroom.start": G, "classroom.code.rotate": G, "classroom.device.admit": G, "classroom.device.remove": G,
        "classroom.device.lock": G, "classroom.present": G, "classroom.activity.launch": G, "classroom.activity.close": G,
        "classroom.results.view": G, "classroom.message.send": G, "classroom.end": G,
        # Asigna trabajo de estudio y ve quién lo completó, sobre sus grupos.
        "study.assignment.create": G, "study.assignment.review": G,
    }),
    "ADMIN": ("Administrador", Menu.ADMIN, 3, {
        # Todo salvo lo que el Maestro le niega: calificar directamente, el modo de estudio del alumno y el intento del alumno.
        **{c: a for c, a in _TODOS_ORG.items()
           if c not in ("student.progress.write", "student.exam.attempt", *PERMISOS_DE_ESTUDIO_DEL_ALUMNO)},
    }),
    "REPORTS": ("Reportes", Menu.REPORTS, 2, {
        # Sólo lectura. Ninguna escritura sobre datos académicos, en ninguna circunstancia.
        "student.progress.read": O, "results.read": O, "reports.student.view": O, "content.read": O,
        "identity.user.read": O, "identity.group.read": O, "identity.role.read": O,
        "identity.password.change_own": S, "identity.session.read": S, "identity.session.revoke_own": S,
    }),
    "TECHNICIAN": ("Técnico AVACOM", Menu.TECHNICIAN, 2, {
        # Diagnóstico, red, dispositivos y respaldos. Sin acceso a datos personales ni evidencias (BR-097).
        "identity.device.manage": O, "identity.role.read": O, "identity.session.read": O,
        "identity.password.change_own": S, "identity.session.revoke_own": S,
    }),
}

_BASE = dict(intentos_maximos=5, ventana_intentos_min=15, bloqueo_minutos=15, duracion_sesion_min=240,
             vigencia_credencial_dias=None, inactividad_min=20)

# perfil -> columnas de la política por defecto (BR-023: personal y alumnos por separado)
POLITICAS_POR_DEFECTO: dict[Menu, dict] = {
    Menu.STUDENT: dict(_BASE, tipo_identificador=TipoIdentificador.CODIGO_ESTUDIANTIL, tipo_secreto=TipoSecreto.PIN,
                       longitud_minima=6, exige_mayuscula=False, exige_minuscula=False, exige_digito=True,
                       exige_simbolo=False, permite_acceso_temporal=True, inactividad_min=30),
    Menu.TEACHER: dict(_BASE, tipo_identificador=TipoIdentificador.DNI, tipo_secreto=TipoSecreto.PASSWORD,
                       longitud_minima=8, exige_mayuscula=True, exige_minuscula=False, exige_digito=False,
                       exige_simbolo=True, permite_acceso_temporal=False),
    Menu.ADMIN: dict(_BASE, tipo_identificador=TipoIdentificador.DNI, tipo_secreto=TipoSecreto.PASSWORD,
                     longitud_minima=12, exige_mayuscula=True, exige_minuscula=True, exige_digito=True,
                     exige_simbolo=True, permite_acceso_temporal=False, bloqueo_minutos=30),
    Menu.REPORTS: dict(_BASE, tipo_identificador=TipoIdentificador.DNI, tipo_secreto=TipoSecreto.PASSWORD,
                       longitud_minima=8, exige_mayuscula=True, exige_minuscula=False, exige_digito=False,
                       exige_simbolo=True, permite_acceso_temporal=False),
    Menu.TECHNICIAN: dict(_BASE, tipo_identificador=TipoIdentificador.DNI, tipo_secreto=TipoSecreto.PASSWORD,
                          longitud_minima=12, exige_mayuscula=True, exige_minuscula=True, exige_digito=True,
                          exige_simbolo=True, permite_acceso_temporal=False, bloqueo_minutos=30),
}

# Lo único que puede hacer una sesión nacida de una autorización temporal de examen.
PERMISOS_SESION_TEMPORAL = frozenset({
    "student.exam.attempt", "student.progress.read", "student.progress.write",
    "content.read", "results.read", "identity.session.revoke_own",
})

# Lo único que puede hacer quien aún tiene una credencial provisional.
PERMISOS_CON_CREDENCIAL_PROVISIONAL = frozenset({"identity.password.change_own", "identity.session.revoke_own"})

# Eventos que publica el módulo (identidad.*.v1, como en el Documento Maestro).
EVENTOS = {
    "usuario_creado": "identidad.usuario.creado.v1",
    "usuario_actualizado": "identidad.usuario.actualizado.v1",
    "usuarios_importados": "identidad.usuarios.importados.v1",
    "usuario_vinculado": "identidad.usuario.vinculado.v1",
    "rol_asignado": "identidad.rol.asignado.v1",
    "rol_revocado": "identidad.rol.revocado.v1",
    "rol_creado": "identidad.rol.creado.v1",
    "sesion_abierta": "identidad.sesion.abierta.v1",
    "sesion_cerrada": "identidad.sesion.cerrada.v1",
    "sesiones_revocadas": "identidad.sesiones.revocadas.v1",
    "sesion_restaurada": "identidad.sesion.restaurada.v1",
    "credencial_restablecida": "identidad.credencial.restablecida.v1",
    "credencial_cambiada": "identidad.credencial.cambiada.v1",
    "cuenta_bloqueada": "identidad.cuenta.bloqueada.v1",
    "cuenta_desbloqueada": "identidad.cuenta.desbloqueada.v1",
    "escalada_concedida": "identidad.escalada.concedida.v1",
    "escalada_revocada": "identidad.escalada.revocada.v1",
    "acceso_temporal_otorgado": "identidad.acceso_temporal.otorgado.v1",
    "acceso_temporal_canjeado": "identidad.acceso_temporal.canjeado.v1",
    "acceso_temporal_revocado": "identidad.acceso_temporal.revocado.v1",
    "politica_configurada": "identidad.politica.configurada.v1",
    "grupo_creado": "identidad.grupo.creado.v1",
    "grupo_actualizado": "identidad.grupo.actualizado.v1",
    "miembro_agregado": "identidad.grupo.miembro_agregado.v1",
    "miembro_retirado": "identidad.grupo.miembro_retirado.v1",
    "dispositivo_registrado": "identidad.dispositivo.registrado.v1",
    "dispositivo_actualizado": "identidad.dispositivo.actualizado.v1",
    "organizacion_instalada": "identidad.organizacion.instalada.v1",
}

MINUTOS_ACCESO_TEMPORAL = 5
FALLOS_MAXIMOS_ACCESO_TEMPORAL = 3
CREDENCIALES_NO_REUTILIZABLES = 3
# BR-101: toda escalada caduca. Tope de 24 horas (la más larga del Maestro, ESC-05).
ESCALADA_MAXIMA_HORAS = 24
# Columnas que acepta la importación por archivo delimitado (FUN-003).
COLUMNAS_IMPORTACION = ("rol", "alias", "nombres", "apellidos", "tipo_identificador", "identificador", "grupo", "secreto")
