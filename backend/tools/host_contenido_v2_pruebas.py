"""
Host de pruebas que imita la **API de Contenido v2** de AVACOM Biblioteca (contrato 2)
en loopback, con la forma comprobada en vivo el 2026-09-21 contra `GET /v2/openapi.json`
(copia en spec-driven/02-classroom-engine/openapi.v2.json):

  GET  /v2/health                                     → {contract: 2, schema, index: ready|rebuilding, installedCourses: n}
  GET  /v2/courses?page&pageSize                      → {items:[CourseSummary], page, pageSize, total}
  GET  /v2/courses/{id}?mode&profile                  → el ESQUEMA: metadatos, lecciones con resúmenes de objeto y medios
  GET  /v2/courses/{id}/lessons/{lid}?mode&profile&seed&includeActivityKeys
                                                      → la lección completa recortada (+ courseId, version)
  GET  /v2/courses/{id}/objects/{oid}?profile&seed&includeActivityKeys
                                                      → un objeto completo (+ courseId, version, lessonId)
  GET  /v2/courses/{id}/questions/{qid}/grading-guide?version
  POST /v2/evaluate · /v2/evaluate/batch (≤ 200)      → veredicto con las claves del manifiesto completo · {results[]}

El recorte (`objeto_visible`) y la corrección (`calificar`) están calcados de `visible_object` y
`evaluate_response` de `validate_course.py`, el validador de referencia que publica la biblioteca
junto a `course.schema.json` (copias en spec-driven/02-classroom-engine/). `includeActivityKeys`
conserva las claves de una actividad con `feedback: immediate`; con un examen es 403
`answer_keys_forbidden`. El aula nunca lo pide.
  POST /v2/media-sessions · DELETE /v2/media-sessions/{id}
  Servidor de medios aparte (mediaPort): /s/{cap}/{mediaId}[/@captions|/@transcript|/@files|/{ruta}] con Range, sin token

Autenticación: cabecera `X-Avacom-Token`; sin ella o con otra, 401 `unauthorized`. Escribe
`link.json` ({contract, apiPort, mediaPort, token, pid, startedAt}) donde se le indique, para
que el backend lo encuentre con AVACOM_CONTENIDO_ENLACE_V2. `rechazar_proximas = n` fuerza n
401 seguidos (para probar el reintento único); `reconstruyendo = True` responde 503
`index_rebuilding`; `desactivados` responde 403 `policy_disabled` y omite el curso de la lista.

Uso a mano, sin la biblioteca real:

    python -m tools.host_contenido_v2_pruebas %TEMP%\\link-pruebas.json
    set AVACOM_CONTENIDO_ENLACE_V2=%TEMP%\\link-pruebas.json
"""
from __future__ import annotations

import copy
import json
import os
import secrets
import sys
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

# Lo que la API recorta antes de entregar una pregunta: ANSWER_KEY_FIELDS, ANSWER_KEY_OPTION_FIELDS y
# ANSWER_KEY_BLANK_FIELDS de `validate_course.py` (spec-driven/02-classroom-engine), el validador de
# referencia de la biblioteca cuyo `visible_object` define lo que un dispositivo de alumno puede recibir.
CLAVES_PREGUNTA = {
    "multiple_choice": ("feedback",),
    "true_false": ("answer", "feedback"),
    "fill_blanks": ("feedback",),
    "matching": ("pairs", "wrongPairs", "feedback"),
    "ordering": ("correctOrder", "wrongOrders", "feedback"),
    "open": ("modelAnswer", "rubric", "incorrectExamples", "keywords", "feedback"),
}
CLAVES_OPCION = ("isCorrect", "feedback")
CLAVES_HUECO = ("acceptedAnswers", "wrongAnswers", "numericTolerance")
# Lo que el esquema del curso resume de cada objeto (CourseOutline).
CLAVES_RESUMEN_OBJETO = ("id", "type", "title", "modes", "topicRef", "estimatedDurationSec", "mediaId")
MODOS = ("simple", "class", "exam", "review", "free_learning")
LOTE_MAXIMO = 200

PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0300"
    "0501fe0d8d3d0e0000000049454e44ae426082"
)


def objeto_visible(objeto: dict, *, perfil: str, claves_actividad: bool = False) -> dict:
    """Lo que la API devuelve de un objeto: `visible_object` de validate_course.py, paso por paso.
    Las claves de un examen se quitan SIEMPRE; las de una actividad sólo se conservan si se pidió
    `includeActivityKeys` y la actividad tiene `feedback: immediate`. `profile=student` quita las
    notas del docente del objeto, de sus láminas o páginas y de sus preguntas."""
    salida = copy.deepcopy(objeto)
    if perfil == "student":
        salida.pop("teacherNotes", None)
        for clave in ("slides", "pages"):
            for pagina in salida.get(clave) or []:
                pagina.pop("teacherNotes", None)
    conservar = (claves_actividad and salida.get("type") == "activity"
                 and (salida.get("settings") or {}).get("feedback") == "immediate")
    for pregunta in salida.get("questions") or []:
        if perfil == "student":
            pregunta.pop("teacherNotes", None)
        if conservar:
            continue
        for campo in CLAVES_PREGUNTA.get(pregunta.get("type"), ()):
            pregunta.pop(campo, None)
        for opcion in pregunta.get("options") or []:
            for campo in CLAVES_OPCION:
                opcion.pop(campo, None)
        for hueco in pregunta.get("blanks") or []:
            for campo in CLAVES_HUECO:
                hueco.pop(campo, None)
    return salida


def leccion_visible(leccion: dict, *, perfil: str, modo: str | None, claves_actividad: bool = False) -> dict:
    """La lección filtrada por modo y recortada por perfil, con cada objeto como lo entrega la API."""
    salida = {k: v for k, v in leccion.items() if k != "objects" and not (perfil == "student" and k == "teacherNotes")}
    salida["objects"] = [objeto_visible(o, perfil=perfil, claves_actividad=claves_actividad)
                         for o in filtrar_modo(leccion.get("objects") or [], modo)]
    return salida


def _verdadero(valor) -> bool:
    return str(valor or "").strip().lower() in ("1", "true", "yes")


def _rotacion(semilla: str | None, n: int) -> int:
    """Sin semilla, una posición; con semilla, un desplazamiento derivado de ella. Nunca el orden de origen."""
    if n < 2:
        return 0
    if not semilla:
        return 1
    return 1 + sum(ord(c) for c in semilla) % (n - 1)


def barajar_preguntas(preguntas: list[dict], semilla: str | None) -> None:
    """Las opciones, parejas y elementos llegan en otro orden en cada llamada (rotados), para que una
    prueba que guarde posiciones en vez de `id` falle."""
    for pregunta in preguntas:
        for clave in ("options", "right", "items"):
            lista = pregunta.get(clave)
            if isinstance(lista, list) and len(lista) > 1:
                k = _rotacion(semilla, len(lista))
                pregunta[clave] = lista[k:] + lista[:k]


def filtrar_modo(objetos: list[dict], modo: str | None) -> list[dict]:
    if not modo:
        return objetos
    return [o for o in objetos if not o.get("modes") or modo in o["modes"]]


def resumen_objeto(o: dict) -> dict:
    salida = {k: o[k] for k in CLAVES_RESUMEN_OBJETO if k in o}
    if o.get("type") == "lecture":
        salida["pageCount"] = len(o.get("slides") or [])
    elif o.get("type") == "explanation":
        salida["pageCount"] = len(o.get("pages") or [])
    elif o.get("type") in ("activity", "exam"):
        salida["questionCount"] = len(o.get("questions") or [])
    return salida


def resumen_medio(m: dict) -> dict:
    salida = {k: v for k, v in m.items() if k not in ("path", "captionsPath", "transcriptPath")}
    salida["hasCaptions"] = bool(m.get("captionsPath"))
    salida["hasTranscript"] = bool(m.get("transcriptPath"))
    return salida


def ficha(m: dict) -> dict:
    """CourseSummary."""
    return {"courseId": m.get("id"), "version": m.get("version"), "title": m.get("title"), "subtitle": m.get("subtitle"),
            "language": m.get("language"), "translationGroupId": m.get("translationGroupId"), "classification": m.get("classification"),
            "estimatedDurationMin": m.get("estimatedDurationMin"), "modes": m.get("modes"),
            "curriculumRefs": [{"framework": r.get("framework"), "code": r.get("code")} for r in m.get("curriculumRefs") or []],
            "lessonCount": len(m.get("lessons") or []), "coverMediaId": m.get("coverMediaId"), "updatedAt": "2026-09-18T16:21:50Z"}


# ------------------------------------------------------------------ calificar

def _normalizar(texto, sensible_mayusculas: bool, ignorar_acentos: bool) -> str:
    """`_normalize` de validate_course.py: espacios colapsados, minúsculas y sin acentos según el hueco."""
    t = " ".join(str(texto).split())
    if not sensible_mayusculas:
        t = t.lower()
    if ignorar_acentos:
        t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return t


def calificar(pregunta: dict, respuesta: dict) -> dict:
    """El veredicto con las claves del manifiesto completo, calcado de `evaluate_response` de
    validate_course.py (la definición ejecutable de la corrección, que la biblioteca replica en C#):

      - `correct` es SIEMPRE booleano en las preguntas automáticas: `ratio == 1.0`. Un crédito
        parcial es `correct: false` con `score` mayor que cero.
      - `feedback[0]` es la retroalimentación general (`feedback.correct` o `.incorrect`); después
        vienen las específicas de la opción, el hueco, la pareja o el orden elegidos.
      - Opción múltiple: el crédito parcial exige `allowMultiple`; ratio = (aciertos − fallos) / correctas.
      - Completar: `numeric` admite coma decimal y `numericTolerance`; `text`/`select` comparan con
        `caseSensitive` (falso por defecto) e `ignoreAccents` (verdadero por defecto).
      - Relacionar: ratio = parejas correctas / esperadas; ordenar: posiciones acertadas / total.
      - Abierta: sin nota, `requiresManualGrading` y sin retroalimentación.

    Una respuesta con otra forma es ValueError → 422 `invalid_response`."""
    tipo = pregunta.get("type")
    puntos = float(pregunta.get("points") or 0)
    parcial = bool(pregunta.get("partialCredit"))
    retro_general = pregunta.get("feedback") or {}
    salida: dict = {"questionId": pregunta["id"], "maxScore": puntos, "requiresManualGrading": False, "feedback": []}

    if tipo == "open":
        if not isinstance(respuesta, dict) or not any(respuesta.get(k) for k in ("text", "drawingRef", "audioRef")):
            raise ValueError("Response must contain text, drawingRef or audioRef.")
        salida.update(score=None, correct=None, requiresManualGrading=True)
        return salida

    if tipo == "true_false":
        valor = respuesta.get("value")
        if not isinstance(valor, bool):
            raise ValueError("Response must contain a boolean 'value'.")
        ratio = 1.0 if valor is pregunta["answer"] else 0.0

    elif tipo == "multiple_choice":
        elegidas = respuesta.get("selectedOptionIds")
        if not isinstance(elegidas, list):
            raise ValueError("Response must contain an array 'selectedOptionIds'.")
        opciones = pregunta.get("options") or []
        if any(e not in {o["id"] for o in opciones} for e in elegidas):
            raise ValueError("Unknown option id.")
        elegidas = set(elegidas)
        correctas = {o["id"] for o in opciones if o.get("isCorrect")}
        for o in opciones:
            if o["id"] in elegidas and not o.get("isCorrect") and o.get("feedback"):
                salida["feedback"].append(o["feedback"])
        if pregunta.get("allowMultiple") and parcial:
            aciertos, fallos = len(elegidas & correctas), len(elegidas - correctas)
            ratio = max(0.0, (aciertos - fallos) / len(correctas))
        else:
            ratio = 1.0 if elegidas == correctas else 0.0

    elif tipo == "fill_blanks":
        dados = respuesta.get("blanks")
        if not isinstance(dados, dict):
            raise ValueError("Response must contain an object 'blanks'.")
        huecos = pregunta.get("blanks") or []
        aciertos = 0
        for b in huecos:
            valor = dados.get(b["id"], "")
            if b.get("inputMode") == "numeric":
                try:
                    numero = float(str(valor).replace(",", "."))
                    ok = any(abs(numero - float(a)) <= b.get("numericTolerance", 0) for a in b["acceptedAnswers"])
                except ValueError:
                    ok = False
            else:
                def norma(x, b=b):
                    return _normalizar(x, b.get("caseSensitive", False), b.get("ignoreAccents", True))
                ok = norma(valor) in {norma(a) for a in b["acceptedAnswers"]}
            if ok:
                aciertos += 1
            else:
                for w in b.get("wrongAnswers") or []:
                    if w.get("feedback") and _normalizar(w["value"], False, True) == _normalizar(valor, False, True):
                        salida["feedback"].append(w["feedback"])
        ratio = aciertos / len(huecos) if parcial else (1.0 if aciertos == len(huecos) else 0.0)

    elif tipo == "matching":
        parejas = respuesta.get("pairs")
        if not isinstance(parejas, list):
            raise ValueError("Response must contain an array 'pairs'.")
        dadas = {(p.get("leftId"), p.get("rightId")) for p in parejas if isinstance(p, dict)}
        correctas = {(p["leftId"], p["rightId"]) for p in pregunta.get("pairs") or []}
        for w in pregunta.get("wrongPairs") or []:
            if (w["leftId"], w["rightId"]) in dadas:
                salida["feedback"].append(w["feedback"])
        aciertos = len(dadas & correctas)
        ratio = aciertos / len(correctas) if parcial else (1.0 if dadas == correctas else 0.0)

    elif tipo == "ordering":
        orden = respuesta.get("order")
        if not isinstance(orden, list):
            raise ValueError("Response must contain an array 'order'.")
        correcto = pregunta.get("correctOrder") or []
        for w in pregunta.get("wrongOrders") or []:
            if w.get("order") == orden:
                salida["feedback"].append(w["feedback"])
        if parcial:
            ratio = sum(1 for a, b in zip(orden, correcto) if a == b) / len(correcto)
        else:
            ratio = 1.0 if orden == correcto else 0.0
    else:
        raise ValueError(f"unknown question type {tipo}")

    salida["score"] = round(puntos * ratio, 4)
    salida["correct"] = ratio == 1.0
    general = retro_general.get("correct") if ratio == 1.0 else retro_general.get("incorrect")
    if general:
        salida["feedback"].insert(0, general)
    return salida


class HostContenidoV2Pruebas:
    def __init__(self, ruta_enlace: str, manifiestos: dict[str, dict], archivados: dict[tuple[str, str], dict] | None = None,
                 medios: dict[str, tuple[str, bytes]] | None = None, desactivados: set[str] | None = None,
                 invalidos: set[str] | None = None):
        self.ruta_enlace = ruta_enlace
        self.manifiestos = dict(manifiestos)                    # courseId → manifiesto COMPLETO (con claves) de la versión instalada
        self.archivados = dict(archivados or {})                # (courseId, version) → manifiesto archivado (sólo evaluate y grading-guide)
        self.medios = dict(medios or {})                        # mediaId, "mediaId/@captions", "mediaId/@transcript" o "mediaId/ruta" → (tipo, bytes)
        self.desactivados = set(desactivados or ())
        # Paquetes que no pasan la verificación (visto en vivo con AVACOM Contenido 2.1.7): la API los LISTA en
        # /v2/courses pero responde 500 `package_invalid` a todo lo demás (curso, lección, objeto, evaluar, medios).
        self.invalidos = set(invalidos or ())
        self.token = secrets.token_urlsafe(32)
        self.reconstruyendo = False
        self.rechazar_proximas = 0
        self.peticiones: list[str] = []
        self.consultas: list[dict] = []
        self.cuerpos: list[dict] = []
        self.sesiones: dict[str, dict] = {}                     # capacidad → {id, courseId, mediaIds, expira}
        self._api: ThreadingHTTPServer | None = None
        self._medios: ThreadingHTTPServer | None = None

    # ------------------------------------------------------------ ciclo de vida
    def iniciar(self) -> "HostContenidoV2Pruebas":
        self._api = ThreadingHTTPServer(("127.0.0.1", 0), self._manejador_api())
        self._medios = ThreadingHTTPServer(("127.0.0.1", 0), self._manejador_medios())
        for servidor in (self._api, self._medios):
            servidor.daemon_threads = True
            threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.escribir_enlace()
        return self

    @property
    def puerto(self) -> int:
        return self._api.server_address[1] if self._api else 0

    @property
    def puerto_medios(self) -> int:
        return self._medios.server_address[1] if self._medios else 0

    def escribir_enlace(self) -> None:
        os.makedirs(os.path.dirname(self.ruta_enlace) or ".", exist_ok=True)
        with open(self.ruta_enlace, "w", encoding="utf-8") as archivo:
            json.dump({"contract": 2, "apiPort": self.puerto, "mediaPort": self.puerto_medios, "token": self.token,
                       "pid": os.getpid(), "startedAt": datetime.now(timezone.utc).isoformat()}, archivo)

    def rotar_token(self) -> None:
        """La biblioteca se reinició: token nuevo en link.json."""
        self.token = secrets.token_urlsafe(32)
        self.escribir_enlace()

    def borrar_enlace(self) -> None:
        try:
            os.remove(self.ruta_enlace)
        except OSError:
            pass

    def detener(self) -> None:
        for servidor in (self._api, self._medios):
            if servidor:
                servidor.shutdown()
                servidor.server_close()
        self._api = self._medios = None
        self.borrar_enlace()

    # ----------------------------------------------------------------- datos
    def _curso(self, ref: str, version: str | None) -> dict | None:
        if version and version != str(self.manifiestos.get(ref, {}).get("version", "")):
            return self.archivados.get((ref, version))
        return self.manifiestos.get(ref)

    @staticmethod
    def _leccion(curso: dict, leccion_ref: str) -> dict | None:
        return next((l for l in curso.get("lessons") or [] if str(l.get("id")) == leccion_ref), None)

    @staticmethod
    def _objeto(curso: dict, objeto_ref: str) -> tuple[dict, dict] | None:
        for l in curso.get("lessons") or []:
            for o in l.get("objects") or []:
                if str(o.get("id")) == objeto_ref:
                    return l, o
        return None

    @staticmethod
    def _pregunta(curso: dict, objeto_ref: str, pregunta_ref: str) -> dict | None:
        hallado = HostContenidoV2Pruebas._objeto(curso, objeto_ref)
        if not hallado:
            return None
        return next((q for q in hallado[1].get("questions") or [] if str(q.get("id")) == pregunta_ref), None)

    def _esquema(self, curso: dict, modo: str | None, perfil: str) -> dict:
        salida = {k: v for k, v in curso.items() if k not in ("id", "lessons", "media", "teacherNotes")}
        salida = {"courseId": curso.get("id"), **salida}
        if perfil != "student" and curso.get("teacherNotes") is not None:
            salida["teacherNotes"] = curso["teacherNotes"]
        salida["lessons"] = [
            {**{k: v for k, v in l.items() if k not in ("objects", "teacherNotes")},
             "objects": [resumen_objeto(o) for o in filtrar_modo(l.get("objects") or [], modo)]}
            for l in curso.get("lessons") or []
        ]
        salida["media"] = [resumen_medio(m) for m in curso.get("media") or []]
        return salida

    def _abrir_sesion(self, curso: dict, media_ids: list[str] | None, leccion_ref: str | None, ttl: int) -> dict:
        medios = {str(m.get("id")): m for m in curso.get("media") or []}
        if media_ids is not None:
            pedidos = [m for m in media_ids if m in medios]
        elif leccion_ref:
            leccion = self._leccion(curso, leccion_ref)
            if leccion is None:
                raise LookupError("lesson_not_found")
            texto = json.dumps(leccion)
            pedidos = [m for m in medios if f'"{m}"' in texto]
        else:
            pedidos = list(medios)
        cap = secrets.token_urlsafe(16)
        sesion_id = "ms_" + secrets.token_hex(8)
        base = f"http://127.0.0.1:{self.puerto_medios}/s/{cap}/"
        self.sesiones[cap] = {"id": sesion_id, "courseId": curso.get("id"), "mediaIds": set(pedidos),
                              "expira": time.time() + ttl}
        urls, extras = {}, {}
        for m in pedidos:
            medio = medios[m]
            # Contrato 2 (2026-10-07): una lección `html` se abre por su `entry` como una simulación, y un video con `posterPath` publica
            # `extras[mediaId].poster` en <baseUrl><mediaId>/@poster.
            urls[m] = f"{base}{m}/{medio['entry']}" if medio.get("kind") in ("simulation", "html") and medio.get("entry") else f"{base}{m}"
            extra = {}
            if medio.get("kind") == "simulation":
                extra["files"] = f"{base}{m}/@files"
            if medio.get("captionsPath"):
                extra["captions"] = f"{base}{m}/@captions"
            if medio.get("transcriptPath"):
                extra["transcript"] = f"{base}{m}/@transcript"
            if medio.get("kind") == "video" and medio.get("posterPath"):
                extra["poster"] = f"{base}{m}/@poster"
            if extra:
                extras[m] = extra
        expira = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
        return {"sessionId": sesion_id, "baseUrl": base, "expiresAt": expira, "urls": urls, "extras": extras}

    # -------------------------------------------------------------- servidores
    def _manejador_api(self):
        host = self

        class Manejador(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                pass

            def _json(self, codigo: int, datos) -> None:
                cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(cuerpo)

            def _error(self, estado: int, codigo: str, mensaje: str) -> None:
                self._json(estado, {"error": {"code": codigo, "message": mensaje, "details": {}}})

            def _autorizado(self) -> bool:
                if host.rechazar_proximas > 0:
                    host.rechazar_proximas -= 1
                    self._error(401, "unauthorized", "Missing or invalid X-Avacom-Token")
                    return False
                if self.headers.get("X-Avacom-Token") != host.token:
                    self._error(401, "unauthorized", "Missing or invalid X-Avacom-Token")
                    return False
                return True

            def _entrada(self):
                url = urlparse(self.path)
                camino = unquote(url.path)
                consulta = {k: v[0] for k, v in parse_qs(url.query).items()}
                host.peticiones.append(f"{self.command} {camino}")
                host.consultas.append(consulta)
                return camino, consulta, [p for p in camino.split("/") if p]

            def _perfil_modo(self, consulta):
                perfil = consulta.get("profile") or "student"
                modo = consulta.get("mode")
                if perfil not in ("student", "teacher"):
                    self._error(400, "invalid_parameter", "profile must be student or teacher")
                    return None
                if modo and modo not in MODOS:
                    self._error(400, "invalid_parameter", "mode must be simple, class, exam, review or free_learning")
                    return None
                return perfil, modo

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                camino, consulta, partes = self._entrada()
                if not self._autorizado():
                    return
                if camino == "/v2/health":
                    return self._json(200, {"contract": 2, "schema": "1.0", "index": "rebuilding" if host.reconstruyendo else "ready",
                                            "installedCourses": len(host.manifiestos), "appVersion": "2.1.7"})
                if host.reconstruyendo:
                    return self._error(503, "index_rebuilding", "Index is rebuilding")

                if camino == "/v2/courses":
                    fichas = [ficha(m) for ref, m in host.manifiestos.items() if ref not in host.desactivados]
                    pagina, tamano = int(consulta.get("page") or 1), int(consulta.get("pageSize") or 20)
                    inicio = (pagina - 1) * tamano
                    return self._json(200, {"items": fichas[inicio:inicio + tamano], "page": pagina, "pageSize": tamano, "total": len(fichas)})

                if len(partes) >= 3 and partes[0] == "v2" and partes[1] == "courses":
                    ref = partes[2]
                    curso = host.manifiestos.get(ref)
                    if ref in host.invalidos:
                        return self._error(500, "package_invalid", "Installed package failed verification: E-PKG-COURSE")
                    if len(partes) == 3:
                        pm = self._perfil_modo(consulta)
                        if pm is None:
                            return None
                        if ref in host.desactivados:
                            return self._error(403, "policy_disabled", "Disabled by school policy")
                        if curso is None:
                            return self._error(404, "course_not_found", "Course not installed")
                        return self._json(200, host._esquema(curso, pm[1], pm[0]))
                    if curso is None:
                        return self._error(404, "course_not_found", "Course not installed")
                    if ref in host.desactivados:
                        return self._error(403, "policy_disabled", "Disabled by school policy")
                    claves_actividad = _verdadero(consulta.get("includeActivityKeys"))
                    if len(partes) == 5 and partes[3] == "lessons":
                        pm = self._perfil_modo(consulta)
                        if pm is None:
                            return None
                        leccion = host._leccion(curso, partes[4])
                        if leccion is None:
                            return self._error(404, "lesson_not_found", "Lesson not found")
                        if claves_actividad and any(o.get("type") == "exam" for o in filtrar_modo(leccion.get("objects") or [], pm[1])):
                            return self._error(403, "answer_keys_forbidden", "Answer keys are never sent for exams")
                        salida = leccion_visible(leccion, perfil=pm[0], modo=pm[1], claves_actividad=claves_actividad)
                        for o in salida["objects"]:
                            barajar_preguntas(o.get("questions") or [], consulta.get("seed"))
                        return self._json(200, {**salida, "courseId": ref, "version": curso.get("version")})
                    if len(partes) == 5 and partes[3] == "objects":
                        pm = self._perfil_modo(consulta)
                        if pm is None:
                            return None
                        hallado = host._objeto(curso, partes[4])
                        if hallado is None:
                            return self._error(404, "object_not_found", "Object not found")
                        if claves_actividad and hallado[1].get("type") == "exam":
                            return self._error(403, "answer_keys_forbidden", "Answer keys are never sent for exams")
                        salida = objeto_visible(hallado[1], perfil=pm[0], claves_actividad=claves_actividad)
                        barajar_preguntas(salida.get("questions") or [], consulta.get("seed"))
                        return self._json(200, {**salida, "courseId": ref, "version": curso.get("version"), "lessonId": hallado[0].get("id")})
                    if len(partes) == 6 and partes[3] == "questions" and partes[5] == "grading-guide":
                        version = consulta.get("version")
                        fuente = host._curso(ref, version)
                        if fuente is None:
                            return self._error(404, "version_not_available", f"Version {version} is not available")
                        pregunta = None
                        for l in fuente.get("lessons") or []:
                            for o in l.get("objects") or []:
                                pregunta = pregunta or next((q for q in o.get("questions") or [] if str(q.get("id")) == partes[4]), None)
                        if not pregunta:
                            return self._error(404, "question_not_found", "Question not found")
                        return self._json(200, {"courseId": ref, "version": fuente.get("version"), "questionId": pregunta["id"],
                                                "prompt": pregunta.get("prompt"), "points": pregunta.get("points"),
                                                "responseFormat": pregunta.get("responseFormat"), "modelAnswer": pregunta.get("modelAnswer"),
                                                "rubric": pregunta.get("rubric") or [], "incorrectExamples": pregunta.get("incorrectExamples") or []})
                return self._error(404, "not_found", "Unknown endpoint")

            def do_POST(self):
                camino, _, _ = self._entrada()
                if not self._autorizado():
                    return
                largo = int(self.headers.get("Content-Length") or 0)
                cuerpo = json.loads(self.rfile.read(largo) or b"{}") if largo else {}
                host.cuerpos.append(cuerpo)
                if host.reconstruyendo:
                    return self._error(503, "index_rebuilding", "Index is rebuilding")

                if camino == "/v2/evaluate":
                    try:
                        return self._json(200, self._evaluar(cuerpo))
                    except LookupError as e:
                        return self._error(404, str(e), str(e).replace("_", " "))
                    except ValueError as e:
                        return self._error(422, "invalid_response", str(e))
                    except RuntimeError:
                        return self._error(500, "package_invalid", "Installed package failed verification: E-PKG-COURSE")
                if camino == "/v2/evaluate/batch":
                    items = cuerpo.get("items")
                    if not isinstance(items, list) or len(items) > LOTE_MAXIMO:
                        return self._error(400, "invalid_parameter", f"items must be an array of at most {LOTE_MAXIMO}")
                    try:
                        return self._json(200, {"results": [self._evaluar(i) for i in items]})
                    except LookupError as e:
                        return self._error(404, str(e), str(e).replace("_", " "))
                    except ValueError as e:
                        return self._error(422, "invalid_response", str(e))
                    except RuntimeError:
                        return self._error(500, "package_invalid", "Installed package failed verification: E-PKG-COURSE")
                if camino == "/v2/media-sessions":
                    ref = str(cuerpo.get("courseId") or "")
                    curso = host.manifiestos.get(ref)
                    if ref in host.invalidos:
                        return self._error(500, "package_invalid", "Installed package failed verification: E-PKG-COURSE")
                    if curso is None:
                        return self._error(404, "course_not_found", "Course not installed")
                    ttl = int(cuerpo.get("ttlSec") or 14400)
                    if not 1 <= ttl <= 28800:
                        return self._error(400, "invalid_parameter", "ttlSec out of range")
                    try:
                        return self._json(200, host._abrir_sesion(curso, cuerpo.get("mediaIds"), cuerpo.get("lessonId"), ttl))
                    except LookupError as e:
                        return self._error(404, str(e), "Lesson not found")
                return self._error(404, "not_found", "Unknown endpoint")

            def do_DELETE(self):
                camino, _, partes = self._entrada()
                if not self._autorizado():
                    return
                if len(partes) == 3 and partes[1] == "media-sessions":
                    for cap, s in list(host.sesiones.items()):
                        if s["id"] == partes[2]:
                            del host.sesiones[cap]
                            self.send_response(204)
                            self.end_headers()
                            return
                    return self._error(404, "media_session_not_found", "Not found")
                return self._error(404, "not_found", "Unknown endpoint")

            def _evaluar(self, cuerpo: dict) -> dict:
                ref = str(cuerpo.get("courseId") or "")
                version = cuerpo.get("version")
                if ref in host.invalidos:
                    raise RuntimeError("package_invalid")
                if ref not in host.manifiestos:
                    raise LookupError("course_not_found")
                curso = host._curso(ref, version)
                if curso is None:
                    raise LookupError("version_not_available")
                hallado = host._objeto(curso, str(cuerpo.get("objectId") or ""))
                if hallado is None:
                    raise LookupError("object_not_found")
                pregunta = host._pregunta(curso, str(cuerpo.get("objectId") or ""), str(cuerpo.get("questionId") or ""))
                if pregunta is None:
                    raise LookupError("question_not_found")
                respuesta = cuerpo.get("response")
                if not isinstance(respuesta, dict):
                    raise ValueError("response must be an object")
                return calificar(pregunta, respuesta)

        return Manejador

    def _manejador_medios(self):
        host = self

        class Medios(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                pass

            def _error(self, estado: int, codigo: str) -> None:
                cuerpo = json.dumps({"error": {"code": codigo, "message": "Not found", "details": {}}}).encode()
                self.send_response(estado)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(cuerpo)

            def _bytes(self, tipo: str, datos: bytes) -> None:
                rango = self.headers.get("Range")
                desde, hasta, parcial = 0, len(datos) - 1, False
                if rango and rango.startswith("bytes="):
                    a, _, b = rango[6:].partition("-")
                    if a == "" and b:
                        desde = max(0, len(datos) - int(b))
                    else:
                        desde = int(a or 0)
                        hasta = int(b) if b else len(datos) - 1
                    parcial = True
                    if desde >= len(datos):
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{len(datos)}")
                        self.end_headers()
                        return
                trozo = datos[desde:hasta + 1]
                self.send_response(206 if parcial else 200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(trozo)))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "no-store")
                if parcial:
                    self.send_header("Content-Range", f"bytes {desde}-{hasta}/{len(datos)}")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(trozo)

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                camino = unquote(urlparse(self.path).path)
                host.peticiones.append(f"MEDIA GET {camino}")
                partes = [p for p in camino.split("/") if p]
                if len(partes) < 3 or partes[0] != "s":
                    return self._error(404, "media_session_not_found")
                sesion = host.sesiones.get(partes[1])
                if sesion is None or sesion["expira"] < time.time():
                    return self._error(404, "media_session_not_found")
                media_id = partes[2]
                if media_id not in sesion["mediaIds"]:
                    return self._error(404, "media_session_not_found")
                resto = "/".join(partes[3:])
                if resto == "@files":
                    curso = host.manifiestos.get(sesion["courseId"]) or {}
                    medio = next((m for m in curso.get("media") or [] if str(m.get("id")) == media_id), {})
                    archivos = sorted(k.split("/", 1)[1] for k in host.medios if k.startswith(media_id + "/") and not k.startswith(media_id + "/@"))
                    cuerpo = json.dumps({"mediaId": media_id, "entry": medio.get("entry"), "files": archivos}).encode()
                    return self._bytes("application/json; charset=utf-8", cuerpo)
                clave = f"{media_id}/{resto}" if resto else media_id
                medio = host.medios.get(clave)
                if medio is None:
                    return self._error(404, "media_session_not_found")
                return self._bytes(*medio)

        return Medios


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("TEMP", "."), "link-pruebas.json")
    ejemplo = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "..", "spec-driven", "02-classroom-engine", "example.json")
    with open(ejemplo, encoding="utf-8") as f:
        manifiesto = json.load(f)
    medios = {m["id"]: ("image/png", PNG_1x1) for m in manifiesto.get("media", []) if m.get("kind") == "image"}
    host = HostContenidoV2Pruebas(ruta, {manifiesto["id"]: manifiesto}, medios=medios).iniciar()
    print(f"API de Contenido v2 de pruebas en http://127.0.0.1:{host.puerto} (medios en {host.puerto_medios}) · link.json en {ruta}")
    print("set AVACOM_CONTENIDO_ENLACE_V2=" + ruta)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        host.detener()
