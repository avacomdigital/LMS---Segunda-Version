"""
Sistema de logs en archivos de texto (§2 del prompt de MOD-019): JSON Lines, un archivo por canal, rotación por
tamaño, carpeta decidida una sola vez al arrancar y un filtro de saneamiento que impide que un dato personal llegue
a un archivo que el técnico lee en texto plano (BR-097, §2.6).

    backend-app.log        petición → caso de uso → resultado, con `ruta` happy/sad/bad
    backend-errores.log    sólo WARNING o superior, con traza
    backend-auditoria.log  un renglón por asiento anexado (secuencia, acción, resultado; sin valores), verificaciones, saltos
    backend-clientes.log   los renglones WARNING+ que suben OPS y Student (§2.4, POST /api/logs/clientes/)
    instalacion.log        arranque, migraciones, apertura de la bitácora, siembra
    pruebas-<corrida>.log  todo el backend durante una corrida de pruebas, etiquetado por caso

Este archivo lo importa `settings.py` antes de que existan las apps: no puede importar nada de Django ni de los
modelos. El contexto (corr, dispositivo, caso) viene de `audit.contexto`, que tampoco lo hace.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import logging.handlers
import os
import sys
import tempfile
import traceback
from pathlib import Path

from . import contexto

CANAL_ESCRITURA = "escritura"
CANAL_COMUNICACION = "comunicacion"
CANAL_DISPOSITIVO = "dispositivo"
CANAL_APLICACION = "aplicacion"
CANAL_AUDITORIA = "auditoria"
CANAL_INSTALACION = "instalacion"
CANALES = (CANAL_ESCRITURA, CANAL_COMUNICACION, CANAL_DISPOSITIVO, CANAL_APLICACION, CANAL_AUDITORIA, CANAL_INSTALACION)

RUTA_HAPPY, RUTA_SAD, RUTA_BAD = "happy", "sad", "bad"
RUTAS = (RUTA_HAPPY, RUTA_SAD, RUTA_BAD)

APPS = ("backend", "ops", "student")

ENTORNO_INSTALADO = "instalado"
ENTORNO_DESARROLLO = "desarrollo"
ENTORNO_PRUEBAS = "pruebas"

# Rotación por tamaño: el mismo criterio que `Registro.cs` del instalador. Los logs NO son evidencia: se purgan.
TAMANO_MAXIMO = 2 * 1024 * 1024
COPIAS = 5

# §2.6: claves que jamás se escriben en un log. Se comparan en minúsculas y por «contiene».
CLAVES_PROHIBIDAS = frozenset({
    "secreto", "pin", "token", "password", "contrasena", "contraseña", "clave", "respuesta", "respuestas",
    "nombre", "nombres", "apellido", "apellidos", "dni", "documento", "authorization", "cookie", "identificador",
    "fecha_nacimiento", "correo", "email", "telefono",
})
# Claves que sí son identificadores técnicos aunque contengan una palabra prohibida.
CLAVES_PERMITIDAS = frozenset({"identificador_hw", "usuario_id", "dispositivo_id", "persona_id", "sesion_id", "token_id",
                               "correlacion_id", "correlacion", "corr", "nombre_archivo", "archivo"})
REDACTADO = "[redactado]"

LOGGER_RAIZ = "avacom"
LOGGER_APP = "avacom.app"
LOGGER_AUDITORIA = "avacom.auditoria"
LOGGER_CLIENTES = "avacom.clientes"
LOGGER_INSTALACION = "avacom.instalacion"

_MODULO_POR_LOGGER = {"aula": "aula", "acceso": "acceso", "dispositivos": "dispositivos", "estudio": "estudio",
                      "auditoria": "auditoria", "instalacion": "instalacion", "clientes": "clientes", "app": "backend"}


# ------------------------------------------------------------------------------- carpeta

def entorno(env=None, argv=None) -> str:
    """instalado · desarrollo · pruebas. `AVACOM_LMS_ENTORNO` manda; si no, `manage.py test` es pruebas y
    `AVACOM_LMS_DEBUG=0` (el servicio instalado) es instalado."""
    env = os.environ if env is None else env
    argv = sys.argv if argv is None else argv
    declarado = (env.get("AVACOM_LMS_ENTORNO") or "").strip().lower()
    if declarado in (ENTORNO_INSTALADO, ENTORNO_DESARROLLO, ENTORNO_PRUEBAS):
        return declarado
    if len(argv) > 1 and argv[1] == "test":
        return ENTORNO_PRUEBAS
    if env.get("AVACOM_LMS_DEBUG", "1") == "0":
        return ENTORNO_INSTALADO
    return ENTORNO_DESARROLLO


def carpeta_logs(base_dir: Path, env=None, argv=None, ahora: dt.datetime | None = None) -> Path:
    """§2.2: la carpeta se decide una sola vez al arrancar, con esta prioridad:
    1. AVACOM_LMS_DIR_LOGS · 2. instalado → %ProgramData%\\AVACOM\\OPS Master\\Logs · 3. desarrollo → backend\\logs ·
    4. pruebas → una carpeta temporal por corrida (jamás ProgramData)."""
    env = os.environ if env is None else env
    propia = (env.get("AVACOM_LMS_DIR_LOGS") or "").strip()
    if propia:
        return Path(propia)
    cual = entorno(env, argv)
    if cual == ENTORNO_PRUEBAS:
        marca = (ahora or dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
        return Path(env.get("TEMP") or env.get("TMP") or tempfile.gettempdir()) / "avacom-lms-pruebas" / f"{marca}-{os.getpid()}"
    if cual == ENTORNO_INSTALADO:
        program_data = env.get("ProgramData") or env.get("PROGRAMDATA") or r"C:\ProgramData"
        return Path(program_data) / "AVACOM" / "OPS Master" / "Logs"
    return Path(base_dir) / "logs"


def carpeta_de_respaldo(env=None) -> Path:
    """Si la carpeta elegida no se puede escribir (permisos, disco) se cae a %TEMP%\\avacom-lms\\logs (§2.3.4)."""
    env = os.environ if env is None else env
    return Path(env.get("TEMP") or env.get("TMP") or tempfile.gettempdir()) / "avacom-lms" / "logs"


def preparar_carpeta(carpeta: Path, env=None) -> tuple[Path, str | None]:
    """Crea la carpeta y comprueba que se puede escribir. Devuelve (carpeta efectiva, aviso o None)."""
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / ".escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink(missing_ok=True)
        return carpeta, None
    except OSError as error:
        respaldo = carpeta_de_respaldo(env)
        try:
            respaldo.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return respaldo, f"No se pudo escribir en {carpeta} ({error.__class__.__name__}: {error}); los logs van a {respaldo}."


# ---------------------------------------------------------------------------- saneamiento

def _prohibida(clave: str) -> bool:
    baja = str(clave).lower()
    if baja in CLAVES_PERMITIDAS:
        return False
    return any(p in baja for p in CLAVES_PROHIBIDAS)


def sanear(valor, profundidad: int = 0):
    """Descarta (redacta) toda clave prohibida en cualquier nivel de un dict; recorta lo demasiado hondo."""
    if profundidad > 6:
        return REDACTADO
    if isinstance(valor, dict):
        return {str(k): (REDACTADO if _prohibida(k) else sanear(v, profundidad + 1)) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set, frozenset)):
        return [sanear(v, profundidad + 1) for v in valor]
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)


# ------------------------------------------------------------------------------- formato

class FiltroContexto(logging.Filter):
    """Agrega a cada registro lo que viene del contexto de la operación (§2.5): corr, caso, dispositivo, usuario."""

    def __init__(self, app: str = "backend"):
        super().__init__()
        self.app = app

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = contexto.actual()
        for nombre, valor in (("corr", ctx.corr), ("caso", ctx.caso), ("dispositivo_id", ctx.dispositivo_id),
                              ("usuario_id", ctx.usuario_id), ("origen", ctx.origen)):
            if not hasattr(record, nombre) or getattr(record, nombre) is None:
                setattr(record, nombre, valor)
        if not getattr(record, "app", None):
            record.app = self.app
        if not getattr(record, "canal", None):
            record.canal = canal_por_defecto(record)
        return True


def canal_por_defecto(record: logging.LogRecord) -> str:
    nombre = record.name
    if nombre.startswith(LOGGER_AUDITORIA):
        return CANAL_AUDITORIA
    if nombre.startswith(LOGGER_INSTALACION):
        return CANAL_INSTALACION
    if nombre.startswith("django.db") or nombre.startswith("avacom.escritura"):
        return CANAL_ESCRITURA
    if nombre.startswith("django.request") or nombre.startswith("django.server") or nombre.startswith("django.channels") \
            or nombre.startswith("daphne") or "websocket" in nombre or nombre.startswith("avacom.comunicacion"):
        return CANAL_COMUNICACION
    return CANAL_APLICACION


def modulo_de(nombre_logger: str) -> str:
    partes = nombre_logger.split(".")
    if partes[0] != LOGGER_RAIZ or len(partes) < 2:
        return partes[0]
    return _MODULO_POR_LOGGER.get(partes[1], partes[1])


class FormateadorJson(logging.Formatter):
    """Una línea JSON por registro, con los campos mínimos de §2.1 y claves ordenadas de forma estable."""

    def format(self, record: logging.LogRecord) -> str:
        ts = dt.datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds")
        detalle = getattr(record, "detalle", None)
        traza = None
        if record.exc_info and record.exc_info[0] is not None:
            traza = "".join(traceback.format_exception(*record.exc_info))
        elif getattr(record, "exc_text", None):
            traza = record.exc_text
        try:
            mensaje = record.getMessage()
        except Exception:   # noqa: BLE001 — un mensaje mal formateado no puede tumbar el log
            mensaje = str(record.msg)
        linea = {
            "ts": ts,
            "nivel": record.levelname,
            "canal": getattr(record, "canal", None) or canal_por_defecto(record),
            "app": getattr(record, "app", None) or "backend",
            "modulo": getattr(record, "modulo", None) or modulo_de(record.name),
            "evento": getattr(record, "evento", None),
            "ruta": getattr(record, "ruta", None),
            "caso": getattr(record, "caso", None),
            "dispositivo_id": getattr(record, "dispositivo_id", None),
            "usuario_id": getattr(record, "usuario_id", None),
            "corr": getattr(record, "corr", None),
            "secuencia_bitacora": getattr(record, "secuencia_bitacora", None),
            "mensaje": sanear_texto(mensaje),
            "detalle": sanear(detalle) if detalle is not None else None,
            "traza": traza,
            "logger": record.name,
        }
        try:
            return json.dumps(linea, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            linea["detalle"] = REDACTADO
            return json.dumps(linea, ensure_ascii=False, default=str)


def sanear_texto(texto: str) -> str:
    """El mensaje es texto libre: sólo se recorta. Lo estructurado va en `detalle`, que sí se sanea por clave."""
    return texto if len(texto) <= 2000 else texto[:2000] + "…"


class HandlerRotativo(logging.handlers.RotatingFileHandler):
    """Rotación por tamaño que jamás eleva una excepción al llamador (§2.5): un disco lleno no tumba el nodo."""

    def __init__(self, filename, **kwargs):
        kwargs.setdefault("maxBytes", TAMANO_MAXIMO)
        kwargs.setdefault("backupCount", COPIAS)
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("delay", True)
        super().__init__(filename, **kwargs)

    def handleError(self, record) -> None:   # noqa: N802 — nombre de logging
        pass


# --------------------------------------------------------------------------- configuración

def configurar(carpeta: Path, app: str = "backend", cual_entorno: str = ENTORNO_DESARROLLO, nivel: str = "INFO",
               corrida: str | None = None) -> dict:
    """El `dictConfig` de settings.LOGGING. Un handler rotativo por canal, formato JSON propio (sin dependencias
    nuevas) y el filtro de contexto en todos."""
    carpeta = Path(carpeta)

    def archivo(nombre: str, nivel_h: str = "DEBUG") -> dict:
        return {"()": "audit.logging_setup.HandlerRotativo", "filename": str(carpeta / nombre), "level": nivel_h,
                "formatter": "json", "filters": ["contexto"]}

    handlers = {
        "app": archivo(f"{app}-app.log"),
        "errores": archivo(f"{app}-errores.log", "WARNING"),
        "auditoria": archivo(f"{app}-auditoria.log"),
        "clientes": archivo(f"{app}-clientes.log"),
        "instalacion": archivo("instalacion.log"),
    }
    en_pruebas = cual_entorno == ENTORNO_PRUEBAS
    extra_pruebas: list[str] = []
    if en_pruebas:
        handlers["pruebas"] = archivo(f"pruebas-{corrida or 'corrida'}.log")
        extra_pruebas = ["pruebas"]
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"contexto": {"()": "audit.logging_setup.FiltroContexto", "app": app}},
        "formatters": {"json": {"()": "audit.logging_setup.FormateadorJson"}},
        "handlers": handlers,
        "loggers": {
            LOGGER_RAIZ: {"handlers": ["app", "errores", *extra_pruebas], "level": "DEBUG" if en_pruebas else nivel, "propagate": False},
            LOGGER_AUDITORIA: {"handlers": ["auditoria", "errores", *extra_pruebas], "level": "DEBUG", "propagate": False},
            LOGGER_CLIENTES: {"handlers": ["clientes", "errores", *extra_pruebas], "level": "DEBUG", "propagate": False},
            LOGGER_INSTALACION: {"handlers": ["instalacion", "errores", *extra_pruebas], "level": "DEBUG", "propagate": False},
            # Lo que Django y Channels avisan (WARNING+) también queda en errores; su consola sigue como venía.
            "django": {"handlers": ["errores", *extra_pruebas], "level": "INFO", "propagate": True},
            "django.request": {"handlers": ["errores", *extra_pruebas], "level": "WARNING", "propagate": True},
            "daphne": {"handlers": ["errores", *extra_pruebas], "level": "WARNING", "propagate": True},
        },
    }


def ruta_por_estado(status: int, excepcion: bool = False) -> str:
    """2xx/3xx → happy · 4xx previsto → sad · excepción o 5xx → bad (§2.1)."""
    if excepcion or status >= 500:
        return RUTA_BAD
    if status >= 400:
        return RUTA_SAD
    return RUTA_HAPPY


def logger_app() -> logging.Logger:
    return logging.getLogger(LOGGER_APP)


def logger_auditoria() -> logging.Logger:
    return logging.getLogger(LOGGER_AUDITORIA)


def logger_clientes() -> logging.Logger:
    return logging.getLogger(LOGGER_CLIENTES)


def logger_instalacion() -> logging.Logger:
    return logging.getLogger(LOGGER_INSTALACION)

