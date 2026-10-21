"""
Soporte para las PRUEBAS de los módulos que escriben en la cola única (Fase 3 de MOD-015). No es parte de la interfaz de producción (`nodo.servicios`) y ningún caso de uso lo
importa: sólo `<modulo>/tests/`.

  cola(modulo)      lo que ese módulo publicó en `m15_evento`, con el vocabulario de su cola antigua (`id`, `tipo_evento`, `agregado_tipo`, `agregado_id`, `carga`, `creado_en`) y el
                    subconjunto de la API de un manager de Django que las pruebas usaban sobre `m.EventoSalida.objects` (filter · exclude · order_by · get · first · last · latest ·
                    count · exists · values_list · values · iteración y rebanado): la misma prueba lee lo mismo con el mismo texto. `create(...)` publica un evento EN NOMBRE de ese
                    módulo, en su propia transacción, para las pruebas que sembraban una fila en la cola antigua de otro módulo. Nada se puede modificar ni borrar (P-03).
  nodo_limpio()     olvida el estado vivo del nodo (la marca alta del reloj, el ancla, la caché de servicios): una prueba que mueve un reloj falso parte de cero, como las de `nodo`.
  espiar(...)       registra lo que un caso de uso quiso publicar (cada llamada al `publicar` de su adaptador) sin impedir que ocurra: la base de las pruebas de paridad.
  recortar(...)     simula, dentro de la transacción de UNA prueba, una instalación que tenía historia al cortar: retira el corte vacío que dejó la migración y corta de nuevo.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

from django.db import transaction

from . import models as m
from . import servicios

_CAMPOS = {"id": "secuencia", "tipo_evento": "tipo"}
_SOBRE = ("evento_id", "version", "modulo", "actor", "dispositivo_id", "correlacion_id", "clase", "sensibilidad", "catalogado", "carga_omitida")


def _campo(nombre: str) -> str:
    """`tipo_evento` → `tipo`, `-id` → `-secuencia`, `carga__resultado` → `carga__resultado`."""
    signo = "-" if nombre.startswith("-") else ""
    raiz, separador, resto = nombre.lstrip("-").partition("__")
    return signo + _CAMPOS.get(raiz, raiz) + separador + resto


def _condiciones(condiciones: dict) -> dict:
    return {_campo(clave): valor for clave, valor in condiciones.items()}


class Fila:
    """Una fila de `m15_evento` con el vocabulario de las colas antiguas (`id`, `tipo_evento`, …) y, además, el del sobre."""

    def __init__(self, evento: m.Evento):
        self.id = self.secuencia = int(evento.secuencia)
        self.tipo_evento = self.tipo = evento.tipo
        self.agregado_tipo, self.agregado_id, self.carga, self.creado_en = evento.agregado_tipo, evento.agregado_id, evento.carga, int(evento.creado_en)
        for campo in _SOBRE:
            setattr(self, campo, getattr(evento, campo))

    def como_dict(self) -> dict:
        return {"id": self.id, "tipo_evento": self.tipo_evento, "agregado_tipo": self.agregado_tipo, "agregado_id": self.agregado_id, "carga": self.carga,
                "creado_en": self.creado_en, **{campo: getattr(self, campo) for campo in _SOBRE}}

    def __repr__(self) -> str:
        return f"<Evento {self.id} {self.tipo_evento} {self.agregado_tipo}:{self.agregado_id}>"


class Cola:
    def __init__(self, modulo: str, filas=None):
        self.modulo = modulo
        self._filas = filas if filas is not None else m.Evento.objects.filter(modulo=modulo).order_by("secuencia")

    def _con(self, filas) -> "Cola":
        return Cola(self.modulo, filas)

    def filter(self, **condiciones) -> "Cola":
        return self._con(self._filas.filter(**_condiciones(condiciones)))

    def exclude(self, **condiciones) -> "Cola":
        return self._con(self._filas.exclude(**_condiciones(condiciones)))

    def order_by(self, *campos: str) -> "Cola":
        return self._con(self._filas.order_by(*(_campo(c) for c in campos)))

    def all(self) -> "Cola":
        return self._con(self._filas.all())

    def count(self) -> int:
        return self._filas.count()

    def exists(self) -> bool:
        return self._filas.exists()

    def get(self, **condiciones) -> Fila:
        return Fila(self._filas.get(**_condiciones(condiciones)))

    def first(self) -> Fila | None:
        fila = self._filas.first()
        return Fila(fila) if fila else None

    def last(self) -> Fila | None:
        fila = self._filas.last()
        return Fila(fila) if fila else None

    def latest(self, campo: str = "id") -> Fila:
        return Fila(self._filas.latest(_campo(campo)))

    def values_list(self, *campos: str, flat: bool = False):
        return self._filas.values_list(*(_campo(c) for c in campos), flat=flat)

    def values(self, *campos: str) -> list[dict]:
        filas = [f.como_dict() for f in self]
        return filas if not campos else [{c: fila[c] for c in campos} for fila in filas]

    def __iter__(self) -> Iterator[Fila]:
        return (Fila(f) for f in self._filas)

    def __len__(self) -> int:
        return self._filas.count()

    def __getitem__(self, indice):
        if isinstance(indice, slice):
            return [Fila(f) for f in self._filas[indice]]
        return Fila(self._filas[indice])

    def create(self, *, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict, creado_en: int | None = None) -> Fila:
        """Publica un evento EN NOMBRE de este módulo (lo que una prueba sembraba a mano en su cola antigua), en su propia transacción y con la fecha que se le dé."""
        from .aplicacion.publicar import Publicar
        from .infraestructura import contenedor

        s = contenedor.servicios()
        with transaction.atomic(), s.uow(lectura=True) as uow:
            sobre = Publicar(s).ejecutar(uow, modulo=self.modulo, agregado_tipo=agregado_tipo, agregado_id=str(agregado_id), tipo=tipo_evento, carga=carga, creado_en=creado_en)
        return Fila(m.Evento.objects.get(pk=sobre.secuencia))

    def update(self, **_):
        raise TypeError("La cola única es inmutable (P-03): una prueba mueve su reloj, no la fecha de un evento ya publicado.")

    def delete(self):
        raise TypeError("La cola única no se borra desde una prueba: el único borrado es la purga (P-08).")


def cola(modulo: str) -> Cola:
    return Cola(modulo)


def nodo_limpio() -> None:
    from .infraestructura import contenedor

    contenedor.reiniciar()


@contextmanager
def espiar(adaptador, metodo: str = "publicar"):
    """`with espiar(OutboxDjango) as llamadas:` registra `(args, kwargs)` de cada llamada al `publicar` del adaptador del módulo sin impedir que ocurra."""
    original = getattr(adaptador, metodo)
    llamadas: list[tuple[tuple, dict]] = []

    def espia(self, *args, **kwargs):
        llamadas.append((args, kwargs))
        return original(self, *args, **kwargs)

    with mock.patch.object(adaptador, metodo, espia):
        yield llamadas


def recortar(modulo: str, ultima_legada: int) -> dict:
    """Retira el corte (vacío) que dejó la migración del módulo y corta de nuevo con `ultima_legada`, como si la instalación hubiera tenido esa historia al migrar."""
    m.Corte.objects.filter(pk=modulo).delete()
    return servicios.cortar(modulo, int(ultima_legada), asentar=False)


def sembrar_historia(modelo_legado, modulo: str, eventos: list[dict], creado_en: int) -> list[int]:
    """La historia que una instalación tendría en su cola ANTIGUA al migrar: copia `eventos` (`{tipo, agregado_tipo, agregado_id, carga}`, lo que un caso de uso publicó) a la tabla
    antigua del módulo (`modelo_legado`, el `EventoSalida` del propio módulo, que es quien llama) con ids por ENCIMA de la última secuencia global —así ninguna fila de `m15_evento`
    anterior se confunde con la historia— y corta ahí. Devuelve los ids sembrados, en orden."""
    base = servicios.ultima_secuencia()
    ids = []
    for i, e in enumerate(eventos, start=1):
        modelo_legado.objects.create(id=base + i, agregado_tipo=e["agregado_tipo"], agregado_id=e["agregado_id"], tipo_evento=e["tipo"], carga=e["carga"], creado_en=creado_en)
        ids.append(base + i)
    recortar(modulo, base + len(eventos))
    return ids


def como_consumidor(leer, marca: int, tipos=None, limite: int = 3) -> list[dict]:
    """Lee como un consumidor: lotes de `limite` (pequeño, para que un lote cruce el corte) hasta que no queda nada. `leer(marca, limite, tipos) -> (eventos, hasta)`."""
    salida: list[dict] = []
    for _ in range(10_000):
        eventos, hasta = leer(marca, limite, tipos)
        salida += eventos
        if not eventos and hasta <= marca:
            return salida
        marca = hasta
    raise AssertionError("la lectura no termina: `hasta` avanza sin agotar la fuente")
