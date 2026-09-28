"""
Cliente de la **API de Contenido v2** de AVACOM Biblioteca (app «AVACOM Contenido»,
contrato 2): la que entrega el curso con el esquema 1.0 recortado, califica respuestas y
sirve los medios del paquete por sesiones de medios.

Convive con `cliente.py` (contrato 1, `enlace.json`, `X-Avacom-Ficha`), que sigue
alimentando `/api/biblioteca/*` y el flujo de intentos del expediente. Este módulo es
el ÚNICO sitio del LMS que habla el v2; MOD-007 lo usa a través de
`classroom_engine.infraestructura.fuente_biblioteca`.

Contrato de referencia: `GET /v2/openapi.json` de la propia API (copia en
spec-driven/02-classroom-engine/openapi.v2.json), comprobado en vivo el 2026-09-21.

Reglas del documento «Mapeo de campos · API de Contenido v2» que aquí se cumplen:
  - `link.json` se relee EN CADA petición: `apiPort`, `mediaPort` y `token` cambian en
    cada arranque de la biblioteca y no se guardan entre llamadas.
  - Un 401 reintenta UNA vez tras releer `link.json`; el segundo 401 es error.
  - La ausencia de `link.json` produce «sin contenido» (BibliotecaNoDisponible →
    503 con motivo y sugerencia), no un error.
  - `POST /v2/evaluate` viaja siempre con `version`.
  - Nada se cachea: ni el curso, ni el `token`, ni las sesiones de medios.

Cómo se pide cada cosa (todo con la cabecera `X-Avacom-Token`):
  GET  /v2/health                                  → {contract: 2, schema, index: ready|rebuilding, installedCourses: n}
  GET  /v2/courses?page&pageSize                   → {items[CourseSummary], page, pageSize, total}
  GET  /v2/courses/{id}?mode&profile               → el ESQUEMA del curso: metadatos, lecciones con resúmenes de
                                                     objeto (pageCount, questionCount, mediaId) y la lista de medios
  GET  /v2/courses/{id}/lessons/{lid}?mode&profile → la lección COMPLETA (láminas, páginas, preguntas sin claves)
  GET  /v2/courses/{id}/objects/{oid}?profile&seed → un objeto completo
  POST /v2/media-sessions {courseId, mediaIds|lessonId, ttlSec}
                                                   → {sessionId, baseUrl, expiresAt, urls{mediaId: url}, extras{mediaId:
                                                     {captions, transcript, files}}}; las URL viven en el servidor de
                                                     medios (mediaPort) y no piden token: son capacidades efímeras
  POST /v2/evaluate · /v2/evaluate/batch           → EvaluationResult · {results[]}
  GET  /v2/courses/{id}/questions/{qid}/grading-guide?version
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from .cliente import SUGERENCIA_ABRIR, BibliotecaError, BibliotecaNoDisponible

API = "v2"
CONTRATO = 2
CABECERA_TOKEN = "X-Avacom-Token"

# ------------------------------------------------------------------ rutas
RUTA_SALUD = "/v2/health"
RUTA_CURSOS = "/v2/courses"
RUTA_CURSO = "/v2/courses/{curso}"
RUTA_LECCION = "/v2/courses/{curso}/lessons/{leccion}"
RUTA_OBJETO = "/v2/courses/{curso}/objects/{objeto}"
RUTA_GUIA = "/v2/courses/{curso}/questions/{pregunta}/grading-guide"
RUTA_EVALUAR = "/v2/evaluate"
RUTA_EVALUAR_LOTE = "/v2/evaluate/batch"
RUTA_SESIONES_MEDIOS = "/v2/media-sessions"

LOTE_MAXIMO = 200          # «hasta 200 respuestas dentro de items»
PAGINA_CURSOS = 100
TTL_SESION_MEDIOS_SEG = 60  # una sesión por petición de bytes; muere sola, no se guarda

# Enumeraciones del contrato. Si llega un valor fuera de estas listas, el contrato subió
# de versión: el LMS lo MUESTRA con rótulo genérico, no lo descarta (§9 del mapeo).
MODOS = ("simple", "class", "exam", "review", "free_learning")
PERFILES = ("student", "teacher")
CODIGOS_ERROR = (
    "unauthorized", "not_found", "course_not_found", "lesson_not_found", "object_not_found", "question_not_found",
    "version_not_available", "media_session_not_found", "policy_disabled", "disabled_by_policy", "answer_keys_forbidden",
    "index_rebuilding", "invalid_parameter", "invalid_response",
)

SUGERENCIA_SIN_CONTENIDO = SUGERENCIA_ABRIR


# ------------------------------------------------------------ descubrimiento

def ruta_enlace() -> str:
    """Dónde está `link.json`. Se fuerza con AVACOM_CONTENIDO_ENLACE_V2 (setting o
    variable de entorno) para probar contra el host de pruebas sin instalar nada."""
    forzada = getattr(settings, "AVACOM_CONTENIDO_ENLACE_V2", None) or os.environ.get("AVACOM_CONTENIDO_ENLACE_V2")
    if forzada:
        return forzada
    base = os.environ.get("ProgramData") or os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
    return os.path.join(base, "AVACOM", "content", "link.json")


def _clave(nota: dict, *nombres):
    """Acepta camelCase, minúsculas y PascalCase: el LMS no se ata a la serialización."""
    for nombre in nombres:
        for candidata in (nombre, nombre.lower(), nombre[:1].upper() + nombre[1:]):
            if candidata in nota:
                return nota[candidata]
    return None


def leer_enlace() -> dict:
    """Lee `link.json` EN CADA llamada. Devuelve {contrato, puerto, puerto_medios, token, proceso, iniciada_en}.

    Sin archivo, ilegible o incompleto → BibliotecaNoDisponible: es «sin contenido»,
    el estado normal de un aula con la biblioteca cerrada."""
    ruta = ruta_enlace()
    if not os.path.exists(ruta):
        raise BibliotecaNoDisponible(
            "AVACOM Biblioteca no está encendida en este equipo (no hay link.json): sin contenido.",
            sugerencia=SUGERENCIA_SIN_CONTENIDO,
        )
    try:
        with open(ruta, encoding="utf-8") as archivo:
            nota = json.load(archivo)
    except (OSError, json.JSONDecodeError) as error:
        raise BibliotecaNoDisponible(f"link.json no se pudo leer: {error}") from error
    if not isinstance(nota, dict):
        raise BibliotecaNoDisponible("link.json no tiene la forma esperada.")

    puerto = _clave(nota, "apiPort", "port", "puerto")
    puerto_medios = _clave(nota, "mediaPort")
    token = _clave(nota, "token")
    proceso = _clave(nota, "pid", "processId", "proceso")
    contrato = _clave(nota, "contract", "contrato")
    if isinstance(puerto, str) and puerto.isdigit():
        puerto = int(puerto)
    if not isinstance(puerto, int) or not isinstance(token, str) or not token:
        raise BibliotecaNoDisponible("link.json está incompleto (faltan apiPort o token).")
    if isinstance(contrato, int) and contrato > CONTRATO:
        raise BibliotecaNoDisponible(
            f"La biblioteca habla el contrato {contrato} y este LMS sólo entiende hasta el {CONTRATO}: hay que actualizar el LMS.",
            sugerencia="Actualiza AVACOM OPS antes de volver a intentarlo.",
        )
    return {
        "contrato": contrato if isinstance(contrato, int) else None,
        "puerto": puerto,
        "puerto_medios": puerto_medios if isinstance(puerto_medios, int) else None,
        "token": token,
        "proceso": proceso if isinstance(proceso, int) else None,
        "iniciada_en": _clave(nota, "startedAt"),
    }


# ---------------------------------------------------------------- transporte

# Sin proxy: es loopback y un proxy del sistema desviaría 127.0.0.1 a ningún sitio.
_abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _tiempo_espera() -> float:
    return float(getattr(settings, "AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG", 3))


def _detalle_de_error(error: urllib.error.HTTPError) -> tuple[str, str]:
    """(codigo, mensaje) del cuerpo de error: `{"error": {"code", "message", "details"}}`.
    Se aceptan también `{code, message}`, `{error: "code", detail}` y texto plano."""
    try:
        texto = error.read().decode("utf-8", errors="replace")[:600]
    except OSError:
        texto = ""
    codigo, mensaje = "", ""
    try:
        datos = json.loads(texto) if texto else {}
    except json.JSONDecodeError:
        datos = {}
    if isinstance(datos, dict):
        anidado = datos.get("error")
        if isinstance(anidado, dict):
            codigo = str(anidado.get("code") or anidado.get("codigo") or "")
            mensaje = str(anidado.get("message") or anidado.get("detail") or anidado.get("mensaje") or "")
        else:
            codigo = str(datos.get("code") or datos.get("codigo") or (anidado if isinstance(anidado, str) else "") or "")
            mensaje = str(datos.get("message") or datos.get("detail") or datos.get("motivo") or "")
    if not mensaje:
        mensaje = texto or str(error.reason) or f"HTTP {error.code}"
    return codigo or _codigo_por_estado(error.code), mensaje


def _codigo_por_estado(estado: int) -> str:
    return {401: "unauthorized", 404: "not_found", 400: "invalid_parameter", 422: "invalid_response", 503: "index_rebuilding"}.get(estado, "")


def _abrir(url: str, metodo: str, datos: bytes | None, encabezados: dict):
    """Abre una URL de la biblioteca (API o servidor de medios) traduciendo el transporte."""
    peticion = urllib.request.Request(url, data=datos, headers=encabezados, method=metodo)
    try:
        return _abridor.open(peticion, timeout=_tiempo_espera())
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError as error:
        raise BibliotecaNoDisponible(
            "link.json apunta a un puerto donde nadie escucha: la biblioteca se cerró."
        ) from error
    except (TimeoutError, ConnectionError, OSError) as error:
        raise BibliotecaNoDisponible(f"La biblioteca no contestó a tiempo ({error}).") from error


def _pedir(metodo: str, camino: str, consulta: dict | None = None, cuerpo: dict | None = None,
           cabeceras: dict | None = None, crudo: bool = False, reintentar: bool = True):
    """La única función que habla con la API (puerto `apiPort`).

    Devuelve el JSON decodificado o, con `crudo=True`, la respuesta HTTP abierta (quien
    la pide la cierra). Traduce el transporte a BibliotecaNoDisponible y los HTTP de
    error a BibliotecaError(estado, detalle, codigo=<código del contrato>)."""
    nota = leer_enlace()
    filtros = {k: v for k, v in (consulta or {}).items() if v not in (None, "")}
    url = f"http://127.0.0.1:{nota['puerto']}{camino}"
    if filtros:
        url += "?" + urllib.parse.urlencode(filtros)

    datos = None
    encabezados = {CABECERA_TOKEN: nota["token"], "Accept": "application/json, */*"}
    if cuerpo is not None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        encabezados["Content-Type"] = "application/json; charset=utf-8"
    encabezados.update(cabeceras or {})

    try:
        respuesta = _abrir(url, metodo, datos, encabezados)
    except urllib.error.HTTPError as error:
        codigo, detalle = _detalle_de_error(error)
        if error.code == 401 and reintentar:
            # El token cambió (la biblioteca se reinició): releer link.json y reintentar UNA vez.
            return _pedir(metodo, camino, consulta, cuerpo, cabeceras, crudo, reintentar=False)
        raise BibliotecaError(error.code, detalle, codigo=codigo) from error

    if crudo:
        return respuesta
    try:
        with respuesta:
            texto = respuesta.read().decode("utf-8")
            return json.loads(texto) if texto.strip() else {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        raise BibliotecaError(502, f"La biblioteca contestó algo que no es JSON ({error}).", codigo="invalid_response") from error


def _pedir_medio(url: str, rango: str | None, metodo: str):
    """Bytes del servidor de medios (`mediaPort`). La URL es una capacidad efímera de una
    sesión: no lleva token ni se guarda. Devuelve la respuesta HTTP abierta."""
    if not url.startswith("http://127.0.0.1:") and not url.startswith("http://localhost:"):
        raise BibliotecaError(502, f"La biblioteca devolvió una URL de medio fuera del loopback: {url}", codigo="invalid_response")
    cabeceras = {"Range": rango} if rango else {}
    try:
        return _abrir(url, metodo, None, cabeceras)
    except urllib.error.HTTPError as error:
        codigo, detalle = _detalle_de_error(error)
        raise BibliotecaError(error.code, detalle, codigo=codigo) from error


def _ref(valor: str) -> str:
    return urllib.parse.quote(str(valor), safe="")


def _lista(respuesta, *claves) -> list:
    if isinstance(respuesta, list):
        return respuesta
    if isinstance(respuesta, dict):
        for clave in claves:
            if isinstance(respuesta.get(clave), list):
                return respuesta[clave]
    return []


def _con_id(datos: dict) -> dict:
    """El esquema 1.0 llama `id` al curso; la API lo entrega como `courseId`. Se aceptan los dos."""
    if isinstance(datos, dict) and "id" not in datos and datos.get("courseId"):
        datos["id"] = datos["courseId"]
    return datos


# ------------------------------------------------------------------ contrato

def salud() -> dict:
    """`GET /v2/health`: {contract, schema, index: ready|rebuilding, installedCourses: n}."""
    return _pedir("GET", RUTA_SALUD)


def cursos(**filtros) -> list[dict]:
    """`GET /v2/courses`, paginado: todas las fichas (CourseSummary) de los cursos instalados
    y permitidos por la política. Admite los filtros del contrato (country, level, grade,
    subject, mode, q…)."""
    salida: list[dict] = []
    pagina = 1
    while True:
        datos = _pedir("GET", RUTA_CURSOS, consulta={**filtros, "page": pagina, "pageSize": PAGINA_CURSOS})
        items = [c for c in _lista(datos, "items", "courses") if isinstance(c, dict)]
        salida.extend(items)
        total = datos.get("total") if isinstance(datos, dict) else None
        if not items or not isinstance(total, int) or len(salida) >= total or len(items) < PAGINA_CURSOS:
            return salida
        pagina += 1


def huella(fichas: list[dict]) -> str:
    """Resumen de lo instalado (courseId@version): cambia cuando cambia el catálogo. Es lo
    único que tendría sentido comparar si algún día hubiera una caché en memoria (no la hay)."""
    base = "|".join(sorted(f"{c.get('courseId') or c.get('id')}@{c.get('version')}" for c in fichas))
    return "v2-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:16] if base else "v2-vacio"


def esquema_curso(curso_ref: str, *, modo: str | None = None, perfil: str | None = None) -> dict:
    """`GET /v2/courses/{courseId}?mode=&profile=`: metadatos, lecciones con RESÚMENES de
    objeto (`pageCount`, `questionCount`, `mediaId`) y la lista de medios. Sin láminas ni
    preguntas: eso se pide por lección u objeto. `mode` filtra lo que no admite ese modo;
    `profile=student` recorta `teacherNotes`."""
    return _con_id(_pedir("GET", RUTA_CURSO.format(curso=_ref(curso_ref)), consulta={"mode": modo, "profile": perfil}))


def leccion(curso_ref: str, leccion_ref: str, *, modo: str | None = None, perfil: str | None = None,
            semilla: str | None = None) -> dict:
    """`GET /v2/courses/{courseId}/lessons/{lessonId}`: la lección completa (Lesson del esquema
    1.0 más courseId y version), filtrada por modo y recortada por perfil. `seed` fija el
    barajado de las opciones para que toda la clase vea el mismo orden."""
    return _pedir("GET", RUTA_LECCION.format(curso=_ref(curso_ref), leccion=_ref(leccion_ref)),
                  consulta={"mode": modo, "profile": perfil, "seed": semilla})


def objeto(curso_ref: str, objeto_ref: str, *, perfil: str | None = None, semilla: str | None = None) -> dict:
    """`GET /v2/courses/{courseId}/objects/{objectId}`: un objeto completo más courseId, version y lessonId."""
    return _pedir("GET", RUTA_OBJETO.format(curso=_ref(curso_ref), objeto=_ref(objeto_ref)),
                  consulta={"profile": perfil, "seed": semilla})


def curso(curso_ref: str, *, version: str | None = None, modo: str | None = None, perfil: str | None = None,
          semilla: str | None = None) -> dict:
    """El curso COMPLETO con la forma del esquema 1.0 que lee el normalizador del aula: el
    esquema (`esquema_curso`) con cada lección sustituida por su versión completa.

    La API no sirve el esquema de una versión archivada (sólo `evaluate` y `grading-guide`
    aceptan `version`): pedir otra versión que la instalada es `version_not_available`."""
    datos = esquema_curso(curso_ref, modo=modo, perfil=perfil)
    instalada = str(datos.get("version") or "")
    if version and instalada and version != instalada:
        raise BibliotecaError(404, f"La versión {version} no está disponible; la instalada es {instalada}.", codigo="version_not_available")
    lecciones = []
    for resumen in datos.get("lessons") or []:
        if not isinstance(resumen, dict):
            continue
        if not resumen.get("objects"):
            lecciones.append(resumen)            # con `mode` la lección quedó vacía: no hay nada que bajar
            continue
        completa = leccion(curso_ref, str(resumen.get("id", "")), modo=modo, perfil=perfil, semilla=semilla)
        for clave in ("courseId", "version"):
            completa.pop(clave, None)
        lecciones.append({**resumen, **completa})
    datos["lessons"] = lecciones
    return datos


def guia_calificacion(curso_ref: str, pregunta_ref: str, version: str | None = None) -> dict:
    """`GET …/questions/{questionId}/grading-guide?version=`: rúbrica y respuesta modelo de una
    pregunta abierta. Sólo para calificar A MANO (MOD-011): el aula no la expone."""
    return _pedir("GET", RUTA_GUIA.format(curso=_ref(curso_ref), pregunta=_ref(pregunta_ref)), consulta={"version": version})


def evaluar(curso_ref: str, version: str, objeto_ref: str, pregunta_ref: str, respuesta: dict) -> dict:
    """`POST /v2/evaluate`. La clave se compara donde vive; aquí sólo vuelve el veredicto.
    `version` se manda SIEMPRE para que un intento se califique con las claves con las que se hizo."""
    if not version:
        raise ValueError("evaluar() exige la versión del curso (regla del contrato: mándenla siempre).")
    return _pedir("POST", RUTA_EVALUAR, cuerpo={
        "courseId": curso_ref, "version": version, "objectId": objeto_ref, "questionId": pregunta_ref, "response": respuesta,
    })


def evaluar_lote(items: list[dict]) -> list[dict]:
    """`POST /v2/evaluate/batch` → `{results[]}` en el orden pedido; hasta 200 por llamada, más se trocean."""
    salida: list[dict] = []
    for inicio in range(0, len(items), LOTE_MAXIMO):
        trozo = items[inicio:inicio + LOTE_MAXIMO]
        for item in trozo:
            if not item.get("version"):
                raise ValueError("Cada respuesta del lote exige la versión del curso.")
        datos = _pedir("POST", RUTA_EVALUAR_LOTE, cuerpo={"items": trozo})
        salida.extend(x for x in _lista(datos, "results", "items") if isinstance(x, dict))
    return salida


# -------------------------------------------------------------------- medios

def sesion_medios(curso_ref: str, media_refs: list[str] | None = None, leccion_ref: str | None = None,
                  ttl_seg: int = TTL_SESION_MEDIOS_SEG) -> dict:
    """`POST /v2/media-sessions`: URL-capacidad efímeras en el servidor de medios para una
    lista de medios, una lección o el curso entero. Devuelve {sessionId, baseUrl, expiresAt,
    urls{mediaId: url}, extras{mediaId: {captions, transcript, files}}}. No se guarda."""
    cuerpo: dict = {"courseId": curso_ref, "ttlSec": int(ttl_seg)}
    if media_refs:
        cuerpo["mediaIds"] = list(media_refs)
    elif leccion_ref:
        cuerpo["lessonId"] = leccion_ref
    return _pedir("POST", RUTA_SESIONES_MEDIOS, cuerpo=cuerpo)


def abrir_medio(curso_ref: str, media_ref: str, ruta_interna: str | None = None, rango: str | None = None, metodo: str = "GET"):
    """Bytes de un medio del paquete, en paso a través: abre una sesión de medios de un
    minuto sólo para ese medio y pide la URL que devuelve. Devuelve la respuesta HTTP cruda
    (Content-Type, Content-Length, Content-Range, Accept-Ranges); quien la pide la cierra.

    `ruta_interna`: `subtitulos` (VTT) o `transcripcion` (texto) para audio y video, o la
    ruta de un archivo dentro de la carpeta de una simulación (`index.html`, `js/app.js`)."""
    try:
        sesion = sesion_medios(curso_ref, [media_ref])
    except BibliotecaError as error:
        # La API responde 400 invalid_parameter a un mediaId que no está en el curso: para el aula es «no existe».
        if error.codigo == "invalid_parameter" and "media" in error.detalle.lower():
            raise BibliotecaError(404, error.detalle, codigo="not_found") from error
        raise
    urls = sesion.get("urls") or {}
    url = urls.get(media_ref)
    if not url:
        raise BibliotecaError(404, f"El medio «{media_ref}» no está en el curso.", codigo="not_found")
    if ruta_interna:
        ruta_interna = ruta_interna.strip("/")
        extras = (sesion.get("extras") or {}).get(media_ref) or {}
        if ruta_interna in ("subtitulos", "captions"):
            url = extras.get("captions")
            if not url:
                raise BibliotecaError(404, "Este medio no tiene subtítulos.", codigo="not_found")
        elif ruta_interna in ("transcripcion", "transcript"):
            url = extras.get("transcript")
            if not url:
                raise BibliotecaError(404, "Este medio no tiene transcripción.", codigo="not_found")
        else:
            # Archivo dentro de la simulación: <baseUrl><mediaId>/<ruta>. La URL del medio apunta a su entrada.
            base = str(sesion.get("baseUrl") or url.rsplit("/", 1)[0] + "/")
            url = f"{base}{_ref(media_ref)}/{urllib.parse.quote(ruta_interna, safe='/')}"
    return _pedir_medio(url, rango, metodo)


# -------------------------------------------------------------------- estado

def estado() -> dict:
    """NUNCA lanza. `disponible=False` con motivo y sugerencia cuando no hay contenido."""
    salida = {
        "api": API, "contrato": None, "esquema": None, "version_app": None, "disponible": False, "motivo": "", "sugerencia": None, "puerto": None,
        "puerto_medios": None, "proceso": None, "huella": "", "cursos_instalados": [], "reconstruyendo_indice": False,
    }
    try:
        nota = leer_enlace()
    except BibliotecaNoDisponible as error:
        salida.update(motivo=error.motivo, sugerencia=error.sugerencia)
        return salida
    salida.update(puerto=nota["puerto"], puerto_medios=nota["puerto_medios"], proceso=nota["proceso"], contrato=nota["contrato"])
    try:
        datos = salud()
        reconstruyendo = str(datos.get("index") or "") == "rebuilding"
        fichas = [] if reconstruyendo else cursos()
    except BibliotecaNoDisponible as error:
        salida.update(motivo=error.motivo, sugerencia=error.sugerencia)
        return salida
    except BibliotecaError as error:
        if error.codigo == "index_rebuilding" or error.estado == 503:
            salida.update(reconstruyendo_indice=True, motivo="La biblioteca está reconstruyendo su índice.",
                          sugerencia="Vuelve a intentarlo en unos segundos.")
        else:
            salida.update(motivo=f"La biblioteca respondió {error.estado}: {error.detalle}", sugerencia=SUGERENCIA_ABRIR)
        return salida
    salida.update(
        disponible=True, contrato=datos.get("contract", salida["contrato"]), reconstruyendo_indice=reconstruyendo,
        esquema=str(datos.get("schema") or "") or None,     # versión del esquema de curso (course.schema.json), hoy «1.0»
        version_app=str(datos.get("appVersion") or "") or None,  # build de AVACOM Contenido (2.1.7 en vivo); ausente en el contrato entregado
        huella=huella(fichas),
        cursos_instalados=[{"curso_ref": str(c.get("courseId") or c.get("id") or ""), "version": str(c.get("version") or ""),
                            "titulo": c.get("title")} for c in fichas],
    )
    if reconstruyendo:
        salida.update(motivo="La biblioteca está reconstruyendo su índice.", sugerencia="Vuelve a intentarlo en unos segundos.")
    return salida
