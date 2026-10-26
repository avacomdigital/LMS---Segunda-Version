"""
Calendario y retención de los respaldos (FUN-169, CAP-100, BR-017). Puro: recibe instantes y devuelve decisiones; no lee el reloj ni la zona horaria (las pone el llamador).

  · Un respaldo automático corre a una hora local del equipo, en los días elegidos. Si el equipo estaba apagado a esa hora, se recupera al encender (se pone al día UNA vez).
  · Entre dos completos van incrementales: un completo cada `completo_cada_dias` días (por defecto 7).
  · La retención guarda los últimos N respaldos y NUNCA deja sin base a un incremental que se conserva ni borra el último restaurable.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import catalogos as cat
from .errores import DatosInvalidos

DESTINOS = ("local",)          # exportar a una unidad es SIEMPRE manual y con pase (D-19): el calendario no saca datos del equipo


@dataclass(frozen=True)
class Programa:
    activo: bool = True
    hora_min: int = cat.HORA_POR_DEFECTO_MIN         # minutos desde la medianoche local
    dias: tuple[int, ...] = cat.DIAS                 # lunes = 0
    completo_cada_dias: int = cat.COMPLETO_CADA_DIAS
    retencion: int = cat.RETENCION_POR_DEFECTO
    incluir_reinstalable: bool = False               # el contenido reinstalable (biblioteca, medios en caché) no entra salvo que se pida
    destino: str = "local"


def validar(datos: dict, actual: Programa | None = None) -> Programa:
    """Aplica los campos recibidos sobre el programa actual (los que faltan no cambian) y rechaza lo absurdo."""
    base = actual or Programa()
    if not isinstance(datos, dict):
        raise DatosInvalidos("La programación debe ser un objeto.")

    def entero(nombre: str, minimo: int, maximo: int, defecto: int) -> int:
        v = datos.get(nombre, defecto)
        if isinstance(v, bool) or not isinstance(v, int) or not minimo <= v <= maximo:
            raise DatosInvalidos(f"`{nombre}` debe ser un entero entre {minimo} y {maximo}.", campo=nombre)
        return v

    activo = datos.get("activo", base.activo)
    incluir = datos.get("incluir_reinstalable", base.incluir_reinstalable)
    if not isinstance(activo, bool) or not isinstance(incluir, bool):
        raise DatosInvalidos("`activo` e `incluir_reinstalable` son verdadero o falso.")
    dias = datos.get("dias", list(base.dias))
    if not isinstance(dias, (list, tuple)) or not dias or any(isinstance(d, bool) or not isinstance(d, int) or d not in cat.DIAS for d in dias):
        raise DatosInvalidos("`dias` es una lista de 0 (lunes) a 6 (domingo), sin vacíos.", campo="dias")
    destino = datos.get("destino", base.destino)
    if destino not in DESTINOS:
        raise DatosInvalidos(f"`destino` es uno de {', '.join(DESTINOS)}.", campo="destino")
    return Programa(activo=activo, hora_min=entero("hora_min", 0, 1439, base.hora_min), dias=tuple(sorted(set(dias))),
                    completo_cada_dias=entero("completo_cada_dias", 1, 60, base.completo_cada_dias), retencion=entero("retencion", 3, 120, base.retencion),
                    incluir_reinstalable=incluir, destino=destino)


def a_dict(p: Programa) -> dict:
    return {"activo": p.activo, "hora_min": p.hora_min, "dias": list(p.dias), "completo_cada_dias": p.completo_cada_dias, "retencion": p.retencion,
            "incluir_reinstalable": p.incluir_reinstalable, "destino": p.destino}


def _dia_y_minuto_local(instante_ms: int, desfase_min: int) -> tuple[int, int, int]:
    """(número de día local desde 1970, día de la semana con lunes = 0, minuto del día) de un instante, con el desfase de la zona horaria del equipo."""
    local = int(instante_ms) // cat.MINUTO_MS + int(desfase_min)
    dia, minuto = divmod(local, 1440)
    return dia, (dia + 3) % 7, minuto      # el 1 de enero de 1970 fue jueves (= 3)


def ultimo_horario(programa: Programa, ahora_ms: int, desfase_min: int) -> int | None:
    """El instante (ms) del último horario programado que ya pasó, o None si el programa no tiene ninguno en la última semana."""
    dia, _, minuto = _dia_y_minuto_local(ahora_ms, desfase_min)
    for atras in range(0, 8):
        d = dia - atras
        if (d + 3) % 7 not in programa.dias:
            continue
        if atras == 0 and minuto < programa.hora_min:
            continue
        return (d * 1440 + programa.hora_min - int(desfase_min)) * cat.MINUTO_MS
    return None


def siguiente_horario(programa: Programa, ahora_ms: int, desfase_min: int) -> int | None:
    """El próximo horario programado (ms) después de `ahora_ms`, o None si el programa está apagado."""
    if not programa.activo:
        return None
    dia, _, minuto = _dia_y_minuto_local(ahora_ms, desfase_min)
    for adelante in range(0, 8):
        d = dia + adelante
        if (d + 3) % 7 not in programa.dias:
            continue
        if adelante == 0 and minuto >= programa.hora_min:
            continue
        return (d * 1440 + programa.hora_min - int(desfase_min)) * cat.MINUTO_MS
    return None


def corresponde(programa: Programa, ahora_ms: int, ultimo_automatico_ms: int | None, desfase_min: int) -> int | None:
    """
    ¿Toca un respaldo automático? Devuelve el horario que se está cumpliendo (ms) o None. Toca si hay un horario ya pasado que NINGÚN respaldo automático cubrió; se pone al día una vez,
    aunque el equipo haya estado apagado varios horarios.
    """
    if not programa.activo:
        return None
    horario = ultimo_horario(programa, ahora_ms, desfase_min)
    if horario is None:
        return None
    if ultimo_automatico_ms is not None and int(ultimo_automatico_ms) >= horario:
        return None
    return horario


def tipo_que_toca(programa: Programa, ultimo_completo_ms: int | None, ahora_ms: int) -> str:
    """Completo si no hay ninguno o ya pasaron `completo_cada_dias` (con medio día de holgura: el horario no cae al milisegundo); si no, incremental."""
    if ultimo_completo_ms is None:
        return cat.T_COMPLETO
    if int(ahora_ms) - int(ultimo_completo_ms) >= programa.completo_cada_dias * cat.DIA_MS - 12 * cat.HORA_MS:
        return cat.T_COMPLETO
    return cat.T_INCREMENTAL


@dataclass(frozen=True)
class Candidato:
    respaldo_id: str
    creado_en: int
    tipo: str
    base_id: str | None
    restaurable: bool
    existe: bool


def caducables(respaldos: list[Candidato], retencion: int) -> list[str]:
    """
    Los que la retención deja caducar. Se conservan los `retencion` más recientes que existen; además, la cadena de cada uno (un incremental necesita su base y las anteriores) y el último
    restaurable, pase lo que pase. Lo que no existe (fallido, incompleto, caducado) no cuenta ni se vuelve a caducar.
    """
    vivos = sorted((r for r in respaldos if r.existe), key=lambda r: (r.creado_en, r.respaldo_id), reverse=True)
    por_id = {r.respaldo_id: r for r in respaldos}
    conservar: set[str] = {r.respaldo_id for r in vivos[:max(1, int(retencion))]}
    ultimo_restaurable = next((r for r in vivos if r.restaurable), None)
    if ultimo_restaurable is not None:
        conservar.add(ultimo_restaurable.respaldo_id)
    pendientes = list(conservar)
    while pendientes:                                                # la cadena de base de cada uno que se conserva
        r = por_id.get(pendientes.pop())
        if r is not None and r.base_id and r.base_id not in conservar:
            conservar.add(r.base_id)
            pendientes.append(r.base_id)
    return [r.respaldo_id for r in vivos if r.respaldo_id not in conservar]
