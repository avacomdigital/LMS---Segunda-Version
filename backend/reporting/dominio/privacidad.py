"""
El umbral de privacidad (BR-086): un reporte AGREGADO que abarca menos de cinco alumnos no expone comparativas individuales identificables si el administrador activó el
umbral. Es una configuración del nodo y viene apagada. Con el umbral activo, el reporte —y el archivo que sale de él— muestran sólo los totales y lo dicen.

Qué cuenta como agregado: el reporte de una clase y el de un grupo (comparan personas entre sí). El informe de UN alumno es nominal por naturaleza (lo ve quien tiene
`reports.student.view`) y el de uso de equipos no lleva personas: ninguno de los dos se recorta.
Este archivo no importa Django.
"""
from __future__ import annotations

from . import catalogos as cat


def aplica(alumnos: int, umbral_activo: bool) -> bool:
    return bool(umbral_activo) and int(alumnos) < cat.MINIMO_DE_ALUMNOS


def aviso(alumnos: int) -> str:
    return (f"Este reporte abarca {alumnos} {'alumno' if alumnos == 1 else 'alumnos'}, menos de {cat.MINIMO_DE_ALUMNOS}: el colegio activó la privacidad y por eso "
            "sólo se muestran los totales, sin comparar a las personas entre sí.")


def bloque(alumnos: int, umbral_activo: bool) -> dict:
    """El bloque `privacidad` de un reporte: si el umbral está activo, si se aplicó, el mínimo y el aviso en lenguaje llano."""
    aplicada = aplica(alumnos, umbral_activo)
    return {"umbral_activo": bool(umbral_activo), "aplicada": aplicada, "minimo": cat.MINIMO_DE_ALUMNOS, "alumnos": int(alumnos), "aviso": aviso(alumnos) if aplicada else ""}
