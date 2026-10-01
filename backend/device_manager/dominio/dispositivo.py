"""
El dispositivo y la sesión de alumno en él: catálogos cerrados, eventos, permisos y reglas
puras de MOD-009. Ningún archivo de esta carpeta importa Django.

La regla de oro del módulo (Documento Maestro, frontera de MOD-009): el dispositivo nunca
bloquea al alumno. Bloquear una tableta la deja fuera de las sesiones nuevas y de los
lanzamientos; retirarla (activo = false) conserva su historial.
"""
from __future__ import annotations

from .errores import DatosInvalidos

# ------------------------------------------------------------------- catálogos

TABLETA, MASTER, OTRO = "TABLETA", "MASTER", "OTRO"
TIPOS = (TABLETA, MASTER, OTRO)

WINDOWS, ANDROID = "windows", "android"
PLATAFORMAS = ("", WINDOWS, ANDROID)

USUARIO, INACTIVIDAD, SISTEMA, RELEVO = "usuario", "inactividad", "sistema", "relevo"
MOTIVOS_CIERRE = (USUARIO, INACTIVIDAD, SISTEMA, RELEVO)

# Perfil del equipo (009-06, 008-01): «compartido» es la tableta del aula que usa quien la tenga en la mano; «asignado» es el
# equipo nominal de UNA persona. El modo de estudio sirve en cualquier equipo (D-15), pero un paquete sólo se descarga en el asignado a
# su dueño: uno descargado en un equipo compartido sería accesible al siguiente alumno (BR-054).
COMPARTIDO, ASIGNADO = "compartido", "asignado"
PERFILES = (COMPARTIDO, ASIGNADO)

# Capacidad de CONTROL que la tableta declara poder garantizar durante un examen (MOD-010, BR-075, DEC-009). `controlado` significa que la capa del
# sistema operativo está aprovisionada (Device Owner en Android; Assigned Access o Shell Launcher en Windows); `supervisado`, que la app registra lo que
# pasa pero el sistema ofrece una salida; `abierto`, que sólo se registran entrega y tiempo. Vacío = la tableta nunca lo declaró: el nodo la trata como
# `abierto` (no presume lo que no sabe).
ABIERTO, SUPERVISADO, CONTROLADO = "abierto", "supervisado", "controlado"
NIVELES_CONTROL = (ABIERTO, SUPERVISADO, CONTROLADO)

# Una tableta se considera viva si dio señal en el último minuto (el sondeo del aula es cada 2 s).
LATIDO_VIVO_MS = 60_000

# ---------------------------------------------------------------------- eventos
# Sección L de MOD-009 en el Documento Maestro. `bloqueado`/`desbloqueado` y la sesión de alumno
# son hechos propios de este proyecto (el bloqueo por el profesor no existe en el catálogo del Maestro).
EV_REGISTRADO = "dispositivo.registrado.v1"
EV_INVENTARIO_ACTUALIZADO = "dispositivo.inventario.actualizado.v1"
EV_RECONECTADO = "dispositivo.reconectado.v1"
EV_BLOQUEADO = "dispositivo.bloqueado.v1"
EV_DESBLOQUEADO = "dispositivo.desbloqueado.v1"
EV_SESION_ABIERTA = "dispositivo.sesion.abierta.v1"
EV_SESION_CERRADA = "dispositivo.sesion.cerrada.v1"
# FUN-092 y FUN-093: la asignación nominal del equipo (perfil «asignado») y su liberación.
EV_ASIGNADO = "dispositivo.asignado.v1"
EV_LIBERADO = "dispositivo.liberado.v1"
EVENTOS = (EV_REGISTRADO, EV_INVENTARIO_ACTUALIZADO, EV_RECONECTADO, EV_BLOQUEADO, EV_DESBLOQUEADO,
           EV_SESION_ABIERTA, EV_SESION_CERRADA, EV_ASIGNADO, EV_LIBERADO)

# --------------------------------------------------------------------- permisos
# Sección J de MOD-009 (`device.*`). `device.block` es del proyecto: lo ejerce el profesor desde el aula. `device.assign` y
# `device.release` (FUN-092, FUN-093) equivalen a `identity.device.manage` (técnico y administrador).
P_REGISTER, P_READ, P_UPDATE, P_BLOCK = "device.register", "device.read", "device.update", "device.block"
P_ASSIGN, P_RELEASE = "device.assign", "device.release"
PERMISOS = (P_REGISTER, P_READ, P_UPDATE, P_BLOCK, P_ASSIGN, P_RELEASE)


# ----------------------------------------------------------------------- reglas

def normalizar_identificador(valor) -> str:
    texto = str(valor or "").strip()
    if not texto:
        raise DatosInvalidos("Falta el identificador del dispositivo.")
    if len(texto) > 128:
        raise DatosInvalidos("El identificador del dispositivo supera los 128 caracteres.")
    return texto


def normalizar_nombre(valor, obligatorio: bool = False, por_defecto: str = "") -> str:
    texto = str(valor or "").strip()
    if not texto:
        if obligatorio:
            raise DatosInvalidos("Falta el nombre del dispositivo.")
        texto = por_defecto
    return texto[:120]


def validar_tipo(valor) -> str:
    tipo = str(valor or TABLETA).strip().upper()
    if tipo not in TIPOS:
        raise DatosInvalidos(f"Tipo de dispositivo desconocido: {valor!r}. Tipos: {', '.join(TIPOS)}.", tipo=valor)
    return tipo


def validar_plataforma(valor) -> str:
    plataforma = str(valor or "").strip().lower()
    if plataforma not in PLATAFORMAS:
        raise DatosInvalidos(f"Plataforma desconocida: {valor!r}. Plataformas: windows, android.", plataforma=valor)
    return plataforma


def validar_capacidad_control(valor) -> str:
    """La capacidad que declara una tableta: vacío (no la declaró) o uno de los tres niveles. Un valor desconocido es un error de datos."""
    texto = str(valor or "").strip().lower()
    if texto and texto not in NIVELES_CONTROL:
        raise DatosInvalidos(f"capacidad_control debe ser uno de: {', '.join(NIVELES_CONTROL)}.", capacidad_control=valor)
    return texto


def normalizar_alumno(valor) -> str:
    """El alumno al que se asigna el equipo: la referencia lógica a `m01_usuario.id` (hasta 64 caracteres)."""
    texto = str(valor or "").strip()
    if not texto:
        raise DatosInvalidos("Falta alumno_id: a quién se asigna el equipo.")
    if len(texto) > 64:
        raise DatosInvalidos("alumno_id supera los 64 caracteres.")
    return texto


def validar_motivo_cierre(valor) -> str:
    motivo = str(valor or SISTEMA).strip().lower()
    if motivo not in MOTIVOS_CIERRE:
        raise DatosInvalidos(f"Motivo de cierre desconocido: {valor!r}. Motivos: {', '.join(MOTIVOS_CIERRE)}.")
    return motivo


def en_linea(ultimo_latido_en: int | None, ahora: int) -> bool:
    return ultimo_latido_en is not None and ahora - ultimo_latido_en <= LATIDO_VIVO_MS
