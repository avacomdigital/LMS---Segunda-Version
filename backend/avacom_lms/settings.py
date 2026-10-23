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
    # `manage.py test` NO lo lee: las pruebas fijan su propia configuración (con la sesión obligatoria del .env de desarrollo, el `setUp` de todas
    # las de API fallaba al instalar el nodo) y no deben depender de la base ni de las claves de quien las corre.
    if "test" in sys.argv[1:2] or not ruta.is_file():
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
    "cola_medios",
    "audit",
    "gradebook",
    "search",
    "reporting",
    "licenciamiento",
    "nodo",
    "actualizacion",
]

MIDDLEWARE = [
    # MOD-019: `corr` por petición (X-Avacom-Correlacion), aparato validado (X-Avacom-Dispositivo), línea por petición
    # en backend-app.log y asiento de denegación en todo 403. Va primero para envolver a todo lo demás.
    "audit.middleware.CorrelacionMiddleware",
    # Bugfix 01 (QA-27): las direcciones `/api/m/<pase>/…` de los medios llevan su permiso en el camino (el visor no manda cabeceras). Reescribe la ruta
    # a la normal ANTES de `CommonMiddleware`, y por dentro de la auditoría, que registra ya la ruta sin el pase.
    "acceso.interfaces.medios.PaseDeMediosMiddleware",
    # MOD-018: el ÚNICO sitio donde una licencia puede responder «no disponible por licencia» (402). Va DESPUÉS del pase de medios (ve ya la ruta normal) y por dentro de la
    # auditoría; lee el estado de memoria, deja pasar ante cualquier fallo y nunca toca lo intocable (aula, evaluación en curso, modo estudio, login, latido, /health/).
    "licenciamiento.interfaces.middleware.LicenciaMiddleware",
    # MOD-017: el ÚNICO sitio donde una actualización responde «el aula se está actualizando» (503 `actualizacion_en_curso`, nunca un 4xx): SÓLO el inicio de una clase
    # (`POST /api/aula/sesiones/`) y SÓLO desde que el nodo acepta una orden hasta que el Host devuelve su resultado (P-08, R-01, R-02). Lee memoria y deja pasar ante cualquier fallo.
    "actualizacion.interfaces.middleware.ActualizacionMiddleware",
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

# --------------------------------------------------------- Caché en memoria (cola de medios)
# `LocMemCache`: el nodo es UN proceso, así que una caché por proceso basta. La usa la cola de medios (alias `medios`) para el índice caliente de recursos,
# los medios pequeños y la versión vigente de cada curso. Los medios grandes no pasan por aquí: viven en disco (AVACOM_COLA_DIR).
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "avacom-default"},
    "medios": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "avacom-medios", "OPTIONS": {"MAX_ENTRIES": 2000, "CULL_FREQUENCY": 4}},
}

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

REST_FRAMEWORK = {
    # El módulo `acceso` aporta la autenticación JWT. Sin cabecera Authorization el
    # portador es anónimo, así que las rutas del expediente siguen abiertas (Q-04)
    # hasta que AVACOM_LMS_EXIGIR_SESION=1 las cierre (Q-34).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "acceso.interfaces.medios.AutenticacionPaseDeMedios",   # sólo opina si el middleware resolvió un pase de medios
        "acceso.interfaces.autenticacion.AutenticacionJwt",
    ],
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
# Segundos que el nodo reutiliza una sesión de medios de Contenido por (curso, medio) en vez de abrir una por cada trozo (`Range`) que
# pide un reproductor: con 35 tabletas ahorra un `POST /v2/media-sessions` (~45 ms) por trozo. 0 = una sesión por petición (como antes).
AVACOM_CONTENIDO_SESION_MEDIOS_SEG = int(os.environ.get("AVACOM_CONTENIDO_SESION_MEDIOS_SEG", str(15 * 60)))
# Segundos que el nodo recuerda la persona de un pase de medios en vez de comprobar la sesión entera (8 consultas) en CADA imagen, audio o trozo de video.
# Cerrar la sesión, cambiar la clave o mover a la persona lo vacía al instante; el tiempo sólo cubre la caducidad y la inactividad. 0 = comprobar siempre.
AVACOM_PASE_MEDIOS_CACHE_SEG = int(os.environ.get("AVACOM_PASE_MEDIOS_CACHE_SEG", "15"))

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

# ------------------------------------------------------------- Search (MOD-021)
# App `search` (`/api/search/`, tablas m21_*). El índice local (SQLite FTS5) de evaluaciones, estudios asignados y clases se mantiene con los eventos de sus módulos; el
# catálogo de cursos se pregunta en vivo a la biblioteca (artículo 14). "0" desactiva el hilo que lo pone al día cada AVACOM_SEARCH_INTERVALO_S segundos.
AVACOM_SEARCH_PROGRAMADOR = os.environ.get("AVACOM_SEARCH_PROGRAMADOR", "1") == "1"
AVACOM_SEARCH_INTERVALO_S = float(os.environ.get("AVACOM_SEARCH_INTERVALO_S", "5"))

# App `reporting` (`/api/reportes/`, tablas m13_*): reportes de clase, alumno, grupo y uso de equipos sobre lo que otros módulos ya calcularon, y su exportación a archivo.
# El hilo del nodo (FUN-144) actualiza los agregados SÓLO cuando no hay una clase abierta; "0" lo desactiva. AVACOM_REPORTES_INTERVALO_S es cada cuánto mira (por omisión 60 s).
# AVACOM_REPORTES_EXPORTACION_TTL_S: cuánto espera el nodo a que el equipo confirme dónde guardó un archivo antes de darla por no entregada (por omisión 900 s).
AVACOM_REPORTES_PROGRAMADOR = os.environ.get("AVACOM_REPORTES_PROGRAMADOR", "1") == "1"
AVACOM_REPORTES_INTERVALO_S = float(os.environ.get("AVACOM_REPORTES_INTERVALO_S", "60"))
AVACOM_REPORTES_EXPORTACION_TTL_S = int(os.environ.get("AVACOM_REPORTES_EXPORTACION_TTL_S", "900"))
AVACOM_REPORTES_SINCRONIZAR = os.environ.get("AVACOM_REPORTES_SINCRONIZAR", "1") == "1"

# ---------------------------------------------------------- Licensing (MOD-018)
# App `licenciamiento` (`/api/licencia/`, tablas m18_*): valida sin internet qué puede hacer esta instalación y hasta cuándo. NUNCA detiene una clase.
# El ENTORNO NO sale de `AVACOM_LMS_ENTORNO` (se lee de backend.env, un texto editable): un nodo es de producción si existe el marcador de canal `.avacom-canal` que escribe el instalador, si
# corre bajo `Program Files` o si `AVACOM_LMS_ENTORNO=instalado`; sólo un repositorio de desarrollo (con `.git` y sin marcador) es desarrollo, y `manage.py test` es pruebas (P-12).
from licenciamiento.dominio import entorno as _licencia_entorno  # noqa: E402 — puro: no importa Django

AVACOM_LICENCIA_ENTORNO = _licencia_entorno.clasificar(BASE_DIR, os.environ, sys.argv)
# "firmada" fuerza en desarrollo y pruebas la verificación real de licencias (en producción es SIEMPRE firmada, sea lo que sea esta variable); "auto" = sin licencia en desarrollo y pruebas.
AVACOM_LICENCIA_MODO = os.environ.get("AVACOM_LICENCIA_MODO", "auto")
# Carpeta de estado de la licencia SÓLO en desarrollo y pruebas; en producción es siempre %ProgramData%\AVACOM\OPS Master\Config\licencia\ (esta variable se ignora).
AVACOM_LICENCIA_DIR = os.environ.get("AVACOM_LICENCIA_DIR", "")
# "0" desactiva el hilo que valida al arrancar y recalcula el estado (por omisión cada 300 s).
# Fase 5 (P-24): garantía mínima de identidad para dar de alta un equipo NUEVO en un nodo de producción: declarada (ninguna: lo de siempre) · software · hardware. Lo registrado no se toca.
AVACOM_LICENCIA_IDENTIDAD_MINIMA = os.environ.get("AVACOM_LICENCIA_IDENTIDAD_MINIMA", "declarada")
AVACOM_LICENCIA_PROGRAMADOR = os.environ.get("AVACOM_LICENCIA_PROGRAMADOR", "1") == "1"
AVACOM_LICENCIA_INTERVALO_S = float(os.environ.get("AVACOM_LICENCIA_INTERVALO_S", "300"))

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

# ------------------------------------------------ Node Platform y Cola de Salida (MOD-015)
# App `nodo` (`/api/nodo/`, tablas m15_*): la cola única con secuencia global (`m15_evento`), el registro de consumidores con sus marcas, la cola de problemas, el corte de cada
# módulo y el estado del nodo. NUNCA detiene una clase (R-01).
# AVACOM_NODO_DIR: carpeta de las anclas de la secuencia y del reloj (fuera de la base) SÓLO en desarrollo (por defecto %TEMP%\avacom-nodo-dev); en pruebas cada corrida usa una
# temporal y en producción es siempre %ProgramData%\AVACOM\OPS Master\Config\nodo\ (esta variable se ignora).
AVACOM_NODO_DIR = os.environ.get("AVACOM_NODO_DIR", "")
# Estricto (pruebas y desarrollo): un tipo fuera del catálogo o una carga con datos que no pueden viajar FALLAN. En un nodo instalado el hecho no se pierde: el evento entra marcado
# (`catalogado=0` / `carga_omitida=1`), se registra con ERROR y queda un asiento (R-06).
AVACOM_NODO_ESTRICTO = os.environ.get("AVACOM_NODO_ESTRICTO", "0" if AVACOM_LMS_ENTORNO == "instalado" else "1") == "1"
# La purga (BR-017…019) está construida y APAGADA: sin MOD-016 ningún evento está en un respaldo verificado, así que nada sería elegible. "1" enciende la rutina (que seguirá sin
# borrar hasta que el respaldo exista).
AVACOM_NODO_PURGA = os.environ.get("AVACOM_NODO_PURGA", "0") == "1"
# Publicar los eventos técnicos nodo.* agregados por lote y consumidor (marca avanzada, reintento, apartado, reproceso, salud al cambiar). "0" los apaga (Q-N6).
AVACOM_NODO_EVENTOS_TECNICOS = os.environ.get("AVACOM_NODO_EVENTOS_TECNICOS", "1") == "1"
# Consumidores: tamaño del lote, intentos antes de apartar un evento, espera base y tope de la espera creciente (ms), rezago a partir del cual un consumidor se declara suspendido.
AVACOM_NODO_LOTE = int(os.environ.get("AVACOM_NODO_LOTE", "200"))
AVACOM_NODO_MAX_INTENTOS = int(os.environ.get("AVACOM_NODO_MAX_INTENTOS", "5"))
AVACOM_NODO_ESPERA_BASE_MS = int(os.environ.get("AVACOM_NODO_ESPERA_BASE_MS", "1000"))
AVACOM_NODO_ESPERA_TOPE_MS = int(os.environ.get("AVACOM_NODO_ESPERA_TOPE_MS", "60000"))
AVACOM_NODO_REZAGO_LIMITE = int(os.environ.get("AVACOM_NODO_REZAGO_LIMITE", "10000"))
# Retención: la mínima de BR-017 (7 días) y cuánto dura un ciclo (Q-N4: «5 ciclos» de la clase aprendizaje; MOD-002 no existe).
AVACOM_NODO_RETENCION_MIN_DIAS = int(os.environ.get("AVACOM_NODO_RETENCION_MIN_DIAS", "7"))
AVACOM_NODO_CICLO_MESES = int(os.environ.get("AVACOM_NODO_CICLO_MESES", "12"))
# Umbrales del modo restringido (Q-N1, propuesta): disco libre mínimo (GB y %), tamaño del WAL sin volcar (MB).
AVACOM_NODO_DISCO_MIN_GB = float(os.environ.get("AVACOM_NODO_DISCO_MIN_GB", "2"))
AVACOM_NODO_DISCO_MIN_PCT = float(os.environ.get("AVACOM_NODO_DISCO_MIN_PCT", "5"))
AVACOM_NODO_WAL_MAX_MB = float(os.environ.get("AVACOM_NODO_WAL_MAX_MB", "512"))

# ---------------------------------------------------------- Actualizaciones (MOD-017 · Update Manager)
# App `actualizacion` (`/api/actualizacion/`, tablas m17_*). Verifica paquetes `.avupd` firmados (Ed25519), decide y deja la ORDEN al Host (que es quien aplica, con el backend parado).
# AVACOM_ACTUALIZACION_DIR: la carpeta de paquetes, staging, orden y resultado SÓLO en desarrollo y pruebas (por defecto una temporal); en producción es siempre
# %ProgramData%\AVACOM\OPS Master\Actualizaciones. AVACOM_ACTUALIZACION_UNIDADES: carpetas (separadas por `;`) que hacen de unidad extraíble en desarrollo y pruebas (una
# carpeta montada con `subst` también sirve); en producción las unidades son las reales. AVACOM_ACTUALIZACION_CANAL: el canal por internet (P-18), apagado de fábrica (vacío).
AVACOM_ACTUALIZACION_DIR = os.environ.get("AVACOM_ACTUALIZACION_DIR", "")
AVACOM_ACTUALIZACION_UNIDADES = os.environ.get("AVACOM_ACTUALIZACION_UNIDADES", "")
AVACOM_ACTUALIZACION_CANAL = os.environ.get("AVACOM_ACTUALIZACION_CANAL", "")
# El vigilante del proceso ASGI (lee el resultado del Host al arrancar, abre ventanas, archiva a los 14 días, anuncia paquetes nuevos) y su cadencia en segundos.
AVACOM_ACTUALIZACION_VIGILANTE = os.environ.get("AVACOM_ACTUALIZACION_VIGILANTE", "1") == "1"
AVACOM_ACTUALIZACION_INTERVALO_S = float(os.environ.get("AVACOM_ACTUALIZACION_INTERVALO_S", "30"))
# Tope del paquete en MB (nunca por encima de los 512 del dominio).
AVACOM_ACTUALIZACION_MAX_MB = int(os.environ.get("AVACOM_ACTUALIZACION_MAX_MB", "512"))

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
# RF-004: política institucional de publicación de resultados para una asignación nueva cuando el profesor no elige otra:
# `tras_liberar` (manual, el valor seguro) · `al_entregar` (inmediata) · `al_finalizar_grupo` · `nunca`. (`programada` exige fecha: no sirve de defecto.)
AVACOM_EVAL_RESULTADOS_POR_DEFECTO = os.environ.get("AVACOM_EVAL_RESULTADOS_POR_DEFECTO", "tras_liberar")

# ---------------------------------------------------------------- Cola de medios
# App `cola_medios` (`/api/medios/cola/`, tablas cm_*). Reparte los bytes de video, audio, imagen, PDF y html que vienen de AVACOM Contenido a las tabletas:
# los trae UNA vez a una caché de disco con su SHA-256, regula cuántos y a qué ritmo, y los sirve con `Range` a las tres rutas de medios del aula, del modo
# estudio y de la evaluación. Ver spec-driven/11-cola-de-medios.md.
_EN_PRUEBAS = "test" in sys.argv[1:2]
# "0" apaga la cola: todos los medios vuelven al paso a través de siempre.
AVACOM_COLA_ACTIVA = os.environ.get("AVACOM_COLA_ACTIVA", "1") == "1"
# Dónde viven los bytes. Desarrollo: backend/cache_medios. Instalado: %ProgramData%\AVACOM\OPS Master\CacheMedios (lo fija el instalador). Pruebas: temporal.
AVACOM_COLA_DIR = os.environ.get("AVACOM_COLA_DIR") or ("" if _EN_PRUEBAS else str(BASE_DIR / "cache_medios"))
AVACOM_COLA_MAX_MB = int(os.environ.get("AVACOM_COLA_MAX_MB", "4096"))                 # tope de la caché en disco
AVACOM_COLA_LIBRE_MIN_MB = int(os.environ.get("AVACOM_COLA_LIBRE_MIN_MB", "1024"))     # espacio que debe quedar libre en el disco
# Descargas simultáneas desde la fuente (hilos). 0 = sin hilos: la descarga se hace dentro de la propia petición (así corren las pruebas).
AVACOM_COLA_DESCARGAS = int(os.environ.get("AVACOM_COLA_DESCARGAS", "0" if _EN_PRUEBAS else "3"))
AVACOM_COLA_TRANSFERENCIAS = int(os.environ.get("AVACOM_COLA_TRANSFERENCIAS", "24"))   # transferencias simultáneas hacia las tabletas
AVACOM_COLA_ANCHO_ENTRADA_KBPS = int(os.environ.get("AVACOM_COLA_ANCHO_ENTRADA_KBPS", "0"))   # tope global fuente → nodo; 0 = sin tope
AVACOM_COLA_ANCHO_SALIDA_KBPS = int(os.environ.get("AVACOM_COLA_ANCHO_SALIDA_KBPS", "0"))     # tope global nodo → tabletas; 0 = sin tope
AVACOM_COLA_REVALIDAR_SEG = int(os.environ.get("AVACOM_COLA_REVALIDAR_SEG", "60"))     # cada cuánto se pregunta a la biblioteca si el curso sigue y en qué versión
AVACOM_COLA_ESPERA_INICIO_SEG = float(os.environ.get("AVACOM_COLA_ESPERA_INICIO_SEG", "6"))   # menos que la paciencia de los clientes (audio 10 s, imagen 10 s)
AVACOM_COLA_ESPERA_PAQUETE_SEG = float(os.environ.get("AVACOM_COLA_ESPERA_PAQUETE_SEG", "120"))
AVACOM_COLA_ESPERA_CUPO_SEG = float(os.environ.get("AVACOM_COLA_ESPERA_CUPO_SEG", "20"))
AVACOM_COLA_REINTENTOS = int(os.environ.get("AVACOM_COLA_REINTENTOS", "3"))
AVACOM_COLA_SERVIR_SIN_BIBLIOTECA = os.environ.get("AVACOM_COLA_SERVIR_SIN_BIBLIOTECA", "0") == "1"
