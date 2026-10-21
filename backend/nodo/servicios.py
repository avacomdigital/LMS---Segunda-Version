"""
La interfaz de MOD-015 para los OTROS módulos del mismo proceso (BR-004): quien publica un hecho, quien lee una fuente, quien registra un consumidor o pregunta qué hora es, lo hace
aquí; nadie lee ni escribe `m15_*`. Lo que una vista HTTP de `/api/nodo/` hace, también pasa por aquí.

  publicar(...)                   el evento en la MISMA transacción que el hecho; fuera de ella falla (BR-001, R-02). Un INSERT (R-08).
  leer(modulo, desde, limite, tipos)   la fachada: la tabla antigua del módulo (si está cortado) y después `m15_evento`, como un flujo continuo (P-05)
  registrar_lector_legado / cortar     lo que un módulo hace al pasar a la cola única (Fase 3)
  registrar_consumidor / aplicar_lote / aplicar_hasta_vaciar / marca / reproducir / reprocesar     el registro de consumidores y su ayudante único (P-06, P-07)
  ahora_ms()                      el reloj del nodo: `max(reloj del sistema, marca alta)` (P-13)
  nuevo_id()                      el generador de identificadores (Q-38: hoy UUID4; cinco segmentos con Q-N2)
  estado() / estado_resumido() / cola() / problemas() / purgar()     lo que ven la pantalla técnica y `/health/`
  arrancar() / parar()            las anclas y la fila de arranque (P-10 en lo que toca a la Fase 2)

Regla de la casa (R-01): nada de aquí detiene una clase. Lo que no es `publicar` ni una lectura, nunca lanza hacia un programador (se registra).
"""
from __future__ import annotations

import logging

from .aplicacion.puertos import Actor, Aplicador, LectorLegado
from .dominio import catalogos as cat
from .dominio import sobre as dom_sobre

log = logging.getLogger("avacom.nodo")


def _s():
    from .infraestructura import contenedor
    return contenedor.servicios()


# ----------------------------------------------------------------------------------------------------------------------- publicar y leer

def publicar(modulo: str, agregado_tipo: str, agregado_id: str, tipo: str, carga: dict, *, actor: str | None = None, dispositivo_id: str | None = None,
             correlacion_id: str | None = None, version: int | None = None) -> dict:
    """El sobre completo, con su `secuencia`. Exige una transacción abierta en la conexión (la del hecho)."""
    from .aplicacion.publicar import Publicar
    s = _s()
    with s.uow(lectura=True) as uow:
        return Publicar(s).ejecutar(uow, modulo=modulo, agregado_tipo=agregado_tipo, agregado_id=agregado_id, tipo=tipo, carga=carga, actor=actor, dispositivo_id=dispositivo_id,
                                    correlacion_id=correlacion_id, version=version).como_dict()


def leer(modulo: str, desde: int, limite: int, tipos: tuple[str, ...] | None = None) -> tuple[list[dict], int]:
    """`(eventos, hasta_donde_se_miró)` de esa fuente con secuencia MAYOR a `desde`, en orden. Lectura pura, sin transacción."""
    from .aplicacion.leer import Leer
    s = _s()
    with s.uow(lectura=True) as uow:
        return Leer(s).ejecutar(uow, modulo, int(desde), int(limite), tipos)


def ultima_secuencia(modulo: str | None = None) -> int:
    s = _s()
    with s.uow(lectura=True) as uow:
        return uow.eventos.ultima_secuencia(modulo)


def registrar_lector_legado(modulo: str, lector: LectorLegado) -> None:
    """Lo que un módulo cortado registra al cargar: la función que lee SU tabla antigua (`id ≤ hasta`). La cola no lee tablas ajenas (R-09)."""
    _s().legados[modulo] = lector


def cortar(modulo: str, ultima_legada: int, *, actor: str = cat.SISTEMA, version_contrato: int = 1) -> dict:
    """El corte de un módulo (Fase 3, P-05): una transacción propia con la fila del corte y el salto del contador."""
    from .aplicacion.leer import Cortar
    s = _s()
    with s.uow() as uow:
        corte = Cortar(s).ejecutar(uow, modulo, ultima_legada, actor=actor, version_contrato=version_contrato)
        return {"modulo": corte.modulo, "ultima_legada": corte.ultima_legada, "cortado_en": corte.cortado_en, "contador": uow.eventos.contador()}


def corte_de(modulo: str) -> dict | None:
    s = _s()
    with s.uow(lectura=True) as uow:
        c = uow.cortes.get(modulo)
        return None if c is None else {"modulo": c.modulo, "ultima_legada": c.ultima_legada, "cortado_en": c.cortado_en}


# ----------------------------------------------------------------------------------------------------------------------- consumidores

def registrar_consumidor(nombre: str, modulo: str, fuentes: tuple[str, ...] | list[str], tipos: tuple[str, ...] | list[str] = (), *, version_contrato: int = 1,
                         limite_rezago: int | None = None, aplicar: Aplicador | None = None, actor: str = cat.SISTEMA) -> dict:
    """Registra (o actualiza) un consumidor y deja sus marcas listas (cero para uno nuevo, BR-007). Un contrato incompatible se rechaza (INV-007)."""
    from .aplicacion.consumidores import RegistrarConsumidor
    from .dominio.errores import ContratoIncompatible
    s = _s()
    try:
        with s.uow() as uow:
            return RegistrarConsumidor(s).ejecutar(uow, nombre, modulo, fuentes, tipos, version_contrato=version_contrato, limite_rezago=limite_rezago, actor=actor, aplicar=aplicar)
    except ContratoIncompatible as error:
        with s.uow() as uow:        # el asiento sobrevive al error (la transacción del registro ya se revirtió)
            uow.auditoria.registrar(actor, cat.A_MODULO_INCOMPATIBLE, "m15_consumidor", nombre, nuevo=error.extra.get("asiento"))
        raise


def desregistrar_consumidor(nombre: str, *, actor: str = cat.SISTEMA) -> bool:
    from .aplicacion.consumidores import DesregistrarConsumidor
    s = _s()
    with s.uow() as uow:
        return DesregistrarConsumidor(s).ejecutar(uow, nombre, actor=actor)


def aplicar_lote(consumidor: str, fuente: str, aplicar: Aplicador | None = None, limite: int | None = None) -> dict:
    """UN lote: lee sin bloqueo, bloquea y relee, aísla cada evento, avanza la marca en la misma transacción, reintenta y aparta (P-06, P-07)."""
    from .aplicacion.consumidores import AplicarLote
    return AplicarLote(_s()).ejecutar(consumidor, fuente, aplicar, limite)


def aplicar_hasta_vaciar(consumidor: str, fuente: str, aplicar: Aplicador | None = None, paginas: int = 20, limite: int | None = None) -> dict:
    from .aplicacion.consumidores import AplicarLote
    return AplicarLote(_s()).hasta_vaciar(consumidor, fuente, aplicar, paginas, limite)


def marca(consumidor: str, fuente: str) -> int:
    s = _s()
    with s.uow(lectura=True) as uow:
        return uow.marcas.estado(consumidor, fuente)[0]


def reproducir(consumidor: str, fuente: str | None = None, *, actor: Actor | None = None, desde_el_sistema: bool = False) -> dict:
    from .aplicacion.consumidores import Reproducir
    return Reproducir(_s()).ejecutar(actor or Actor(id=cat.SISTEMA), consumidor, fuente, desde_el_sistema=desde_el_sistema or actor is None)


def reprocesar(problema_id: int, actor: Actor) -> dict:
    from .aplicacion.consumidores import Reprocesar
    return Reprocesar(_s()).ejecutar(actor, int(problema_id))


def cola(actor: Actor | None = None) -> dict:
    from .aplicacion.consumidores import EstadoDeCola
    return EstadoDeCola(_s()).ejecutar(actor or Actor(id=cat.SISTEMA), desde_el_sistema=actor is None)


def problemas(actor: Actor, consumidor: str | None = None, estado: str | None = None, limite: int = 100) -> dict:
    from .aplicacion.consumidores import ListarProblemas
    return ListarProblemas(_s()).ejecutar(actor, consumidor, estado, limite)


# ----------------------------------------------------------------------------------------------------------------------- reloj, ids, estado

def ahora_ms() -> int:
    """El reloj del nodo (BR-062, INV-017, P-13): `max(reloj del sistema, marca alta)`."""
    return _s().ahora_ms()


def nuevo_id() -> str:
    return dom_sobre.nuevo_id()


def estado(actor: Actor | None = None) -> dict:
    """El estado del nodo evaluado ahora (y publicado si cambió). Con `actor`, exige `node.health.read`."""
    from .aplicacion.estado import EstadoDelNodo
    s = _s()
    return EstadoDelNodo(s).ejecutar(actor) if actor is not None else EstadoDelNodo(s).evaluar()


def estado_resumido() -> dict:
    """Lo que `/health/` añade (campo aditivo `nodo`). Nunca lanza, nunca escribe."""
    try:
        from .aplicacion.estado import EstadoDelNodo
        return EstadoDelNodo(_s()).resumido()
    except Exception as error:   # noqa: BLE001 — el health nunca falla por el nodo
        return {"estado": "desconocido", "motivos": [], "restringido": False, "error": str(error)}


def purgar(actor: Actor | None = None, *, forzar: bool = False) -> dict:
    from .aplicacion.purga import Purgar
    return Purgar(_s()).ejecutar(actor, forzar=forzar)


# ----------------------------------------------------------------------------------------------------------------------- arranque y parada

def arrancar() -> dict | None:
    """Lo llama `asgi.py` al levantar el proceso. Nunca lanza (R-01): si algo falla, se registra y el nodo sigue."""
    from .aplicacion.arranque import Arrancar
    s = _s()
    try:
        s.salud.comprobar_integridad()
        resultado = Arrancar(s).ejecutar()
        from .aplicacion.estado import EstadoDelNodo
        EstadoDelNodo(s).evaluar()
        return resultado
    except Exception:   # noqa: BLE001
        log.exception("El arranque del nodo (cola única) no se pudo registrar: el nodo sigue", extra={"evento": "nodo.arranque_fallo", "ruta": "bad"})
        s.vivo.arrancado = True
        return None


def parar() -> None:
    """La parada limpia (gancho `atexit`; la Fase 5 la llama también desde el servicio). Nunca lanza."""
    from .aplicacion.arranque import Parar
    Parar(_s()).ejecutar()
