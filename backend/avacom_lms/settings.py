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
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "acceso",
    "device_manager",
    "biblioteca",
    "expediente",
    "classroom_engine",
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
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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
