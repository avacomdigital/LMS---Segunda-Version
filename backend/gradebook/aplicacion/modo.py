"""
La configuración académica de la institución:

  VerConfiguracion     el modo y la escala de cada nivel educativo, la política y las escalas adoptadas
  ConfigurarNivel      FUN-125: alterna un nivel entre modo simple y calificaciones y elige su escala; `validar` sólo comprueba las precondiciones
  ConfigurarPolitica   país, jurisdicción, institución y qué intento cuenta (las ponderaciones quedan preparadas para V1; no se aplican)
  ClasificarEvaluacion si una evaluación es diagnóstica, formativa o sumativa y si afecta la calificación oficial

El modo simple es el valor por defecto de todo nivel: sin una configuración explícita, un nivel no muestra notas. Pasar de un modo a otro es una decisión del
administrador y NO se puede hacer mientras haya evaluaciones en curso en ese nivel (cambiaría las reglas a mitad de una evaluación). Cambiar de modo no
convierte nada solo: ni se registran las notas técnicas que ya existían, ni se borran las calificaciones ya registradas.
"""
from __future__ import annotations

import re

from ..dominio import catalogos as cat
from ..dominio import plantillas_escalas as plantillas
from ..dominio.errores import ConflictoDeVersion, DatosInvalidos, EscalaNoVigente, ModoBloqueado, NoEncontrado
from .base import _CasoDeUso, exigir_en_asignacion, exigir_nodo_instalado, sistema_de
from .derivados import ReconstruirDerivados, RecalcularResultado, clasificacion_efectiva, politica_de_intentos
from .escalas import escala_a_salida
from .puertos import Actor


def nivel_a_salida(uow, nivel_clave: str, fila: dict | None) -> dict:
    version = uow.escalas.version(fila["escala_version_id"]) if fila and fila.get("escala_version_id") else None
    return {"nivel_clave": nivel_clave, "modo": fila["modo"] if fila else cat.SIMPLE, "por_defecto": fila is None, "version": fila["version"] if fila else 0,
            "escala": None if version is None else sistema_de(version),
            "actualizada_en": fila["actualizada_en"] if fila else None, "actualizada_por": fila["actualizada_por"] if fila else ""}


def politica_a_salida(p: dict) -> dict:
    return {"pais": p["pais"], "jurisdiccion": p["jurisdiccion"], "institucion": p["institucion"], "politica_intentos": p["politica_intentos"],
            "politica_provisional": p["politica_intentos"] == cat.POLITICA_PROVISIONAL and p.get("version", 0) == 0, "ponderaciones": p["ponderaciones"],
            "ponderaciones_aplicadas": False, "version": p.get("version", 0)}


class VerConfiguracion(_CasoDeUso):
    def ejecutar(self, actor: Actor) -> dict:
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir(actor, cat.P_READ)
            filas = {f["nivel_clave"]: f for f in uow.niveles.todos()}
            return {"niveles": [nivel_a_salida(uow, n, filas.get(n)) for n in cat.NIVELES], "politica": politica_a_salida(uow.politica.get()),
                    "escalas": [escala_a_salida(e, ultima=uow.escalas.ultima_version(e["id"])) for e in uow.escalas.listar()],
                    "modos": list(cat.MODOS), "politicas_de_intentos": list(cat.POLITICAS_DE_INTENTOS), "servidor_en": self.s.reloj.ahora_ms()}


class ConfigurarNivel(_CasoDeUso):
    """`datos`: `{modo, escala_version_id | escala_id (modo calificaciones), version_esperada?, validar?}`. Con `validar` no cambia nada: responde si se
    puede, qué lo impide y qué advertencias hay."""

    def ejecutar(self, actor: Actor, nivel_clave: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            self.s.autorizacion.exigir(actor, cat.P_MODE_SET)
            exigir_nodo_instalado(uow)
            if nivel_clave not in cat.NIVELES:
                raise DatosInvalidos(f"El nivel «{nivel_clave}» no existe.", niveles=list(cat.NIVELES))
            modo = str(datos.get("modo") or "")
            if modo not in cat.MODOS:
                raise DatosInvalidos("`modo` debe ser «simple» o «calificaciones».", modos=list(cat.MODOS))
            actual = uow.niveles.get(nivel_clave)
            modo_actual = actual["modo"] if actual else cat.SIMPLE
            version = None
            if modo == cat.CALIFICACIONES:
                if datos.get("escala_version_id"):
                    version = uow.escalas.version(str(datos["escala_version_id"]))
                elif datos.get("escala_id"):
                    version = uow.escalas.ultima_version(str(datos["escala_id"]))
                else:
                    raise DatosInvalidos("El modo calificaciones exige elegir una escala: `escala_id` o `escala_version_id`.")
                if version is None:
                    raise EscalaNoVigente("Esa escala no existe: adopta primero una plantilla o crea una escala propia.")
                if not version["activa"]:
                    raise EscalaNoVigente("Esa escala está desactivada.", escala=version["codigo"])
            grupos = uow.identidad.grupos_de_nivel(nivel_clave)
            bloqueos: list[str] = []
            advertencias: list[str] = []
            en_curso = 0
            if modo != modo_actual:
                alumnos = [a["id"] for g in grupos for a in uow.identidad.alumnos_del_grupo(g)]
                en_curso = uow.evaluacion.evaluaciones_en_curso(grupos, alumnos)
                if en_curso:
                    bloqueos.append(f"Hay {en_curso} evaluaciones en curso en este nivel: espera a que terminen para cambiar el modo.")
                if modo == cat.SIMPLE:
                    publicadas = sum(1 for g in grupos for c in uow.calificaciones.de_grupo(g) if c["estado"] == cat.DEFINITIVA)
                    if publicadas:
                        advertencias.append(f"{publicadas} calificaciones ya publicadas dejarán de mostrarse a los alumnos en modo simple (no se borran).")
                else:
                    advertencias.append("Las evaluaciones ya calificadas antes de este cambio no se convierten en calificaciones solas: se registran cuando el profesor lo decide.")
            if version is not None:
                # Las normas varían por nivel: una plantilla se sugiere para ciertos niveles, y aplicarla a otro es posible pero se avisa (no se inventa una equivalencia).
                escala = uow.escalas.por_id(version["escala_id"]) or {}
                sugerida = plantillas.plantilla(escala.get("plantilla_origen") or "")
                if sugerida is not None and sugerida.niveles and nivel_clave not in sugerida.niveles:
                    advertencias.append(f"La plantilla «{sugerida.codigo}», de donde sale esta escala, no se sugiere para el nivel {nivel_clave}: revisa que la normativa de ese nivel "
                                        "permita calificar así.")
            esperada = datos.get("version_esperada")
            if esperada is not None and actual is not None and esperada != actual["version"]:
                raise ConflictoDeVersion("Otro administrador cambió este nivel mientras lo editabas: vuelve a leerlo.", version_actual=actual["version"])
            vista = nivel_a_salida(uow, nivel_clave, actual)
            if datos.get("validar"):
                return {"permitido": not bloqueos, "bloqueos": bloqueos, "advertencias": advertencias, "en_curso": en_curso, "grupos": len(grupos),
                        "de": modo_actual, "a": modo, "actual": vista, "servidor_en": ahora}
            if bloqueos:
                raise ModoBloqueado(bloqueos[0], en_curso=en_curso, nivel_clave=nivel_clave)
            version_id = version["id"] if version else None
            if actual is not None and actual["modo"] == modo and actual.get("escala_version_id") == version_id:
                return {"cambiado": False, "nivel": vista, "advertencias": advertencias, "servidor_en": ahora}      # idempotente: ya estaba así
            fila = uow.niveles.guardar(nivel_clave, modo, version_id, actor.id or "admin", ahora, esperada if actual is not None else None)
            if fila is None:
                raise ConflictoDeVersion("Otro administrador cambió este nivel mientras lo editabas: vuelve a leerlo.", version_actual=(uow.niveles.get(nivel_clave) or {}).get("version"))
            self._publicar(uow, "Nivel", nivel_clave, cat.EV_MODO_CAMBIADO, {
                "nivel_clave": nivel_clave, "modo_anterior": modo_actual, "modo_nuevo": modo, "escala_version_anterior": (actual or {}).get("escala_version_id"),
                "escala_version_nueva": version_id, "version": fila["version"]}, ahora)
            uow.auditoria.registrar(actor.id or "admin", cat.A_MODO_CAMBIADO, "m11_config_nivel", nivel_clave,
                                    anterior={"modo": modo_actual, "escala_version_id": (actual or {}).get("escala_version_id")},
                                    nuevo={"modo": modo, "escala_version_id": version_id, "escala": version["codigo"] if version else None, "version": fila["version"]})
            return {"cambiado": True, "nivel": nivel_a_salida(uow, nivel_clave, fila), "advertencias": advertencias, "servidor_en": ahora}


class ConfigurarPolitica(_CasoDeUso):
    """`datos`: `{pais?, jurisdiccion?, institucion?, politica_intentos?, ponderaciones?}`. Cambiar qué intento cuenta recalcula lo derivado (no toca ninguna
    calificación). Las ponderaciones se guardan para V1 y NO se aplican: no se inventa una ponderación que la institución no ha declarado."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            self.s.autorizacion.exigir(actor, cat.P_MODE_SET)
            exigir_nodo_instalado(uow)
            actual = uow.politica.get()
            nuevo = dict(actual)
            if "pais" in datos:
                pais = str(datos.get("pais") or "").strip().upper()
                if pais and not re.fullmatch(r"[A-Z]{2}", pais):
                    raise DatosInvalidos("`pais` debe ser un código ISO de dos letras.", pais=pais)
                nuevo["pais"] = pais
            for clave, largo in (("jurisdiccion", 120), ("institucion", 200)):
                if clave in datos:
                    nuevo[clave] = str(datos.get(clave) or "").strip()[:largo]
            if "politica_intentos" in datos:
                if datos["politica_intentos"] not in cat.POLITICAS_DE_INTENTOS:
                    raise DatosInvalidos("`politica_intentos` no es válida.", validas=list(cat.POLITICAS_DE_INTENTOS))
                nuevo["politica_intentos"] = datos["politica_intentos"]
            if "ponderaciones" in datos:
                if not isinstance(datos["ponderaciones"], dict):
                    raise DatosInvalidos("`ponderaciones` debe ser un objeto.")
                nuevo["ponderaciones"] = datos["ponderaciones"]
            if actual.get("version", 0) > 0 and all(nuevo[k] == actual[k] for k in ("pais", "jurisdiccion", "institucion", "politica_intentos", "ponderaciones")):
                return {"politica": politica_a_salida(actual), "recalculado": None, "cambiado": False, "servidor_en": ahora}     # idempotente: ya estaba así
            fila = uow.politica.guardar(nuevo, actor.id or "admin", ahora)
            cambio_intentos = fila["politica_intentos"] != actual["politica_intentos"]
            self._publicar(uow, "Politica", "institucional", cat.EV_POLITICA, {
                "pais": fila["pais"], "politica_intentos": fila["politica_intentos"], "politica_anterior": actual["politica_intentos"], "version": fila["version"]}, ahora)
            uow.auditoria.registrar(actor.id or "admin", cat.A_POLITICA, "m11_politica", "institucional",
                                    anterior={k: actual[k] for k in ("pais", "jurisdiccion", "politica_intentos")},
                                    nuevo={k: fila[k] for k in ("pais", "jurisdiccion", "politica_intentos")} | {"version": fila["version"]})
            recalculado = None
            if cambio_intentos:
                recalculado = ReconstruirDerivados(self.s).ejecutar(actor, desde_el_sistema=True)
            return {"politica": politica_a_salida(fila), "recalculado": recalculado, "cambiado": True, "servidor_en": ahora}


class ClasificarEvaluacion(_CasoDeUso):
    """`datos`: `{tipo_evaluacion, afecta_oficial?, objetivos?}`. Diagnóstica, formativa o sumativa, y si cuenta para la calificación oficial. MOD-010 no lo
    sabe y no se le añade: es una decisión pedagógica del libro. `objetivos` son referencias a objetivos de aprendizaje o competencias (de la biblioteca o
    de MOD-012); aquí no se definen."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = uow.evaluacion.asignacion(asignacion_id)
            if asignacion is None:
                raise NoEncontrado("No existe esa asignación.", asignacion_id=asignacion_id)
            exigir_en_asignacion(uow, self.s.autorizacion, actor, cat.P_MODIFY, asignacion)
            tipo = str(datos.get("tipo_evaluacion") or "")
            if tipo not in cat.TIPOS_DE_EVALUACION:
                raise DatosInvalidos("`tipo_evaluacion` debe ser diagnostica, formativa o sumativa.", validos=list(cat.TIPOS_DE_EVALUACION))
            previa = clasificacion_efectiva(uow, asignacion)
            afecta = datos.get("afecta_oficial", tipo == cat.SUMATIVA)
            if not isinstance(afecta, bool):
                raise DatosInvalidos("`afecta_oficial` debe ser verdadero o falso.")
            objetivos = datos.get("objetivos", previa["objetivos"])
            if not isinstance(objetivos, list) or not all(isinstance(o, str) and 0 < len(o) <= 120 for o in objetivos) or len(objetivos) > 50:
                raise DatosInvalidos("`objetivos` debe ser una lista de hasta 50 referencias de texto.")
            if (tipo, afecta, objetivos) == (previa["tipo_evaluacion"], previa["afecta_oficial"], previa["objetivos"]) and uow.clasificaciones.get(asignacion_id) is not None:
                return {"asignacion_id": asignacion_id, "tipo_evaluacion": tipo, "afecta_oficial": afecta, "objetivos": objetivos, "cambiado": False,
                        "politica_intentos": politica_de_intentos(uow, asignacion), "servidor_en": ahora}          # idempotente: ya estaba así
            fila = uow.clasificaciones.guardar(asignacion_id, tipo, afecta, objetivos, actor.id or "docente", ahora)
            self._publicar(uow, "Asignacion", asignacion_id, cat.EV_CLASIFICACION, {
                "asignacion_id": asignacion_id, "tipo_evaluacion": tipo, "afecta_oficial": afecta, "anterior": previa["tipo_evaluacion"]}, ahora)
            uow.auditoria.registrar(actor.id or "docente", cat.A_CLASIFICACION, "m11_clasificacion", asignacion_id,
                                    anterior={"tipo_evaluacion": previa["tipo_evaluacion"], "afecta_oficial": previa["afecta_oficial"]},
                                    nuevo={"tipo_evaluacion": tipo, "afecta_oficial": afecta})
            derivar = RecalcularResultado(self.s)
            alumnos = {i["alumno_id"] for i in uow.evaluacion.intentos_de_asignacion(asignacion_id)} | {c["alumno_id"] for c in uow.calificaciones.de_asignacion(asignacion_id)}
            for alumno_id in sorted(alumnos):
                derivar.resultado(uow, asignacion, alumno_id, ahora)
            return {"asignacion_id": asignacion_id, "tipo_evaluacion": fila["tipo_evaluacion"], "afecta_oficial": fila["afecta_oficial"], "objetivos": fila["objetivos"],
                    "cambiado": True, "politica_intentos": politica_de_intentos(uow, asignacion), "servidor_en": ahora}


class VerClasificacion(_CasoDeUso):
    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        with self.s.uow(lectura=True) as uow:
            asignacion = uow.evaluacion.asignacion(asignacion_id)
            if asignacion is None:
                raise NoEncontrado("No existe esa asignación.", asignacion_id=asignacion_id)
            exigir_en_asignacion(uow, self.s.autorizacion, actor, cat.P_READ, asignacion)
            return {"asignacion_id": asignacion_id, **clasificacion_efectiva(uow, asignacion), "politica_intentos": politica_de_intentos(uow, asignacion),
                    "servidor_en": self.s.reloj.ahora_ms()}
