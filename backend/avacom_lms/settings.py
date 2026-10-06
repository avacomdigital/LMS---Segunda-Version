"""
Backend de AVACOM LMS (AVACOM OPS Master + AVACOM Student).

Este backend NO administra cursos. Los cursos viven en AVACOM Biblioteca y se
consultan en vivo por loopback. Aquí sólo se guarda el expediente del estudiante:
inscripción, aperturas del visor, progreso por sección, intentos y notas.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env_de_desarrollo() -> None:
    """Lee `backend/.env` (clave=valor por línea) para el desarrollo local. NUNCA pisa una variable que ya venga del entorno: en el equipo instalado la
    configuración llega desde backend.env por el servicio, y este archivo (que no se versiona: está en .gitignore) no existe."""
    ruta = BASE_DIR / ".env"
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env_de_desarrollo()

SECRET_KEY = os.environ.get("AVACOM_LMS_SECRET", "prototipo-aula-sin-internet-no-es-secreto")
DEBUG = os.environ.get("AVACOM_LMS_DEBUG", "1") == "1"

# El aula es una LAN cerrada: las tabletas llegan por la IP del equipo maestro.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    # `daphne` va primero: sustituye a `runserver` por un servidor ASGI que también atiende WebSocket
    # (tiempo real del aula, `classroom_engine/interfaces/websockets.py`).
    "daphne",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "channels",
    "acceso",
    "device_manager",
    "biblioteca",
    "expediente",
    "classroom_engine",
    "modo_estudio",
    "evaluacion",
    "audit",
]

MIDDLEWARE = [
    # MOD-019: `corr` por petición (X-Avacom-Correlacion), aparato validado (X-Avacom-Dispositivo), línea por petición
    # en backend-app.log y asiento de denegación en todo 403. Va primero para envolver a todo lo demás.
    "audit.middleware.CorrelacionMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "avacom_lms.urls"
WSGI_APPLICATION = "avacom_lms.wsgi.application"
ASGI_APPLICATION = "avacom_lms.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("AVACOM_LMS_DB", str(BASE_DIR / "db.sqlite3")),
        # Con el tiempo real hay varios hilos escribiendo a la vez (vistas, sockets y programador). Sin esto SQLite
        # responde «database is locked» al instante cuando una transacción que leyó intenta escribir mientras otra
        # confirmó: WAL deja leer mientras se escribe y BEGIN IMMEDIATE toma el turno de escritura al empezar, de modo
        # que los escritores hacen fila (hasta `timeout` segundos) en lugar de fallar.
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL;",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------- Tiempo real (Channels)
# El nodo del aula es UN solo proceso en una LAN cerrada y sin internet: la capa de canales en memoria basta
# y no exige Redis. Si algún día el nodo corre en varios procesos, aquí se cambia por `channels_redis`.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

REST_FRAMEWORK = {
    # El módulo `acceso` aporta la autenticación JWT. Sin cabecera Authorization el
    # portador es anónimo, así que las rutas del expediente siguen abiertas (Q-04)
    # hasta que AVACOM_LMS_EXIGIR_SESION=1 las cierre (Q-34).
    "DEFAULT_AUTHENTICATION_CLASSES": ["acceso.interfaces.autenticacion.AutenticacionJwt"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}

# -------------------------------------------------------------------- Acceso
# Claves del módulo de acceso (32 bytes en base64). Las entrega el instalador en
# backend.env. Si faltan, se derivan con HKDF de SECRET_KEY y /health/ lo avisa.
AVACOM_LMS_CLAVE_DATOS = os.environ.get("AVACOM_LMS_CLAVE_DATOS") or None     # AES-256-GCM (PII)
AVACOM_LMS_CLAVE_INDICE = os.environ.get("AVACOM_LMS_CLAVE_INDICE") or None   # HMAC-SHA-256 (índice ciego)
AVACOM_LMS_CLAVE_TOKENS = os.environ.get("AVACOM_LMS_CLAVE_TOKENS") or None   # JWT HS256
# Argon2id: por encima del mínimo OWASP (m=19 MiB, t=2, p=1). Las pruebas lo bajan.
AVACOM_LMS_ARGON2 = {"time_cost": 3, "memory_cost": 65536, "parallelism": 1}
# Q-34: con "1" las rutas del expediente y la biblioteca exigen sesión.
AVACOM_LMS_EXIGIR_SESION = os.environ.get("AVACOM_LMS_EXIGIR_SESION", "0") == "1"

# ---------------------------------------------------------------- Biblioteca
# Ruta forzada de la nota de enlace. Permite probar la integración con un host
# de pruebas sin instalar la biblioteca (ver tools/host_biblioteca_pruebas.py).
AVACOM_CONTENIDO_ENLACE = os.environ.get("AVACOM_CONTENIDO_ENLACE") or None
# Ruta forzada de `link.json`, la nota de enlace de la API de Contenido v2 (apiPort +
# token). Por defecto vive junto a enlace.json; el host de pruebas v2 la escribe donde
# se le pida (ver tools/host_contenido_v2_pruebas.py).
AVACOM_CONTENIDO_ENLACE_V2 = os.environ.get("AVACOM_CONTENIDO_ENLACE_V2") or None
# Tiempo de espera hacia la biblioteca. Es loopback: si no contesta en tres
# segundos, no va a contestar, y esperar más congela la pantalla del profesor.
AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG = float(os.environ.get("AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG", "3"))

# ---------------------------------------------------- Classroom Engine (MOD-007)
# App `classroom_engine`. Los cursos salen SIEMPRE de la biblioteca (AVACOM Contenido, API v2). El manifiesto de
# ejemplo (spec-driven/02-classroom-engine/example.json) sólo existe para las pruebas y el desarrollo: está
# APAGADO salvo que se pida con AVACOM_AULA_PERMITIR_EJEMPLO=1 (o se corra `manage.py test`). Apagado, cualquier
# petición de la fuente «ejemplo» —de un cliente viejo, de una preferencia guardada o de una variable de entorno—
# se resuelve con la biblioteca. El instalador no lo enciende y el ejemplo ni siquiera viaja en él.
AVACOM_AULA_PERMITIR_EJEMPLO = os.environ.get("AVACOM_AULA_PERMITIR_EJEMPLO") == "1" or "test" in sys.argv[1:2]
AVACOM_AULA_FUENTE_CURSOS = os.environ.get("AVACOM_AULA_FUENTE_CURSOS", "biblioteca")
AVACOM_AULA_CURSO_EJEMPLO = os.environ.get("AVACOM_AULA_CURSO_EJEMPLO") or str(
    BASE_DIR.parent / "spec-driven" / "02-classroom-engine" / "example.json"
)

# ------------------------------------------------- Tiempo real y programador del aula
# Un participante «conectado» que no manda latido en este tiempo pasa a «reconectando» (FUN-073).
AVACOM_AULA_LATIDO_VENCIDO_MS = int(os.environ.get("AVACOM_AULA_LATIDO_VENCIDO_MS", "15000"))
# Sin latido en este tiempo, un «reconectando» pasa a «salió» (deja de contar como admitido).
AVACOM_AULA_AUSENCIA_MS = int(os.environ.get("AVACOM_AULA_AUSENCIA_MS", str(5 * 60 * 1000)))
# Una clase abierta sin ninguna actividad durante este tiempo se cierra sola (JRN-011: 120 min, no 20).
AVACOM_AULA_INACTIVIDAD_MS = int(os.environ.get("AVACOM_AULA_INACTIVIDAD_MS", str(120 * 60 * 1000)))
# Capacidad del nodo (BR-063): 50 dispositivos en operación normal y 100 en pico. Al llegar al pico
# se rechazan las conexiones NUEVAS sin degradar a las conectadas. La licencia (MOD-018) los fijará.
AVACOM_AULA_DISPOSITIVOS_NORMAL = int(os.environ.get("AVACOM_AULA_DISPOSITIVOS_NORMAL", "50"))
AVACOM_AULA_DISPOSITIVOS_PICO = int(os.environ.get("AVACOM_AULA_DISPOSITIVOS_PICO", "100"))
# `unirse` con código equivocado: intentos permitidos por tableta (o dirección) en la ventana.
AVACOM_AULA_UNIRSE_INTENTOS = int(os.environ.get("AVACOM_AULA_UNIRSE_INTENTOS", "8"))
AVACOM_AULA_UNIRSE_VENTANA_MS = int(os.environ.get("AVACOM_AULA_UNIRSE_VENTANA_MS", "60000"))
# "0" desactiva el programador (presencia por latido, cierre por inactividad, archivado y detección de caída).
AVACOM_AULA_PROGRAMADOR = os.environ.get("AVACOM_AULA_PROGRAMADOR", "1") == "1"
# "0" desactiva la suspensión de las clases abiertas al arrancar el nodo (BR-051).
AVACOM_AULA_DETECTAR_CAIDA = os.environ.get("AVACOM_AULA_DETECTAR_CAIDA", "1") == "1"

# ------------------------------------------------------------- Audit (MOD-019)
# App `audit` (`/api/auditoria/`, `/api/logs/`, tablas m19_*). Sistema de logs en archivos JSON Lines (§2 del prompt):
# la carpeta se decide UNA vez al arrancar (AVACOM_LMS_DIR_LOGS → instalado: %ProgramData%\AVACOM\OPS Master\Logs →
# desarrollo: backend\logs → pruebas: carpeta temporal por corrida, jamás ProgramData).
from audit import logging_setup as _logs  # noqa: E402 — puro: no importa Django ni modelos

AVACOM_LMS_ENTORNO = _logs.entorno()
_carpeta_logs, AVACOM_LMS_AVISO_LOGS = _logs.preparar_carpeta(_logs.carpeta_logs(BASE_DIR))
AVACOM_LMS_DIR_LOGS_EFECTIVO = str(_carpeta_logs)
LOGGING = _logs.configurar(_carpeta_logs, app="backend", cual_entorno=AVACOM_LMS_ENTORNO,
                           nivel=os.environ.get("AVACOM_LMS_NIVEL_LOG", "INFO"), corrida=_carpeta_logs.name)
TEST_RUNNER = "audit.pruebas.CorredorDePruebas"
# Umbral de rotación de la bitácora por tamaño (FUN-201; §4.3): 100 MB por defecto.
AVACOM_LMS_AUDITORIA_UMBRAL_MB = int(os.environ.get("AVACOM_LMS_AUDITORIA_UMBRAL_MB", "100"))
# Cadencia del verificador de la cadena (segundos): cada hora fuera de clase, y al rotar. "0" lo desactiva.
AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S = int(os.environ.get("AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S", "3600"))
# En pruebas una acción fuera del catálogo falla; en producción se asienta `auditoria.accion_desconocida` (§3.5).
AVACOM_LMS_AUDITORIA_ESTRICTA = os.environ.get("AVACOM_LMS_AUDITORIA_ESTRICTA", "1" if AVACOM_LMS_ENTORNO == "pruebas" else "0") == "1"
# Tope de renglones por entrega y por minuto que acepta POST /api/logs/clientes/ de cada equipo (§4.2).
AVACOM_LMS_LOGS_CLIENTES_MAX_RENGLONES = int(os.environ.get("AVACOM_LMS_LOGS_CLIENTES_MAX_RENGLONES", "200"))
AVACOM_LMS_LOGS_CLIENTES_MAX_POR_MINUTO = int(os.environ.get("AVACOM_LMS_LOGS_CLIENTES_MAX_POR_MINUTO", "1000"))

# ---------------------------------------------------------- Modo Estudio (MOD-008)
# App `modo_estudio` (`/api/modo-estudio/`, tablas m08_*). Lee la lección en vivo por los casos de uso del aula, así que usa la misma
# fuente de cursos (AVACOM_AULA_FUENTE_CURSOS). D-8: cuánto dura en el aparato un paquete de una asignación SIN fecha límite; con
# fecha, dura hasta la fecha límite más la gracia.
AVACOM_ESTUDIO_VIGENCIA_DIAS = int(os.environ.get("AVACOM_ESTUDIO_VIGENCIA_DIAS", "14"))
# DEC-019: minutos de gracia por defecto de una asignación nueva (el profesor puede cambiarlos por asignación).
AVACOM_ESTUDIO_GRACIA_MIN = int(os.environ.get("AVACOM_ESTUDIO_GRACIA_MIN", "15"))
# Tope de tamaño de UN medio al preparar un paquete: el nodo lo lee entero para medirlo y calcular su SHA-256, así que un medio
# mayor se deja fuera del paquete (`no_incluidos`, `medio_demasiado_grande`) en vez de bloquear la petición.
AVACOM_ESTUDIO_MEDIO_MAX_MB = int(os.environ.get("AVACOM_ESTUDIO_MEDIO_MAX_MB", "512"))

# ------------------------------------------------- Evaluation & Delivery Engine (MOD-010)
# App `evaluacion` (`/api/evaluacion/`, tablas m10_*). El examen se lee en vivo de la misma fuente de cursos del aula; aquí sólo se guarda lo que
# el alumno hizo con él. Ver spec-driven/06-evaluation-delivery/backend.md §8.
# Silencio de la tableta tras el cual el intento se pausa y su reloj se congela en el último latido (INV-010: reconexión en 30 s).
AVACOM_EVAL_LATIDO_VENCIDO_MS = int(os.environ.get("AVACOM_EVAL_LATIDO_VENCIDO_MS", "30000"))
# Cadencia de latido que se recomienda a la tableta: el punto de recuperación es de 5 s (INV-010).
AVACOM_EVAL_LATIDO_SEG = int(os.environ.get("AVACOM_EVAL_LATIDO_SEG", "5"))
# DEC-019: minutos de gracia por defecto de una asignación nueva (el profesor puede cambiarlos por asignación).
AVACOM_EVAL_GRACIA_MIN = int(os.environ.get("AVACOM_EVAL_GRACIA_MIN", "15"))
# "0" desactiva el programador (pausa por falta de latido, entrega por tiempo o plazo, activación y archivado).
AVACOM_EVAL_PROGRAMADOR = os.environ.get("AVACOM_EVAL_PROGRAMADOR", "1") == "1"
# "0" no pasa los intentos abiertos a `restaurando` al arrancar el nodo (BR-051).
AVACOM_EVAL_DETECTAR_REINICIO = os.environ.get("AVACOM_EVAL_DETECTAR_REINICIO", "1") == "1"
# Horas que una asignación cerrada espera antes de pasar a `archivada`.
AVACOM_EVAL_ARCHIVADO_H = int(os.environ.get("AVACOM_EVAL_ARCHIVADO_H", "24"))
# Tope de respuestas por envío (lo que sale de la cola local de una tableta).
AVACOM_EVAL_MAX_RESPUESTAS = int(os.environ.get("AVACOM_EVAL_MAX_RESPUESTAS", "200"))
# Desfase del reloj de la tableta a partir del cual se registra el incidente `reloj_desfasado` (INV-017).
AVACOM_EVAL_DESFASE_RELOJ_MS = int(os.environ.get("AVACOM_EVAL_DESFASE_RELOJ_MS", "5000"))
# Combinaciones que prueba el armado `random_balanced` antes de quedarse con la mejor.
AVACOM_EVAL_ARMADO_INTENTOS = int(os.environ.get("AVACOM_EVAL_ARMADO_INTENTOS", "200"))
