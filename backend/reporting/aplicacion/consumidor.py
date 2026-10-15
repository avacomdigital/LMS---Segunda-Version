"""
El consumidor de las colas de los módulos (`aula.*`, `evaluacion.*`, `calificacion.*`, `estudio.*`), la actualización periódica de los agregados y la reconstrucción.

  ConsumirEventos      lee la cola de salida de cada módulo desde SU marca de lectura, en el orden de su secuencia, y pone al día lo derivado (FUN-145: marca lo incompleto)
  ActualizarAgregados  FUN-144: fuera del horario de clase recalcula los agregados que quedaron desactualizados, deja que caduquen las señales y las exportaciones sin confirmar
  Reconstruir          FUN-147 / BR-007: borra TODAS las proyecciones, reinicia las marcas a cero y reproduce toda la cola; lo reconstruido es idéntico

Reglas, todas comprobadas por pruebas:
  · IDEMPOTENTE. Un evento no lleva el resultado: avisa que algo cambió y aquí se vuelve a leer la fuente de verdad (`proyectar.py`). Procesar dos veces el mismo no duplica nada.
  · ORDEN. Los eventos se aplican por secuencia; la marca sólo avanza dentro de la MISMA transacción que lo aplicado.
  · AISLADO. Un evento que no se puede aplicar se aísla (savepoint) y RETIENE la marca unos ciclos; si sigue fallando se deja atrás CON un asiento: nunca en silencio.
  · SIN CLASE ABIERTA NO HAY COSTE EN CLASE. Durante una clase, lo único que se aplica es la clase terminada; los agregados sólo se MARCAN como desactualizados y se recalculan
    después (o en el momento en que alguien pide ese reporte).
No es una cola nueva: lee la de cada módulo por su interfaz y guarda sólo su marca. Cuando exista MOD-015 las marcas se llevarán allí.
"""
from __future__ import annotations

import logging

from ..dominio import catalogos as cat
from ..dominio import integracion
from ..dominio.errores import SesionActiva
from .base import _CasoDeUso, _fuente
from .puertos import Actor, UnidadDeTrabajo
from .proyectar import Proyector

log = logging.getLogger("avacom.reporting.consumidor")


class _ConAvisos(_CasoDeUso):
    """Lo común de quienes pueden avisar `reporte.marcado_incompleto.v1`. Al RECONSTRUIR no se avisa: se rehace lo que ya existía y un aviso repetido no dice nada nuevo."""

    def __init__(self, servicios, *, sin_avisos: bool = False):
        super().__init__(servicios)
        self.sin_avisos = sin_avisos


class _Aplicador(_ConAvisos):
    """Aplica UN evento dentro de la transacción del consumidor."""

    def aplicar(self, uow: UnidadDeTrabajo, fuente: str, evento: dict, ahora: int) -> None:
        carga = evento.get("carga") or {}
        if fuente == cat.AULA:
            self._aula(uow, evento, carga, ahora)
        elif fuente == cat.ESTUDIO:
            self._estudio(uow, evento, carga, ahora)
            self._marcar(uow, fuente, evento, carga, ahora)
        else:
            self._marcar(uow, fuente, evento, carga, ahora)

    # ------------------------------------------------------------------------------------------------------------------- aula
    def _aula(self, uow: UnidadDeTrabajo, evento: dict, carga: dict, ahora: int) -> None:
        sesion_id = carga.get("sesion_id") or evento.get("agregado_id") or ""
        if not sesion_id:
            return
        if evento["tipo"] != cat.EV_AULA_FINALIZADA:
            # Una respuesta o un cambio de presencia de una clase que sigue abierta no cuesta nada: se mira sólo su fila, no su detalle.
            sesion = uow.aula.sesion(sesion_id)
            if sesion is None or sesion["estado"] not in cat.SESIONES_TERMINADAS:
                return
        r = Proyector(self.s).clase(uow, sesion_id, ahora)
        if r["nueva_incompletitud"]:
            self._avisar_incompleto(uow, "clase", sesion_id, r["grupo_id"], r["nueva_incompletitud"], ahora)

    # ----------------------------------------------------------------------------------------------------------------- estudio
    def _estudio(self, uow: UnidadDeTrabajo, evento: dict, carga: dict, ahora: int) -> None:
        """La cola de estudio de una tableta: `estudio.sesion.cerrada.v1` dice cuánto le quedó por enviar y `estudio.trabajo.integrado.v1`, que el nodo ya lo integró."""
        alumno, equipo = carga.get("alumno_id") or "", carga.get("dispositivo_id") or ""
        if not alumno or not equipo:
            return
        if evento["tipo"] == cat.EV_EST_SESION_CERRADA:
            cola = carga.get("cola_pendiente")
            cola = int(cola) if isinstance(cola, int) and not isinstance(cola, bool) and cola >= 0 else 0
            anterior = [f for f in uow.equipos_estado.pendientes_de([alumno]) if f["dispositivo_id"] == equipo]
            uow.equipos_estado.fijar(alumno, equipo, cola, ahora)
            if cola > 0 and not anterior:
                for grupo_id in uow.identidad.grupos_del_alumno(alumno):
                    self._avisar_incompleto(uow, "grupo", grupo_id, grupo_id, integracion.resumir([integracion.senal(equipo, cat.COLA_DE_ESTUDIO, ahora + 1)], 1, ahora), ahora)
        elif evento["tipo"] == cat.EV_EST_INTEGRADO:
            uow.equipos_estado.fijar(alumno, equipo, 0, ahora)

    # ------------------------------------------------------------------------------------------------------------------ marcar
    def _marcar(self, uow: UnidadDeTrabajo, fuente: str, evento: dict, carga: dict, ahora: int) -> None:
        """Un evento de evaluación, calificación o estudio avisa que cambió algo de un grupo: se marca su avance como desactualizado (se recalcula fuera de clase o al pedirlo)."""
        grupos = self._grupos_afectados(uow, fuente, evento["tipo"], carga)
        grupos = uow.identidad.todos_los_grupos() if grupos is None else grupos
        uow.avances.marcar_todos_sucios(list(grupos), ahora)

    @staticmethod
    def _grupos_afectados(uow: UnidadDeTrabajo, fuente: str, tipo: str, carga: dict) -> list[str] | None:
        """Los grupos que toca un evento, o None si no se puede saber (se marcan todos: es lo conservador). Un evento ligado a un alumno o a una asignación que no pertenece a
        ningún grupo (alumnos sueltos) no toca a ninguno."""
        if tipo in cat.EVENTOS_DE_ALCANCE_GLOBAL:
            nivel = carga.get("nivel_clave")
            return uow.identidad.grupos_de_nivel(nivel) if nivel else None
        grupos: set[str] = set()
        if carga.get("grupo_id"):
            grupos.add(carga["grupo_id"])
        alumno = carga.get("alumno_id")
        if alumno:
            grupos |= set(uow.identidad.grupos_del_alumno(alumno))
        asignacion_id = carga.get("asignacion_id")
        if asignacion_id:
            dueno = uow.estudio if fuente == cat.ESTUDIO else uow.evaluacion
            asignacion = dueno.asignacion(asignacion_id)
            if asignacion and asignacion.get("grupo_id"):
                grupos.add(asignacion["grupo_id"])
        if grupos:
            return sorted(grupos)
        return [] if (alumno or asignacion_id) else None

    # ------------------------------------------------------------------------------------------------------------- FUN-145
    def _avisar_incompleto(self, uow: UnidadDeTrabajo, ambito: str, referencia: str, grupo_id: str, integ: dict, ahora: int) -> None:
        """`reporte.marcado_incompleto.v1`: UNA vez por cambio (el reporte pasó de completo a incompleto, o ganó un motivo), nunca por cada lectura."""
        if self.sin_avisos:
            return
        self._publicar(uow, "Reporte", f"{ambito}:{referencia}", cat.EV_MARCADO_INCOMPLETO, {
            "ambito": ambito, "referencia": referencia, "grupo_id": grupo_id, "sin_sincronizar": integ["sin_sincronizar"], "equipos": integ["equipos"],
            "motivos": [m["codigo"] for m in integ["motivos"]]}, ahora)


class ConsumirEventos(_ConAvisos):
    def ejecutar(self, limite: int | None = None) -> dict:
        """Un ciclo sobre las cuatro fuentes. Devuelve lo leído y aplicado por fuente y si queda más por leer."""
        limite = limite or self.s.config.lote_eventos
        total = {"leidos": 0, "procesados": 0, "fallidos": [], "pendientes": False, "fuentes": {}}
        for nombre in cat.FUENTES:
            r = self._una_fuente(nombre, limite)
            total["leidos"] += r["leidos"]
            total["procesados"] += r["procesados"]
            total["fallidos"] += r["fallidos"]
            total["pendientes"] = total["pendientes"] or r["pendientes"]
            total["fuentes"][nombre] = r["marca"]
        return total

    def _una_fuente(self, nombre: str, limite: int) -> dict:
        tipos = cat.EVENTOS_CONSUMIDOS[nombre]
        # Sin nada nuevo que leer no hace falta el bloqueo de escritura del nodo: se mira primero SIN transacción (cada consulta de un reporte pasa por aquí).
        with self.s.uow(lectura=True) as uow:
            marca = uow.marcas.get(nombre)
            eventos, nueva = _fuente(uow, nombre).eventos_desde(marca, limite, tipos)
        if not eventos and nueva <= marca:
            return {"leidos": 0, "procesados": 0, "fallidos": [], "marca": marca, "pendientes": False}
        ahora = self.s.reloj.ahora_ms()
        procesados = 0
        fallidos: list[dict] = []
        with self.s.uow() as uow:
            estado = uow.marcas.estado(nombre)               # se vuelve a leer ya con el bloqueo: otro ciclo pudo adelantarse
            marca = estado["secuencia"]
            eventos, nueva = _fuente(uow, nombre).eventos_desde(marca, limite, tipos)
            aplicador = _Aplicador(self.s, sin_avisos=self.sin_avisos)
            primero: dict | None = None
            for evento in eventos:
                try:
                    with uow.aislado():
                        aplicador.aplicar(uow, nombre, evento, ahora)
                    procesados += 1
                except Exception as error:      # noqa: BLE001 — un evento que no se puede aplicar no detiene a los demás: se registra y se sigue con ellos
                    fallidos.append({"secuencia": evento["secuencia"], "tipo": evento["tipo"], "error": type(error).__name__})
                    log.exception("Reportes no pudo aplicar el evento %s de %s (%s)", evento["secuencia"], nombre, evento["tipo"])
                    primero = primero or {"evento": evento, "error": type(error).__name__}
            hasta, fallo_secuencia, fallos = nueva, 0, 0
            if primero is not None:
                # La marca NO pasa de largo del evento que falló: se reintenta en el ciclo siguiente (lo que va detrás ya quedó aplicado y reaplicarlo es idempotente).
                # Sólo tras `MAX_FALLOS_DE_EVENTO` ciclos seguidos se deja atrás, y entonces con un asiento en la bitácora: nunca se pierde en silencio.
                evento = primero["evento"]
                secuencia = evento["secuencia"]
                fallos = (estado["fallos"] if estado["fallo_secuencia"] == secuencia else 0) + 1
                if fallos >= cat.MAX_FALLOS_DE_EVENTO:
                    carga = evento.get("carga") or {}
                    uow.auditoria.registrar(cat.SISTEMA, cat.A_EVENTO_OMITIDO, f"{nombre}_evento_salida", str(secuencia), nuevo={
                        "fuente": nombre, "tipo": evento["tipo"], "alumno_id": carga.get("alumno_id"), "grupo_id": carga.get("grupo_id"), "sesion_id": carga.get("sesion_id"),
                        "error": primero["error"], "fallos": fallos})
                    log.error("Reportes dejó atrás el evento %s de %s (%s) tras %s fallos seguidos: queda en la bitácora; se corrige con una reconstrucción",
                              secuencia, nombre, evento["tipo"], fallos)
                    fallo_secuencia, fallos = 0, 0
                else:
                    hasta, fallo_secuencia = max(marca, min(nueva, secuencia - 1)), secuencia
            if hasta > marca or fallo_secuencia != estado["fallo_secuencia"] or fallos != estado["fallos"]:
                uow.marcas.guardar(nombre, max(marca, hasta), ahora, fallo_secuencia=fallo_secuencia, fallos=fallos)
            return {"leidos": len(eventos), "procesados": procesados, "fallidos": fallidos, "marca": max(marca, hasta), "pendientes": len(eventos) >= limite and not fallidos}

    def hasta_vaciar(self, paginas: int = 20) -> dict:
        """Procesa ciclos hasta alcanzar las colas (o `paginas` ciclos): lo que usa una consulta para responder con los reportes al día. Un ciclo con fallos se detiene ahí: cada
        ciclo (una consulta, el hilo del nodo) es UN reintento del evento que falló, no cinco seguidos."""
        total = {"leidos": 0, "procesados": 0, "fallidos": []}
        for _ in range(paginas):
            r = self.ejecutar()
            total["leidos"] += r["leidos"]
            total["procesados"] += r["procesados"]
            total["fallidos"] += r["fallidos"]
            if not r["pendientes"]:
                break
        return total


class RecalcularGrupos(_ConAvisos):
    """Recalcula el avance de los grupos desactualizados (todos o los pedidos). Una transacción por grupo: uno que falla no deshace a los demás."""

    def ejecutar(self, grupo_ids: list[str] | None = None) -> dict:
        with self.s.uow(lectura=True) as uow:
            pendientes = uow.avances.sucios() if grupo_ids is None else list(grupo_ids)
        recalculados = 0
        fallidos: list[str] = []
        for grupo_id in pendientes:
            ahora = self.s.reloj.ahora_ms()
            try:
                with self.s.uow() as uow:
                    Proyector(self.s).grupo(uow, grupo_id, ahora)
                recalculados += 1
            except Exception:       # noqa: BLE001 — un grupo con un dato roto no impide recalcular los demás
                log.exception("Reportes no pudo recalcular el avance del grupo %s", grupo_id)
                fallidos.append(grupo_id)
        return {"recalculados": recalculados, "fallidos": fallidos}


class ActualizarAgregados(_CasoDeUso):
    """FUN-144: la actualización periódica. Sólo corre FUERA del horario de clase —el nodo no sabe de horarios, sabe si hay una clase abierta—: con una clase en curso espera, para
    no competir con las tabletas por el turno de escritura. Pone al día la cola, recalcula los agregados sucios, limpia las señales de integración que ya caducaron y publica
    `reporte.agregados_actualizados.v1` sólo si algo cambió."""

    def ejecutar(self, *, forzar: bool = False) -> dict:
        with self.s.uow(lectura=True) as uow:
            if not forzar and uow.aula.hay_sesion_activa():
                return {"omitido": "clase_en_curso"}
        leidos = ConsumirEventos(self.s).hasta_vaciar(paginas=50)
        grupos = RecalcularGrupos(self.s).ejecutar()
        ahora = self.s.reloj.ahora_ms()
        limpiadas = 0
        with self.s.uow(lectura=True) as uow:
            con_senales = [c["sesion_id"] for c in uow.clases.con_senales() if not integracion.vigentes(c["senales"], ahora)]
        for sesion_id in con_senales:
            with self.s.uow() as uow:
                if Proyector(self.s).clase(uow, sesion_id, ahora)["cambio"]:
                    limpiadas += 1
        from .exportar import CaducarVencidas       # (importación tardía: `exportar` usa este módulo)

        caducadas = CaducarVencidas(self.s).ejecutar()
        with self.s.uow() as uow:
            uow.estado.anotar_actualizacion(ahora)
            if leidos["procesados"] or grupos["recalculados"] or limpiadas:
                self._publicar(uow, "Reportes", "agregados", cat.EV_AGREGADOS_ACTUALIZADOS, {
                    "eventos": leidos["procesados"], "grupos": grupos["recalculados"], "clases_con_senales_vencidas": limpiadas}, ahora)
        return {"eventos": leidos["procesados"], "fallidos": leidos["fallidos"], "grupos": grupos["recalculados"], "grupos_fallidos": grupos["fallidos"], "clases_limpiadas": limpiadas,
                "exportaciones_caducadas": caducadas}


class Reconstruir(_CasoDeUso):
    """FUN-147 / BR-007. Borra TODAS las proyecciones (sólo las derivadas: nunca la configuración, las exportaciones ni los recientes), reinicia las marcas a cero, reproduce toda la
    cola de cada módulo, proyecta lo que la cola no alcance a decir (una clase cerrada antes de que existieran sus eventos) y recalcula cada grupo. Lo reconstruido es IDÉNTICO.

    El cambio se confirma DE GOLPE: mientras dura, quien consulta sigue viendo los datos de antes (con el estado `reconstruyendose` y su antigüedad), y si algo falla no queda nada a medias."""

    def ejecutar(self, actor: Actor, *, desde_el_sistema: bool = False) -> dict:
        from ..dominio.errores import ReconstruccionEnCurso

        ahora = self.s.reloj.ahora_ms()
        por = actor.id or cat.SISTEMA
        with self.s.uow() as uow:
            if not desde_el_sistema:
                self.s.autorizacion.exigir(actor, cat.P_REBUILD)
            if uow.estado.get()["reconstruyendose"]:
                raise ReconstruccionEnCurso("Ya se están reconstruyendo los reportes: espera a que termine.")
            if uow.aula.hay_sesion_activa():
                raise SesionActiva("Hay una clase en curso: reconstruir los reportes espera a que termine para no competir con las tabletas.")
            uow.estado.empezar_reconstruccion(ahora, por)
        error = ""
        borradas: dict[str, int] = {}
        reproduccion: dict = {}
        proyectadas = 0
        grupos: dict = {"recalculados": 0, "fallidos": []}
        try:
            with self.s.uow():          # UNA transacción para todo el cambio: las demás son puntos de guardado dentro de ella
                with self.s.uow() as uow:
                    borradas = uow.proyecciones.borrar_derivadas()
                reproduccion = ConsumirEventos(self.s, sin_avisos=True).hasta_vaciar(paginas=100_000)
                proyectadas = self._clases_sin_proyectar(ahora)
                grupos = self._todos_los_grupos(ahora)
        except Exception as e:      # noqa: BLE001 — se deja dicho y el estado vuelve a «no reconstruyéndose»: nada queda a medias
            log.exception("Falló la reconstrucción de los reportes")
            error = f"{type(e).__name__}: {e}"[:300]
            raise
        finally:
            fin = self.s.reloj.ahora_ms()
            with self.s.uow() as uow:
                uow.estado.terminar_reconstruccion(fin, por, error)
        with self.s.uow() as uow:
            uow.auditoria.registrar(por, cat.A_RECONSTRUIDO, "m13_marca_consumidor", "", nuevo={
                "filas_borradas": borradas, "eventos": reproduccion.get("procesados"), "clases_proyectadas_de_mas": proyectadas, "grupos": grupos["recalculados"],
                "grupos_fallidos": len(grupos["fallidos"])})
            self._publicar(uow, "Reportes", "agregados", cat.EV_AGREGADOS_RECONSTRUIDOS, {"eventos": reproduccion.get("procesados"), "grupos": grupos["recalculados"],
                                                                                          "grupos_fallidos": len(grupos["fallidos"]), "por": por}, fin)
        return {"borradas": borradas, "eventos": reproduccion.get("procesados"), "fallidos": reproduccion.get("fallidos"), "clases_proyectadas_de_mas": proyectadas,
                "grupos": grupos["recalculados"], "grupos_fallidos": grupos["fallidos"], "servidor_en": fin}

    def _clases_sin_proyectar(self, ahora: int) -> int:
        """Las clases terminadas que la cola no llegó a proyectar (por ejemplo, cerradas antes de que existiera este módulo). Proyectar una ya proyectada no escribe nada."""
        with self.s.uow(lectura=True) as uow:
            ids = [s["id"] for s in uow.aula.sesiones() if s["estado"] in cat.SESIONES_TERMINADAS and uow.clases.get(s["id"]) is None]
        n = 0
        for sesion_id in ids:
            with self.s.uow() as uow:
                if Proyector(self.s).clase(uow, sesion_id, ahora)["cambio"]:
                    n += 1
        return n

    def _todos_los_grupos(self, ahora: int) -> dict:
        with self.s.uow() as uow:
            grupos = uow.identidad.todos_los_grupos()
            uow.avances.marcar_todos_sucios(grupos, ahora)
        return RecalcularGrupos(self.s, sin_avisos=True).ejecutar()
