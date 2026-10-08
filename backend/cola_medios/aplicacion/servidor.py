"""
El servidor de medios del nodo: lo que los módulos del aula, del modo estudio y de la evaluación usan en lugar de abrir cada medio directo en la fuente.

    abrir      los bytes de un medio, con `Range`. Si ya está en la caché se sirve de disco; si lo están bajando, se SIGUE esa descarga (varias tabletas
               que piden lo mismo esperan al mismo hilo); si no lo hay, se pone en la cola con la prioridad de quien lo pide. Devuelve `None` cuando la
               cola no puede ayudar a tiempo —y quien llama sirve el medio en paso a través, como antes—. Lanza `ErrorDeOrigen` con el error original de
               la fuente (la biblioteca cerrada, el curso retirado por la política, el medio inexistente).
    preparar   deja en cola, sin esperar, los medios que se van a necesitar (lo que el profesor proyecta, los de un examen, los de una lección).
    medir      tamaño y SHA-256 de un medio para un paquete de estudio: lo trae una vez a la caché y todos los alumnos reutilizan la medida.

La autorización sigue siendo de quien llama (la asignación, el intento, la sesión) y la del curso sigue siendo de la biblioteca: antes de servir una copia se
confirma —cada `revalidar_seg`— que el curso se sigue ofreciendo y en qué versión; una versión nueva descarta la copia vieja.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter

from ..dominio import catalogos as cat
from ..dominio import errores as err
from ..dominio.clave import ClaveMedio
from ..dominio.rangos import Insatisfacible, interpretar
from ..dominio.ritmo import Cubo, Cupo, Cupos
from .almacen import Almacen
from .config import Config
from .descargador import Contextos, Descargador
from .planificador import Planificador
from .puertos import Difusion, Memoria, Origen, Registro, Reloj
from .respuesta import RespuestaLocal
from .tarea import Tarea

log = logging.getLogger("avacom.cola_medios")


class Servidor:
    def __init__(self, *, config: Config, registro: Registro, almacen: Almacen, origen: Origen, memoria: Memoria, difusion: Difusion, reloj: Reloj,
                 planificador: Planificador | None = None, motivo_apagada: str = ""):
        self.cfg = config
        self.motivo_apagada = motivo_apagada          # por qué se apagó sola (p. ej. no hay permiso en la carpeta de la caché); vacío si no se apagó
        self.registro = registro
        self.almacen = almacen
        self.origen = origen
        self.memoria = memoria
        self.difusion = difusion
        self.reloj = reloj
        self.planificador = planificador or Planificador()
        self.entrada = Cubo(config.ancho_entrada_bps)
        self.salida = Cubo(config.ancho_salida_bps)
        self.cupos = Cupos(config.transferencias)
        self.descargador = Descargador(config=config, registro=registro, almacen=almacen, origen=origen, memoria=memoria, difusion=difusion,
                                       reloj=reloj, planificador=self.planificador, entrada=self.entrada, contextos=Contextos(registro))
        self._candado_usos = threading.Lock()
        self._usos: dict[str, tuple[int, int]] = {}
        self._cuentas: Counter = Counter()
        self._cuentas_candado = threading.Lock()

    # ================================================================= abrir
    @property
    def en_linea(self) -> bool:
        """Sin hilos de descarga (pruebas) la descarga se hace en la propia petición."""
        return self.cfg.hilos <= 0

    def contar(self, nombre: str, n: int = 1) -> None:
        with self._cuentas_candado:
            self._cuentas[nombre] += n

    def abrir(self, clave: ClaveMedio, rango: str | None, metodo: str, *, prioridad: int, modulo: str, contexto_ref: str = "") -> RespuestaLocal | None:
        if not self.cfg.activa:
            return None
        if metodo == "HEAD":
            return self._cabeceras(clave)
        version = self._version(clave)
        rec, tarea = self._asegurar(clave, version, prioridad, modulo, contexto_ref)
        if rec is not None:
            self.contar("aciertos")
            return self._local(rec, rango)
        if tarea is None:
            self.contar("directos")
            return None
        respuesta = self._seguir(tarea, clave, rango)
        self.contar("siguiendo" if respuesta is not None else "directos")
        return respuesta

    # ------------------------------------------------------------ el curso vigente
    def _version(self, clave: ClaveMedio) -> str:
        """La versión instalada del curso, preguntada a la biblioteca cada `revalidar_seg`. Lanza `ErrorDeOrigen` si no está o ya no se ofrece."""
        llave = f"cm:v:{clave.fuente}:{clave.curso_ref}"
        version = self.memoria.get(llave)
        if version is not None:
            return version
        try:
            version = self.origen.version_del_curso(clave.fuente, clave.curso_ref)
        except err.ErrorDeOrigen as error:
            previa = self.registro.obtener(clave.huella())
            if error.transitorio and self.cfg.servir_sin_biblioteca and previa and previa["estado"] == cat.DISPONIBLE and previa["curso_version"]:
                return previa["curso_version"]
            raise
        self.memoria.set(llave, version, max(1, self.cfg.revalidar_seg))
        return version

    # ---------------------------------------------------------------- la caché
    def _recurso(self, clave: ClaveMedio) -> dict | None:
        huella = clave.huella()
        fila = self.memoria.get(f"cm:r:{huella}")
        if fila is None:
            fila = self.registro.obtener(huella)
            if fila is not None and fila["estado"] == cat.DISPONIBLE:
                self.memoria.set(f"cm:r:{huella}", fila, self.cfg.memoria_seg)
        return fila

    def _descartar(self, fila: dict) -> None:
        self.descargador.expulsar(fila["id"], fila)

    def _asegurar(self, clave: ClaveMedio, version: str, prioridad: int, modulo: str, contexto_ref: str, *, en_linea: bool = True,
                  forzar: bool = False) -> tuple[dict | None, Tarea | None]:
        """(recurso completo, None) si ya está en la caché; (None, tarea) si se está bajando o se acaba de poner en cola; (None, None) si la cola no debe
        intervenir (un fallo reciente: se sirve en paso a través hasta que pase el tiempo de espera)."""
        huella = clave.huella()
        ahora = self.reloj.ahora_ms()
        with self.planificador.candado:
            tarea = self.planificador.activa(huella)
            if tarea is not None:
                self.planificador.priorizar(tarea, prioridad)
                return None, tarea
            fila = self._recurso(clave)
            if fila is not None:
                if fila["estado"] == cat.DISPONIBLE:
                    if fila["curso_version"] == version and self.almacen.tamano(fila["id"]) == fila["bytes_total"]:
                        self._registrar_uso(fila["id"])
                        return fila, None
                    self._descartar(fila)                       # otra versión del curso, o el archivo ya no está completo
                    fila = None
                elif fila["curso_version"] and fila["curso_version"] != version:
                    self._descartar(fila)
                    fila = None
                elif fila["estado"] == cat.FALLIDO and not forzar and (fila["reintentar_despues"] or 0) > ahora:
                    return None, None
            if fila is None:
                fila = self.registro.crear({
                    "id": _nuevo_id(), "clave": huella, "fuente": clave.fuente, "curso_ref": clave.curso_ref, "curso_version": version,
                    "media_ref": clave.media_ref, "ruta": clave.ruta, "estado": cat.PENDIENTE, "prioridad": prioridad,
                    "creado_en": ahora, "actualizado_en": ahora})
            else:
                fila = self.registro.actualizar(fila["id"], estado=cat.PENDIENTE, prioridad=prioridad, curso_version=version, error_codigo="",
                                                error_detalle="", reintentar_despues=None, actualizado_en=ahora) or fila
            previa = self.registro.mejor_prioridad(fila["id"], ahora)       # lo que otras solicitudes vigentes (p. ej. una proyección) ya le dieron
            tarea = self.planificador.crear(fila, clave, version, prioridad if previa is None else min(prioridad, previa))
        if en_linea and self.en_linea:
            self.descargador.ejecutar(tarea)
        return None, tarea

    def _registrar_uso(self, recurso_id: str) -> None:
        with self._candado_usos:
            _, veces = self._usos.get(recurso_id, (0, 0))
            self._usos[recurso_id] = (self.reloj.ahora_ms(), veces + 1)

    # ------------------------------------------------------------------ servir
    def _cabeceras_http(self, tipo: str, total: int, tramo, extra: dict | None, etag: str = "") -> tuple[int, dict, int, int]:
        cab = {"Content-Type": tipo or "application/octet-stream", "Accept-Ranges": "bytes", "Cache-Control": "no-store"}
        if tramo is not None:
            estado, inicio, longitud = 206, tramo.inicio, tramo.longitud
            cab["Content-Range"] = tramo.encabezado(total)
        else:
            estado, inicio, longitud = 200, 0, total
        cab["Content-Length"] = str(longitud)
        cab.update(extra or {})
        return estado, cab, inicio, longitud

    def _local(self, fila: dict, rango: str | None) -> RespuestaLocal | None:
        """Un recurso completo, de memoria si es pequeño y si no del archivo."""
        total = int(fila["bytes_total"])
        try:
            tramo = interpretar(rango, total)
        except Insatisfacible:
            return self._insatisfacible(total)
        datos = self.memoria.get(f"cm:b:{fila['id']}") if total <= self.cfg.pequeno_bytes else None
        if datos is not None and len(datos) != total:
            datos = None
        estado, cab, inicio, longitud = self._cabeceras_http(fila["tipo_mime"], total, tramo, fila.get("cabeceras"))
        return RespuestaLocal(estado=estado, cabeceras=cab, inicio=inicio, longitud=longitud, ruta=self.almacen.ruta(fila["id"]), datos=datos, tarea=None,
                              recurso_id=fila["id"], lectores=self.almacen.lectores, estancado_seg=self.cfg.estancado_seg,
                              en_una_pieza=fila["fuente"] in self.cfg.fuentes_en_una_pieza)

    def _insatisfacible(self, total: int) -> RespuestaLocal:
        return RespuestaLocal(estado=416, cabeceras={"Content-Range": f"bytes */{total}", "Cache-Control": "no-store", "Content-Length": "0"}, inicio=0,
                              longitud=0, ruta=None, datos=b"", tarea=None, recurso_id="", lectores=None, estancado_seg=self.cfg.estancado_seg)

    def _cabeceras(self, clave: ClaveMedio) -> RespuestaLocal | None:
        """HEAD: si el recurso está en la caché y vigente, se contesta de la fila (tamaño y tipo); si no, la cola no interviene."""
        version = self._version(clave)
        fila = self._recurso(clave)
        if fila is None or fila["estado"] != cat.DISPONIBLE or fila["curso_version"] != version:
            return None
        estado, cab, inicio, longitud = self._cabeceras_http(fila["tipo_mime"], int(fila["bytes_total"]), None, fila.get("cabeceras"))
        return RespuestaLocal(estado=estado, cabeceras=cab, inicio=0, longitud=0, ruta=None, datos=b"", tarea=None, recurso_id=fila["id"], lectores=None,
                              estancado_seg=self.cfg.estancado_seg, sin_cuerpo=True)

    def _seguir(self, tarea: Tarea, clave: ClaveMedio, rango: str | None) -> RespuestaLocal | None:
        """Sirve un recurso que se está bajando leyendo del archivo a medida que crece. None si no llega a tiempo o la petición salta demasiado lejos."""
        limite = time.monotonic() + self.cfg.espera_inicio_seg
        if not tarea.esperar(lambda: tarea.terminada or tarea.bytes_total is not None, limite - time.monotonic()):
            return None
        if tarea.estado in (cat.FALLIDO, cat.CANCELADO):
            return self._falla(tarea)
        if tarea.estado == cat.DISPONIBLE:
            fila = self._recurso(clave)
            return self._local(fila, rango) if fila is not None else None
        total = tarea.bytes_total
        try:
            tramo = interpretar(rango, total)
        except Insatisfacible:
            return self._insatisfacible(total)
        necesario = tramo.inicio if tramo is not None else 0
        if necesario - tarea.bytes_hechos > self.cfg.adelanto_max_bytes:
            return None                                      # un salto lejano: la cola seguirá bajando; esta petición va directo a la fuente
        if not tarea.esperar(lambda: tarea.terminada or tarea.bytes_hechos > necesario, limite - time.monotonic()):
            return None
        if tarea.estado in (cat.FALLIDO, cat.CANCELADO):
            return self._falla(tarea)
        if tarea.estado == cat.DISPONIBLE:
            fila = self._recurso(clave)
            return self._local(fila, rango) if fila is not None else None
        extra = (self.registro.por_id(tarea.id) or {}).get("cabeceras")
        estado, cab, inicio, longitud = self._cabeceras_http(tarea.mime, total, tramo, extra)
        return RespuestaLocal(estado=estado, cabeceras=cab, inicio=inicio, longitud=longitud, ruta=self.almacen.ruta(tarea.id), datos=None, tarea=tarea,
                              recurso_id=tarea.id, lectores=self.almacen.lectores, estancado_seg=self.cfg.estancado_seg)

    @staticmethod
    def _falla(tarea: Tarea) -> None:
        if isinstance(tarea.error, err.ErrorDeOrigen):
            raise tarea.error
        return None

    # ================================================================ preparar
    def preparar(self, medios: list[tuple[str, str]], *, fuente: str, curso_ref: str, modulo: str, contexto_ref: str, prioridad: int,
                 persona_id: str = "", dispositivo_id: str = "", reemplazar: bool = False) -> dict:
        """Pone en cola, sin esperar, los medios que se van a necesitar. Nunca lanza: preparar es una cortesía, no una condición."""
        if not self.cfg.activa or not medios:
            return {"encolados": 0, "omitidos": 0}
        medios = list(medios)[: self.cfg.max_preparar]
        try:
            version = self._version(ClaveMedio.de(fuente, curso_ref, medios[0][0]))
        except err.ErrorDeOrigen as error:
            log.info("No se prepararon medios de %s: %s", curso_ref, error, extra={"evento": "medios.cola.preparacion_omitida"})
            return {"encolados": 0, "omitidos": len(medios)}
        ahora = self.reloj.ahora_ms()
        vence = ahora + self.cfg.vigencia_proyeccion_seg * 1000 if prioridad == cat.PROYECCION else None
        ids: list[str] = []
        encolados = omitidos = 0
        for media_ref, ruta in medios:
            clave = ClaveMedio.de(fuente, curso_ref, media_ref, ruta)
            try:
                fila, tarea = self._asegurar(clave, version, prioridad, modulo, contexto_ref, en_linea=False)
            except Exception:   # noqa: BLE001 — preparar uno no frena a los demás
                log.exception("No se pudo preparar %s", clave.rotulo(), extra={"evento": "medios.cola.preparacion_fallo"})
                omitidos += 1
                continue
            recurso_id = fila["id"] if fila is not None else (tarea.id if tarea is not None else "")
            if not recurso_id:
                omitidos += 1
                continue
            ids.append(recurso_id)
            encolados += 1
            if contexto_ref:
                self.registro.solicitar(recurso_id, modulo=modulo, contexto_ref=contexto_ref, prioridad=prioridad, persona_id=persona_id,
                                        dispositivo_id=dispositivo_id, ahora=ahora, vence_en=vence)
        if reemplazar and prioridad == cat.PROYECCION and contexto_ref:
            bajados = self.registro.bajar_proyecciones(modulo, contexto_ref, ids, cat.CLASE)
            self.planificador.bajar(bajados, cat.CLASE)
        if contexto_ref:
            try:
                self.difusion.recurso_cambio(modulo, contexto_ref)
            except Exception:   # noqa: BLE001
                log.exception("No se pudo avisar de la preparación")
        return {"encolados": encolados, "omitidos": omitidos}

    # ================================================================== medir
    def medir(self, clave: ClaveMedio, *, prioridad: int, modulo: str, contexto_ref: str, tope_bytes: int) -> dict | None:
        """{bytes, sha256, mime} del medio, trayéndolo a la caché si hace falta. None si la cola no puede (quien llama mide por su cuenta).
        Lanza `ErrorDeOrigen` y `DemasiadoGrande`."""
        if not self.cfg.activa:
            return None
        version = self._version(clave)
        fila, tarea = self._asegurar(clave, version, prioridad, modulo, contexto_ref)
        if fila is None and tarea is None:
            return None
        if fila is None:
            limite = time.monotonic() + self.cfg.espera_paquete_seg
            if not tarea.esperar(lambda: tarea.terminada or tarea.bytes_total is not None, limite - time.monotonic()):
                return None
            if not tarea.terminada and tarea.bytes_total is not None and tarea.bytes_total > tope_bytes:
                self._cancelar_si_es_de_fondo(tarea)
                raise err.DemasiadoGrande(tarea.bytes_total)
            if not tarea.esperar(lambda: tarea.terminada, limite - time.monotonic()):
                return None
            if tarea.estado != cat.DISPONIBLE:
                self._falla(tarea)
                return None
            fila = self._recurso(clave)
            if fila is None:
                return None
        if int(fila["bytes_total"] or 0) > tope_bytes:
            raise err.DemasiadoGrande(int(fila["bytes_total"]))
        if prioridad is not None and modulo and contexto_ref:
            self.registro.solicitar(fila["id"], modulo=modulo, contexto_ref=contexto_ref, prioridad=prioridad, persona_id="", dispositivo_id="",
                                    ahora=self.reloj.ahora_ms(), vence_en=None)
        return {"bytes": int(fila["bytes_total"]), "sha256": fila["sha256"], "mime": fila["tipo_mime"]}

    def _cancelar_si_es_de_fondo(self, tarea: Tarea) -> None:
        if tarea.prioridad >= cat.ESTUDIO and self.almacen.lectores.activos(tarea.id) == 0:
            tarea.cancelar = True

    # ======================================================== cancelar / reintentar
    def cancelar(self, recurso_id: str) -> bool:
        ahora = self.reloj.ahora_ms()
        tarea = next((t for t in self.planificador.activas() if t.id == recurso_id), None)
        if tarea is not None:
            tarea.cancelar = True
            if tarea.estado == cat.PENDIENTE:             # todavía no la tomó ningún hilo: se cierra aquí
                with self.planificador.candado:
                    if tarea.estado == cat.PENDIENTE:
                        self.almacen.borrar(tarea.id)
                        self.registro.actualizar(tarea.id, estado=cat.CANCELADO, bytes_hechos=0, actualizado_en=ahora, terminado_en=ahora,
                                                 error_codigo=cat.CANCELADO_POR_USUARIO, error_detalle="La preparación se canceló.")
                        tarea.terminar(cat.CANCELADO, codigo=cat.CANCELADO_POR_USUARIO)
                        self.planificador.terminar(tarea)
            return True
        fila = self.registro.por_id(recurso_id)
        if fila is None or fila["estado"] in (cat.DISPONIBLE, cat.CANCELADO):
            return False
        self.registro.actualizar(recurso_id, estado=cat.CANCELADO, actualizado_en=ahora, terminado_en=ahora, error_codigo=cat.CANCELADO_POR_USUARIO,
                                 error_detalle="La preparación se canceló.")
        self.memoria.delete(f"cm:r:{fila['clave']}")
        return True

    def reintentar(self, recurso_id: str) -> bool:
        fila = self.registro.por_id(recurso_id)
        if fila is None or fila["estado"] in (cat.DISPONIBLE, cat.PENDIENTE, cat.DESCARGANDO):
            return False
        clave = ClaveMedio.de(fila["fuente"], fila["curso_ref"], fila["media_ref"], fila["ruta"])
        try:
            version = self._version(clave)
        except err.ErrorDeOrigen:
            return False
        _, tarea = self._asegurar(clave, version, cat.PRECARGA, "", "", en_linea=False, forzar=True)
        return tarea is not None

    # ============================================================== mantenimiento
    def rehidratar(self) -> int:
        """Al arrancar el nodo: lo que estaba pendiente o a medias cuando se apagó vuelve a la cola (con lo ya descargado, que se reanuda)."""
        ahora = self.reloj.ahora_ms()
        n = 0
        for fila in self.registro.activos():
            if self.planificador.activa(fila["clave"]) is not None:
                continue                                      # ya está en la cola (o bajándose): nada que retomar
            clave = ClaveMedio.de(fila["fuente"], fila["curso_ref"], fila["media_ref"], fila["ruta"])
            try:
                version = self._version(clave)
            except err.ErrorDeOrigen:
                continue
            if fila["curso_version"] and fila["curso_version"] != version:
                self.descargador.expulsar(fila["id"], fila)
                continue
            fila = self.registro.actualizar(fila["id"], estado=cat.PENDIENTE, actualizado_en=ahora) or fila
            prioridad = self.registro.mejor_prioridad(fila["id"], ahora)
            self.planificador.crear(fila, clave, version, prioridad if prioridad is not None else cat.PRECARGA)
            n += 1
        return n

    def mantenimiento(self) -> dict:
        """Lo que se hace cada rato, sin que nadie lo pida: anotar usos, quitar lo que falta o sobra, respetar el tope de la caché."""
        ahora = self.reloj.ahora_ms()
        retomados = self.rehidratar()                         # lo que quedó pendiente sin tarea viva (la biblioteca no estaba al arrancar, un fallo) vuelve a la cola
        with self._candado_usos:
            usos, self._usos = self._usos, {}
        if usos:
            self.registro.aplicar_usos(usos)
        ids_vivos = self.registro.ids()
        sueltos = 0
        for ruta in self.almacen.huerfanos(ids_vivos):
            try:
                ruta.unlink()
                sueltos += 1
            except OSError:
                pass
        faltantes = 0
        for fila in self.registro.listar(cat.DISPONIBLE, limite=100000):
            if not self.almacen.existe(fila["id"]):
                self.descargador.expulsar(fila["id"], fila)
                faltantes += 1
        purgados = self.registro.purgar(fallidos_antes_de=ahora - 24 * 3600 * 1000, solicitudes_vencidas_antes_de=ahora)
        sobra = self.registro.resumen().get("bytes_ocupados", 0) - self.cfg.max_bytes
        expulsados = 0
        if sobra > 0:
            expulsados = self.descargador.liberar(sobra)
        return {"usos": len(usos), "huerfanos": sueltos, "faltantes": faltantes, "purgados": purgados, "liberados": expulsados, "retomados": retomados}

    def limpiar(self) -> int:
        """Vacía la caché de lo que no esté en uso (sin respetar la protección de lo reciente). Devuelve cuántos recursos salieron."""
        n = 0
        for fila in self.registro.candidatos_a_expulsion():
            if self.almacen.lectores.activos(fila["id"]) == 0 and self.descargador.expulsar(fila["id"], fila):
                n += 1
        return n

    # ================================================================== estado
    def estado(self) -> dict:
        resumen = self.registro.resumen()
        cola = self.planificador.contar()
        with self._cuentas_candado:
            cuentas = dict(self._cuentas)
        return {
            "activa": self.cfg.activa,
            "motivo_apagada": self.motivo_apagada,
            "modo": "en_linea" if self.en_linea else "hilos",
            "cola": {"pendientes": cola[cat.PENDIENTE], "descargando": cola[cat.DESCARGANDO]},
            "recursos": resumen.get("por_estado", {}),
            "cache": {"bytes_ocupados": resumen.get("bytes_ocupados", 0), "bytes_maximo": self.cfg.max_bytes, "bytes_libres_disco": self.almacen.libre_bytes(),
                      "bytes_libres_minimo": self.cfg.libre_min_bytes, "lecturas_activas": self.almacen.lectores.total()},
            "transferencias": {"en_uso": self.cupos.en_uso, "maximo": self.cupos.maximo, "pico": self.cupos.picos},
            "limites": {"descargas_simultaneas": self.cfg.hilos, "transferencias_simultaneas": self.cfg.transferencias,
                        "ancho_entrada_bps": self.cfg.ancho_entrada_bps, "ancho_salida_bps": self.cfg.ancho_salida_bps},
            "contadores": cuentas,
        }

    def listar(self, *, contexto_ref: str = "", modulo: str = "", estado: str = "", limite: int = 100) -> list[dict]:
        filas = self.registro.del_contexto(contexto_ref, modulo) if contexto_ref else self.registro.listar(estado, limite=limite)
        if estado and contexto_ref:
            filas = [f for f in filas if f["estado"] == estado]
        vivas = {t.id: t for t in self.planificador.activas()}
        salida = []
        for f in filas[:limite]:
            t = vivas.get(f["id"])
            hechos = t.bytes_hechos if t is not None else f["bytes_hechos"]
            total = t.bytes_total if t is not None and t.bytes_total is not None else f["bytes_total"]
            salida.append({**f, "bytes_hechos": hechos, "bytes_total": total,
                           "porcentaje": 100 if f["estado"] == cat.DISPONIBLE else (round(100 * hechos / total) if total else None)})
        return salida


def _nuevo_id() -> str:
    import uuid
    return str(uuid.uuid4())


def tomar_cupo(servidor: Servidor) -> Cupo | None:
    """Un cupo de transferencia hacia una tableta, o None si no hay. Quien lo toma lo libera al terminar (`Cupo.liberar`, idempotente)."""
    if servidor.cupos.intentar():
        return Cupo(servidor.cupos)
    return None
