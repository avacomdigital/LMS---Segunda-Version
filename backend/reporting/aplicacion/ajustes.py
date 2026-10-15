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


def _salida(c: dict) -> dict:
    return {"umbral_privacidad": c["umbral_privacidad"], "extraibles_permitidos": c["extraibles_permitidos"], "exigir_razon": c["exigir_razon"], "version": c["version"],
            "actualizada_en": c["actualizada_en"], "actualizada_por": c["actualizada_por"] or None, "minimo_de_alumnos": cat.MINIMO_DE_ALUMNOS,
            "razones": [{"codigo": k, "etiqueta": v} for k, v in cat.RAZONES_DE_EXPORTACION.items()], "formatos": list(cat.FORMATOS), "destinos": list(cat.DESTINOS)}


class VerConfiguracion(_CasoDeUso):
    def ejecutar(self, actor: Actor) -> dict:
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir_alguno(actor, (cat.P_VIEW, cat.P_GROUP, cat.P_STUDENT, cat.P_USAGE, cat.P_EXPORT, cat.P_SETTINGS))
            return {"configuracion": _salida(uow.config.get()), "servidor_en": self.s.reloj.ahora_ms()}


class CambiarConfiguracion(_CasoDeUso):
    def ejecutar(self, actor: Actor, cuerpo: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_SETTINGS)
        cambios = {}
        for campo in CAMPOS_DE_CONFIGURACION:
            if campo in cuerpo:
                if not isinstance(cuerpo[campo], bool):
                    raise DatosInvalidos(f"`{campo}` debe ser verdadero o falso.", campo=campo)
                cambios[campo] = cuerpo[campo]
        if not cambios:
            raise DatosInvalidos("No hay nada que cambiar: manda al menos uno de " + ", ".join(CAMPOS_DE_CONFIGURACION) + ".")
        esperada = cuerpo.get("version_esperada")
        if esperada is not None and (isinstance(esperada, bool) or not isinstance(esperada, int)):
            raise DatosInvalidos("`version_esperada` debe ser un entero.", valor=str(esperada)[:20])
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            actual = uow.config.get()
            nuevos = {**{c: actual[c] for c in CAMPOS_DE_CONFIGURACION}, **cambios}
            if all(nuevos[c] == actual[c] for c in CAMPOS_DE_CONFIGURACION):
                return {"configuracion": _salida(actual), "cambiado": False, "servidor_en": ahora}        # repetir lo mismo no deja asiento ni sube la versión
            guardada = uow.config.guardar(nuevos, actor.id or cat.SISTEMA, ahora, esperada)
            if guardada is None:
                raise ConflictoDeVersion("Otra persona cambió esta configuración mientras la editabas: vuelve a leerla.", version_actual=actual["version"])
            uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_CONFIGURACION, "m13_config", "nodo",
                                    anterior={c: actual[c] for c in CAMPOS_DE_CONFIGURACION}, nuevo={c: guardada[c] for c in CAMPOS_DE_CONFIGURACION})
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
