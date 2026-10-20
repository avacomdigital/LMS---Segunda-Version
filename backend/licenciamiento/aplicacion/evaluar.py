"""
Evaluar la licencia: FUN-189 (validar al arrancar), FUN-190 (contar equipos y usuarios), FUN-192 y FUN-193 (gracia y degradación, que SALEN del tiempo) y FUN-194 (reactivar tras una
restauración). Lo repite el programador cada pocos minutos y lo dispara el arranque y cada acción del administrador.

Tres tiempos, para tocar la base de datos lo menos posible (R-07):

    1. LEER      una consulta sin transacción con todo lo que hace falta (historial, observaciones, marca alta) más lo que dicen los puertos (reloj, anclas, huella, conteos)
    2. PLANEAR   puro: de esas entradas salen el estado, los avisos y la lista de escrituras que hacen falta (casi siempre ninguna)
    3. APLICAR   UNA transacción corta, sólo si hay algo que escribir; los eventos y asientos llevan una clave y son IDEMPOTENTES (repetir un tick no repite nada)

No se guarda un «estado actual»: el estado se DERIVA del historial de sólo inserción, de las observaciones y del reloj confiable. Nada de aquí lanza hacia afuera (R-04): ante cualquier
fallo se queda el último estado bueno (o, si no lo hay, el de la política: la ventana de evaluación) y se registra.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from ..dominio import catalogos as cat
from ..dominio import cupo as cu
from ..dominio import estado as est
from ..dominio import huella as hu
from ..dominio import licencia as lic_mod
from ..dominio import reloj as rj
from ..dominio.cupo import Consumo
from ..dominio.errores import LicenciaInvalida
from ..dominio.licencia import Licencia
from ..dominio.politica import HORA_MS
from .base import _CasoDeUso, corto, resumen_de_huella, resumen_de_licencia
from .puertos import Instantanea, LecturaDeAnclas

log = logging.getLogger("avacom.licenciamiento")

MARGEN_DE_MARCA_MS = 600_000         # la marca alta no se reescribe más seguido que esto cuando la evalúa el programador (una escritura pequeña cada ~10 min)


@dataclass
class Escritura:
    tipo: str                         # instalacion · historial · observacion · marca · evento · espejo · espejo_borrar · ancla
    datos: dict = field(default_factory=dict)


@dataclass
class Entradas:
    origen: str
    ahora_reloj: int
    monotono: int
    previo: tuple[int, int, int] | None
    instalacion: dict | None
    vigente: dict | None
    liberadas_db: set
    marca_db: int
    ultima_audit: int | None
    anclas: LecturaDeAnclas
    espejo: bytes | None
    tumbas_externas: set
    obs: dict
    claves: dict
    actuales: dict
    inst_hash: bytes
    consumo: Consumo | None
    bloqueos: list = field(default_factory=list)
    novedades: list = field(default_factory=list)       # secretos propios del nodo que no se pudieron abrir y se apartaron (se asientan como integridad alterada)


@dataclass
class Plan:
    escrituras: list[Escritura]
    instantanea: Instantanea


def mas_nueva(a: Licencia, b: Licencia) -> bool:
    """¿`a` se emitió después que `b`? (la fecha de emisión y, a igual fecha, la serie)."""
    return (a.emitida, a.serie) > (b.emitida, b.serie)


def episodio_abierto(obs: dict) -> bool:
    """¿La base dice que hay una fecha adelantada sin resolver (Q-L13)? La última `reloj_salto_adelante` ABRIÓ un episodio (`inicio`, no `fin`) y ninguna `reloj_confirmado` es posterior.
    Se compara por `id`, el orden de inserción: un salto del reloj tuerce las horas (`en`)."""
    salto, confirmado = obs.get(cat.O_SALTO), obs.get(cat.O_CONFIRMADO)
    return (salto is not None and bool(salto["detalle"].get("inicio")) and not salto["detalle"].get("fin")
            and salto["id"] > (confirmado["id"] if confirmado is not None else 0))


def resolver_el_reloj(politica, *, ahora_reloj: int, monotono: int, previo, marca_db: int, marcas_externas, ultima_audit: int | None, obs: dict) -> rj.Resolucion:
    """Lo que el nodo concluye del reloj (la única decisión sobre qué hora vale): `reloj.resolver` con lo que hay en la base y fuera de ella."""
    return rj.resolver(
        reloj_ms=ahora_reloj, monotono_ms=monotono, previo=previo, marca_propia_ms=max(marca_db, max(marcas_externas, default=0)), ultima_audit_ms=ultima_audit,
        episodio_abierto=episodio_abierto(obs), tolerancia_retroceso_ms=politica.tolerancia_retroceso_ms, salto_adelante_ms=politica.salto_adelante_ms,
        tolerancia_fecha_ms=politica.tolerancia_fecha_ms)


def tumbas_de(datos: bytes | None) -> set[tuple[str, int]]:
    """Las licencias que este nodo liberó, según el archivo de la carpeta de estado. Un archivo ilegible equivale a ninguna."""
    if not datos:
        return set()
    try:
        return {(str(i), int(serie)) for i, serie in json.loads(datos.decode("utf-8")).get("liberadas", [])}
    except (ValueError, TypeError, AttributeError):
        return set()


def tumbas_a_bytes(tumbas: set[tuple[str, int]]) -> bytes:
    return json.dumps({"liberadas": sorted([i, s] for i, s in tumbas)}, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


class Evaluar(_CasoDeUso):
    def ejecutar(self, origen: str = "tick") -> Instantanea:
        """`origen`: arranque · tick · accion · demanda. Devuelve la instantánea que quedó publicada (o, ante un fallo, la última buena)."""
        s = self.s
        with s.bloqueo:
            entradas, asentado = None, False
            try:
                entradas = self._leer(origen)
                plan = self._planear(entradas)
                asentado = self._aplicar(plan.escrituras)
                s.vivo.publicar(plan.instantanea)
                s.vivo.recordar_reloj(entradas.ahora_reloj, entradas.monotono, plan.instantanea.estado.ahora)
                return plan.instantanea
            except Exception:   # noqa: BLE001 — R-04: un fallo de licenciamiento nunca cierra nada
                log.exception("No se pudo evaluar la licencia; se conserva el último estado bueno", extra={"evento": "licencia.evaluacion_fallo", "ruta": "bad"})
                return s.vivo.leer() or self._de_la_politica()
            finally:
                if entradas is not None and entradas.novedades and not asentado:
                    s.nodo.devolver_novedades(entradas.novedades)             # lo que no llegó a asentarse se reintenta en el siguiente ciclo

    def hora_confiable(self) -> int:
        """
        La hora con que se FECHA un hecho de la licencia ahora mismo (la solicitud, la instalación, la liberación): la del equipo, salvo que esté adelantada y el nodo no la acepte (Q-L13),
        y entonces la confiable. SÓLO LEE: no asienta, no publica ni recuerda nada (la evaluación de la acción que sigue lo hace); así una acción no cambia el orden de lo que el
        nodo reconoce —por ejemplo, reactivar desde el espejo tras una restauración— sólo por preguntar la hora. Un fallo de lectura devuelve la hora del equipo: nunca estorba (R-04).
        """
        s = self.s
        try:
            with s.uow(lectura=True) as uow:
                marca_db, ultima_audit = uow.marca.valor(), uow.auditoria.ultima_marca()
                obs = {tipo: uow.observaciones.ultima(tipo) for tipo in (cat.O_SALTO, cat.O_CONFIRMADO)}
            ahora = s.reloj.ahora_ms()
            res = resolver_el_reloj(s.config.politica, ahora_reloj=ahora, monotono=s.reloj.monotono_ms(), previo=s.vivo.reloj_previo(), marca_db=marca_db,
                                    marcas_externas=s.anclas.leer().marcas.values(), ultima_audit=ultima_audit, obs=obs)
            return res.lectura.ahora if res.adelantado else ahora
        except Exception:   # noqa: BLE001 — R-04: preguntar la hora nunca impide una acción
            log.exception("No se pudo resolver la hora confiable; se usa la del equipo", extra={"evento": "licencia.hora_fallo", "ruta": "bad"})
            return s.reloj.ahora_ms()

    # ------------------------------------------------------------------------------------------------------------------------- 1 · leer
    def _leer(self, origen: str) -> Entradas:
        s = self.s
        with s.uow(lectura=True) as uow:
            instalacion = uow.instalacion.obtener()
            vigente = uow.historial.vigente()
            liberadas_db = uow.historial.liberadas()
            marca_db = uow.marca.valor()
            ultima_audit = uow.auditoria.ultima_marca()
            obs = {tipo: uow.observaciones.ultima(tipo) for tipo in cat.OBSERVACIONES}
        actuales = hu.factores_validos(s.huella.crudos())
        inst_hash = hu.hash_de_factor(hu.F_INSTALACION, s.nodo.secreto_de_instalacion().hex())
        equipos, usuarios = s.conteos.equipos(), s.conteos.usuarios()
        return Entradas(
            origen=origen, ahora_reloj=s.reloj.ahora_ms(), monotono=s.reloj.monotono_ms(), previo=s.vivo.reloj_previo(), instalacion=instalacion, vigente=vigente,
            liberadas_db=liberadas_db, marca_db=marca_db, ultima_audit=ultima_audit, anclas=s.anclas.leer(), espejo=s.almacen.leer(cat.ARCHIVO_ESPEJO),
            tumbas_externas=tumbas_de(s.almacen.leer(cat.ARCHIVO_TUMBAS)), obs=obs, claves=s.claves.publicas(), actuales=actuales, inst_hash=inst_hash,
            consumo=Consumo(equipos, usuarios) if equipos is not None and usuarios is not None else None, bloqueos=s.vivo.tomar_bloqueos(),
            novedades=s.nodo.tomar_novedades())             # al final: para entonces el secreto de instalación y las anclas ya se leyeron, y cualquier archivo apartado ya está en la lista

    # ------------------------------------------------------------------------------------------------------------------------- 2 · planear
    def _planear(self, e: Entradas) -> Plan:
        s, politica = self.s, self.s.config.politica
        w: list[Escritura] = []

        # ---- 0. el reloj (P-06 · Q-L13), ANTES que nada: de él sale la hora con que se fecha todo lo demás de este ciclo. Una fecha adelantada NO se acepta: ni la hora confiable, ni la marca
        # alta, ni las anclas, ni los hechos que se asientan llevan la del salto; el episodio vive en la base (una observación `reloj_salto_adelante` que abre y otra que cierra) para que
        # un reinicio no lo olvide, y una confirmación de la administración (`reloj_confirmado` posterior) también lo cierra. Se ordena por `id`: el salto tuerce las horas.
        marca_externa = max(e.anclas.marcas.values(), default=0)
        confirmado = e.obs[cat.O_CONFIRMADO]
        res = resolver_el_reloj(politica, ahora_reloj=e.ahora_reloj, monotono=e.monotono, previo=e.previo, marca_db=e.marca_db, marcas_externas=e.anclas.marcas.values(),
                                ultima_audit=e.ultima_audit, obs=e.obs)
        lectura = res.lectura
        ahora = lectura.ahora if res.adelantado else e.ahora_reloj

        def evento(clave: str, tipo: str, agregado_id: str, carga: dict, accion: str | None = None, detalle: dict | None = None) -> None:
            auditoria = {"accion": accion, "tabla": "m18_licencia", "objeto_id": agregado_id, "nuevo": detalle if detalle is not None else carga} if accion else None
            w.append(Escritura("evento", {"clave": clave, "agregado_tipo": "Licencia", "agregado_id": agregado_id, "tipo": tipo, "carga": {**carga, "instante": ahora}, "auditoria": auditoria}))

        def observar(tipo: str, licencia_id: str = "", serie: int = 0, detalle: dict | None = None) -> None:
            w.append(Escritura("observacion", {"tipo": tipo, "ahora": ahora, "licencia_id": licencia_id, "serie": serie, "detalle": detalle or {}}))

        # ---- 1. cuándo empezó la ventana de evaluación (P-14): en la base Y fuera de ella; si la base no la trae (restauró un respaldo viejo) vale la de afuera
        candidatas = [x for x in (e.instalacion["instalada_en"] if e.instalacion else None, e.anclas.instalada_en) if x is not None]
        instalada_en = min(candidatas) if candidatas else ahora
        if e.instalacion is None:
            w.append(Escritura("instalacion", {"ahora": instalada_en, "version": s.config.version_del_nodo}))
        if not candidatas:
            evento("evaluacion_iniciada", cat.EV_EVALUACION, "nodo", {"evaluacion_dias": politica.evaluacion_dias, "version": s.config.version_del_nodo}, cat.A_EVALUACION,
                   {"evaluacion_dias": politica.evaluacion_dias, "version": s.config.version_del_nodo})

        # ---- 2. las licencias: la de la base, la del espejo en la carpeta de estado y las que este nodo liberó
        lic_db = self._leer_licencia(e.vigente["archivo"] if e.vigente else None, e, observar, "base")
        lic_espejo = self._leer_licencia(e.espejo, e, observar, "espejo")
        tumbas = e.tumbas_externas | e.liberadas_db
        efectiva, fila_instalada_en, reactivada_en = lic_db, (e.vigente["instalada_en"] if e.vigente else None), None
        if e.vigente and e.vigente["tipo"] == cat.H_REACTIVADA and lic_db is not None:
            reactivada_en = e.vigente["instalada_en"]
        if lic_espejo is not None and (lic_espejo.id, lic_espejo.serie) not in tumbas and (lic_db is None or mas_nueva(lic_espejo, lic_db)):
            # FUN-194: la base no sabe de esta licencia (restauración de un respaldo más viejo) pero la carpeta de estado sí: se reactiva, sin pedir nada.
            w.append(Escritura("historial", {"licencia": lic_espejo, "tipo": cat.H_REACTIVADA, "archivo": e.espejo, "por": cat.SISTEMA, "ahora": ahora}))
            evento(f"reactivada:{lic_espejo.id}:{lic_espejo.serie}:{corto(lic_espejo.sha256)}", cat.EV_REACTIVADA, lic_espejo.id,
                   {"licencia_id": lic_espejo.id, "serie": lic_espejo.serie, "archivo": corto(lic_espejo.sha256)}, cat.A_REACTIVADA)
            efectiva, fila_instalada_en, reactivada_en = lic_espejo, ahora, ahora
        elif lic_db is not None and (lic_db.id, lic_db.serie) in tumbas:
            # La base trae una licencia que este nodo LIBERÓ (la restauración la resucitó): se vuelve a liberar. Se ignora también el espejo.
            w.append(Escritura("historial", {"tipo": cat.H_LIBERADA, "archivo": None, "licencia": lic_db, "por": cat.SISTEMA, "ahora": ahora}))
            efectiva, fila_instalada_en, reactivada_en = None, None, None
        if efectiva is lic_db and lic_db is not None and e.vigente and (lic_espejo is None or (lic_espejo.id, lic_espejo.serie) != (lic_db.id, lic_db.serie)):
            w.append(Escritura("espejo", {"datos": e.vigente["archivo"]}))                   # el espejo falta, está dañado o se quedó atrás de la base
        elif lic_espejo is not None and (lic_espejo.id, lic_espejo.serie) in tumbas:
            w.append(Escritura("espejo_borrar"))                                             # el espejo es de una licencia que este nodo liberó

        # ---- 3. lo que se asienta del reloj y la marca alta (P-06 · Q-L13). El piso monótono (H-13): con el reloj de pared por debajo de la marca, el tiempo de la licencia sigue corriendo
        # con el reloj monótono de ESTE proceso en vez de congelarse; con una fecha adelantada sin aceptar (Q-L13), igual: la hora confiable es la referencia, no la del salto.
        confirmado_en = confirmado["en"] if confirmado is not None else 0
        previo_ret = e.obs[cat.O_RETROCESO]
        if lectura.retroceso and (previo_ret is None or ahora - previo_ret["en"] >= cat.REPETICION_OBSERVACION_MS):
            observar(cat.O_RETROCESO, detalle={"atras_ms": lectura.atras_ms})
            evento(f"reloj_retroceso:{ahora // HORA_MS}", cat.EV_RELOJ, "nodo", {"tipo": "retroceso", "atras_ms": lectura.atras_ms}, cat.A_RELOJ)
            previo_ret = {"en": ahora}
        retroceso_activo = lectura.retroceso or (previo_ret is not None and previo_ret["en"] > confirmado_en and ahora - previo_ret["en"] < cat.BANDERA_RELOJ_MS)
        if res.abre_episodio:
            observar(cat.O_SALTO, detalle={"inicio": True, "adelanto_ms": res.adelanto_ms})
            evento(f"reloj_salto:{ahora // HORA_MS}", cat.EV_RELOJ, "nodo", {"tipo": "salto_adelante", "adelanto_ms": res.adelanto_ms}, cat.A_RELOJ)
        if res.cierra_episodio:
            observar(cat.O_SALTO, detalle={"fin": True})
            evento(f"reloj_normal:{ahora // HORA_MS}", cat.EV_RELOJ, "nodo", {"tipo": "normalizado"}, cat.A_RELOJ)
        marca = res.marca
        nueva_marca = rj.marca_siguiente(marca, lectura.ahora)
        # La marca alta sube en la base y en las anclas de afuera, cada una cuando se ha quedado atrás MARGEN o más (una escritura pequeña cada ~10 min), y al instante si una acción,
        # el arranque o una base restaurada (que quedó por debajo de las anclas) lo piden.
        if nueva_marca > e.marca_db and (e.origen != "tick" or nueva_marca - e.marca_db >= MARGEN_DE_MARCA_MS or e.instalacion is None or marca_externa > e.marca_db):
            w.append(Escritura("marca", {"valor": nueva_marca, "ahora": ahora}))
        if nueva_marca > marca_externa and (e.origen != "tick" or nueva_marca - marca_externa >= MARGEN_DE_MARCA_MS or e.instalacion is None or not e.anclas.marcas):
            w.append(Escritura("ancla", {"marca": nueva_marca, "instalada_en": instalada_en}))
        elif e.anclas.instalada_en != instalada_en:
            w.append(Escritura("ancla", {"marca": max(nueva_marca, marca_externa), "instalada_en": instalada_en}))

        # ---- 4. la integridad: anclas que no pasaron su verificación y secretos propios que hubo que apartar por no poder abrirlos (Windows reinstalado, disco clonado; se asienta UNA vez)
        previo_int = e.obs[cat.O_INTEGRIDAD]
        secretos = sorted({cat.NOMBRES_DE_SECRETO.get(nombre, "secreto") for nombre in e.novedades})
        if (e.anclas.alteradas or secretos) and (secretos or previo_int is None or ahora - previo_int["en"] >= 24 * HORA_MS):
            detalle = {"anclas": list(e.anclas.alteradas), **({"secretos": secretos} if secretos else {})}
            observar(cat.O_INTEGRIDAD, detalle=detalle)
            evento(f"integridad:{ahora // (24 * HORA_MS)}{':secretos' if secretos else ''}", cat.EV_INTEGRIDAD, "nodo", detalle, cat.A_INTEGRIDAD)
            previo_int = {"en": ahora}
        integridad = bool(e.anclas.alteradas) or bool(secretos) or (previo_int is not None and ahora - previo_int["en"] < cat.BANDERA_INTEGRIDAD_MS)

        # ---- 5. la huella de este equipo contra la de la licencia
        coincidencia = hu.comparar(efectiva.huella, e.actuales, e.inst_hash) if efectiva is not None else None
        huella_desde = None
        if efectiva is not None and coincidencia is not None:
            ini, fin = e.obs[cat.O_HUELLA_INICIO], e.obs[cat.O_HUELLA_FIN]
            de_esta = ini is not None and ini["licencia_id"] == efectiva.id and ini["serie"] == efectiva.serie
            abierta = de_esta and not (fin is not None and fin["licencia_id"] == efectiva.id and fin["serie"] == efectiva.serie and fin["en"] >= ini["en"])
            if not coincidencia.ok:
                if abierta:
                    huella_desde = ini["en"]
                else:
                    observar(cat.O_HUELLA_INICIO, efectiva.id, efectiva.serie, {"coinciden": coincidencia.coinciden, "k": coincidencia.k, "factores": coincidencia.en_licencia})
                    huella_desde = ahora
            elif abierta:
                observar(cat.O_HUELLA_FIN, efectiva.id, efectiva.serie, {"coinciden": coincidencia.coinciden})

        # ---- 6. el estado
        estado = est.calcular(est.Contexto(
            licencia=efectiva, ahora=lectura.ahora, instalada_en=instalada_en, coincidencia=coincidencia, licencia_instalada_en=fila_instalada_en, huella_distinta_desde=huella_desde,
            reactivada_en=reactivada_en, reloj_retroceso=retroceso_activo, reloj_adelanto_ms=res.adelanto_ms, integridad_alterada=integridad), politica)

        # ---- 7. los bloqueos de licencia (módulo apagado o cupo agotado) que las peticiones fueron contando en memoria: UN asiento por actor, clave y hora (P-09, R-07)
        for bloqueo in e.bloqueos:
            w.append(Escritura("bloqueo", dict(bloqueo)))

        # ---- 8. las transiciones que el tiempo provoca, con clave: una sola vez por episodio
        lic_id, serie = (efectiva.id, efectiva.serie) if efectiva is not None else ("nodo", 0)
        carga = {"estado": estado.estado, "motivo": estado.motivo, "dias_restantes": estado.dias_restantes, "licencia_id": lic_id, "serie": serie}
        if estado.estado in (cat.EN_GRACIA, cat.LIBERACION_PENDIENTE):
            evento(f"gracia:{lic_id}:{serie}:{estado.motivo}:{estado.hasta}", cat.EV_GRACIA, lic_id, carga, cat.A_GRACIA)
        elif estado.estado == cat.DEGRADADA:
            evento(f"degradada:{lic_id}:{serie}:{estado.motivo}:{estado.hasta}", cat.EV_DEGRADADAS, lic_id, carga, cat.A_DEGRADADA)
        elif estado.estado in (cat.ACTIVA, cat.REACTIVADA):
            umbral = est.umbral_de_aviso(estado.dias_restantes, politica)
            if umbral is not None:
                evento(f"aviso:{lic_id}:{serie}:{umbral}", cat.EV_AVISO, lic_id, {**carga, "umbral": umbral})
        if e.origen == "arranque":
            evento(f"validada:{s.vivo.arranque_id()}", cat.EV_VALIDADA, lic_id, carga)
        if e.consumo is not None:
            lim = estado.limites
            evento(f"consumo:{ahora // HORA_MS}", cat.EV_CONSUMO, "nodo", {"equipos": e.consumo.equipos, "usuarios": e.consumo.usuarios, "limite_equipos": lim.equipos, "limite_usuarios": lim.usuarios})
            w[-1].datos["consumo"] = {"ahora": ahora, "equipos": e.consumo.equipos, "usuarios": e.consumo.usuarios}      # FUN-190: se guarda una vez por hora, con su evento

        lim = estado.limites
        instantanea = Instantanea(
            estado=estado, avisos=tuple(est.avisos(estado, e.consumo, politica)), consumo=e.consumo, licencia=resumen_de_licencia(efectiva) if efectiva is not None else None,
            huella=resumen_de_huella(coincidencia, hu.nivel_de(e.actuales)), modo=s.config.modo, entorno=s.config.entorno, calculada_en=ahora,
            limites_de_concurrencia=cu.concurrencia(lim.concurrentes_normal, lim.concurrentes_pico, s.config.concurrencia_normal, s.config.concurrencia_pico))
        return Plan(w, instantanea)

    def _leer_licencia(self, datos: bytes | None, e: Entradas, observar, donde: str) -> Licencia | None:
        """Una licencia guardada, vuelta a verificar con las llaves de AHORA. Si ya no pasa (llaves distintas, archivo dañado, una de desarrollo en producción) se toma como ausente y se deja constancia."""
        if not datos:
            return None
        try:
            licencia = lic_mod.leer(bytes(datos), e.claves)
        except LicenciaInvalida as error:
            previa = e.obs[cat.O_FIRMA_INVALIDA]
            if previa is None or e.ahora_reloj - previa["en"] >= 24 * HORA_MS:
                observar(cat.O_FIRMA_INVALIDA, detalle={"donde": donde, "motivo": error.motivo})
            return None
        if licencia.tipo == lic_mod.TIPO_DESARROLLO and self.s.config.entorno == "produccion":
            return None
        return licencia

    # ------------------------------------------------------------------------------------------------------------------------- 3 · aplicar
    def _aplicar(self, escrituras: list[Escritura]) -> bool:
        """Escribe lo que el plan pide. `True` si los hechos de la base quedaron asentados (o no había ninguno); `False` si la base no los aceptó y se reintentan en el siguiente ciclo."""
        s = self.s
        en_base = [x for x in escrituras if x.tipo in ("instalacion", "historial", "observacion", "marca", "evento", "bloqueo")]
        if any(x.tipo == "evento" for x in en_base):
            # La mayoría de los ciclos no tiene nada nuevo: los eventos con clave ya existente se descartan con UNA lectura, para no abrir una transacción de escritura en vano (R-07).
            with s.uow(lectura=True) as uow:
                ya = uow.outbox.existentes([x.datos["clave"] for x in en_base if x.tipo == "evento"])
            en_base = [x for x in en_base if x.tipo != "evento" or x.datos["clave"] not in ya]
        if en_base:
            try:
                with s.uow() as uow:
                    for w in en_base:
                        self._una(uow, w)
            except Exception:   # noqa: BLE001 — la base ocupada no impide dar el estado; el siguiente tick reintenta (las claves hacen idempotente lo que sí quedó)
                log.exception("No se pudieron asentar los hechos de la licencia; se reintenta en el siguiente ciclo", extra={"evento": "licencia.escritura_fallo", "ruta": "bad"})
                return False
        for w in escrituras:
            try:
                if w.tipo == "espejo":
                    s.almacen.escribir(cat.ARCHIVO_ESPEJO, bytes(w.datos["datos"]))
                elif w.tipo == "espejo_borrar":
                    s.almacen.borrar(cat.ARCHIVO_ESPEJO)
                elif w.tipo == "ancla":
                    s.anclas.escribir(int(w.datos["marca"]), w.datos.get("instalada_en"))
            except Exception:   # noqa: BLE001 — una carpeta de estado que no se puede escribir se avisa, no cierra nada
                log.exception("No se pudo escribir en la carpeta de estado de la licencia", extra={"evento": "licencia.estado_fallo", "ruta": "bad"})
        return True

    @staticmethod
    def _una(uow, w: Escritura) -> None:
        d = w.datos
        if w.tipo == "instalacion":
            uow.instalacion.crear(d["ahora"], d["version"])
        elif w.tipo == "historial":
            lic = d["licencia"]
            uow.historial.insertar({"licencia_id": lic.id if lic else "", "serie": lic.serie if lic else 0, "kid": lic.kid if lic else "", "tipo": d["tipo"], "archivo": d["archivo"],
                                    "sha256": lic.sha256 if lic else "", "instalada_en": d["ahora"], "instalada_por": d["por"]})
        elif w.tipo == "observacion":
            uow.observaciones.registrar(d["tipo"], d["ahora"], d["licencia_id"], d["serie"], d["detalle"])
        elif w.tipo == "marca":
            uow.marca.subir(d["valor"], d["ahora"])
        elif w.tipo == "bloqueo":
            clave = str(d["clave"])
            detalle = {"cupo": clave.split(":", 1)[1]} if clave.startswith("cupo:") else {"capacidad": clave}
            uow.auditoria.registrar(cat.SISTEMA, cat.A_BLOQUEO, "m18_licencia", "nodo", nuevo={**detalle, "cantidad": int(d["cantidad"]), "hora": int(d["hora"]), "actor": str(d["actor"])[:64]})
        elif w.tipo == "evento":
            if uow.outbox.publicar(d["agregado_tipo"], d["agregado_id"], d["tipo"], d["carga"], clave=d["clave"]):
                if d["auditoria"]:
                    a = d["auditoria"]
                    uow.auditoria.registrar(cat.SISTEMA, a["accion"], a["tabla"], a["objeto_id"], nuevo=a["nuevo"])
                if d.get("consumo"):
                    uow.consumo.guardar(d["consumo"]["ahora"], d["consumo"]["equipos"], d["consumo"]["usuarios"])

    def _de_la_politica(self) -> Instantanea:
        """Sin estado bueno y sin poder evaluar: el de la política (la ventana de evaluación desde AHORA, con todo habilitado). Nada se restringe."""
        s = self.s
        ahora = s.reloj.ahora_ms()
        estado = est.calcular(est.Contexto(licencia=None, ahora=ahora, instalada_en=ahora), s.config.politica)
        lim = estado.limites
        return Instantanea(estado=estado, modo=s.config.modo, entorno=s.config.entorno, calculada_en=ahora,
                           limites_de_concurrencia=cu.concurrencia(lim.concurrentes_normal, lim.concurrentes_pico, s.config.concurrencia_normal, s.config.concurrencia_pico))
