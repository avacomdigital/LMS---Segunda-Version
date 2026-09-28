"""
La sesión de clase: estados, transiciones autorizadas (INV-025), participantes,
controles y eventos. Es lo que MOD-007 POSEE; el curso sólo se referencia.

Estados del Documento Maestro (sección H de MOD-007):
    planificada → abierta → suspendida → abierta …  → cerrada → archivada (24 h)
Una sesión cerrada nunca se reabre: se crea una nueva. Reanudar conserva el
mismo código de unión, porque cambiarlo rompería la reconexión de las tabletas.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from .catalogos import VIAS_ORIGEN
from .errores import DatosInvalidos, SesionCerrada, TransicionInvalida

# ------------------------------------------------------------------ estados

PLANIFICADA, ABIERTA, SUSPENDIDA, CERRADA, ARCHIVADA = "planificada", "abierta", "suspendida", "cerrada", "archivada"
ESTADOS_SESION = (PLANIFICADA, ABIERTA, SUSPENDIDA, CERRADA, ARCHIVADA)
ACTIVAS = (ABIERTA, SUSPENDIDA)      # cuentan para el código de unión y para el grupo (DEC-035)
TRANSICIONES: dict[str, frozenset[str]] = {
    PLANIFICADA: frozenset({ABIERTA}),
    ABIERTA: frozenset({SUSPENDIDA, CERRADA}),
    SUSPENDIDA: frozenset({ABIERTA, CERRADA}),
    CERRADA: frozenset({ARCHIVADA}),
    ARCHIVADA: frozenset(),
}
ARCHIVO_TRAS_MS = 24 * 60 * 60 * 1000   # cerrada → archivada a las veinticuatro horas


def comprobar_transicion(actual: str, nuevo: str) -> None:
    """INV-025: una sesión existe en exactamente un estado y sólo transita por transiciones autorizadas."""
    if nuevo not in TRANSICIONES.get(actual, frozenset()):
        if actual in (CERRADA, ARCHIVADA):
            raise SesionCerrada(f"La sesión está {actual} y no admite «{nuevo}».", estado=actual)
        raise TransicionInvalida(f"De «{actual}» no se pasa a «{nuevo}».", estado=actual, destino=nuevo)


def exigir_abierta(estado: str, accion: str = "esta acción") -> None:
    """BR-052: cerrada no admite participantes nuevos ni cambios de foco; suspendida tampoco opera."""
    if estado != ABIERTA:
        if estado in (CERRADA, ARCHIVADA):
            raise SesionCerrada(f"La sesión está {estado}: no admite {accion}.", estado=estado)
        raise TransicionInvalida(f"La sesión está {estado}: no admite {accion} hasta reanudarla.", estado=estado)


# ---------------------------------------------------------------- participantes

ESPERANDO, CONECTADO, RECONECTANDO, SALIO, RECHAZADO, EXPULSADO = (
    "esperando", "conectado", "reconectando", "salio", "rechazado", "expulsado")
ESTADOS_PARTICIPANTE = (ESPERANDO, CONECTADO, RECONECTANDO, SALIO, RECHAZADO, EXPULSADO)
ADMITIDOS = (CONECTADO, RECONECTANDO)          # cuentan como «dispositivo admitido» (FUN-070)
PRESENCIA_DECLARABLE = (CONECTADO, RECONECTANDO, SALIO)   # lo que una tableta puede declarar de sí misma (FUN-073)
CON_SALIDA = (SALIO, RECHAZADO, EXPULSADO)

# -------------------------------------------------------------------- controles

SEGUIMIENTO, BLOQUEO = "seguimiento", "bloqueo"
TIPOS_CONTROL = (SEGUIMIENTO, BLOQUEO)   # BR-050 y FUN-074

# --------------------------------------------------------------- distribuciones

RECURSO, ACTIVIDAD = "recurso", "actividad"
CLASES_DISTRIBUCION = (RECURSO, ACTIVIDAD)
GRUPO, SELECCION = "grupo", "seleccion"
ALCANCES = (GRUPO, SELECCION)
PENDIENTE, ENTREGADO, FALLIDO = "pendiente", "entregado", "fallido"
ESTADOS_ENTREGA = (PENDIENTE, ENTREGADO, FALLIDO)

ORIGENES_CIERRE = ("profesor", "inactividad", "administrador", "sistema")
CAUSAS_SUSPENSION = ("caida_nodo", "corte_electrico", "reinicio", "manual")

# ---------------------------------------------------------------------- eventos
# Los dieciséis eventos que publica MOD-007 (sección L del Maestro).
EV_SESION_INICIADA = "aula.sesion.iniciada.v1"
EV_CODIGO_GENERADO = "aula.codigo.generado.v1"
EV_CODIGO_ROTADO = "aula.codigo.rotado.v1"
EV_DISPOSITIVO_ADMITIDO = "aula.dispositivo.admitido.v1"
EV_DISPOSITIVO_RECHAZADO = "aula.dispositivo.rechazado.v1"
EV_DISPOSITIVO_READMITIDO = "aula.dispositivo.readmitido.v1"
EV_DISPOSITIVO_EXPULSADO = "aula.dispositivo.expulsado.v1"
EV_DISPOSITIVOS_BLOQUEADOS = "aula.dispositivos.bloqueados.v1"
EV_PRESENCIA_REGISTRADA = "aula.presencia.registrada.v1"
EV_RECURSO_PROYECTADO = "aula.recurso.proyectado.v1"
EV_ACTIVIDAD_LANZADA = "aula.actividad.lanzada.v1"
EV_ACTIVIDAD_CERRADA = "aula.actividad.cerrada.v1"
EV_RESULTADOS_MOSTRADOS = "aula.resultados.mostrados.v1"
EV_MENSAJE_ENVIADO = "aula.mensaje.enviado.v1"
EV_SESION_REANUDADA = "aula.sesion.reanudada.v1"
EV_SESION_FINALIZADA = "aula.sesion.finalizada.v1"
EVENTOS = (
    EV_SESION_INICIADA, EV_CODIGO_GENERADO, EV_CODIGO_ROTADO, EV_DISPOSITIVO_ADMITIDO, EV_DISPOSITIVO_RECHAZADO,
    EV_DISPOSITIVO_READMITIDO, EV_DISPOSITIVO_EXPULSADO, EV_DISPOSITIVOS_BLOQUEADOS, EV_PRESENCIA_REGISTRADA,
    EV_RECURSO_PROYECTADO, EV_ACTIVIDAD_LANZADA, EV_ACTIVIDAD_CERRADA, EV_RESULTADOS_MOSTRADOS, EV_MENSAJE_ENVIADO,
    EV_SESION_REANUDADA, EV_SESION_FINALIZADA,
)

# --------------------------------------------------------------------- permisos
# Los once permisos que exige MOD-007 (sección J). Los siembra MOD-001; aquí sólo se nombran.
P_START, P_CODE_ROTATE, P_DEVICE_ADMIT, P_DEVICE_REMOVE, P_DEVICE_LOCK = (
    "classroom.start", "classroom.code.rotate", "classroom.device.admit", "classroom.device.remove", "classroom.device.lock")
P_PRESENT, P_ACTIVITY_LAUNCH, P_ACTIVITY_CLOSE, P_RESULTS_VIEW, P_MESSAGE_SEND, P_END = (
    "classroom.present", "classroom.activity.launch", "classroom.activity.close", "classroom.results.view",
    "classroom.message.send", "classroom.end")
PERMISOS = (P_START, P_CODE_ROTATE, P_DEVICE_ADMIT, P_DEVICE_REMOVE, P_DEVICE_LOCK, P_PRESENT, P_ACTIVITY_LAUNCH,
            P_ACTIVITY_CLOSE, P_RESULTS_VIEW, P_MESSAGE_SEND, P_END)


# ------------------------------------------------------------------ vía de inicio

@dataclass(frozen=True)
class ViaDeInicio:
    """BR-044: cuatro vías, un mismo tipo de sesión. Cada vía exige sus referencias."""

    via: str
    curso_ref: str = ""
    leccion_ref: str = ""
    objeto_ref: str = ""
    nodo_ref: str = ""

    def validar(self) -> None:
        if self.via not in VIAS_ORIGEN:
            raise DatosInvalidos(f"La vía «{self.via}» no existe. Vías: {', '.join(VIAS_ORIGEN)}.", via=self.via)
        if self.via == "leccion" and not (self.curso_ref and self.leccion_ref):
            raise DatosInvalidos("La vía «leccion» exige curso_ref y leccion_ref.")
        if self.via == "recurso" and not (self.curso_ref and self.objeto_ref):
            raise DatosInvalidos("La vía «recurso» exige curso_ref y objeto_ref.")
        if self.via == "arbol" and not self.nodo_ref:
            raise DatosInvalidos("La vía «arbol» exige nodo_ref (nodo del árbol académico, MOD-003).")

    @property
    def necesita_curso(self) -> bool:
        return self.via in ("leccion", "recurso") or (self.via == "libre" and bool(self.curso_ref))


# ---------------------------------------------------------------- código de unión

def generar_codigo(ocupado=lambda codigo: False, intentos: int = 50) -> str:
    """Seis dígitos, legibles a cuatro metros (PAN-002). Se evita colisionar con las sesiones activas."""
    for _ in range(intentos):
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        if not ocupado(codigo):
            return codigo
    raise TransicionInvalida("No se pudo generar un código de unión libre.")


# --------------------------------------------------------------------- resumen

@dataclass
class ResumenSesion:
    """Lo que se conserva cinco años (m07_resumen)."""

    participantes: int = 0
    conectados_maximo: int = 0
    admitidos_nominal: int = 0
    selectores: int = 0
    distribuciones: int = 0
    actividades: int = 0
    avisos: int = 0
    pendientes: int = 0               # intentos abiertos al cierre (MOD-010, por el puerto)
    duracion_ms: int = 0
    origen_cierre: str = "profesor"
    consolidado_en: int = 0

    def como_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Selector:
    """Lo que el profesor tiene seleccionado para proyectar (BR-049). Se valida contra el curso vigente.
    No es un lanzamiento: no espera confirmación ni genera intentos."""

    curso_ref: str = ""
    curso_version: str = ""
    leccion_ref: str = ""
    objeto_ref: str = ""
    objeto_tipo: str = ""
    unidad_ref: str = ""
    unidad_indice: int | None = None
    media_ref: str = ""
    rotulo: str = ""
    extra: dict = field(default_factory=dict)

    def validar(self) -> None:
        if not (self.curso_ref or self.media_ref):
            raise DatosInvalidos("El selector exige curso_ref (y objeto_ref) o media_ref.")
        if self.unidad_ref and not self.objeto_ref:
            raise DatosInvalidos("Una unidad (lámina, página o pregunta) exige su objeto_ref.")


# ------------------------------------------------------------------ lanzamiento

def validar_regla_entera(valor, nombre: str, minimo: int = 1) -> int | None:
    """`intentos_permitidos` y `tiempo_limite_seg` del lanzamiento: enteros ≥ 1 o ausentes (manda el objeto)."""
    if valor in (None, ""):
        return None
    try:
        entero = int(valor)
    except (TypeError, ValueError):
        raise DatosInvalidos(f"{nombre} debe ser un entero.", **{nombre: valor})
    if entero < minimo:
        raise DatosInvalidos(f"{nombre} debe ser al menos {minimo}.", **{nombre: valor})
    return entero
