"""
Fuente de cursos REAL: AVACOM Biblioteca a través de la **API de Contenido v2**
(`biblioteca.contenido_v2`). MOD-007 no abre sockets: reutiliza el descubrimiento de
`link.json`, el token, el reintento único tras 401, el tiempo de espera y la
degradación que viven en ese módulo.

Qué pide y cómo:
  GET  /v2/courses                                  → las fichas de los cursos instalados (la lista del panel)
  GET  /v2/courses/{id}?mode=class&profile=…        → el esquema del curso, y por cada lección con objetos
  GET  /v2/courses/{id}/lessons/{lid}?mode&profile  → la lección completa; juntos forman el curso 1.0 que normaliza el aula
  POST /v2/media-sessions + GET en mediaPort        → bytes del medio, en paso a través
  POST /v2/evaluate · /v2/evaluate/batch            → el veredicto, siempre con `version`

Traducción de los códigos de error del contrato a los del aula:
  sin link.json / puerto muerto / sin respuesta          → FuenteNoDisponible (503, estado normal)
  index_rebuilding (503)                                 → FuenteNoDisponible con «vuelve a intentarlo»
  course_not_found · version_not_available (404)         → CursoNoEncontrado
  not_found · lesson_not_found · object_not_found ·
  question_not_found · media_session_not_found (404)     → ReferenciaNoEncontrada
  policy_disabled · disabled_by_policy (403)             → DesactivadoPorPolitica (404 para el aula)
  invalid_parameter (400) · invalid_response (422)       → DatosInvalidos
  unauthorized tras el reintento (401) · answer_keys_forbidden · demás → FuenteError (502)
"""
from __future__ import annotations

from biblioteca import contenido_v2 as v2
from biblioteca.cliente import BibliotecaError, BibliotecaNoDisponible

from ..aplicacion.puertos import Bytes
from ..dominio.errores import (
    CapacidadAusente,
    CursoNoEncontrado,
    DatosInvalidos,
    DesactivadoPorPolitica,
    FuenteError,
    FuenteNoDisponible,
    PaqueteInvalido,
    ReferenciaNoEncontrada,
)

MODO_AULA = "class"                                   # el aula siempre pide el curso en modo clase
PERFIL_POR_ROL = {"docente": "teacher", "estudiante": "student"}
SUGERENCIA_INDICE = "La biblioteca está reconstruyendo su índice; vuelve a intentarlo en unos segundos."
SUGERENCIA_PAQUETE = ("El paquete instalado no pasa la verificación de AVACOM Contenido (E-PKG-*): "
                      "reinstálalo o pide a la biblioteca una versión publicada con el esquema vigente.")

CODIGOS_CURSO = ("course_not_found", "version_not_available")
CODIGOS_REFERENCIA = ("not_found", "lesson_not_found", "object_not_found", "question_not_found", "media_session_not_found")
CODIGOS_POLITICA = ("policy_disabled", "disabled_by_policy")


def _traducir(error: Exception, *, curso_ref: str = "", media_ref: str = "", pregunta_ref: str = "") -> Exception:
    if isinstance(error, BibliotecaNoDisponible):
        return FuenteNoDisponible(error.motivo, sugerencia=error.sugerencia)
    if not isinstance(error, BibliotecaError):
        return error
    codigo, estado, detalle = error.codigo, error.estado, error.detalle
    extra = {"codigo_biblioteca": codigo} if codigo else {}
    if codigo == "index_rebuilding" or estado == 503:
        return FuenteNoDisponible(detalle or "La biblioteca está reconstruyendo su índice.", sugerencia=SUGERENCIA_INDICE, **extra)
    if codigo in CODIGOS_POLITICA:
        return DesactivadoPorPolitica(detalle, curso_ref=curso_ref, **extra)
    if codigo == "package_invalid":
        # Visto en vivo con AVACOM Contenido 2.1.7 (500): el paquete está instalado pero no pasa la
        # verificación (E-PKG-COURSE…). No está en el openapi entregado; se trata como código propio.
        return PaqueteInvalido(detalle or "El paquete instalado no pasa la verificación de la biblioteca.",
                               sugerencia=SUGERENCIA_PAQUETE, estado_biblioteca=estado,
                               **({"curso_ref": curso_ref} if curso_ref else {}), **extra)
    if codigo in CODIGOS_CURSO:
        return CursoNoEncontrado(detalle, curso_ref=curso_ref, **extra)
    if codigo in CODIGOS_REFERENCIA or estado == 404:
        if media_ref or pregunta_ref or codigo in ("object_not_found", "question_not_found", "media_session_not_found"):
            return ReferenciaNoEncontrada(detalle, media_ref=media_ref, pregunta_ref=pregunta_ref, **extra)
        return CursoNoEncontrado(detalle, curso_ref=curso_ref, **extra)
    if codigo in ("invalid_parameter", "invalid_response") or estado in (400, 422):
        return DatosInvalidos(detalle, **extra)
    if estado == 501:
        return CapacidadAusente(detalle, capacidades=error.capacidades)
    return FuenteError(detalle, estado_biblioteca=estado, **extra)


class FuenteBiblioteca:
    nombre = "biblioteca"

    def cursos(self) -> list[dict]:
        """Las fichas de `GET /v2/courses` convertidas en cursos «de esquema»: el panel sólo
        necesita clasificación, título, portada y conteos, no las láminas. Lo que la política
        desactivó no viene en la lista (§7 del mapeo)."""
        try:
            fichas = v2.cursos()
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            raise _traducir(error) from error
        salida = []
        for ficha in fichas:
            ref = str(ficha.get("courseId") or ficha.get("id") or "")
            if not ref:
                continue
            if "lessons" in ficha:
                salida.append(dict(ficha, id=ref))
                continue
            try:
                # El esquema trae `media` (para la portada) y las lecciones con sus objetos resumidos.
                salida.append(v2.esquema_curso(ref, modo=MODO_AULA, perfil="student"))
            except (BibliotecaNoDisponible, BibliotecaError) as error:
                traducido = _traducir(error, curso_ref=ref)
                if isinstance(traducido, PaqueteInvalido):
                    # La biblioteca lo lista pero no lo sirve: la ficha se queda en el panel, marcada, para
                    # que el docente sepa que existe y por qué no se abre. Sin lecciones ni portada.
                    salida.append({**ficha, "id": ref, "lessons": [], "media": [],
                                   "no_disponible": {"codigo": traducido.codigo, "detalle": traducido.detalle,
                                                     "codigo_biblioteca": "package_invalid", "sugerencia": SUGERENCIA_PAQUETE}})
                    continue
                if isinstance(traducido, (CursoNoEncontrado, DesactivadoPorPolitica, ReferenciaNoEncontrada)):
                    continue
                raise traducido from error
        return salida

    def curso(self, curso_ref: str, *, version: str | None = None, rol: str = "estudiante", semilla: str | None = None) -> dict:
        try:
            datos = v2.curso(curso_ref, version=version, modo=MODO_AULA, perfil=PERFIL_POR_ROL.get(rol, "student"), semilla=semilla)
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            raise _traducir(error, curso_ref=curso_ref) from error
        if not isinstance(datos, dict):
            raise FuenteError("La biblioteca no devolvió un curso.", curso_ref=curso_ref)
        return datos

    def medio(self, curso_ref: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str) -> Bytes:
        try:
            respuesta = v2.abrir_medio(curso_ref, media_ref, ruta, rango, metodo)
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            raise _traducir(error, curso_ref=curso_ref, media_ref=media_ref) from error
        return Bytes(respuesta.headers.get("Content-Type") or "application/octet-stream", flujo=respuesta)

    def evaluar(self, curso_ref: str, version: str, objeto_ref: str, pregunta_ref: str, respuesta: dict) -> dict:
        try:
            return v2.evaluar(curso_ref, version, objeto_ref, pregunta_ref, respuesta)
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            raise _traducir(error, curso_ref=curso_ref, pregunta_ref=pregunta_ref) from error

    def evaluar_lote(self, curso_ref: str, version: str, items: list[dict]) -> list[dict]:
        try:
            return v2.evaluar_lote([{"courseId": curso_ref, "version": version, **item} for item in items])
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            raise _traducir(error, curso_ref=curso_ref) from error

    def esquema(self, curso_ref: str) -> dict:
        try:
            datos = v2.esquema_curso(curso_ref, modo="exam", perfil="student")      # con `mode=class` el examen (modo `exam`) no aparece
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            raise _traducir(error, curso_ref=curso_ref) from error
        if not isinstance(datos, dict):
            raise FuenteError("La biblioteca no devolvió el esquema del curso.", curso_ref=curso_ref)
        return datos

    def examen_pool(self, curso_ref: str, objeto_ref: str) -> dict:
        try:
            return v2.examen_pool(curso_ref, objeto_ref)
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            raise _traducir(error, curso_ref=curso_ref) from error

    def examen_preguntas(self, curso_ref: str, objeto_ref: str, ids: list[str], semilla: str | None = None) -> dict:
        try:
            return v2.examen_preguntas(curso_ref, objeto_ref, ids, semilla)
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            raise _traducir(error, curso_ref=curso_ref, pregunta_ref=",".join(ids)) from error

    def estado(self) -> dict:
        return v2.estado()
