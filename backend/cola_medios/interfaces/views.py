"""
Rutas de la cola de medios (`/api/medios/cola/`): ver cómo van los recursos y, sólo para el personal, cancelar, reintentar o vaciar.

Leer el estado lo puede hacer cualquier sesión (no lleva bytes ni contenido, sólo referencias y avance); cambiar algo exige no ser una tableta de alumno.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from ..dominio import catalogos as cat
from ..infraestructura.contenedor import servidor


def _recurso(fila: dict) -> dict:
    return {
        "id": fila["id"], "estado": fila["estado"], "prioridad": cat.PRIORIDADES.get(fila["prioridad"], str(fila["prioridad"])),
        "fuente": fila["fuente"], "curso_ref": fila["curso_ref"], "curso_version": fila["curso_version"], "media_ref": fila["media_ref"], "ruta": fila["ruta"],
        "tipo_mime": fila["tipo_mime"], "bytes_total": fila["bytes_total"], "bytes_hechos": fila["bytes_hechos"], "porcentaje": fila.get("porcentaje"),
        "sha256": fila["sha256"], "intentos": fila["intentos"], "error_codigo": fila["error_codigo"], "error_detalle": fila["error_detalle"],
        "usos": fila["usos"], "creado_en": fila["creado_en"], "actualizado_en": fila["actualizado_en"], "terminado_en": fila["terminado_en"],
        "ultimo_uso_en": fila["ultimo_uso_en"],
    }


class VistaCola(APIView):
    permission_classes = [SesionSiSeExige]

    @staticmethod
    def _personal(request) -> bool:
        principal = principal_de(request)
        return principal is None or str(getattr(principal, "menu", "")) != "student"

    def _denegar(self):
        return Response({"detail": "Sólo el personal del aula puede cambiar la cola de medios.", "codigo": "sin_permiso"}, status=status.HTTP_403_FORBIDDEN)


class EstadoView(VistaCola):
    """Cómo va la cola: pendientes, descargas, caché (bytes y espacio), cupos de transferencia y límites vigentes."""

    def get(self, request):
        return Response(servidor().estado())


class RecursosView(VistaCola):
    """`?contexto=<sesión|asignación|intento>` los recursos de ESA clase (con su avance); `?estado=` filtra; `?limite=` (hasta 200)."""

    def get(self, request):
        q = request.query_params
        try:
            limite = max(1, min(200, int(q.get("limite") or 100)))
        except ValueError:
            limite = 100
        estado = q.get("estado") or ""
        if estado and estado not in cat.ESTADOS:
            return Response({"detail": f"Estado desconocido. Estados: {', '.join(cat.ESTADOS)}.", "codigo": "datos_invalidos"}, status=status.HTTP_400_BAD_REQUEST)
        filas = servidor().listar(contexto_ref=q.get("contexto") or "", modulo=q.get("modulo") or "", estado=estado, limite=limite)
        return Response({"recursos": [_recurso(f) for f in filas], "total": len(filas)})


class RecursoView(VistaCola):
    def get(self, request, recurso_id: str):
        fila = next((f for f in servidor().listar(limite=100000) if f["id"] == recurso_id), None)
        if fila is None:
            return Response({"detail": "No existe ese recurso.", "codigo": "no_encontrado"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_recurso(fila))


class CancelarView(VistaCola):
    def post(self, request, recurso_id: str):
        if not self._personal(request):
            return self._denegar()
        if not servidor().cancelar(recurso_id):
            return Response({"detail": "Ese recurso no se puede cancelar (no existe o ya está listo).", "codigo": "conflicto"}, status=status.HTTP_409_CONFLICT)
        return Response({"cancelado": True, "recurso_id": recurso_id})


class ReintentarView(VistaCola):
    def post(self, request, recurso_id: str):
        if not self._personal(request):
            return self._denegar()
        if not servidor().reintentar(recurso_id):
            return Response({"detail": "Ese recurso no se puede reintentar (no existe, ya está en cola o la biblioteca no responde).", "codigo": "conflicto"},
                            status=status.HTTP_409_CONFLICT)
        return Response({"reintentando": True, "recurso_id": recurso_id})


class LimpiarView(VistaCola):
    """Vacía la caché de lo que nadie está leyendo. La próxima petición de cada medio lo vuelve a traer."""

    def post(self, request):
        if not self._personal(request):
            return self._denegar()
        return Response({"expulsados": servidor().limpiar()})
