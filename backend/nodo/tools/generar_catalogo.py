"""
Genera `nodo/dominio/catalogo_datos.py` a partir del inventario de las colas (`inventario_colas.py`): a cada tipo de evento que ya existe en el código le asigna UNA clase
(BR-133: «declarada en el documento, no en el código del productor»), una sensibilidad, su retención y su clave de deduplicación, con las reglas de abajo y las quince fichas
del Maestro como excepciones. Lo que salga de aquí lo cura el CTO (Q-N5); el archivo generado es la fuente que lee el nodo.

    cd backend
    .venv\\Scripts\\python -m nodo.tools.generar_catalogo

Puro: no importa Django.
"""
from __future__ import annotations

import re
from pathlib import Path

from nodo.dominio import catalogos as cat
from nodo.tools.inventario_colas import inventario

DESTINO = Path(__file__).resolve().parents[1] / "dominio" / "catalogo_datos.py"

# clase por prefijo (dominio del tipo)
CLASE_POR_PREFIJO = {
    "identidad": cat.CLASE_DOMINIO, "licencia": cat.CLASE_DOMINIO,
    "evaluacion": cat.CLASE_APRENDIZAJE, "calificacion": cat.CLASE_APRENDIZAJE, "estudio": cat.CLASE_APRENDIZAJE,
    "aula": cat.CLASE_AULA, "dispositivo": cat.CLASE_DISPOSITIVO, "auditoria": cat.CLASE_AUDITORIA,
    "reporte": cat.CLASE_TECNICO, "busqueda": cat.CLASE_TECNICO,
}
# excepciones de clase: estructura, configuración y catálogo son DOMINIO aunque el prefijo sea académico
CLASE_POR_TIPO = {
    "calificacion.escala_adoptada.v1": cat.CLASE_DOMINIO, "calificacion.escala_convertida.v1": cat.CLASE_DOMINIO, "calificacion.modo_cambiado.v1": cat.CLASE_DOMINIO,
    "calificacion.politica_configurada.v1": cat.CLASE_DOMINIO, "calificacion.clasificacion_definida.v1": cat.CLASE_DOMINIO,
    "evaluacion.creada.v1": cat.CLASE_DOMINIO, "evaluacion.reactivo.anadido.v1": cat.CLASE_DOMINIO,
    "calificacion.agregados_recalculados.v1": cat.CLASE_TECNICO, "calificacion.derivadas_reconstruidas.v1": cat.CLASE_TECNICO, "calificacion.libro_exportado.v1": cat.CLASE_TECNICO,
    "licencia.validada.v1": cat.CLASE_TECNICO, "licencia.consumo_calculado.v1": cat.CLASE_TECNICO, "licencia.aviso_emitido.v1": cat.CLASE_TECNICO,
    "licencia.reloj_sospechoso.v1": cat.CLASE_TECNICO, "licencia.integridad_alterada.v1": cat.CLASE_TECNICO,
    "estudio.paquete.descargado.v1": cat.CLASE_DISPOSITIVO, "estudio.descarga.denegada.v1": cat.CLASE_DISPOSITIVO, "estudio.limpieza.reintentada.v1": cat.CLASE_DISPOSITIVO,
}
# sensibilidad: por defecto interna; lo que nombra a un alumno (intento, respuesta, incidente, progreso, calificación) es personal de menor; lo de una persona del personal, personal
PERSONAL_MENOR = re.compile(r"^(evaluacion\.(intento|respuesta|incidente|admision|envio|autocalificacion|dispositivo_admitido|resultado_intento|revision)|calificacion\.(registrada|ajustada|anulada|manual|rubrica|publicada|publicacion|valoracion|retroalimentada|intento|estado_simple|observacion)|estudio\.(leccion|practica|actividad|trabajo|sesion)|aula\.(respuesta|intento|proyeccion\.alumno|ayuda)|identidad\.estudiante|reporte\.(alumno|boletin))")
PERSONAL = re.compile(r"^(identidad\.(usuario|usuarios|credencial|docente|cuenta|sesion|sesiones|traspaso|acceso_temporal|escalada|rol\.asignado|rol\.revocado|grupo\.miembro)|dispositivo\.sesion|reporte\.(grupo|exportado))")
# clave de deduplicación: la del Maestro en sus quince fichas; para el resto, la clave del agregado
CLAVE_POR_TIPO = {
    "evaluacion.intento_abierto.v1": ("intento_id",),
    "evaluacion.respuesta_registrada.v1": ("intento_id", "pregunta_ref", "sesion_ref", "secuencia"),
    "evaluacion.respuesta_deduplicada.v1": ("clave",),
    "evaluacion.intento_entregado.v1": ("intento_id",),
    "evaluacion.incidente_registrado.v1": ("incidente_id",),
    "evaluacion.asignada.v1": ("asignacion_id", "grupo_id", "curso_version"),
    "calificacion.registrada.v1": ("intento_id", "version"),
    "calificacion.ajustada.v1": ("calificacion_id", "version"),
    "aula.sesion.iniciada.v1": ("sesion_id",),
    "aula.sesion.reanudada.v1": ("sesion_id", "instante_corte"),
    "aula.sesion.finalizada.v1": ("sesion_id",),
    "dispositivo.limpieza.aplicada.v1": ("dispositivo_id", "orden_id"),
    "nodo.recuperacion_completada.v1": ("incidente",),
}
# retención distinta a la de su clase (fichas del Maestro)
RETENCION_POR_TIPO = {
    "evaluacion.incidente_registrado.v1": 5 * 365, "calificacion.registrada.v1": None, "calificacion.ajustada.v1": None, "aula.sesion.finalizada.v1": 5 * 365,
    "nodo.recuperacion_completada.v1": 30,
}


def sensibilidad_de(tipo: str) -> str:
    if PERSONAL_MENOR.match(tipo):
        return cat.S_PERSONAL_MENOR
    if PERSONAL.match(tipo):
        return cat.S_PERSONAL
    return cat.S_INTERNA


def clase_de(tipo: str) -> str:
    if tipo in CLASE_POR_TIPO:
        return CLASE_POR_TIPO[tipo]
    prefijo = tipo.split(".")[0]
    if prefijo == "nodo":
        return cat.CLASE_SINCRONIZACION if tipo in cat.EVENTOS_DE_SINCRONIZACION else cat.CLASE_TECNICO
    return CLASE_POR_PREFIJO.get(prefijo, cat.CLASE_TECNICO)


def version_de(tipo: str) -> int:
    return int(tipo.rsplit(".v", 1)[1])


def generar() -> str:
    inv = inventario()
    filas: list[tuple[str, str, str, str, tuple[str, ...], str, int]] = []
    for modulo, datos in sorted(inv.items()):
        for tipo in datos["produce"]:
            filas.append((tipo, modulo, clase_de(tipo), sensibilidad_de(tipo), CLAVE_POR_TIPO.get(tipo, ("agregado_id",)), _ret(tipo), version_de(tipo)))
    for tipo in cat.EVENTOS:
        filas.append((tipo, cat.MODULO, clase_de(tipo), cat.S_INTERNA, CLAVE_POR_TIPO.get(tipo, ("agregado_id",)), _ret(tipo), version_de(tipo)))
    filas.sort()
    lineas = [
        '"""',
        "El catálogo de tipos de evento de la cola única (P-04, BR-133): tipo → (módulo productor, clase, sensibilidad, clave de deduplicación, retención en días o None, versiones).",
        "",
        "GENERADO por `nodo/tools/generar_catalogo.py` a partir del inventario del código; se vuelve a generar cuando un módulo añade un tipo. Lo que se cure a mano (Q-N5) va en",
        "el generador, no aquí. Las retenciones salen de la clase (`catalogos.retencion_dias`) salvo las fichas del Maestro, que traen la suya (`RETENCION`: «clase» = la de su clase).",
        "Puro: no importa nada.",
        '"""',
        "from __future__ import annotations",
        "",
        "# tipo: (modulo, clase, sensibilidad, clave_dedup, retencion, versiones)",
        "TIPOS: dict[str, tuple[str, str, str, tuple[str, ...], str | int | None, tuple[int, ...]]] = {",
    ]
    for tipo, modulo, clase, sens, clave, ret, version in filas:
        lineas.append(f"    {tipo!r}: ({modulo!r}, {clase!r}, {sens!r}, {clave!r}, {ret!r}, ({version},)),")
    lineas.append("}")
    lineas.append("")
    return "\n".join(lineas)


def _ret(tipo: str):
    return RETENCION_POR_TIPO[tipo] if tipo in RETENCION_POR_TIPO else "clase"


if __name__ == "__main__":
    DESTINO.write_text(generar(), encoding="utf-8", newline="\n")
    print("escrito", DESTINO)
