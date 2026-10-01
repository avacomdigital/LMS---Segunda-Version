"""
El motor de MOD-010: las operaciones que comparten varios casos de uso y que no pertenecen a uno solo.

  asegurar_asignacion / asegurar_intento   las transiciones que el RELOJ ya provocó (D-15). Idempotentes: cada caso de uso las aplica antes de
                                           leer o escribir, y el programador del nodo las aplica a todo el nodo cada 5 s. La corrección no depende
                                           de que el hilo del programador esté vivo.
  entregar / _calificar                    FUN-114, FUN-112, FUN-113: entregar un intento y calificarlo con UNA llamada por lote a la biblioteca
  incidente                                FUN-117: un incidente se registra, se sella y se publica; NUNCA cambia el estado del intento (BR-077)
  plan_de_bloqueo                          D-12: lo que la tableta debe aplicar, decidido por el nodo

INV-018: ninguna función de este archivo lleva un intento a `anulado`.
"""
from __future__ import annotations

from ..dominio import asignacion as asig_dom
from ..dominio import bloqueo
from ..dominio import catalogos as cat
from ..dominio import intento as int_dom
from ..dominio import respuestas as resp_dom
from ..dominio.errores import DatosInvalidos
from .base import Servicios, nuevo_id
from .puertos import UnidadDeTrabajo

SISTEMA = cat.SISTEMA


class Motor:
    def __init__(self, servicios: Servicios):
        self.s = servicios

    # ----------------------------------------------------------------------------------- publicar y avisar

    def publicar(self, uow: UnidadDeTrabajo, agregado_tipo: str, agregado_id: str, evento: str, carga: dict, ahora: int) -> None:
        uow.outbox.publicar(agregado_tipo, agregado_id, evento, {**carga, "instante": ahora})

    @staticmethod
    def avisar(uow: UnidadDeTrabajo, asignacion: dict, que: str = "evaluacion", **carga) -> None:
        """El aviso de tiempo real sólo nace en una clase; sin ella funcionan el latido y el sondeo."""
        if asignacion.get("sesion_id"):
            uow.tiempo_real.cambio(asignacion["sesion_id"], que, {"asignacion_id": asignacion["id"], **carga})

    # ---------------------------------------------------------------------------------------- incidentes

    def incidente(self, uow: UnidadDeTrabajo, intento: dict, tipo: str, ahora: int, *, detalle: dict | None = None,
                  dispositivo_id: str | None = None, ref_cliente: str = "", reportado_en_tableta: int | None = None,
                  ocurrido_en: int | None = None, actor: str = SISTEMA, asignacion: dict | None = None) -> tuple[dict, bool]:
        """FUN-117. Idempotente por `ref_cliente`. Un incidente alimenta el expediente de integridad y nunca modifica el estado del intento."""
        definicion = cat.INCIDENTES.get(tipo)
        if definicion is None:
            raise DatosInvalidos(f"Tipo de incidente desconocido: «{tipo}».", tipo=tipo, tipos=sorted(cat.INCIDENTES))
        fila, creada = uow.incidentes.crear({
            "id": nuevo_id(), "intento_id": intento["id"], "tipo": tipo, "severidad": definicion.severidad, "origen": definicion.origen,
            "ocurrido_en": ahora if ocurrido_en is None else int(ocurrido_en), "reportado_en_tableta": reportado_en_tableta,
            "dispositivo_id": (dispositivo_id if dispositivo_id is not None else intento.get("dispositivo_id")) or "",
            "detalle": dict(detalle or {}), "resolucion": cat.RESOLUCION_REGISTRADO, "ref_cliente": str(ref_cliente or "")[:64]})
        if creada:
            self.publicar(uow, "Intento", intento["id"], cat.EV_INCIDENTE, {
                "incidente_id": fila["id"], "intento_id": intento["id"], "asignacion_id": intento["asignacion_id"],
                "dispositivo_id": fila["dispositivo_id"], "tipo": tipo, "severidad": definicion.severidad,
                "resolucion": fila["resolucion"]}, ahora)
            uow.auditoria.registrar(actor, "evaluacion.incidente.registrado", "m10_incidente", fila["id"],
                                    nuevo={"tipo": tipo, "severidad": definicion.severidad, "origen": definicion.origen,
                                           "intento_id": intento["id"]}, dispositivo_id=fila["dispositivo_id"] or None)
            if asignacion is not None:
                self.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
        return fila, creada

    # --------------------------------------------------------------------------- el plan de bloqueo (D-12)

    @staticmethod
    def plan_de_bloqueo(intento: dict, asignacion: dict, capacidad: str) -> dict:
        return bloqueo.plan_de_bloqueo(intento["nivel_efectivo"], capacidad, nivel_exigido=asignacion["nivel_examen"])

    # --------------------------------------------------------------- transiciones por tiempo de la asignación

    def asegurar_asignacion(self, uow: UnidadDeTrabajo, asignacion: dict, ahora: int) -> dict:
        """Aplica lo que el reloj ya provocó (D-15): `programada → activa`, `activa → activa_fuera_de_plazo | cerrada`, `cerrada → archivada`.
        Un plazo endurecido vencido CIERRA y entrega los intentos abiertos (TST-033); uno blando sólo marca (BR-073)."""
        nuevo = asig_dom.estado_por_tiempo(asignacion, ahora, self.s.config.archivado_ms)
        anterior = asignacion["estado"]
        if nuevo == anterior:
            return asignacion
        campos: dict = {"estado": nuevo}
        if anterior == cat.PROGRAMADA:
            campos["publicada_en"] = asignacion.get("abre_en") or ahora
        cierre = None
        if nuevo == cat.CERRADA:
            cierre = asig_dom.cierre_por_plazo(asignacion) or ahora
            campos["cerrada_en"] = cierre
        if nuevo == cat.ARCHIVADA:
            campos["archivada_en"] = ahora
        asignacion = uow.asignaciones.actualizar(asignacion["id"], **campos)
        if nuevo == cat.ACTIVA_FUERA_DE_PLAZO:
            for it in uow.intentos.de_asignacion(asignacion["id"], (cat.EN_CURSO, cat.PAUSADO, cat.RESTAURANDO)):
                cambios = int_dom.vencio_el_plazo_blando(it)
                if cambios:
                    uow.intentos.actualizar(it["id"], **cambios)
        elif nuevo == cat.CERRADA:
            self._entregar_abiertos(uow, asignacion, ahora, cierre, cat.O_PLAZO)
            self.publicar(uow, "Asignacion", asignacion["id"], cat.EV_ASIGNACION_CERRADA, {
                "asignacion_id": asignacion["id"], "origen": "plazo", "cerrada_en": cierre}, ahora)
            uow.auditoria.registrar(SISTEMA, "evaluacion.asignacion.cerrada", "m10_asignacion", asignacion["id"],
                                    anterior={"estado": anterior}, nuevo={"estado": cat.CERRADA, "origen": "plazo"})
        self.avisar(uow, asignacion)
        return asignacion

    def _entregar_abiertos(self, uow: UnidadDeTrabajo, asignacion: dict, ahora: int, cierre_en: int, origen: str) -> int:
        """Al cerrar la asignación: lo respondido se entrega tal cual (no se pierde nada) y los `no_iniciado` quedan como evidencia."""
        entregados = 0
        for it in uow.intentos.de_asignacion(asignacion["id"], (cat.EN_CURSO, cat.EN_CURSO_FUERA_DE_PLAZO, cat.PAUSADO, cat.RESTAURANDO)):
            hasta, por_tiempo = self._corte_de_reloj(it, ahora, cierre_en)
            self.entregar(uow, it, asignacion, ahora, cat.O_TIEMPO if por_tiempo else origen, hasta=hasta,
                          incidente="tiempo_agotado" if por_tiempo else "entrega_automatica",
                          detalle={"limite_seg": it.get("tiempo_limite_seg")} if por_tiempo else {"limite_en": cierre_en, "origen": origen})
            entregados += 1
        return entregados

    def _corte_de_reloj(self, intento: dict, ahora: int, tope: int) -> tuple[int, bool]:
        """(hasta dónde llegó el reloj, ¿se agotó el tiempo antes?) de un intento que hay que cerrar en `tope`. Un intento que estuvo en silencio
        tiene el reloj detenido en su último latido; uno que ya había agotado su tiempo se entrega en ese instante, no en el cierre."""
        corte = min(ahora, tope)
        if intento["estado"] in cat.CORRIENDO:
            ultimo = intento.get("ultimo_latido_en") or intento.get("reloj_desde") or corte
            if ahora - ultimo > self.s.config.latido_vencido_ms:
                corte = min(corte, max(ultimo, intento.get("reloj_desde") or ultimo))
            agota = int_dom.instante_de_agotamiento(intento)
            if agota is not None and agota <= corte:
                return agota, True
        return corte, False

    # --------------------------------------------------------------------- transiciones por tiempo del intento

    def asegurar_intento(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, ahora: int) -> dict:
        """Lo que el reloj ya provocó en UN intento: si el tiempo se agotó, se entrega (TST-032); si la tableta dejó de dar señal, se pausa y el
        reloj se detiene en su último latido (INV-010). El agotamiento se evalúa primero y sólo hasta donde llegó el reloj: un alumno desconectado
        no consume tiempo mientras no hay señal."""
        if intento["estado"] not in cat.CORRIENDO:
            return intento
        umbral = self.s.config.latido_vencido_ms
        ultimo = intento.get("ultimo_latido_en") or intento.get("reloj_desde") or ahora
        silencio = ahora - ultimo
        fin_efectivo = ahora if silencio <= umbral else ultimo
        agota = int_dom.instante_de_agotamiento(intento)
        if agota is not None and agota <= fin_efectivo:
            return self.entregar(uow, intento, asignacion, ahora, cat.O_TIEMPO, hasta=agota, incidente="tiempo_agotado",
                                 detalle={"limite_seg": intento.get("tiempo_limite_seg")})
        if silencio > umbral:
            return self.pausar(uow, intento, asignacion, ahora, cat.C_SIN_LATIDO)
        return intento

    def pausar(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, ahora: int, causa: str) -> dict:
        cambios = int_dom.pausar(intento, ahora, causa)
        silencio = int_dom.silencio_ms(intento, ahora)
        ultimo = intento.get("ultimo_latido_en")
        intento = uow.intentos.actualizar(intento["id"], **cambios)
        # La desconexión OCURRIÓ cuando se perdió la señal (el último latido), no cuando el nodo lo notó: así queda en su sitio de la línea de tiempo.
        self.incidente(uow, intento, "desconexion", ahora, detalle={"ultimo_latido_en": ultimo, "silencio_ms": silencio, "detectado_en": ahora},
                       ocurrido_en=cambios["pausas"][-1]["desde"], asignacion=asignacion)
        self.publicar(uow, "Intento", intento["id"], cat.EV_INTENTO_PAUSADO, {
            "intento_id": intento["id"], "asignacion_id": intento["asignacion_id"], "alumno_id": intento["alumno_id"], "causa": causa,
            "reloj_congelado_en": cambios["pausas"][-1]["desde"]}, ahora)
        uow.auditoria.registrar(SISTEMA, "evaluacion.intento.pausado", "m10_intento_formal", intento["id"],
                                anterior={"estado": cat.EN_CURSO}, nuevo={"estado": cat.PAUSADO, "causa": causa},
                                dispositivo_id=intento.get("dispositivo_id") or None)
        self.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
        return intento

    # ------------------------------------------------------------------------------ entregar y calificar

    def entregar(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, ahora: int, origen: str, *, hasta: int | None = None,
                 actor: str = SISTEMA, incidente: str | None = None, detalle: dict | None = None) -> dict:
        """FUN-114: lleva el intento a `entregado`, lo califica (FUN-112) y publica. Idempotente: un intento ya entregado se devuelve tal cual."""
        if intento["estado"] in cat.ENTREGADOS or intento["estado"] == cat.ANULADO:
            return intento
        cambios = int_dom.entregar(intento, ahora, origen, hasta)
        corte = cambios["entregado_en"]
        limite = asignacion.get("limite_en")
        fuera = bool(intento.get("fuera_de_plazo")) or (asignacion["plazo"] == cat.BLANDO and limite is not None and corte > limite)
        cambios["fuera_de_plazo"] = fuera
        anterior = intento["estado"]
        intento = uow.intentos.actualizar(intento["id"], **cambios)
        if incidente:
            self.incidente(uow, intento, incidente, ahora, detalle=detalle, actor=actor, asignacion=asignacion)
        intento, nota = self._calificar(uow, intento, asignacion, ahora)
        self.publicar(uow, "Intento", intento["id"], cat.EV_INTENTO_ENTREGADO, {
            "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"],
            "entregado_en": intento["entregado_en"], "origen_entrega": origen, "respuestas_contadas": len(intento["respuestas"]),
            "requiere_revision": nota["requiere_revision"], "fuera_de_plazo": fuera}, ahora)
        if fuera:
            self.publicar(uow, "Intento", intento["id"], cat.EV_INTENTO_FUERA_DE_PLAZO, {
                "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"],
                "limite_en": limite, "entregado_en": intento["entregado_en"]}, ahora)
        self._eventos_de_calificacion(uow, intento, asignacion, nota, ahora)
        uow.auditoria.registrar(actor, cat.A_INTENTO_ENTREGADO, "m10_intento_formal", intento["id"],
                                anterior={"estado": anterior}, nuevo={"estado": intento["estado"], "origen_entrega": origen,
                                                                       "respuestas": len(intento["respuestas"])},
                                dispositivo_id=intento.get("dispositivo_id") or None)
        self.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
        return intento

    def _calificar(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, ahora: int, *, por: str = SISTEMA) -> tuple[dict, dict]:
        """FUN-112/113 (D-16): UNA llamada por lote a la biblioteca con la versión del intento (nunca otra). Escala interna 0–100. Un reactivo que
        la biblioteca marca para corrección manual deja el puntaje nulo y el intento `en_revision_docente`. Sin biblioteca, el intento queda
        `entregado` con `calificacion_pendiente` y se resuelve después (INV-005: el resultado es el mismo). Devuelve (intento, nota)."""
        respuestas = [dict(r) for r in intento["respuestas"]]
        por_calificar = resp_dom.sin_veredicto(respuestas)
        if por_calificar:
            veredictos = self.s.contenido.calificar(
                asignacion["fuente_curso"], asignacion["curso_ref"], intento["curso_version"],
                [{"objeto_ref": asignacion["objeto_ref"], "pregunta_ref": r["pregunta_ref"], "respuesta": r["respuesta"]} for r in por_calificar])
            for r in respuestas:
                v = veredictos.get(r["pregunta_ref"])
                if v is not None and r.get("veredicto") is None:
                    r["veredicto"] = v
        sin_veredicto = resp_dom.sin_veredicto(respuestas)
        pendiente_de_biblioteca = bool(sin_veredicto)
        totales = resp_dom.totales(respuestas, intento["armado"], (intento.get("armado_meta") or {}).get("puntos") or {})
        revision = resp_dom.requiere_revision(respuestas)
        campos: dict = {"respuestas": respuestas, "puntaje": totales["puntaje"], "puntaje_maximo": totales["puntaje_maximo"],
                        "porcentaje": totales["porcentaje"], "sin_calificar": totales["sin_calificar"], "requiere_revision": revision,
                        "calificacion_pendiente": pendiente_de_biblioteca}
        if pendiente_de_biblioteca:
            # Sin el veredicto de la biblioteca no hay ni una nota parcial: un cero provisional se leería como una calificación (INV-005: el
            # resultado de calificar después es el mismo que el de calificar ahora, y mientras tanto no se afirma nada).
            campos.update(puntaje=None, puntaje_maximo=None, porcentaje=None)
        destino = intento["estado"]
        if not pendiente_de_biblioteca:
            destino = int_dom.tras_calificar(revision)
            if destino == cat.CALIFICADO:
                campos.update(calificado_por=por, calificado_en=ahora, porcentaje=totales["porcentaje"] if totales["porcentaje"] is not None else 0.0)
            elif intento["estado"] == cat.CALIFICADO:
                campos.update(calificado_por="", calificado_en=None)      # un envío tardío trajo reactivos de revisión (E-4)
        if destino != intento["estado"]:
            int_dom.comprobar_transicion(intento["estado"], destino)
            campos["estado"] = destino
        intento = uow.intentos.actualizar(intento["id"], **campos)
        return intento, {"requiere_revision": revision, "calificacion_pendiente": pendiente_de_biblioteca, "estado": destino,
                         "calificadas": len(respuestas) - totales["sin_calificar"], "porcentaje": totales["porcentaje"],
                         "califico": bool(por_calificar)}              # False: no había nada nuevo que mandar a la biblioteca

    def _eventos_de_calificacion(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, nota: dict, ahora: int) -> None:
        base = {"intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"]}
        if nota["calificacion_pendiente"]:
            return
        self.publicar(uow, "Intento", intento["id"], cat.EV_AUTOCALIFICACION, {
            **base, "porcentaje": intento.get("porcentaje"), "sin_calificar": intento.get("sin_calificar", 0),
            "requiere_revision": nota["requiere_revision"], "regla": "autocalificacion_v1"}, ahora)
        if nota["requiere_revision"]:
            self.publicar(uow, "Intento", intento["id"], cat.EV_REVISION_SOLICITADA, {
                **base, "pendientes": resp_dom.pendientes_de_revision(intento["respuestas"])}, ahora)
        else:
            self.publicar(uow, "Intento", intento["id"], cat.EV_INTENTO_CALIFICADO, {
                **base, "porcentaje": intento.get("porcentaje"), "calificado_por": intento.get("calificado_por")}, ahora)
            uow.auditoria.registrar(SISTEMA, "evaluacion.intento.calificado", "m10_intento_formal", intento["id"],
                                    nuevo={"porcentaje": intento.get("porcentaje"), "calificado_por": intento.get("calificado_por")})

    def recalificar(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, ahora: int) -> dict:
        """Reintenta la calificación pendiente (la biblioteca no estaba al entregar). Idempotente."""
        if intento["estado"] not in cat.ENTREGADOS:
            return intento
        intento, nota = self._calificar(uow, intento, asignacion, ahora)
        if nota["califico"]:                   # recalificar lo ya calificado no repite los eventos (INV-005)
            self._eventos_de_calificacion(uow, intento, asignacion, nota, ahora)
        return intento

    # ------------------------------------------------------------------------------------- lo que ve el alumno

    @staticmethod
    def resultado_disponible(asignacion: dict, intento: dict) -> bool:
        """DEC-032: el alumno NUNCA ve su nota antes de que el profesor la publique. Con reactivos por revisar no hay resultado parcial (Q-84)."""
        if intento["estado"] != cat.CALIFICADO or intento.get("calificacion_pendiente"):
            return False
        if asignacion["resultados"] == cat.NUNCA:
            return False
        if asignacion["resultados"] == cat.AL_ENTREGAR:
            return True
        return asignacion.get("liberados_en") is not None

    def estado_del_intento(self, intento: dict, asignacion: dict, capacidad: str, ahora: int, *, sesion_activa: bool = True) -> dict:
        """El cuerpo de `GET /estado/` y del latido: lo que la tableta necesita para saber qué pintar (PAN-121, PAN-122)."""
        suspendido = intento["estado"] in cat.SUSPENDIDOS
        mensaje = None
        if suspendido:
            mensaje = {"codigo": "suspendido", "texto": cat.MENSAJE_SUSPENDIDO}
        elif intento["estado"] == cat.NO_INICIADO:
            mensaje = {"codigo": "espera_admision", "texto": cat.MENSAJE_EN_ESPERA}
        elif not sesion_activa and intento["estado"] in cat.ACEPTAN_RESPUESTAS:
            mensaje = {"codigo": "otra_tableta", "texto": "Este examen continúa en otra tableta. Puedes cerrar esta pantalla."}
        respondidas = len(intento["respuestas"])
        return {
            "intento": {"id": intento["id"], "asignacion_id": intento["asignacion_id"], "estado": intento["estado"], "numero": intento["numero"],
                        "nivel_efectivo": intento["nivel_efectivo"], "pregunta_actual": intento.get("pregunta_actual") or "",
                        "respondidas": respondidas, "total": len(intento["armado"]), "fuera_de_plazo": bool(intento.get("fuera_de_plazo")),
                        "envio_tardio": intento.get("envio_tardio") or "", "navegacion_atras": bool(asignacion.get("permite_retroceso", True)),
                        "secuencia_maxima": intento.get("secuencia_maxima") or 0},
            "reloj": int_dom.reloj(intento, ahora),
            "plan_bloqueo": self.plan_de_bloqueo(intento, asignacion, capacidad),
            "espera_reactivacion": suspendido,
            "sesion_activa": sesion_activa,
            "mensaje": mensaje,
            "resultado_disponible": self.resultado_disponible(asignacion, intento),
            "latido_seg": self.s.config.latido_seg,
            "servidor_en": ahora,
        }
