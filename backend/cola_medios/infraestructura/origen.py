"""
La fuente de los bytes: los MISMOS casos de uso del aula que los módulos ya usaban para abrir un medio (`AbrirMedio` sobre la fuente de cursos del
aula), de modo que la cola no toca la capa de biblioteca: pide lo que pedía cada módulo, sólo que una vez y con un hilo propio.

Los errores del aula (`ErrorAula`) y de la biblioteca (`BibliotecaError`, `BibliotecaNoDisponible`) se entregan envueltos en `ErrorDeOrigen`, que lleva el
original: la vista lo desenvuelve y responde exactamente lo que respondía antes.
"""
from __future__ import annotations

import io

from biblioteca.cliente import BibliotecaError, BibliotecaNoDisponible
from classroom_engine.aplicacion import casos_uso as casos_aula
from classroom_engine.dominio import errores as e7
from classroom_engine.infraestructura.contenedor import servicios as servicios_aula

from ..aplicacion.puertos import RespuestaDeOrigen
from ..dominio.clave import ClaveMedio
from ..dominio.errores import ErrorDeOrigen

TRANSITORIOS = (e7.FuenteNoDisponible, e7.FuenteError, e7.CapacidadAusente)


def _envolver(error: Exception) -> ErrorDeOrigen:
    if isinstance(error, e7.ErrorAula):
        return ErrorDeOrigen(error, transitorio=isinstance(error, TRANSITORIOS), codigo=error.codigo)
    if isinstance(error, BibliotecaNoDisponible):
        return ErrorDeOrigen(error, transitorio=True, codigo="biblioteca_no_disponible")
    return ErrorDeOrigen(error, transitorio=getattr(error, "estado", 500) >= 500, codigo=getattr(error, "codigo", "") or "biblioteca_error")


class OrigenDeAula:
    def abrir(self, clave: ClaveMedio, rango: str | None, metodo: str) -> RespuestaDeOrigen:
        try:
            medio = casos_aula.AbrirMedio(servicios_aula()).ejecutar(clave.curso_ref, clave.media_ref, clave.ruta or None, rango, metodo, clave.fuente or None)
        except (e7.ErrorAula, BibliotecaError, BibliotecaNoDisponible) as error:
            raise _envolver(error) from error
        extra = {k: v for k, v in (medio.cabeceras or {}).items() if str(k).lower().startswith("x-avacom-")}
        if medio.flujo is not None:
            cabeceras = {str(k).lower(): str(v) for k, v in medio.flujo.headers.items()}
            estado = getattr(medio.flujo, "status", None) or getattr(medio.flujo, "code", None) or 200
            return RespuestaDeOrigen(int(estado), cabeceras, medio.flujo, extra)
        datos = medio.datos or b""            # el manifiesto de ejemplo genera los bytes en memoria: no entiende `Range`, se entrega entero
        return RespuestaDeOrigen(200, {"content-type": medio.tipo, "content-length": str(len(datos))}, io.BytesIO(datos), extra)

    def version_del_curso(self, fuente: str, curso_ref: str) -> str:
        try:
            origen = servicios_aula().fuente(fuente or None, curso_ref)
            estado = origen.estado()
        except (e7.ErrorAula, BibliotecaError, BibliotecaNoDisponible) as error:
            raise _envolver(error) from error
        if not estado.get("disponible") or estado.get("reconstruyendo_indice"):
            raise ErrorDeOrigen(e7.FuenteNoDisponible(estado.get("motivo") or "La biblioteca no está disponible.", sugerencia=estado.get("sugerencia")),
                                transitorio=True, codigo="fuente_no_disponible")
        for curso in estado.get("cursos_instalados") or []:
            if str(curso.get("curso_ref")) == curso_ref:
                return str(curso.get("version") or "")
        raise ErrorDeOrigen(e7.CursoNoEncontrado(f"El curso «{curso_ref}» no está disponible en la biblioteca.", curso_ref=curso_ref), transitorio=False,
                            codigo="curso_no_encontrado")
