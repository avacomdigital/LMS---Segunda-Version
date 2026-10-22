"""
Adaptadores de los puertos de MOD-017 sobre Django: los repositorios de `m17_*` (sólo inserción: este archivo no tiene un solo `update` ni `delete`), la cola única de MOD-015
(`nodo.servicios.publicar`, en la transacción del hecho) y la bitácora encadenada de MOD-019 (`audit.servicios.anexar`). Son las ÚNICAS fronteras con otros módulos (R-03).
"""
from __future__ import annotations

from .. import models as m
from ..dominio import catalogos as cat


def _paquete(p: m.Paquete) -> dict:
    return {"paquete_id": p.paquete_id, "nombre": p.nombre, "version_producto": p.version_producto, "serie": int(p.serie), "modulos": list(p.modulos or []), "manifiesto": dict(p.manifiesto or {}),
            "kid": p.kid, "sha256": p.sha256, "bytes": int(p.bytes), "archivo": p.archivo, "origen": p.origen, "recibido_en": int(p.recibido_en), "importado_por": p.importado_por}


def _fila(h: m.Historial) -> dict:
    return {"id": h.id, "paquete_id": h.paquete_id, "tipo": h.tipo, "en": int(h.en), "actor": h.actor, "serie": int(h.serie), "version_producto": h.version_producto, "detalle": dict(h.detalle or {})}


class PaquetesDjango:
    def insertar(self, datos: dict) -> dict:
        return _paquete(m.Paquete.objects.create(**datos))

    def obtener(self, paquete_id: str) -> dict | None:
        p = m.Paquete.objects.filter(paquete_id=str(paquete_id)[:36]).first()
        return None if p is None else _paquete(p)

    def todos(self, limite: int = 200) -> list[dict]:
        return [_paquete(p) for p in m.Paquete.objects.order_by("-recibido_en", "paquete_id")[:limite]]

    def existe_sha(self, sha256: str) -> str | None:
        return m.Paquete.objects.filter(sha256=sha256).values_list("paquete_id", flat=True).first()


class HistorialDjango:
    def insertar(self, datos: dict) -> dict:
        return _fila(m.Historial.objects.create(**datos))

    def de_paquete(self, paquete_id: str) -> list[dict]:
        return [_fila(h) for h in m.Historial.objects.filter(paquete_id=paquete_id).order_by("id")]

    def de_todos(self) -> dict[str, list[dict]]:
        salida: dict[str, list[dict]] = {}
        for h in m.Historial.objects.exclude(paquete_id="").order_by("id"):
            salida.setdefault(h.paquete_id, []).append(_fila(h))
        return salida

    def ultimas(self, limite: int = 100, tipos: tuple[str, ...] | None = None) -> list[dict]:
        consulta = m.Historial.objects.order_by("-id")
        if tipos:
            consulta = consulta.filter(tipo__in=tipos)
        return [_fila(h) for h in consulta[:limite]]

    def rechazado_reciente(self, sha256: str, desde: int) -> bool:
        return m.Historial.objects.filter(tipo=cat.H_RECHAZADO, en__gte=int(desde), detalle__sha256=sha256).exists()


class EventosDelNodo:
    """La cola única de MOD-015 (P-12, P-15): el evento se escribe en la MISMA transacción que el hecho (`publicar` lo exige)."""

    def publicar(self, agregado_tipo: str, agregado_id: str, tipo: str, carga: dict) -> None:
        if tipo not in cat.EVENTOS:
            raise ValueError(f"Evento fuera del catálogo de MOD-017: {tipo}")
        from nodo import servicios as nodo   # frontera entre módulos: sólo en el adaptador
        nodo.publicar(cat.MODULO, agregado_tipo, str(agregado_id)[:256], tipo, carga)


class AuditoriaActualizacion:
    """Anexa a la bitácora encadenada de MOD-019 dentro de la transacción del caso de uso. Nunca lleva rutas de personas ni contenido: ids, versiones, serie, resultado y hash (P-13)."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        if accion not in cat.ACCIONES_DE_AUDITORIA:
            raise ValueError(f"Acción de bitácora fuera del catálogo de MOD-017: {accion}")
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or cat.SISTEMA, accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)
