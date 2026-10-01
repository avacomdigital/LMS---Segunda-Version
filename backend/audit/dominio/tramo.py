"""
Tramos de la cadena (019-04, 019-06, 019-07) y la verificación pura de un rango de asientos (FUN-198/199).

Un tramo es un segmento contiguo de la cadena. El tramo activo hace además de cabeza: su `hasta_secuencia` y su
`huella_cierre` avanzan en la misma transacción que cada asiento. Al rotar, el tramo se cierra y el siguiente nace
con `huella_previa` = `huella_cierre` del anterior, así la cadena no se corta entre tramos.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import huella

ESTADO_ACTIVA, ESTADO_VERIFICADA, ESTADO_CON_SALTO, ESTADO_ROTADA = "activa", "verificada", "con_salto", "rotada"
ESTADOS = (ESTADO_ACTIVA, ESTADO_VERIFICADA, ESTADO_CON_SALTO, ESTADO_ROTADA)

CAUSA_HUELLA = "huella_discordante"
CAUSA_HUECO = "secuencia_con_hueco"
CAUSA_REPETIDA = "secuencia_repetida"
CAUSA_ENLACE = "huella_previa_no_enlaza"
CAUSA_TRIGGERS = "triggers_ausentes"
CAUSA_CABEZA = "cabeza_discordante"


@dataclass
class ResultadoVerificacion:
    ok: bool
    verificados: int
    salto_en_secuencia: int | None = None
    causa: str | None = None
    huella_final: str | None = None

    def como_dict(self) -> dict:
        return {"ok": self.ok, "verificados": self.verificados, "salto_en": self.salto_en_secuencia, "causa": self.causa}


def verificar(asientos, huella_inicial: str, secuencia_inicial: int | None = None) -> ResultadoVerificacion:
    """Recorre `asientos` (dicts con los campos canónicos más `huella_previa` y `huella`, en orden de secuencia)
    recalculando cada huella. Detecta huella discordante, hueco o repetición de secuencia y enlace roto."""
    previa = huella_inicial or huella.GENESIS
    esperada = secuencia_inicial
    verificados = 0
    for a in asientos:
        secuencia = int(a["secuencia"])
        if esperada is not None and secuencia != esperada:
            # Hueco: la primera secuencia que falta es la esperada. Repetición: la que volvió a aparecer.
            if secuencia < esperada:
                return ResultadoVerificacion(False, verificados, secuencia, CAUSA_REPETIDA, previa)
            return ResultadoVerificacion(False, verificados, esperada, CAUSA_HUECO, previa)
        if (a.get("huella_previa") or "").lower() != previa.lower():
            return ResultadoVerificacion(False, verificados, secuencia, CAUSA_ENLACE, previa)
        recalculada = huella.calcular(previa, a)
        if recalculada != (a.get("huella") or "").lower():
            return ResultadoVerificacion(False, verificados, secuencia, CAUSA_HUELLA, previa)
        previa = recalculada
        verificados += 1
        esperada = secuencia + 1
    return ResultadoVerificacion(True, verificados, None, None, previa)
