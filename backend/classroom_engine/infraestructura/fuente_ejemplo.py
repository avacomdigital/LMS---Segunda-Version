"""
Fuente de cursos de EJEMPLO: el manifiesto `example.json` (curso «Ciencias naturales ·
Estados de la materia y sus cambios») leído del disco EN CADA petición.

Existe para probar el aula sin AVACOM Biblioteca instalada. Tiene la misma forma que la
fuente real (`FuenteBiblioteca`, API de Contenido v2): el resto del módulo no distingue
una de otra. No escribe nada, no cachea nada y no guarda el curso en ninguna tabla
(regla de oro, artículo 14). Lo único que NO hace es calificar: la clave se compara
sólo donde vive, así que `evaluar` responde 501 en vez de simular un veredicto.
"""
from __future__ import annotations

import json
import os
from urllib.parse import unquote

from ..aplicacion.puertos import Bytes
from ..dominio.errores import CapacidadAusente, CursoNoEncontrado, FuenteNoDisponible, ReferenciaNoEncontrada
from . import marcadores

ALIAS = ("ejemplo", "ciencias-naturales")   # atajos para el endpoint de prueba


class FuenteEjemplo:
    nombre = "ejemplo"

    def __init__(self, ruta: str):
        self.ruta = ruta

    # ------------------------------------------------------------ manifiesto
    def _leer(self) -> dict:
        if not self.ruta or not os.path.exists(self.ruta):
            raise FuenteNoDisponible(
                f"No hay manifiesto de ejemplo en {self.ruta or '(sin ruta)'}.",
                sugerencia="Define AVACOM_AULA_CURSO_EJEMPLO con la ruta de example.json o usa la fuente «biblioteca».",
            )
        try:
            with open(self.ruta, encoding="utf-8") as archivo:
                datos = json.load(archivo)
        except (OSError, json.JSONDecodeError) as error:
            raise FuenteNoDisponible(f"El manifiesto de ejemplo no se pudo leer: {error}",
                                     sugerencia="Revisa que example.json sea un JSON válido.") from error
        if not isinstance(datos, dict) or "lessons" not in datos:
            raise FuenteNoDisponible("El manifiesto de ejemplo no tiene la forma esperada (falta `lessons`).")
        return datos

    def cursos(self) -> list[dict]:
        return [self._leer()]

    def curso(self, curso_ref: str, *, version: str | None = None, rol: str = "estudiante", semilla: str | None = None) -> dict:
        """El manifiesto completo (el normalizador quita las claves y las notas según el rol).
        Sólo existe una versión: pedir otra es no encontrarla, igual que en la biblioteca."""
        manifiesto = self._leer()
        if curso_ref in ALIAS or curso_ref == str(manifiesto.get("id", "")):
            if version and version != str(manifiesto.get("version", "")):
                raise CursoNoEncontrado(f"La fuente de ejemplo sólo tiene la versión {manifiesto.get('version')}.",
                                        curso_ref=curso_ref, version=version)
            return manifiesto
        raise CursoNoEncontrado(f"La fuente de ejemplo sólo conoce «{manifiesto.get('id')}».", curso_ref=curso_ref)

    # ------------------------------------------------------------- evaluar
    def evaluar(self, curso_ref: str, version: str, objeto_ref: str, pregunta_ref: str, respuesta: dict) -> dict:
        raise CapacidadAusente(
            "La fuente de ejemplo no califica: la clave se compara sólo donde vive, en AVACOM Biblioteca (POST /v2/evaluate).",
            capacidades=[], sugerencia="Usa la fuente «biblioteca» para evaluar respuestas.")

    def evaluar_lote(self, curso_ref: str, version: str, items: list[dict]) -> list[dict]:
        return [self.evaluar(curso_ref, version, i.get("objectId", ""), i.get("questionId", ""), i.get("response") or {}) for i in items]

    def estado(self) -> dict:
        try:
            manifiesto = self._leer()
        except FuenteNoDisponible as error:
            return {"disponible": False, "motivo": error.detalle, "sugerencia": error.sugerencia, "ruta": self.ruta,
                    "huella": "", "cursos_instalados": []}
        return {"disponible": True, "motivo": "", "sugerencia": None, "ruta": self.ruta,
                "huella": f"ejemplo-{manifiesto.get('id')}@{manifiesto.get('version')}",
                "cursos_instalados": [{"curso_ref": str(manifiesto.get("id", "")), "version": str(manifiesto.get("version", "")),
                                       "titulo": manifiesto.get("title")}]}

    # ---------------------------------------------------------------- medios
    def medio(self, curso_ref: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str) -> Bytes:
        manifiesto = self.curso(curso_ref)
        medio = next((x for x in manifiesto.get("media", []) if str(x.get("id")) == media_ref), None)
        if medio is None:
            raise ReferenciaNoEncontrada(f"El medio «{media_ref}» no está en el manifiesto de ejemplo.", media_ref=media_ref)
        clase = str(medio.get("kind", ""))
        titulo = str(medio.get("title") or media_ref)
        ruta = unquote(ruta).strip("/") if ruta else None
        cabeceras = {"X-Avacom-Rotulo": titulo.encode("ascii", "replace").decode(), "X-Avacom-Marcador": "ejemplo"}

        if ruta == "subtitulos":
            if not medio.get("captionsPath"):
                raise ReferenciaNoEncontrada("Este medio no tiene subtítulos.", media_ref=media_ref)
            return Bytes("text/vtt; charset=utf-8", marcadores.vtt_minimo(titulo, medio.get("durationSec")), cabeceras=cabeceras)
        if ruta == "transcripcion":
            if not medio.get("transcriptPath"):
                raise ReferenciaNoEncontrada("Este medio no tiene transcripción.", media_ref=media_ref)
            return Bytes("text/plain; charset=utf-8", marcadores.transcripcion_minima(titulo), cabeceras=cabeceras)

        if clase == "image":
            return Bytes("image/png", marcadores.png_marcador(medio.get("width"), medio.get("height")), cabeceras=cabeceras)
        if clase == "audio":
            return Bytes("audio/wav", marcadores.wav_tono(min(float(medio.get("durationSec") or 1.0), 2.0)), cabeceras=cabeceras)
        if clase == "pdf":
            return Bytes("application/pdf", marcadores.pdf_minimo(titulo, int(medio.get("pageCount") or 1),
                                                                  [medio.get("path", ""), "Este PDF lo genera el LMS como marcador."]),
                         cabeceras=cabeceras)
        if clase == "simulation":
            entrada = str(medio.get("entry") or "index.html")
            if ruta not in (None, "", entrada, "index.html"):
                raise ReferenciaNoEncontrada(f"La simulación de ejemplo sólo sirve su entrada «{entrada}».", ruta=ruta)
            sim = medio.get("simulation") or {}
            parametros = _parametros_de(manifiesto, media_ref)
            return Bytes("text/html; charset=utf-8", marcadores.html_simulacion(
                titulo, sim.get("provider"), parametros, sim.get("designWidth"), sim.get("designHeight"), list(sim.get("shims") or [])),
                cabeceras=cabeceras)
        if clase == "video":
            raise ReferenciaNoEncontrada(
                f"El paquete de ejemplo no incluye el archivo de video «{medio.get('path')}»; lo servirá AVACOM Biblioteca.",
                media_ref=media_ref, sugerencia="Prueba el reproductor con la fuente «biblioteca» o con un MP4 local.")
        raise ReferenciaNoEncontrada(f"Clase de medio «{clase}» sin marcador de ejemplo.", media_ref=media_ref)


def _parametros_de(manifiesto: dict, media_ref: str) -> dict:
    """Los `launchParams` del primer laboratorio que use este medio (sólo para pintar el marcador)."""
    for leccion in manifiesto.get("lessons", []):
        for objeto in leccion.get("objects", []):
            if objeto.get("type") == "simulation_lab" and str(objeto.get("mediaId")) == media_ref:
                return dict(objeto.get("launchParams") or {})
    return {}
