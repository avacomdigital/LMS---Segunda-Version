"""
El descargador: trae UN recurso de AVACOM Contenido a la caché del nodo.

  1. Pide los bytes a la fuente (con `Range: bytes=N-` si ya tiene los primeros N de un intento anterior) y lee el tamaño de sus cabeceras.
  2. Hace sitio: si no cabe en la caché o en el disco, expulsa lo que lleva más tiempo sin usarse; si aun así no cabe, falla con `sin_espacio`.
  3. Escribe en el archivo del recurso trozo a trozo, calcula el SHA-256 al vuelo y avanza el contador de la tarea: las peticiones que ya siguen esa
     descarga leen lo que va llegando.
  4. Verifica el tamaño, deja la fila `disponible` con su huella y avisa.

Si falla por algo transitorio (la fuente no contestó, se cortó la lectura) reintenta con espera creciente; si es definitivo (el medio ya no existe, no cabe)
se rinde de inmediato y lo dice. Una descarga a medias se CONSERVA en disco para reanudarla.
"""
from __future__ import annotations

import hashlib
import http.client
import logging
import threading
import time

from ..dominio import catalogos as cat
from ..dominio import errores as err
from ..dominio import politica
from ..dominio.rangos import total_de_content_range
from ..dominio.ritmo import Cubo
from .almacen import Almacen
from .config import Config
from .planificador import Planificador
from .puertos import Difusion, Memoria, Origen, Registro, Reloj, RespuestaDeOrigen
from .tarea import Tarea

log = logging.getLogger("avacom.cola_medios")

PROGRESO_CADA_BYTES = 4 * 1024 * 1024
PROGRESO_CADA_SEG = 1.0


class Descargador:
    def __init__(self, *, config: Config, registro: Registro, almacen: Almacen, origen: Origen, memoria: Memoria, difusion: Difusion, reloj: Reloj,
                 planificador: Planificador, entrada: Cubo, contextos: "Contextos"):
        self.cfg = config
        self.registro = registro
        self.almacen = almacen
        self.origen = origen
        self.memoria = memoria
        self.difusion = difusion
        self.reloj = reloj
        self.planificador = planificador
        self.entrada = entrada
        self.contextos = contextos
        self.hecho_espacio = threading.Lock()      # una sola expulsión a la vez
        self._reservas: dict[str, int] = {}        # bytes que las descargas en curso todavía van a escribir (para que dos no usen el mismo hueco)

    # ---------------------------------------------------------------- una tarea
    def ejecutar(self, tarea: Tarea) -> None:
        """Lleva la tarea hasta `disponible` o `fallido`/`cancelado`. Nunca lanza: el resultado queda en la tarea y en la base."""
        ahora = self.reloj.ahora_ms()
        tarea.marcar(cat.DESCARGANDO)
        self.registro.actualizar(tarea.id, estado=cat.DESCARGANDO, iniciado_en=ahora, actualizado_en=ahora, error_codigo="", error_detalle="",
                                 reintentar_despues=None)
        self._avisar(tarea)
        ultimo: Exception | None = None
        codigo = cat.INTERNO
        for intento in range(1, self.cfg.reintentos + 1):
            if tarea.cancelar:
                break
            try:
                self.registro.actualizar(tarea.id, intentos=intento)
                self._descargar(tarea)
                return
            except err.Cancelado:
                break
            except err.ErrorDeOrigen as error:
                ultimo, codigo = error, (cat.ORIGEN_NO_DISPONIBLE if error.transitorio else cat.NO_ENCONTRADO)
                if not error.transitorio:
                    break
            except err.SinEspacio as error:
                ultimo, codigo = error, cat.SIN_ESPACIO
                break
            except err.ErrorDeCola as error:
                ultimo, codigo = error, error.codigo or cat.INCOMPLETO
            except Exception as error:   # noqa: BLE001 — un fallo del nodo no puede matar el hilo de descargas
                log.exception("La descarga de %s falló", tarea.clave.rotulo(), extra={"evento": "medios.cola.descarga_fallo"})
                ultimo, codigo = error, cat.INTERNO
            if intento < self.cfg.reintentos:
                self._pausa(min(self.cfg.pausa_reintento_seg * 2.0 ** (intento - 1), 8.0), tarea)
        self._cerrar_sin_exito(tarea, ultimo, codigo)

    def _pausa(self, segundos: float, tarea: Tarea) -> None:
        fin = time.monotonic() + segundos
        while time.monotonic() < fin and not tarea.cancelar:
            time.sleep(min(0.1, max(0.0, fin - time.monotonic())))

    def _cerrar_sin_exito(self, tarea: Tarea, error: Exception | None, codigo: str) -> None:
        ahora = self.reloj.ahora_ms()
        if tarea.cancelar:
            self.almacen.borrar(tarea.id)
            self.registro.actualizar(tarea.id, estado=cat.CANCELADO, bytes_hechos=0, actualizado_en=ahora, terminado_en=ahora, error_codigo=cat.CANCELADO_POR_USUARIO,
                                     error_detalle="La preparación se canceló.")
            tarea.terminar(cat.CANCELADO, codigo=cat.CANCELADO_POR_USUARIO)
        else:
            espera = self.cfg.reintentar_sin_espacio_seg if codigo in cat.SIN_REINTENTO else self.cfg.reintentar_fallido_seg
            detalle = (error.original.detalle if isinstance(error, err.ErrorDeOrigen) and hasattr(error.original, "detalle") else str(error or ""))[:500]
            if codigo == cat.NO_ENCONTRADO:
                # Que la biblioteca diga «ese medio no existe» (o el curso ya no se ofrece) no es una falla de la cola: no deja fila ni sale en el panel. Quien lo
                # esperaba recibe el error original (404 de siempre) por la tarea; la siguiente petición lo vuelve a preguntar, como hacía el paso a través.
                self.almacen.borrar(tarea.id)
                self.registro.eliminar(tarea.id)
            else:
                if codigo == cat.SIN_ESPACIO:
                    self.almacen.borrar(tarea.id)
                # (en los demás casos la descarga parcial se conserva: el siguiente intento la reanuda)
                self.registro.actualizar(tarea.id, estado=cat.FALLIDO, actualizado_en=ahora, terminado_en=ahora, error_codigo=codigo, error_detalle=detalle,
                                         reintentar_despues=ahora + espera * 1000)
            tarea.terminar(cat.FALLIDO, error=error, codigo=codigo)
            log.warning("No se pudo preparar %s: %s", tarea.clave.rotulo(), detalle or codigo,
                        extra={"evento": "medios.cola.descarga_fallida", "detalle": {"codigo": codigo, "recurso": tarea.id}})
        self.memoria.delete(f"cm:r:{tarea.huella}")
        self.planificador.terminar(tarea)
        self._avisar(tarea)

    # ----------------------------------------------------------------- la descarga
    def _descargar(self, tarea: Tarea) -> None:
        previos = self.almacen.tamano(tarea.id)
        respuesta = self.origen.abrir(tarea.clave, f"bytes={previos}-" if previos else None, "GET")
        try:
            hechos, total, sha = self._preparar_inicio(tarea, respuesta, previos)
            self._hacer_sitio(tarea, total, hechos)
            with self.almacen.abrir_para_escribir(tarea.id, continuar=hechos > 0) as archivo:
                ultimo_progreso, ultimo_flujo = time.monotonic(), hechos
                while True:
                    if tarea.cancelar:
                        raise err.Cancelado("cancelado")
                    trozo = respuesta.flujo.read(cat.TROZO_BYTES)
                    if not trozo:
                        break
                    espera = self.entrada.reservar(len(trozo))
                    if espera > 0:
                        self._pausa(espera, tarea)
                    archivo.write(trozo)
                    archivo.flush()
                    sha.update(trozo)
                    hechos += len(trozo)
                    tarea.avanzar(hechos)
                    if hechos - ultimo_flujo >= PROGRESO_CADA_BYTES or time.monotonic() - ultimo_progreso >= PROGRESO_CADA_SEG:
                        self.registro.actualizar(tarea.id, bytes_hechos=hechos)
                        ultimo_progreso, ultimo_flujo = time.monotonic(), hechos
        except (OSError, http.client.HTTPException) as error:
            raise err.ErrorDeCola(f"La lectura de la fuente se cortó: {error}", cat.ORIGEN_NO_DISPONIBLE) from error
        finally:
            respuesta.cerrar()
            self._reservas.pop(tarea.id, None)
        if total is not None and hechos != total:
            raise err.Incompleto(f"Llegaron {hechos} bytes de {total}.", cat.INCOMPLETO)
        self._completar(tarea, hechos, sha.hexdigest(), respuesta)

    def _preparar_inicio(self, tarea: Tarea, respuesta: RespuestaDeOrigen, previos: int):
        """(bytes ya en disco que se conservan, total anunciado, hash con esos bytes ya sumados)."""
        cab = respuesta.cabeceras
        sha = hashlib.sha256()
        hechos = 0
        total: int | None = None
        parcial = total_de_content_range(cab.get("content-range")) if respuesta.estado == 206 else None
        if previos and parcial is not None and parcial[0] == previos:
            hechos, total = previos, parcial[2]                 # la fuente reanudó donde nos quedamos: se re-suma lo que ya había
            with open(self.almacen.ruta(tarea.id), "rb") as previo:
                restante = previos
                while restante > 0:
                    bloque = previo.read(min(cat.TROZO_BYTES, restante))
                    if not bloque:
                        break
                    sha.update(bloque)
                    restante -= len(bloque)
        elif respuesta.estado == 206 and parcial is not None:   # una respuesta parcial que no era la que se pidió
            raise err.ErrorDeCola("La fuente contestó un tramo distinto del pedido.", cat.INCOMPLETO)
        else:
            longitud = cab.get("content-length")
            total = int(longitud) if longitud and longitud.isdigit() else None
        tarea.fijar(total=total, mime=cab.get("content-type") or "application/octet-stream")
        tarea.avanzar(hechos)
        self.registro.actualizar(tarea.id, bytes_total=total, tipo_mime=tarea.mime[:200], bytes_hechos=hechos, cabeceras=respuesta.extra,
                                 curso_version=tarea.version)
        return hechos, total, sha

    def _completar(self, tarea: Tarea, hechos: int, sha256: str, respuesta: RespuestaDeOrigen) -> None:
        ahora = self.reloj.ahora_ms()
        fila = self.registro.actualizar(tarea.id, estado=cat.DISPONIBLE, bytes_total=hechos, bytes_hechos=hechos, sha256=sha256, actualizado_en=ahora,
                                        terminado_en=ahora, validado_en=ahora, error_codigo="", error_detalle="", reintentar_despues=None)
        tarea.terminar(cat.DISPONIBLE, sha256=sha256)
        self.memoria.delete(f"cm:r:{tarea.huella}")
        if hechos <= self.cfg.pequeno_bytes and hechos > 0:
            try:
                with open(self.almacen.ruta(tarea.id), "rb") as archivo:
                    self.memoria.set(f"cm:b:{tarea.id}", archivo.read(), self.cfg.memoria_seg)
            except OSError:
                pass
        self.planificador.terminar(tarea)
        log.info("Recurso listo: %s (%s bytes)", tarea.clave.rotulo(), hechos,
                 extra={"evento": "medios.cola.recurso_disponible", "detalle": {"recurso": tarea.id, "bytes": hechos}})
        if fila is not None:
            self._avisar(tarea)

    # ------------------------------------------------------------ espacio en disco
    def _hacer_sitio(self, tarea: Tarea, total: int | None, ya_hecho: int) -> None:
        """Garantiza que cabe lo que falta por bajar: dentro del tope de la caché y dejando libre el mínimo del disco."""
        falta = (total - ya_hecho) if total is not None else 0
        if total is not None and total > self.cfg.max_bytes:
            raise err.SinEspacio(f"El recurso pesa {total} bytes y la caché admite {self.cfg.max_bytes}.", cat.SIN_ESPACIO)
        if falta <= 0:
            return
        with self.hecho_espacio:
            usados = self.registro.resumen().get("bytes_ocupados", 0) + sum(v for k, v in self._reservas.items() if k != tarea.id)
            sobra_tope = usados + falta - self.cfg.max_bytes
            sobra_disco = self.cfg.libre_min_bytes + falta + sum(v for k, v in self._reservas.items() if k != tarea.id) - self.almacen.libre_bytes()
            necesario = max(sobra_tope, sobra_disco, 0)
            if necesario > 0:
                liberado = self.liberar(necesario, excepto=tarea.id)
                if liberado < necesario:
                    raise err.SinEspacio("No hay espacio en la caché de medios del nodo.", cat.SIN_ESPACIO)
            self._reservas[tarea.id] = falta

    def liberar(self, necesario: int, *, excepto: str = "") -> int:
        """Expulsa recursos disponibles, del menos al más reciente, hasta liberar `necesario` bytes. Devuelve lo liberado."""
        ahora = self.reloj.ahora_ms()
        candidatos = []
        for fila in self.registro.candidatos_a_expulsion():
            if fila["id"] == excepto:
                continue
            candidatos.append(politica.Candidato(id=fila["id"], bytes=int(fila["bytes_total"] or fila["bytes_hechos"] or 0),
                                                 ultimo_uso_ms=int(fila["ultimo_uso_en"] or fila["terminado_en"] or 0),
                                                 en_uso=self.almacen.lectores.activos(fila["id"]) > 0))
        liberado = 0
        for recurso_id in politica.elegir_expulsiones(candidatos, necesario, ahora, self.cfg.proteger_seg * 1000):
            tamano = next(c.bytes for c in candidatos if c.id == recurso_id)
            fila = self.registro.por_id(recurso_id)
            if self.expulsar(recurso_id, fila):
                liberado += tamano
        return liberado

    def expulsar(self, recurso_id: str, fila: dict | None = None) -> bool:
        fila = fila or self.registro.por_id(recurso_id)
        if fila is None:
            return False
        self.almacen.borrar(recurso_id)                # si Windows no lo suelta, el barrido de huérfanos lo quita luego
        self.registro.eliminar(recurso_id)
        self.memoria.delete(f"cm:r:{fila['clave']}")
        self.memoria.delete(f"cm:b:{recurso_id}")
        log.info("Recurso expulsado de la caché: %s/%s", fila["curso_ref"], fila["media_ref"],
                 extra={"evento": "medios.cola.recurso_expulsado", "detalle": {"recurso": recurso_id}})
        return True

    def _avisar(self, tarea: Tarea) -> None:
        for modulo, contexto in self.contextos.de(tarea.id):
            try:
                self.difusion.recurso_cambio(modulo, contexto)
            except Exception:   # noqa: BLE001 — un aviso que no sale no frena la descarga
                log.exception("No se pudo avisar del cambio de un recurso")


class Contextos:
    """Qué clases/asignaciones/exámenes esperan cada recurso, para avisarles. Sale de `cm_solicitud` (con una memoria corta para no preguntar en cada trozo)."""

    def __init__(self, registro: Registro):
        self.registro = registro

    def de(self, recurso_id: str) -> list[tuple[str, str]]:
        try:
            return self.registro.contextos_de(recurso_id)       # type: ignore[attr-defined]
        except Exception:   # noqa: BLE001
            return []
