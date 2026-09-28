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
EVENTOS = (EV_REGISTRADO, EV_INVENTARIO_ACTUALIZADO, EV_RECONECTADO, EV_BLOQUEADO, EV_DESBLOQUEADO,
           EV_SESION_ABIERTA, EV_SESION_CERRADA)

# --------------------------------------------------------------------- permisos
# Sección J de MOD-009 (`device.*`). `device.block` es del proyecto: lo ejerce el profesor desde el aula.
P_REGISTER, P_READ, P_UPDATE, P_BLOCK = "device.register", "device.read", "device.update", "device.block"
PERMISOS = (P_REGISTER, P_READ, P_UPDATE, P_BLOCK)


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


def validar_motivo_cierre(valor) -> str:
    motivo = str(valor or SISTEMA).strip().lower()
    if motivo not in MOTIVOS_CIERRE:
        raise DatosInvalidos(f"Motivo de cierre desconocido: {valor!r}. Motivos: {', '.join(MOTIVOS_CIERRE)}.")
    return motivo


def en_linea(ultimo_latido_en: int | None, ahora: int) -> bool:
    return ultimo_latido_en is not None and ahora - ultimo_latido_en <= LATIDO_VIVO_MS
