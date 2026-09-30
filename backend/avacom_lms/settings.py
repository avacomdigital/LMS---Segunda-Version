"""
Backend de AVACOM LMS (AVACOM OPS Master + AVACOM Student).

Este backend NO administra cursos. Los cursos viven en AVACOM Biblioteca y se
consultan en vivo por loopback. Aquí sólo se guarda el expediente del estudiante:
inscripción, aperturas del visor, progreso por sección, intentos y notas.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

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
]

MIDDLEWARE = [
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
# App `classroom_engine`. La fuente de cursos por defecto es la biblioteca; el
# manifiesto de ejemplo (spec-driven/02-classroom-engine/example.json) alimenta el
# endpoint de prueba mientras la biblioteca publica el esquema de curso 1.0.
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
