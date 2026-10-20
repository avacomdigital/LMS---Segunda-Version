"""
Repositorios sobre el ORM de Django para las tablas `m18_*` (los únicos que escriben en ellas: un escritor por tabla, INV-023), la cola de salida y el adaptador de la bitácora
encadenada de MOD-019. El historial y las observaciones son de SÓLO INSERCIÓN: este archivo no tiene un solo `update()` ni `delete()` sobre ellos (una prueba lo comprueba).
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from .. import models as m


def _licencia(fila: m.Licencia) -> dict:
    return {"id": fila.id, "licencia_id": fila.licencia_id, "serie": fila.serie, "kid": fila.kid, "tipo": fila.tipo, "archivo": bytes(fila.archivo) if fila.archivo is not None else None,
            "sha256": fila.sha256, "instalada_en": fila.instalada_en, "instalada_por": fila.instalada_por}


class InstalacionDjango:
    @staticmethod
    def _dict(fila: m.Instalacion) -> dict:
        return {"instalada_en": fila.instalada_en, "version_primera": fila.version_primera, "creada_en": fila.creada_en}

    def obtener(self) -> dict | None:
        fila = m.Instalacion.objects.filter(pk="nodo").first()
        return self._dict(fila) if fila else None

    def crear(self, ahora: int, version: str) -> dict:
        fila, _ = m.Instalacion.objects.get_or_create(pk="nodo", defaults={"instalada_en": ahora, "version_primera": str(version or "")[:32], "creada_en": ahora})
        return self._dict(fila)


class HistorialDjango:
    def vigente(self) -> dict | None:
        ultima = m.Licencia.objects.order_by("-id").first()
        return _licencia(ultima) if ultima is not None and ultima.tipo != cat.H_LIBERADA else None

    def ultima(self) -> dict | None:
        ultima = m.Licencia.objects.order_by("-id").first()
        return _licencia(ultima) if ultima is not None else None

    def insertar(self, datos: dict) -> dict:
        fila = m.Licencia.objects.create(licencia_id=str(datos["licencia_id"])[:36], serie=int(datos["serie"]), kid=str(datos.get("kid") or "")[:64], tipo=datos["tipo"],
                                         archivo=datos.get("archivo"), sha256=str(datos.get("sha256") or "")[:64], instalada_en=int(datos["instalada_en"]),
                                         instalada_por=str(datos.get("instalada_por") or "")[:64])
        return _licencia(fila)

    def todas(self, limite: int = 50) -> list[dict]:
        return [_licencia(f) for f in m.Licencia.objects.order_by("-id")[:limite]]

    def liberadas(self) -> set[tuple[str, int]]:
        ultimo: dict[tuple[str, int], str] = {}
        for licencia_id, serie, tipo in m.Licencia.objects.order_by("id").values_list("licencia_id", "serie", "tipo"):
            ultimo[(licencia_id, int(serie))] = tipo
        return {clave for clave, tipo in ultimo.items() if tipo == cat.H_LIBERADA}


class ObservacionesDjango:
    @staticmethod
    def _dict(fila: m.Observacion) -> dict:
        return {"tipo": fila.tipo, "licencia_id": fila.licencia_id, "serie": fila.serie, "en": fila.en, "detalle": fila.detalle}

    def registrar(self, tipo: str, ahora: int, licencia_id: str = "", serie: int = 0, detalle: dict | None = None) -> dict:
        return self._dict(m.Observacion.objects.create(tipo=tipo, en=int(ahora), licencia_id=str(licencia_id or "")[:36], serie=int(serie or 0), detalle=detalle or {}))

    def ultima(self, tipo: str, licencia_id: str | None = None, serie: int | None = None) -> dict | None:
        consulta = m.Observacion.objects.filter(tipo=tipo)
        if licencia_id is not None:
            consulta = consulta.filter(licencia_id=licencia_id)
        if serie is not None:
            consulta = consulta.filter(serie=serie)
        fila = consulta.order_by("-en", "-id").first()
        return self._dict(fila) if fila else None


class MarcaDjango:
    def valor(self) -> int:
        fila = m.MarcaAlta.objects.filter(pk="nodo").first()
        return int(fila.valor) if fila else 0

    def subir(self, valor: int, ahora: int) -> None:
        fila, creada = m.MarcaAlta.objects.get_or_create(pk="nodo", defaults={"valor": int(valor), "actualizada_en": int(ahora)})
        if not creada and int(valor) > fila.valor:
            m.MarcaAlta.objects.filter(pk="nodo", valor__lt=int(valor)).update(valor=int(valor), actualizada_en=int(ahora))


class ConsumoDjango:
    def guardar(self, ahora: int, equipos: int, usuarios: int) -> None:
        m.Consumo.objects.update_or_create(pk="nodo", defaults={"calculado_en": int(ahora), "equipos": int(equipos), "usuarios": int(usuarios)})

    def leer(self) -> dict | None:
        fila = m.Consumo.objects.filter(pk="nodo").first()
        return {"calculado_en": fila.calculado_en, "equipos": fila.equipos, "usuarios": fila.usuarios} if fila else None


class OutboxDjango:
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict, clave: str | None = None) -> bool:
        if tipo_evento not in cat.EVENTOS:
            raise ValueError(f"Evento fuera del catálogo de MOD-018: {tipo_evento}")
        datos = {"agregado_tipo": agregado_tipo, "agregado_id": str(agregado_id)[:64], "tipo_evento": tipo_evento, "carga": carga}
        if clave is None:
            m.EventoSalida.objects.create(**datos)
            return True
        _, creado = m.EventoSalida.objects.get_or_create(clave=str(clave)[:190], defaults=datos)
        return creado

    def existentes(self, claves: list[str]) -> set[str]:
        return set(m.EventoSalida.objects.filter(clave__in=[str(c)[:190] for c in claves]).values_list("clave", flat=True)) if claves else set()


class AuditoriaLicencia:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`, app `audit`) dentro de la transacción del caso de uso. Nunca lleva el contenido de una licencia ni huellas crudas."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or cat.SISTEMA, accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)

    def ultima_marca(self) -> int | None:
        from audit import servicios as auditoria
        return auditoria.ultima_marca()
