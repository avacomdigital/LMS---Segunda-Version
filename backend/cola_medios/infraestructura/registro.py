"""El índice persistente de la cola (`cm_recurso`, `cm_solicitud`) sobre el ORM de Django. Implementa el puerto `Registro`: todo entra y sale como diccionarios."""
from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Min, Q, Sum

from ..dominio import catalogos as cat
from ..models import Recurso, Solicitud

_CAMPOS = [f.attname for f in Recurso._meta.concrete_fields]


def _fila(r: Recurso | None) -> dict | None:
    return None if r is None else {c: getattr(r, c) for c in _CAMPOS}


class RegistroOrm:
    def obtener(self, clave: str) -> dict | None:
        return _fila(Recurso.objects.filter(clave=clave).first())

    def por_id(self, recurso_id: str) -> dict | None:
        return _fila(Recurso.objects.filter(pk=recurso_id).first())

    def crear(self, datos: dict) -> dict:
        try:
            with transaction.atomic():
                return _fila(Recurso.objects.create(**datos))
        except IntegrityError:          # otra petición lo creó justo antes: es el mismo recurso
            return self.obtener(datos["clave"])

    def actualizar(self, recurso_id: str, **campos) -> dict | None:
        if campos:
            Recurso.objects.filter(pk=recurso_id).update(**campos)
        return self.por_id(recurso_id)

    def eliminar(self, recurso_id: str) -> None:
        Recurso.objects.filter(pk=recurso_id).delete()

    # ------------------------------------------------------------ solicitudes
    def solicitar(self, recurso_id: str, *, modulo: str, contexto_ref: str, prioridad: int, persona_id: str, dispositivo_id: str, ahora: int,
                  vence_en: int | None) -> None:
        igual = Solicitud.objects.filter(recurso_id=recurso_id, modulo=modulo, contexto_ref=contexto_ref, persona_id=persona_id)
        if igual.update(prioridad=prioridad, dispositivo_id=dispositivo_id, creada_en=ahora, vence_en=vence_en):
            return
        try:
            with transaction.atomic():
                Solicitud.objects.create(id=str(uuid.uuid4()), recurso_id=recurso_id, modulo=modulo, contexto_ref=contexto_ref, prioridad=prioridad,
                                         persona_id=persona_id, dispositivo_id=dispositivo_id, creada_en=ahora, vence_en=vence_en)
        except IntegrityError:
            pass          # otra petición creó la misma solicitud justo antes: da lo mismo

    def mejor_prioridad(self, recurso_id: str, ahora: int) -> int | None:
        vigentes = Solicitud.objects.filter(recurso_id=recurso_id).filter(Q(vence_en__isnull=True) | Q(vence_en__gt=ahora))
        return vigentes.aggregate(m=Min("prioridad"))["m"]

    def bajar_proyecciones(self, modulo: str, contexto_ref: str, excepto: list[str], a: int) -> list[str]:
        consulta = Solicitud.objects.filter(modulo=modulo, contexto_ref=contexto_ref, prioridad=cat.PROYECCION).exclude(recurso_id__in=excepto)
        ids = list(consulta.values_list("recurso_id", flat=True).distinct())
        if ids:
            consulta.update(prioridad=a)
            Recurso.objects.filter(pk__in=ids, prioridad=cat.PROYECCION).update(prioridad=a)
        return ids

    def contextos_de(self, recurso_id: str) -> list[tuple[str, str]]:
        return list(Solicitud.objects.filter(recurso_id=recurso_id).exclude(contexto_ref="").values_list("modulo", "contexto_ref").distinct())

    # ----------------------------------------------------------------- consultas
    def activos(self) -> list[dict]:
        return [_fila(r) for r in Recurso.objects.filter(estado__in=cat.ACTIVOS).order_by("prioridad", "creado_en")]

    def del_contexto(self, contexto_ref: str, modulo: str = "") -> list[dict]:
        filtro = Q(solicitudes__contexto_ref=contexto_ref)
        if modulo:
            filtro &= Q(solicitudes__modulo=modulo)
        return [_fila(r) for r in Recurso.objects.filter(filtro).distinct().order_by("creado_en")]

    def listar(self, estado: str = "", limite: int = 100) -> list[dict]:
        consulta = Recurso.objects.all()
        if estado:
            consulta = consulta.filter(estado=estado)
        return [_fila(r) for r in consulta.order_by("-actualizado_en")[:limite]]

    def resumen(self) -> dict:
        por_estado = {e: 0 for e in cat.ESTADOS}
        for fila in Recurso.objects.values("estado").annotate(n=Count("id")):
            por_estado[fila["estado"]] = fila["n"]
        ocupados = (Recurso.objects.filter(estado=cat.DISPONIBLE).aggregate(s=Sum("bytes_total"))["s"] or 0) \
            + (Recurso.objects.exclude(estado=cat.DISPONIBLE).aggregate(s=Sum("bytes_hechos"))["s"] or 0)
        return {"por_estado": por_estado, "bytes_ocupados": int(ocupados), "recursos": sum(por_estado.values())}

    def candidatos_a_expulsion(self) -> list[dict]:
        return [_fila(r) for r in Recurso.objects.filter(estado=cat.DISPONIBLE)]

    def ids(self) -> set[str]:
        return set(Recurso.objects.values_list("id", flat=True))

    # ---------------------------------------------------------------- mantenimiento
    def aplicar_usos(self, usos: dict[str, tuple[int, int]]) -> None:
        with transaction.atomic():
            for recurso_id, (ultimo, veces) in usos.items():
                Recurso.objects.filter(pk=recurso_id).update(ultimo_uso_en=ultimo, usos=F("usos") + veces)

    def purgar(self, *, fallidos_antes_de: int, solicitudes_vencidas_antes_de: int) -> int:
        n = Recurso.objects.filter(estado__in=(cat.FALLIDO, cat.CANCELADO), actualizado_en__lt=fallidos_antes_de).delete()[0]
        n += Solicitud.objects.filter(vence_en__isnull=False, vence_en__lt=solicitudes_vencidas_antes_de).delete()[0]
        return n
