"""
El contenido visto desde el modo de estudio: los CASOS DE USO DEL AULA (`classroom_engine.aplicacion.casos_uso`) sobre la fuente de cursos, sin
duplicar nada. Se reutiliza `ConsultarCurso` (la vista de aula sin claves), `AbrirMedio` (los bytes de un medio) y la calificación de la
biblioteca (`fuente.evaluar_lote`, la misma degradación que `EnviarRespuestas`). Sólo cambia una cosa: las URL de los medios apuntan a las rutas de
este módulo (`/api/modo-estudio/asignaciones/{id}/medios/…`), que sirven el contenido autorizado por asignación.

Regla de oro (artículo 14): nada se cachea ni se guarda. Cada llamada vuelve a preguntar a la fuente. La clave de una respuesta sólo vive en la
biblioteca: aquí sólo pasan lo que el alumno contestó y el veredicto que devuelve.

Los errores del aula se traducen a los del módulo: `FuenteNoDisponible` (503, con `sugerencia`), `NoEncontrado` (curso, lección, medio o política),
`DatosInvalidos` y `FuenteError` (la fuente contestó con error).
"""
from __future__ import annotations

import dataclasses
import hashlib
from urllib.parse import quote, urlencode

from acceso.interfaces.medios import con_pase
from classroom_engine.aplicacion import casos_uso as casos_aula
from classroom_engine.aplicacion.puertos import Bytes
from classroom_engine.dominio import curso as curso_aula
from classroom_engine.dominio import errores as e7
from classroom_engine.dominio import respuestas as respuestas_aula
from classroom_engine.infraestructura.contenedor import servicios as servicios_aula

from cola_medios import servicio as cola

from ..dominio import bloques as bloques_dom
from ..dominio import errores as e8

TROZO = 64 * 1024
FICHA = ("fuente", "esquema", "curso_ref", "version", "titulo", "subtitulo", "idioma", "clasificacion", "duracion_estimada_min", "modos", "portada_url")


def traducir(error: Exception) -> Exception:
    """Un error del aula → su equivalente en MOD-008. Lo que no es del aula se deja tal cual."""
    if isinstance(error, e7.FuenteNoDisponible):
        return e8.FuenteNoDisponible(error.detalle, sugerencia=error.sugerencia, **error.extra)
    if isinstance(error, (e7.NoEncontrado, e7.DesactivadoPorPolitica)):
        return e8.NoEncontrado(error.detalle, codigo_fuente=error.codigo, **error.extra)
    if isinstance(error, e7.DatosInvalidos):
        return e8.DatosInvalidos(error.detalle, **error.extra)
    if isinstance(error, e7.ErrorAula):
        return e8.FuenteError(error.detalle, codigo_fuente=error.codigo, **error.extra)
    return error


class ContenidoAula:
    """Implementa el puerto `Contenido` con `classroom_engine`."""

    @staticmethod
    def _aula(url_medio=None):
        base = servicios_aula()
        return dataclasses.replace(base, url_medio=url_medio) if url_medio is not None else base

    @staticmethod
    def _url_de_medios(asignacion_id: str, dispositivo: str, alumno_id: str):
        """Las URL de los medios de una asignación. Llevan `dispositivo` (y `alumno_id` si el alumno no es el dueño del aparato) porque las pide un
        visor (WebView, imagen) que no puede mandar cabeceras: así la ruta sabe quién pregunta y desde dónde."""
        consulta = urlencode([(k, v) for k, v in (("dispositivo", dispositivo), ("alumno_id", alumno_id)) if v])

        def url(_fuente: str, _curso_ref: str, media_ref: str, ruta: str | None) -> str:
            base = f"/api/modo-estudio/asignaciones/{quote(asignacion_id, safe='')}/medios/{quote(media_ref, safe='')}/"
            if ruta:
                base += quote(ruta.strip("/"), safe="/")
            return con_pase(f"{base}?{consulta}" if consulta else base)

        return url

    # ------------------------------------------------------------------------------ la lección
    def leccion(self, *, fuente: str, curso_ref: str, leccion_ref: str, asignacion_id: str = "", dispositivo: str = "",
                alumno_id: str = "", semilla: str | None = None) -> dict:
        aula = self._aula(self._url_de_medios(asignacion_id, dispositivo, alumno_id))
        try:
            vista = casos_aula.ConsultarCurso(aula).ejecutar(curso_ref, "estudiante", fuente or None, None, semilla)
            hallado = curso_aula.localizar(vista, leccion_ref=leccion_ref)
        except e7.ErrorAula as error:
            raise traducir(error) from error
        leccion = hallado["leccion"]
        catalogo = {str(x.get("media_ref")): x for x in vista.get("medios") or [] if isinstance(x, dict)}
        medios = {}
        for ref in bloques_dom.medios_de_leccion(leccion):
            medio = catalogo.get(ref)
            medios[ref] = {"clase": medio.get("clase"), "mime": medio.get("mime"), "titulo": medio.get("titulo")} if medio else {}
        # La portada no es un medio de la lección: no se sirve por la asignación, así que su URL no serviría de nada.
        return {"fuente": vista["fuente"], "curso": {**{k: vista.get(k) for k in FICHA}, "portada_url": None}, "leccion": leccion, "medios": medios}

    def version_instalada(self, fuente: str, curso_ref: str) -> str | None:
        try:
            estado = self._aula().fuente(fuente or None, curso_ref).estado()
        except Exception:      # noqa: BLE001 — la versión es un dato de cortesía: sin él, un paquete no vence por versión
            return None
        for curso in estado.get("cursos_instalados") or []:
            if str(curso.get("curso_ref")) == curso_ref:
                return str(curso.get("version") or "") or None
        return None

    # -------------------------------------------------------------------------------- los medios
    def _abrir(self, fuente: str, curso_ref: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str) -> Bytes:
        try:
            return casos_aula.AbrirMedio(self._aula()).ejecutar(curso_ref, media_ref, ruta, rango, metodo, fuente or None)
        except e7.ErrorAula as error:
            raise traducir(error) from error

    def abrir_medio(self, fuente: str, curso_ref: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str) -> Bytes:
        """Por la cola de medios del nodo: lo trae de la fuente UNA vez y lo reparte a todas las tabletas. Si la cola no puede ayudar, se abre en
        paso a través como siempre. La asignación ya decidió que este alumno puede leerlo: la cola sólo reparte bytes."""
        try:
            return cola.abrir_medio(fuente=fuente or None, curso_ref=curso_ref, media_ref=media_ref, ruta=ruta, rango=rango, metodo=metodo,
                                    modulo=cola.MODULO_ESTUDIO, prioridad=cola.ESTUDIO,
                                    directo=lambda: self._abrir(fuente, curso_ref, media_ref, ruta, rango, metodo))
        except e7.ErrorAula as error:
            raise traducir(error) from error

    def tamano_de(self, fuente: str, curso_ref: str, media_ref: str) -> int | None:
        try:
            medio = self.abrir_medio(fuente, curso_ref, media_ref, None, None, "HEAD")
        except Exception:      # noqa: BLE001 — sólo es una estimación
            return None
        if medio.datos is not None:
            return len(medio.datos)
        flujo = medio.flujo
        try:
            longitud = flujo.headers.get("Content-Length") if flujo is not None else None
            return int(longitud) if longitud is not None else None
        except (TypeError, ValueError):
            return None
        finally:
            if flujo is not None:
                flujo.close()

    def medir(self, fuente: str, curso_ref: str, media_ref: str, tope_bytes: int, contexto_ref: str = "") -> dict:
        """Tamaño y SHA-256 del medio. Por la cola: el primer alumno que pide un paquete lo trae a la caché del nodo y los demás reutilizan la medida
        (con 35 tabletas, una descarga en vez de 35). Sin la cola, se lee entero como siempre."""
        try:
            medido = cola.medir_medio(fuente=fuente or None, curso_ref=curso_ref, media_ref=media_ref, tope_bytes=tope_bytes,
                                      modulo=cola.MODULO_ESTUDIO, prioridad=cola.PAQUETE, contexto_ref=contexto_ref)
        except cola.DemasiadoGrande as error:
            raise e8.MedioDemasiadoGrande(f"El medio «{media_ref}» supera el tope de {tope_bytes} bytes.", media_ref=media_ref) from error
        except e7.ErrorAula as error:
            raise traducir(error) from error
        if medido is not None:
            return medido
        medio = self._abrir(fuente, curso_ref, media_ref, None, None, "GET")
        if medio.datos is not None:      # el manifiesto de ejemplo genera los bytes en memoria
            if len(medio.datos) > tope_bytes:
                raise e8.MedioDemasiadoGrande(f"El medio «{media_ref}» supera el tope de {tope_bytes} bytes.", media_ref=media_ref)
            return {"bytes": len(medio.datos), "sha256": hashlib.sha256(medio.datos).hexdigest(), "mime": medio.tipo}
        huella, total, flujo = hashlib.sha256(), 0, medio.flujo
        try:
            while True:
                trozo = flujo.read(TROZO)
                if not trozo:
                    break
                total += len(trozo)
                if total > tope_bytes:
                    raise e8.MedioDemasiadoGrande(f"El medio «{media_ref}» supera el tope de {tope_bytes} bytes.", media_ref=media_ref)
                huella.update(trozo)
        except OSError as error:      # la biblioteca se cortó a mitad del medio
            raise e8.FuenteNoDisponible(f"La biblioteca dejó de responder mientras se leía «{media_ref}».") from error
        finally:
            flujo.close()
        return {"bytes": total, "sha256": huella.hexdigest(), "mime": medio.tipo}

    # ------------------------------------------------------------------------------- calificar
    def calificar(self, fuente: str, curso_ref: str, version: str, items: list[dict]) -> dict[str, dict | None]:
        """La clave se compara DONDE VIVE. Mismo criterio que `EnviarRespuestas._calificar` del aula: un lote; sin biblioteca (o sin la capacidad)
        todo queda sin calificar; si el lote falla por una respuesta mal formada, se prueban una por una (con tope) para no dejar sin veredicto
        a las demás."""
        sin_nota = {i["pregunta_ref"]: None for i in items}
        if not items:
            return {}
        try:
            origen = self._aula().fuente(fuente or None, curso_ref)
        except Exception:      # noqa: BLE001 — sin fuente no hay veredicto, pero la respuesta se guarda
            return sin_nota
        lote = [{"objectId": i["objeto_ref"], "questionId": i["pregunta_ref"], "response": dict(i["respuesta"])} for i in items]
        try:
            crudos = origen.evaluar_lote(curso_ref, version, lote)
            por_pregunta = {str(c.get("questionId") or ""): c for c in crudos}
            return {i["pregunta_ref"]: respuestas_aula.veredicto(por_pregunta.get(i["pregunta_ref"], crudos[n] if n < len(crudos) else {}),
                                                                 i["pregunta_ref"]) for n, i in enumerate(items)}
        except (e7.FuenteNoDisponible, e7.CapacidadAusente):
            return sin_nota                    # la fuente no está: probar una por una sólo sumaría esperas
        except Exception:      # noqa: BLE001
            pass
        veredictos = dict(sin_nota)
        for i in items[:20]:
            try:
                crudo = origen.evaluar(curso_ref, version, i["objeto_ref"], i["pregunta_ref"], dict(i["respuesta"]))
                veredictos[i["pregunta_ref"]] = respuestas_aula.veredicto(crudo, i["pregunta_ref"])
            except Exception:      # noqa: BLE001
                veredictos[i["pregunta_ref"]] = None
        return veredictos
