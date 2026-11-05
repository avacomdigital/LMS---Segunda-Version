"""
Adaptadores de los puertos de MOD-016 sobre Django: los repositorios de `m16_*` (sólo inserción salvo el ajuste), la cola única de MOD-015 (`nodo.servicios.publicar`, en la transacción
del hecho) y la bitácora encadenada de MOD-019 (`audit.servicios.anexar`). Son las ÚNICAS fronteras con otros módulos (R-03).
"""
from __future__ import annotations

from django.db import IntegrityError, transaction

from .. import models as m
from ..dominio import catalogos as cat
from ..dominio import programacion


def _respaldo(r: m.Respaldo) -> dict:
    return {"respaldo_id": r.respaldo_id, "tipo": r.tipo, "base_id": r.base_id, "disparo": r.disparo, "archivo": r.archivo, "sha256": r.sha256, "bytes": int(r.bytes),
            "bytes_claro": int(r.bytes_claro), "creado_en": int(r.creado_en), "secuencia_global": int(r.secuencia_global), "version_producto": r.version_producto, "nodo_id": r.nodo_id,
            "entradas": int(r.entradas), "archivos": int(r.archivos), "incluye_reinstalable": bool(r.incluye_reinstalable), "con_custodia": bool(r.con_custodia), "creado_por": r.creado_por}


def _fila(h: m.Historial) -> dict:
    return {"id": h.id, "respaldo_id": h.respaldo_id, "tipo": h.tipo, "en": int(h.en), "actor": h.actor, "detalle": dict(h.detalle or {})}


class RespaldosDjango:
    def insertar(self, datos: dict) -> dict:
        return _respaldo(m.Respaldo.objects.create(**datos))

    def obtener(self, respaldo_id: str) -> dict | None:
        r = m.Respaldo.objects.filter(respaldo_id=str(respaldo_id)[:36]).first()
        return None if r is None else _respaldo(r)

    def todos(self, limite: int = 500) -> list[dict]:
        return [_respaldo(r) for r in m.Respaldo.objects.order_by("-creado_en", "respaldo_id")[:limite]]

    def existe_sha(self, sha256: str) -> str | None:
        return m.Respaldo.objects.filter(sha256=sha256).values_list("respaldo_id", flat=True).first()


class HistorialDjango:
    def insertar(self, datos: dict) -> dict:
        return _fila(m.Historial.objects.create(**datos))

    def de_respaldo(self, respaldo_id: str) -> list[dict]:
        return [_fila(h) for h in m.Historial.objects.filter(respaldo_id=respaldo_id).order_by("id")]

    def de_todos(self) -> dict[str, list[dict]]:
        salida: dict[str, list[dict]] = {}
        for h in m.Historial.objects.exclude(respaldo_id="").order_by("id"):
            salida.setdefault(h.respaldo_id, []).append(_fila(h))
        return salida

    def ultimas(self, limite: int = 100, tipos: tuple[str, ...] | None = None) -> list[dict]:
        consulta = m.Historial.objects.order_by("-id")
        if tipos:
            consulta = consulta.filter(tipo__in=tipos)
        return [_fila(h) for h in consulta[:limite]]


class AjusteDjango:
    def obtener(self) -> dict:
        a, _ = m.Ajuste.objects.get_or_create(id=1, defaults={"dias": list(cat.DIAS)})
        return {"activo": a.activo, "hora_min": int(a.hora_min), "dias": list(a.dias or cat.DIAS), "completo_cada_dias": int(a.completo_cada_dias), "retencion": int(a.retencion),
                "incluir_reinstalable": bool(a.incluir_reinstalable), "destino": a.destino}

    def guardar(self, datos: dict, en: int, por: str) -> dict:
        campos = {k: datos[k] for k in programacion.a_dict(programacion.Programa())}
        m.Ajuste.objects.update_or_create(id=1, defaults={**campos, "programado_en": int(en), "programado_por": por[:cat.MAX_ACTOR]})
        return self.obtener()


class PasesDjango:
    def usar(self, pase_id: str, en: int, permiso: str, tecnico: str, kid: str, respaldo_id: str = "") -> bool:
        try:
            with transaction.atomic():
                m.PaseUsado.objects.create(pase_id=str(pase_id)[:64], usado_en=int(en), permiso=permiso[:32], tecnico=tecnico[:120], kid=kid[:32], respaldo_id=respaldo_id[:36])
            return True
        except IntegrityError:
            return False


    def todos(self) -> list[dict]:
        return [{"pase_id": p.pase_id, "usado_en": int(p.usado_en), "permiso": p.permiso, "tecnico": p.tecnico, "kid": p.kid, "respaldo_id": p.respaldo_id} for p in m.PaseUsado.objects.all()]

    def reinsertar(self, filas: list[dict]) -> None:
        """Vuelve a anotar pases ya gastados (tras restaurar la base); los que ya están se dejan como están."""
        for f in filas:
            m.PaseUsado.objects.get_or_create(pase_id=f["pase_id"], defaults={k: f[k] for k in ("usado_en", "permiso", "tecnico", "kid", "respaldo_id")})


class EventosDelNodo:
    """La cola única de MOD-015: el evento se escribe en la MISMA transacción que el hecho (`publicar` lo exige)."""

    def publicar(self, agregado_tipo: str, agregado_id: str, tipo: str, carga: dict) -> None:
        if tipo not in cat.EVENTOS:
            raise ValueError(f"Evento fuera del catálogo de MOD-016: {tipo}")
        from nodo import servicios as nodo   # frontera entre módulos: sólo en el adaptador
        nodo.publicar(cat.MODULO, agregado_tipo, str(agregado_id)[:256], tipo, carga)


class AuditoriaRespaldo:
    """Anexa a la bitácora encadenada de MOD-019 dentro de la transacción del caso de uso. Nunca lleva rutas ni contenido: ids, tipos, cifras y huellas cortas."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        if accion not in cat.ACCIONES_DE_AUDITORIA:
            raise ValueError(f"Acción de bitácora fuera del catálogo de MOD-016: {accion}")
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or cat.SISTEMA, accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)

    def del_modulo(self) -> list[dict]:
        """Lo que el módulo ha asentado hasta ahora (para volver a asentar lo que una restauración se lleve)."""
        from audit import servicios as auditoria
        return auditoria.asientos_de_modulo(cat.MODULO)

    def cola(self) -> dict:
        from audit import servicios as auditoria
        return auditoria.cola_de_la_bitacora()

    def recuperar(self, previos: list[dict]) -> int:
        """
        Tras restaurar, vuelve a asentar —con su hora y su autor originales y la marca `recuperado_tras_restauracion`— los asientos del módulo que la base restaurada ya no trae: una
        restauración devuelve TODA la base al instante del respaldo, y sin esto desaparecerían de la bitácora viva las exportaciones, los pases rechazados y las restauraciones abortadas
        de ese tramo (el respaldo de seguridad previo los conserva, pero la bitácora es la que se audita). Idempotente. Devuelve cuántos volvió a asentar.
        """
        from audit import servicios as auditoria
        actuales = {(x["accion"], x["ocurrido_en"], x["objeto_id"] or "") for x in auditoria.asientos_de_modulo(cat.MODULO)}
        n = 0
        for x in previos:
            if x["accion"] not in cat.ACCIONES_DE_AUDITORIA or (x["accion"], x["ocurrido_en"], x["objeto_id"] or "") in actuales:
                continue
            nuevo = dict(x["valor_nuevo"]) if isinstance(x["valor_nuevo"], dict) else ({} if x["valor_nuevo"] is None else {"valor": x["valor_nuevo"]})
            nuevo["recuperado_tras_restauracion"] = True
            auditoria.anexar(x["usuario_id"] or cat.SISTEMA, x["accion"], x["objeto_tabla"] or "", x["objeto_id"] or "", x["valor_anterior"], nuevo, motivo=x["motivo"],
                             resultado=x["resultado"], ocurrido_en=x["ocurrido_en"])
            n += 1
        return n
