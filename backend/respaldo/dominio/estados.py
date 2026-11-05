"""
El estado de un respaldo como función PURA sobre su historial de sólo inserción (el mismo patrón de MOD-017): no existe un «estado actual» guardado que pueda divergir de lo que pasó.

  intento      iniciado → completo_ejecutado | incremental_ejecutado | fallido            (o se apagó el nodo: interrumpido → incompleto; reanudado lo vuelve a empezar)
  verificación verificado | no_verificado   (el último gana: «un respaldo que falla la verificación no se descarta: se marca como no verificado»)
  salida       exportado
  retención    caducado   (gana sobre todo lo demás: el archivo ya no existe)

El Maestro nombra cinco estados (en curso, completo verificado, completo no verificado, exportado, caducado); `incompleto` y `fallido` son extensiones marcadas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from . import catalogos as cat


class Fila(Protocol):
    @property
    def tipo(self) -> str: ...
    @property
    def en(self) -> int: ...
    @property
    def detalle(self) -> dict: ...


@dataclass(frozen=True)
class Derivado:
    estado: str
    ejecutado_en: int | None          # cuándo terminó con éxito
    verificado_en: int | None         # la última verificación que pasó
    exportado: bool
    exportado_en: int | None
    error: str                        # el motivo del último fallo, si lo hubo
    ultima_en: int

    @property
    def restaurable(self) -> bool:
        """Un respaldo es restaurable sólo si terminó y su última verificación pasó (AGG-013: «un punto solo es restaurable si su verificación pasó»)."""
        return self.estado in (cat.E_VERIFICADO, cat.E_EXPORTADO)

    @property
    def existe(self) -> bool:
        """¿El archivo sigue en el equipo? (sólo `caducado` y los que nunca llegaron a existir dicen que no)."""
        return self.estado in (cat.E_VERIFICADO, cat.E_NO_VERIFICADO, cat.E_EXPORTADO)


def derivar(filas: list[Fila], vivo: bool = False) -> Derivado:
    """`vivo`: ¿este proceso lo está haciendo ahora mismo? Un `iniciado` que nadie atiende es un respaldo incompleto (FUN-177)."""
    intento: str | None = None
    ejecutado = verificado = exportado = None
    ultima_verificacion: str | None = None
    error, caducado, ultima = "", False, 0
    for f in filas:                                   # en el orden en que se insertaron
        ultima = max(ultima, int(f.en))
        t = f.tipo
        if t in (cat.H_INICIADO, cat.H_REANUDADO):
            intento, error = "en_curso", ""
        elif t in (cat.H_COMPLETO, cat.H_INCREMENTAL):
            intento, ejecutado = "ok", int(f.en)
        elif t == cat.H_FALLIDO:
            intento, error = "fallido", str((f.detalle or {}).get("motivo") or "")
        elif t == cat.H_INTERRUMPIDO:
            intento = "incompleto"
        elif t == cat.H_VERIFICADO:
            ultima_verificacion, verificado = "ok", int(f.en)
        elif t == cat.H_NO_VERIFICADO:
            ultima_verificacion = "no"
        elif t == cat.H_EXPORTADO:
            exportado = int(f.en)
        elif t == cat.H_CADUCADO:
            caducado = True
    if caducado:
        estado = cat.E_CADUCADO
    elif intento == "en_curso":
        estado = cat.E_EN_CURSO if vivo else cat.E_INCOMPLETO
    elif intento == "incompleto":
        estado = cat.E_INCOMPLETO
    elif intento == "fallido":
        estado = cat.E_FALLIDO
    elif intento == "ok":
        if ultima_verificacion == "ok":
            estado = cat.E_EXPORTADO if exportado is not None else cat.E_VERIFICADO
        else:
            estado = cat.E_NO_VERIFICADO
    else:
        estado = cat.E_INCOMPLETO
    return Derivado(estado=estado, ejecutado_en=ejecutado, verificado_en=verificado, exportado=exportado is not None, exportado_en=exportado, error=error, ultima_en=ultima)
