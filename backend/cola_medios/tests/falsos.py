"""
Dobles de prueba de los puertos de la cola de medios: un índice en memoria, una fuente que se puede hacer lenta o fallar a medias, y un reloj que se mueve a mano.
Con ellos el servidor se prueba con hilos de verdad sin tocar la base de datos (una transacción de prueba no es visible desde otro hilo).
"""
from __future__ import annotations

import dataclasses
import io
import threading
import time
import uuid

from ..aplicacion.almacen import Almacen
from ..aplicacion.config import MIB, Config
from ..aplicacion.puertos import RespuestaDeOrigen
from ..aplicacion.servidor import Servidor
from ..dominio import catalogos as cat
from ..dominio.clave import ClaveMedio
from ..dominio.errores import ErrorDeOrigen


class RelojFalso:
    def __init__(self, ahora: int = 1_000_000_000_000):
        self.ahora = ahora

    def ahora_ms(self) -> int:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += int(segundos * 1000)


class MemoriaFalsa:
    def __init__(self):
        self.datos: dict = {}

    def get(self, clave):
        return self.datos.get(clave)

    def set(self, clave, valor, segundos):
        self.datos[clave] = valor

    def delete(self, clave):
        self.datos.pop(clave, None)


class DifusionFalsa:
    def __init__(self):
        self.avisos: list[tuple[str, str]] = []

    def recurso_cambio(self, modulo, contexto_ref):
        self.avisos.append((modulo, contexto_ref))


class RegistroEnMemoria:
    """Lo mismo que `RegistroOrm`, en un diccionario con candado."""

    def __init__(self):
        self.filas: dict[str, dict] = {}
        self.solicitudes: list[dict] = []
        self.candado = threading.RLock()

    def obtener(self, clave):
        with self.candado:
            fila = next((f for f in self.filas.values() if f["clave"] == clave), None)
            return dict(fila) if fila else None

    def por_id(self, recurso_id):
        with self.candado:
            fila = self.filas.get(recurso_id)
            return dict(fila) if fila else None

    def crear(self, datos):
        with self.candado:
            existente = self.obtener(datos["clave"])
            if existente:
                return existente
            fila = {"tipo_mime": "", "bytes_total": None, "bytes_hechos": 0, "sha256": "", "cabeceras": {}, "intentos": 0, "error_codigo": "",
                    "error_detalle": "", "reintentar_despues": None, "usos": 0, "iniciado_en": None, "terminado_en": None, "validado_en": None,
                    "ultimo_uso_en": None, "curso_version": "", "prioridad": cat.CLASE, **datos}
            self.filas[fila["id"]] = fila
            return dict(fila)

    def actualizar(self, recurso_id, **campos):
        with self.candado:
            fila = self.filas.get(recurso_id)
            if fila is None:
                return None
            fila.update(campos)
            return dict(fila)

    def eliminar(self, recurso_id):
        with self.candado:
            self.filas.pop(recurso_id, None)
            self.solicitudes = [s for s in self.solicitudes if s["recurso_id"] != recurso_id]

    def solicitar(self, recurso_id, *, modulo, contexto_ref, prioridad, persona_id, dispositivo_id, ahora, vence_en):
        with self.candado:
            for s in self.solicitudes:
                if (s["recurso_id"], s["modulo"], s["contexto_ref"], s["persona_id"]) == (recurso_id, modulo, contexto_ref, persona_id):
                    s.update(prioridad=prioridad, vence_en=vence_en)
                    return
            self.solicitudes.append({"recurso_id": recurso_id, "modulo": modulo, "contexto_ref": contexto_ref, "prioridad": prioridad, "persona_id": persona_id,
                                     "vence_en": vence_en})

    def mejor_prioridad(self, recurso_id, ahora):
        with self.candado:
            p = [s["prioridad"] for s in self.solicitudes if s["recurso_id"] == recurso_id and (s["vence_en"] is None or s["vence_en"] > ahora)]
            return min(p) if p else None

    def bajar_proyecciones(self, modulo, contexto_ref, excepto, a):
        with self.candado:
            ids = []
            for s in self.solicitudes:
                if s["modulo"] == modulo and s["contexto_ref"] == contexto_ref and s["prioridad"] == cat.PROYECCION and s["recurso_id"] not in excepto:
                    s["prioridad"] = a
                    ids.append(s["recurso_id"])
            return ids

    def activos(self):
        with self.candado:
            return [dict(f) for f in self.filas.values() if f["estado"] in cat.ACTIVOS]

    def del_contexto(self, contexto_ref, modulo=""):
        with self.candado:
            ids = {s["recurso_id"] for s in self.solicitudes if s["contexto_ref"] == contexto_ref and (not modulo or s["modulo"] == modulo)}
            return [dict(self.filas[i]) for i in ids if i in self.filas]

    def listar(self, estado="", limite=100):
        with self.candado:
            return [dict(f) for f in self.filas.values() if not estado or f["estado"] == estado][:limite]

    def resumen(self):
        with self.candado:
            por_estado = {e: sum(1 for f in self.filas.values() if f["estado"] == e) for e in cat.ESTADOS}
            ocupados = sum((f["bytes_total"] or 0) if f["estado"] == cat.DISPONIBLE else f["bytes_hechos"] for f in self.filas.values())
            return {"por_estado": por_estado, "bytes_ocupados": ocupados, "recursos": len(self.filas)}

    def candidatos_a_expulsion(self):
        with self.candado:
            return [dict(f) for f in self.filas.values() if f["estado"] == cat.DISPONIBLE]

    def aplicar_usos(self, usos):
        with self.candado:
            for recurso_id, (ultimo, veces) in usos.items():
                if recurso_id in self.filas:
                    self.filas[recurso_id]["ultimo_uso_en"] = ultimo
                    self.filas[recurso_id]["usos"] += veces

    def purgar(self, *, fallidos_antes_de, solicitudes_vencidas_antes_de):
        with self.candado:
            n = len(self.filas)
            self.filas = {i: f for i, f in self.filas.items() if not (f["estado"] in (cat.FALLIDO, cat.CANCELADO) and f["actualizado_en"] < fallidos_antes_de)}
            return n - len(self.filas)

    def ids(self):
        with self.candado:
            return set(self.filas)

    def contextos_de(self, recurso_id):
        with self.candado:
            return list({(s["modulo"], s["contexto_ref"]) for s in self.solicitudes if s["recurso_id"] == recurso_id and s["contexto_ref"]})


class FlujoLento:
    """Un flujo que entrega `datos` en trozos con una pausa entre uno y otro, y que puede romperse una vez tras `fallar_tras` bytes."""

    def __init__(self, datos: bytes, retraso: float = 0.0, fallar_tras: int | None = None, puerta: threading.Event | None = None):
        self._io = io.BytesIO(datos)
        self.retraso = retraso
        self.fallar_tras = fallar_tras
        self.leidos = 0
        self.puerta = puerta
        self.cerrado = False

    def read(self, n=-1):
        if self.puerta is not None:
            self.puerta.wait(10)
        if self.retraso:
            time.sleep(self.retraso)
        if self.fallar_tras is not None and self.leidos >= self.fallar_tras:
            self.fallar_tras = None
            raise OSError("la fuente se cortó")
        limite = n if self.fallar_tras is None else min(n, self.fallar_tras - self.leidos)
        trozo = self._io.read(limite)
        self.leidos += len(trozo)
        return trozo

    def close(self):
        self.cerrado = True


class OrigenFalso:
    """Una fuente de medios en memoria: `medios[(curso_ref, media_ref, ruta)] = (tipo, bytes)`. Entiende `Range: bytes=N-` como la de verdad."""

    def __init__(self, medios: dict, version: str = "1.0", cursos: set[str] | None = None):
        self.medios = dict(medios)
        self.version = version
        self.cursos = cursos
        self.llamadas: list[tuple[str, str | None, str]] = []
        self.versiones_pedidas = 0
        self.retraso = 0.0
        self.fallar_tras: int | None = None
        self.puerta: threading.Event | None = None
        self.no_disponible = False
        self.candado = threading.Lock()

    def version_del_curso(self, fuente, curso_ref):
        self.versiones_pedidas += 1
        if self.no_disponible:
            raise ErrorDeOrigen(RuntimeError("la biblioteca está cerrada"), transitorio=True)
        if self.cursos is not None and curso_ref not in self.cursos:
            raise ErrorDeOrigen(LookupError(curso_ref), transitorio=False)
        return self.version

    def abrir(self, clave: ClaveMedio, rango, metodo):
        with self.candado:
            self.llamadas.append((clave.rotulo(), rango, metodo))
        if self.no_disponible:
            raise ErrorDeOrigen(RuntimeError("la biblioteca está cerrada"), transitorio=True)
        medio = self.medios.get((clave.curso_ref, clave.media_ref, clave.ruta))
        if medio is None:
            raise ErrorDeOrigen(LookupError(clave.rotulo()), transitorio=False, codigo="referencia_no_encontrada")
        tipo, datos = medio
        inicio = 0
        estado = 200
        cab = {"content-type": tipo, "accept-ranges": "bytes"}
        if rango and rango.startswith("bytes=") and rango.endswith("-"):
            inicio = int(rango[6:-1])
            estado = 206
            cab["content-range"] = f"bytes {inicio}-{len(datos) - 1}/{len(datos)}"
        cuerpo = datos[inicio:]
        cab["content-length"] = str(len(cuerpo))
        fallar = self.fallar_tras
        self.fallar_tras = None                                  # sólo se rompe la primera lectura
        return RespuestaDeOrigen(estado, cab, FlujoLento(cuerpo, self.retraso, fallar, self.puerta), {"X-Avacom-Marcador": "falso"})


@dataclasses.dataclass
class Montaje:
    servidor: Servidor
    origen: OrigenFalso
    registro: RegistroEnMemoria
    reloj: RelojFalso
    difusion: DifusionFalsa
    memoria: MemoriaFalsa
    almacen: Almacen


def montar(caso, medios: dict, *, version: str = "1.0", **cambios) -> Montaje:
    """Un servidor con todos los puertos falsos y la caché en una carpeta temporal. `cambios` pisa la configuración (`hilos=2`, `max_bytes=…`…)."""
    import shutil
    import tempfile

    carpeta = tempfile.mkdtemp(prefix="avacom-cola-prueba-")
    caso.addCleanup(shutil.rmtree, carpeta, True)
    base = dict(carpeta=carpeta, hilos=0, max_bytes=64 * MIB, libre_min_bytes=0, proteger_seg=0, espera_inicio_seg=3.0, reintentos=2, estancado_seg=5.0, pausa_reintento_seg=0.01)
    base.update(cambios)
    config = Config(**base)
    almacen = Almacen(carpeta)
    almacen.preparar()
    origen = OrigenFalso(medios, version)
    registro, reloj, difusion, memoria = RegistroEnMemoria(), RelojFalso(), DifusionFalsa(), MemoriaFalsa()
    servidor = Servidor(config=config, registro=registro, almacen=almacen, origen=origen, memoria=memoria, difusion=difusion, reloj=reloj)
    caso.addCleanup(servidor.planificador.cerrar)
    return Montaje(servidor, origen, registro, reloj, difusion, memoria, almacen)


def lanzar_hilos(caso, servidor: Servidor, n: int = 2, urgente_primero: bool = False) -> list[threading.Thread]:
    """Hilos de descarga de prueba: lo mismo que `HiloDeDescargas`, sin pasar por el contenedor del proceso."""
    parar = threading.Event()

    def trabajar(urgente: bool):
        while not parar.is_set():
            tarea = servidor.planificador.siguiente(urgente_solo=urgente, segundos=0.1)
            if tarea is not None:
                servidor.descargador.ejecutar(tarea)

    hilos = [threading.Thread(target=trabajar, args=(urgente_primero and i == 0,), daemon=True) for i in range(n)]
    for h in hilos:
        h.start()

    def detener():
        parar.set()
        servidor.planificador.cerrar()
        for h in hilos:
            h.join(2)

    caso.addCleanup(detener)
    return hilos


def leer_todo(local) -> bytes:
    try:
        return local.read(-1)
    finally:
        local.close()


def id_de(montaje: Montaje, clave: ClaveMedio) -> str:
    return montaje.registro.obtener(clave.huella())["id"]


def nuevo_id() -> str:
    return str(uuid.uuid4())
