"""
La máquina de estados de la licencia (P-05) como UNA función pura: `calcular(contexto, política)`. No lee ningún reloj ni ninguna base: recibe el instante confiable y los hechos.

    sin_licencia           ventana de evaluación desde el primer arranque con esta versión (P-14); al terminar, degradada
    activa                 dentro de la vigencia y con la huella de este equipo
    reactivada             igual que activa, justo después de recuperarla tras una restauración (FUN-194)
    en_gracia              venció, o este equipo no es el de la licencia, y todavía quedan días de gracia
    liberacion_pendiente   licencia emitida mientras el equipo anterior se libera (JRN-020, MSG-063): opera con el plazo que trae
    degradada              se acabó la gracia: los módulos licenciables se apagan; el núcleo —y la clase— siguen igual (R-01)

Banderas ortogonales: `reloj_sospechoso` (reloj atrasado), `reloj_adelantado` (fecha adelantada que no se acepta, Q-L13), `huella_parcial`, `integridad_alterada`.

No se guarda un «estado actual» que pueda divergir de la realidad: el estado SALE del tiempo y de los hechos del historial. Las transiciones son consecuencia del tiempo y de las
acciones del administrador. Degradar ocurre EN el instante en que se acaba el plazo (Q-L16: la gracia son 30 días corridos exactos; el instante confiable jamás baja, así que no hace
falta amortiguar nada: la política trae una histéresis y vale 0). Una fecha adelantada NO mueve ese instante (Q-L13): lo que recibe `calcular` ya es la hora confiable, nunca la del
salto, así que ni vence ni degrada nada por ella. Retroceder el reloj tampoco aplaza nada: el vencimiento se mide contra la marca alta.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import catalogos as cat
from .cupo import porcentaje
from .huella import Coincidencia
from .licencia import Licencia, Limites
from .politica import DIA_MS, POLITICA_PROVISIONAL, Politica


@dataclass(frozen=True)
class Contexto:
    licencia: Licencia | None
    ahora: int                                          # el instante CONFIABLE (`reloj.leer(...).ahora`)
    instalada_en: int                                   # primer arranque con licenciamiento: empieza la ventana de evaluación
    coincidencia: Coincidencia | None = None            # huella de la licencia contra la de este equipo (None = no se pudo comparar: se toma como que coincide)
    licencia_instalada_en: int | None = None            # cuándo se instaló ESTA serie en este nodo (para el plazo de una liberación pendiente)
    huella_distinta_desde: int | None = None            # la primera vez que se observó que este equipo no es el de la licencia
    reactivada_en: int | None = None
    reloj_retroceso: bool = False
    reloj_adelanto_ms: int = 0                          # > 0: la fecha del equipo está adelantada tanto y NO se acepta (Q-L13); `ahora` ya es la hora confiable, no la del salto
    integridad_alterada: bool = False


@dataclass(frozen=True)
class Estado:
    estado: str
    motivo: str
    ahora: int
    hasta: int | None                                   # el próximo hito para quien lee: fin de vigencia, de gracia, de liberación o de evaluación
    dias_restantes: int | None
    banderas: frozenset[str] = field(default_factory=frozenset)
    capacidades: frozenset[str] = field(default_factory=frozenset)   # las licenciables habilitadas AHORA
    limites: Limites = Limites(0, 0, 0, 0)
    tipo: str | None = None
    licencia_id: str | None = None
    serie: int | None = None
    reloj_adelanto_ms: int = 0                          # cuánto está adelantada la fecha del equipo (0 si no lo está): `ahora` es la hora confiable y el equipo dice `ahora + esto`

    @property
    def restringe(self) -> bool:
        return set(cat.CAPACIDADES_LICENCIABLES) - set(self.capacidades) != set()


def dias_hasta(hasta: int | None, ahora: int) -> int | None:
    """Días COMPLETOS que faltan (se redondea hacia arriba: «queda 1 día» hasta que pasa el instante). Nunca negativos."""
    if hasta is None:
        return None
    return max(0, -((ahora - hasta) // DIA_MS))


def _licenciables_de(licencia: Licencia | None) -> frozenset[str]:
    if licencia is None:
        return frozenset(cat.CAPACIDADES_LICENCIABLES)
    return frozenset(c for c in cat.CAPACIDADES_LICENCIABLES if licencia.habilita(c))


def _se_puede_degradar(ctx: Contexto, limite: int, politica: Politica) -> bool:
    """Pasó el límite (y la histéresis de la política, que hoy vale 0). Una fecha adelantada no interviene: `ctx.ahora` ya es la hora confiable (Q-L13)."""
    return ctx.ahora >= limite + politica.histeresis_ms


def _banderas(ctx: Contexto, politica: Politica) -> frozenset[str]:
    banderas: set[str] = set()
    if ctx.reloj_retroceso:
        banderas.add(cat.B_RELOJ_SOSPECHOSO)
    if ctx.reloj_adelanto_ms > 0:
        banderas.add(cat.B_RELOJ_ADELANTADO)
    if ctx.coincidencia is not None and ctx.coincidencia.ok and ctx.coincidencia.parcial:
        banderas.add(cat.B_HUELLA_PARCIAL)
    if ctx.integridad_alterada:
        banderas.add(cat.B_INTEGRIDAD_ALTERADA)
    return frozenset(banderas)


def calcular(ctx: Contexto, politica: Politica = POLITICA_PROVISIONAL) -> Estado:
    banderas = _banderas(ctx, politica)
    lic = ctx.licencia
    ahora = ctx.ahora

    def estado(nombre: str, motivo: str, hasta: int | None, habilitadas: frozenset[str], limites: Limites) -> Estado:
        return Estado(nombre, motivo, ahora, hasta, dias_hasta(hasta, ahora), banderas, habilitadas, limites,
                      lic.tipo if lic else None, lic.id if lic else None, lic.serie if lic else None, max(0, ctx.reloj_adelanto_ms))

    # ---- sin licencia (o una que todavía no empieza): la ventana de evaluación. «Todavía no empieza» tiene la misma tolerancia con que `Instalar` la acepta (un día): una licencia que
    # empieza esta tarde, emitida con otro huso, ya rige.
    if lic is None or ahora + politica.tolerancia_inicio_ms < lic.desde:
        fin = ctx.instalada_en + politica.evaluacion_dias * DIA_MS
        motivo = cat.M_AUN_NO_VIGENTE if lic is not None else cat.M_EVALUACION
        if not _se_puede_degradar(ctx, fin, politica):
            return estado(cat.SIN_LICENCIA, motivo, fin, frozenset(cat.CAPACIDADES_LICENCIABLES), politica.limites_evaluacion)
        return estado(cat.DEGRADADA, cat.M_EVALUACION_VENCIDA, fin, frozenset(), politica.limites_evaluacion)

    limites, habilitadas = lic.limites, _licenciables_de(lic)

    # ---- la licencia es de otro equipo: gracia desde la primera vez que se vio
    if ctx.coincidencia is not None and not ctx.coincidencia.ok:
        fin = (ctx.huella_distinta_desde if ctx.huella_distinta_desde is not None else ahora) + lic.gracia_dias * DIA_MS
        if not _se_puede_degradar(ctx, fin, politica):
            return estado(cat.EN_GRACIA, cat.M_HUELLA_DISTINTA, fin, habilitadas, limites)
        return estado(cat.DEGRADADA, cat.M_HUELLA_DISTINTA, fin, frozenset(), limites)

    # ---- vigente
    if ahora <= lic.vence:
        if lic.liberacion_pendiente:
            fin = (ctx.licencia_instalada_en if ctx.licencia_instalada_en is not None else lic.emitida) + lic.liberacion_dias * DIA_MS
            fin = min(fin, lic.vence)
            if not _se_puede_degradar(ctx, fin, politica):
                return estado(cat.LIBERACION_PENDIENTE, cat.M_LIBERACION_PENDIENTE, fin, habilitadas, limites)
            return estado(cat.DEGRADADA, cat.M_LIBERACION_NO_CONFIRMADA, fin, frozenset(), limites)
        if ctx.reactivada_en is not None and 0 <= ahora - ctx.reactivada_en <= politica.ventana_reactivada_ms:
            return estado(cat.REACTIVADA, cat.M_REACTIVADA, lic.vence, habilitadas, limites)
        return estado(cat.ACTIVA, cat.M_VIGENTE, lic.vence, habilitadas, limites)

    # ---- venció: gracia, y después degradada
    fin = lic.vence + lic.gracia_dias * DIA_MS
    if not _se_puede_degradar(ctx, fin, politica):
        return estado(cat.EN_GRACIA, cat.M_VENCIDA, fin, habilitadas, limites)
    return estado(cat.DEGRADADA, cat.M_VENCIDA, fin, frozenset(), limites)


# ------------------------------------------------------------------------------------------------------------------- avisos (lo que muestra el banner)
def avisos(estado: Estado, consumo, politica: Politica = POLITICA_PROVISIONAL) -> list[dict]:
    """
    Los avisos que ve el administrador (banner y pantalla de Licencia), en orden de importancia. Son CÓDIGOS con sus cifras: el texto lo pone el cliente. Ninguno interrumpe una
    clase (la pantalla decide cuándo mostrarlos); sólo existen para que nadie se entere de un vencimiento el día que ocurre.

    La fecha adelantada (Q-L13) es un ERROR y va primero: trae cuántos días está adelantada (al día más cercano, nunca 0), la fecha que tiene el equipo y la que el aula lleva (la hora
    confiable), para que el cliente diga «tu equipo marca X, el aula esperaba Y: corrígela».
    """
    salida: list[dict] = []
    if estado.reloj_adelanto_ms > 0:
        salida.append({"codigo": cat.B_RELOJ_ADELANTADO, "adelanto_dias": max(1, round(estado.reloj_adelanto_ms / DIA_MS)), "fecha_equipo": estado.ahora + estado.reloj_adelanto_ms,
                       "fecha_esperada": estado.ahora})
    if estado.estado == cat.DEGRADADA:
        salida.append({"codigo": "degradada", "motivo": estado.motivo})
    elif estado.estado == cat.EN_GRACIA:
        salida.append({"codigo": "gracia", "motivo": estado.motivo, "dias": estado.dias_restantes})
    elif estado.estado == cat.LIBERACION_PENDIENTE:
        salida.append({"codigo": "liberacion_pendiente", "dias": estado.dias_restantes})
    elif estado.estado == cat.SIN_LICENCIA:
        if estado.dias_restantes is not None and estado.dias_restantes <= politica.evaluacion_aviso_dias:
            salida.append({"codigo": "evaluacion", "dias": estado.dias_restantes, "urgente": estado.dias_restantes <= politica.evaluacion_urgente_dias})
    elif estado.estado in (cat.ACTIVA, cat.REACTIVADA):
        umbral = umbral_de_aviso(estado.dias_restantes, politica)
        if umbral is not None:
            salida.append({"codigo": "por_vencer", "dias": estado.dias_restantes, "umbral": umbral})
    if consumo is not None:
        for tipo, en_uso, limite in (("equipos", consumo.equipos, estado.limites.equipos), ("usuarios", consumo.usuarios, estado.limites.usuarios)):
            pct = porcentaje(en_uso, limite)
            if pct is not None and pct >= politica.cupo_aviso_pct:
                salida.append({"codigo": "cupo", "tipo": tipo, "en_uso": en_uso, "limite": limite, "porcentaje": pct})
    for bandera in (cat.B_RELOJ_SOSPECHOSO, cat.B_HUELLA_PARCIAL, cat.B_INTEGRIDAD_ALTERADA):
        if bandera in estado.banderas:
            salida.append({"codigo": bandera})
    return salida


def umbral_de_aviso(dias_restantes: int | None, politica: Politica = POLITICA_PROVISIONAL) -> int | None:
    """El umbral (30/14/7/3/1) más cercano que ya se cruzó: con 12 días restantes es 14; con 40, ninguno."""
    if dias_restantes is None:
        return None
    cruzados = [u for u in politica.avisos_dias if dias_restantes <= u]
    return min(cruzados) if cruzados else None
