"""
La configuración del nodo y el estado de los agregados:

  VerConfiguracion       el umbral de privacidad (BR-086) y la política de exportación; la lee cualquiera que pueda ver o exportar reportes (OPS necesita saberla para ofrecer los destinos)
  CambiarConfiguracion   `reports.settings.manage` (extensión técnica propuesta): activar el umbral de privacidad, cerrar los medios extraíbles, exigir una razón al exportar
  EstadoDeAgregados      `reports.rebuild`: qué tan al día están las proyecciones (como antigüedad, no como estado interno), qué falta por leer y el resultado de la última reconstrucción
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from ..dominio.errores import ConflictoDeVersion, DatosInvalidos
from .base import _CasoDeUso, estado_y_corte
from .puertos import Actor

CAMPOS_DE_CONFIGURACION = ("umbral_privacidad", "extraibles_permitidos", "exigir_razon")
CAMPOS_DEL_BOLETIN = ("plantilla_boletin", "periodos_boletin", "leyenda_boletin")
TODOS_LOS_CAMPOS = CAMPOS_DE_CONFIGURACION + CAMPOS_DEL_BOLETIN


def _salida(c: dict) -> dict:
    return {"umbral_privacidad": c["umbral_privacidad"], "extraibles_permitidos": c["extraibles_permitidos"], "exigir_razon": c["exigir_razon"], "version": c["version"],
            "plantilla_boletin": c.get("plantilla_boletin") or cat.PLANTILLA_AUTO, "periodos_boletin": list(c.get("periodos_boletin") or []), "leyenda_boletin": c.get("leyenda_boletin") or "",
            "plantillas_de_boletin": list(cat.PLANTILLAS_DE_BOLETIN),
            "actualizada_en": c["actualizada_en"], "actualizada_por": c["actualizada_por"] or None, "minimo_de_alumnos": cat.MINIMO_DE_ALUMNOS,
            "razones": [{"codigo": k, "etiqueta": v} for k, v in cat.RAZONES_DE_EXPORTACION.items()], "formatos": list(cat.FORMATOS), "destinos": list(cat.DESTINOS)}


def _validar_boletin(cuerpo: dict) -> dict:
    """Los ajustes del boletín que trae un cuerpo, validados: la plantilla del catálogo, hasta seis nombres de periodo (textos cortos) y una leyenda acotada."""
    cambios: dict = {}
    if "plantilla_boletin" in cuerpo:
        plantilla = str(cuerpo["plantilla_boletin"] or "")
        if plantilla not in cat.PLANTILLAS_DE_BOLETIN:
            raise DatosInvalidos("La plantilla del boletín debe ser una de: " + ", ".join(cat.PLANTILLAS_DE_BOLETIN) + ".", campo="plantilla_boletin")
        cambios["plantilla_boletin"] = plantilla
    if "periodos_boletin" in cuerpo:
        periodos = cuerpo["periodos_boletin"]
        if not isinstance(periodos, list) or any(not isinstance(p, str) or not p.strip() or len(p.strip()) > 40 for p in periodos):
            raise DatosInvalidos("`periodos_boletin` debe ser una lista de nombres cortos de periodo.", campo="periodos_boletin")
        limpios = [" ".join(p.split()) for p in periodos]
        if len(limpios) > cat.MAX_PERIODOS_DE_BOLETIN or len(set(limpios)) != len(limpios):
            raise DatosInvalidos(f"Hasta {cat.MAX_PERIODOS_DE_BOLETIN} periodos, sin repetir.", campo="periodos_boletin")
        cambios["periodos_boletin"] = limpios
    if "leyenda_boletin" in cuerpo:
        leyenda = cuerpo["leyenda_boletin"]
        if leyenda is not None and not isinstance(leyenda, str):
            raise DatosInvalidos("`leyenda_boletin` debe ser un texto.", campo="leyenda_boletin")
        cambios["leyenda_boletin"] = " ".join(str(leyenda or "").split())[:cat.MAX_LEYENDA_DE_BOLETIN]
    return cambios


class VerConfiguracion(_CasoDeUso):
    def ejecutar(self, actor: Actor) -> dict:
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir_alguno(actor, (cat.P_VIEW, cat.P_GROUP, cat.P_STUDENT, cat.P_USAGE, cat.P_EXPORT, cat.P_SETTINGS))
            return {"configuracion": _salida(uow.config.get()), "servidor_en": self.s.reloj.ahora_ms()}


class CambiarConfiguracion(_CasoDeUso):
    def ejecutar(self, actor: Actor, cuerpo: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_SETTINGS)
        cambios: dict = {}
        for campo in CAMPOS_DE_CONFIGURACION:
            if campo in cuerpo:
                if not isinstance(cuerpo[campo], bool):
                    raise DatosInvalidos(f"`{campo}` debe ser verdadero o falso.", campo=campo)
                cambios[campo] = cuerpo[campo]
        cambios = {**cambios, **_validar_boletin(cuerpo)}
        if not cambios:
            raise DatosInvalidos("No hay nada que cambiar: manda al menos uno de " + ", ".join(TODOS_LOS_CAMPOS) + ".")
        esperada = cuerpo.get("version_esperada")
        if esperada is not None and (isinstance(esperada, bool) or not isinstance(esperada, int)):
            raise DatosInvalidos("`version_esperada` debe ser un entero.", valor=str(esperada)[:20])
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            actual = uow.config.get()
            nuevos = {**{c: actual.get(c) for c in TODOS_LOS_CAMPOS}, **cambios}
            if all(nuevos[c] == actual.get(c) for c in TODOS_LOS_CAMPOS):
                return {"configuracion": _salida(actual), "cambiado": False, "servidor_en": ahora}        # repetir lo mismo no deja asiento ni sube la versión
            guardada = uow.config.guardar(nuevos, actor.id or cat.SISTEMA, ahora, esperada)
            if guardada is None:
                raise ConflictoDeVersion("Otra persona cambió esta configuración mientras la editabas: vuelve a leerla.", version_actual=actual["version"])
            uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_CONFIGURACION, "m13_config", "nodo",
                                    anterior={c: actual.get(c) for c in TODOS_LOS_CAMPOS}, nuevo={c: guardada[c] for c in TODOS_LOS_CAMPOS})
            return {"configuracion": _salida(guardada), "cambiado": True, "servidor_en": ahora}


class EstadoDeAgregados(_CasoDeUso):
    def ejecutar(self, actor: Actor) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir(actor, cat.P_REBUILD)
            estado, corte_en = estado_y_corte(uow, ahora)
            guardado = uow.estado.get()
            fuentes = []
            for nombre, puerto in ((cat.AULA, uow.aula), (cat.EVALUACION, uow.evaluacion), (cat.CALIFICACION, uow.libro), (cat.ESTUDIO, uow.estudio)):
                marca = uow.marcas.estado(nombre)
                eventos, _ = puerto.eventos_desde(marca["secuencia"], 1, cat.EVENTOS_CONSUMIDOS[nombre])
                fuentes.append({"fuente": nombre, "marca": marca["secuencia"], "ultima": puerto.ultima_secuencia(), "pendientes": bool(eventos), "fallos_seguidos": marca["fallos"]})
            hay_clase = uow.aula.hay_sesion_activa()
            return {
                "estado": estado, "corte_en": corte_en, "antiguedad_ms": max(0, ahora - corte_en), "clase_en_curso": hay_clase, "fuentes": fuentes,
                "grupos": {"total": len(uow.identidad.todos_los_grupos()), "desactualizados": len(uow.avances.sucios())}, "clases": uow.clases.contar(),
                "reconstruccion": {"en_curso": guardado["reconstruyendose"], "ultima_en": guardado["reconstruida_en"], "por": guardado["reconstruida_por"] or None,
                                   "error": guardado["ultimo_error"] or None},
                "actualizada_en": guardado["actualizada_en"], "puede_reconstruir": not hay_clase and not guardado["reconstruyendose"], "servidor_en": ahora}
