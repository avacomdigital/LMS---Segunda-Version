"""
El boletín de un estudiante (la vista del PROFESOR): todo lo que lleva en un grupo —notas, resultados e insights— agrupado por curso y paginado, para que la lista de un
grupo con cientos de evaluaciones al año no sea una tabla ilegible sino una página por estudiante.

  · `resumen`   lo que lleva en total (cuántas evaluaciones, con nota, aprobadas, por revisar, sin publicar, sin registro, pendientes) y su promedio simple.
  · `cursos`    lo mismo por curso, con el promedio presentado con el sistema de calificación del nivel y los puntos brutos sumados (lo que obtuvo sobre lo posible).
  · `materias`  las materias del grupo (por el `curso_ref` de cada evaluación) con sus cursos: con ellas se segmenta cuando un profesor dicta varios cursos de una materia.
  · `insights`  lo que se desprende de sus calificaciones registradas, con cuentas sencillas y explicables (nada de modelos): hacia dónde va, en qué curso le va mejor y en
                cuál hay que reforzar, su constancia y lo que el profesor escribió de él (fortalezas, dificultades, oportunidades).
  · `observaciones`  lo que el profesor le recomienda en este periodo (general y por curso), con las frases del catálogo que se tocan sin teclado.
  · `evaluaciones`  UNA página de sus evaluaciones (las de un curso o una materia si se pide, o las más recientes), de a `limite`, cada una con su nota en BRUTO (puntos
                sobre el máximo y porcentaje) y presentada con el sistema del nivel.

Reglas, las mismas del resto del libro: el PROMEDIO ES SIMPLE E INFORMATIVO (no ponderado, no oficial); lo pendiente nunca es un cero; en modo simple no hay notas ni cifras,
sólo si completó cada evaluación; el resultado interno (0–100) lo ve el profesor, nunca el alumno por esta ruta. Lo que se presenta lo calcula el nodo con la versión del
sistema con que se publicó (o la vigente del nivel, rotulado provisional, mientras no se publica).

`armar_boletin` es la pieza común: la usan la ruta del profesor (con su autorización) y la interfaz pública para Reportes (`gradebook.servicios`), que autoriza por su cuenta.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..dominio import catalogos as cat
from ..dominio import curso as cur
from ..dominio import puntaje as pj
from ..dominio.errores import ConflictoDeVersion, DatosInvalidos, NoEncontrado
from .base import _CasoDeUso, bruto_de, filtro_de_materia, materias_de, modo_del_nivel, nuevo_id, sistema_de, version_esperada
from .consultas import _conteo_vacio, _contar, _media, _presentacion, _presentado
from .derivados import clasificacion_de
from .puertos import Actor, UnidadDeTrabajo

POR_PAGINA = 20
MAXIMO_POR_PAGINA = 100
MINIMO_PARA_TENDENCIA = 4                       # con menos de cuatro calificaciones no se dice hacia dónde va
UMBRAL_DE_TENDENCIA = Decimal("5")              # puntos (escala interna 0–100) entre lo reciente y lo anterior para decir que sube o baja
MAXIMO_DE_COMENTARIOS = 3
CON_NOTA = (cat.REVISADO, cat.DEFINITIVO)


def _entero(valor, nombre: str, *, minimo: int, maximo: int | None = None, defecto: int) -> int:
    if valor in (None, ""):
        return defecto
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise DatosInvalidos(f"`{nombre}` debe ser un número entero.", campo=nombre) from None
    if numero < minimo or (maximo is not None and numero > maximo):
        raise DatosInvalidos(f"`{nombre}` debe estar entre {minimo} y {maximo if maximo is not None else 'más'}.", campo=nombre)
    return numero


def _tendencia(con_nota: list[dict]) -> dict:
    """Compara lo más reciente con lo anterior: la media de las últimas k calificaciones contra la de las k de antes (k hasta 3)."""
    if len(con_nota) < MINIMO_PARA_TENDENCIA:
        return {"direccion": "insuficiente", "calificaciones": len(con_nota), "minimo": MINIMO_PARA_TENDENCIA}
    ordenadas = sorted(con_nota, key=lambda i: (i["fecha"] or 0, i["asignacion_id"]))
    k = min(3, len(ordenadas) // 2)
    reciente = [Decimal(str(i["puntaje_efectivo"])) for i in ordenadas[-k:]]
    anterior = [Decimal(str(i["puntaje_efectivo"])) for i in ordenadas[-2 * k:-k]]
    de, a = sum(anterior) / len(anterior), sum(reciente) / len(reciente)
    diferencia = a - de
    direccion = "sube" if diferencia >= UMBRAL_DE_TENDENCIA else "baja" if diferencia <= -UMBRAL_DE_TENDENCIA else "estable"
    return {"direccion": direccion, "de": pj.como_numero(pj.redondear(de, 2)), "a": pj.como_numero(pj.redondear(a, 2)),
            "diferencia": pj.como_numero(pj.redondear(diferencia, 2)), "comparadas": k, "calificaciones": len(con_nota)}


def _comentarios(califs: list[dict], titulos: dict[str, str], fechas: dict[str, int | None]) -> dict:
    """Lo que el profesor escribió: las últimas fortalezas, dificultades y oportunidades (no repetidas), con la evaluación y la fecha. El comentario general de cada una
    se queda en su detalle."""
    salida: dict[str, list] = {"fortalezas": [], "dificultades": [], "oportunidades": []}
    for c in sorted(califs, key=lambda c: (c.get("actualizada_en") or 0, c["id"]), reverse=True):
        for clave in salida:
            texto = str((c.get("retroalimentacion") or {}).get(clave) or "").strip()
            if texto and len(salida[clave]) < MAXIMO_DE_COMENTARIOS and texto not in {x["texto"] for x in salida[clave]}:
                salida[clave].append({"texto": texto, "titulo": titulos.get(c["asignacion_id"], ""), "fecha": fechas.get(c["asignacion_id"])})
    return salida


def _suma_bruta(items: list[dict]) -> dict:
    """Los puntos brutos sumados de unas evaluaciones con nota: lo obtenido sobre lo posible y el porcentaje que resulta. Sólo entran las que tienen puntos (una nota
    registrada a mano sin puntos no suma ni resta); sin ninguna, todo nulo."""
    con_puntos = [i for i in items if i["estado"] in CON_NOTA and (i.get("bruto") or {}).get("puntos") is not None and (i["bruto"].get("puntos_maximos") or 0) > 0]
    if not con_puntos:
        return {"puntos": None, "puntos_maximos": None, "porcentaje": None, "evaluaciones": 0}
    puntos = sum(Decimal(str(i["bruto"]["puntos"])) for i in con_puntos)
    maximos = sum(Decimal(str(i["bruto"]["puntos_maximos"])) for i in con_puntos)
    return {"puntos": pj.como_numero(pj.redondear(puntos, 2)), "puntos_maximos": pj.como_numero(pj.redondear(maximos, 2)),
            "porcentaje": pj.como_numero(pj.redondear(puntos * Decimal(100) / maximos, 2)) if maximos > 0 else None, "evaluaciones": len(con_puntos)}


def salida_observacion(o: dict) -> dict:
    return {"id": o["id"], "alumno_id": o["alumno_id"], "grupo_id": o["grupo_id"], "periodo": o["periodo"], "curso_ref": o["curso_ref"],
            "recomendaciones": [{"codigo": c, "texto": cat.RECOMENDACIONES.get(c, c)} for c in (o.get("recomendaciones") or [])],
            "texto": o["texto"], "version": o["version"], "actualizada_en": o["actualizada_en"], "actualizada_por": o["actualizada_por"]}


def recomendaciones_disponibles() -> list[dict]:
    return [{"codigo": c, "texto": t} for c, t in cat.RECOMENDACIONES.items()]


def armar_boletin(uow: UnidadDeTrabajo, alumno_id: str, grupo: dict, *, curso_ref: str = "", desde: int = 0, limite: int = POR_PAGINA, materia: dict | None = None,
                  ahora: int = 0) -> dict:
    """El boletín de un alumno en un grupo, sin autorizar a nadie (quien llama ya lo hizo). `materia` recorta las evaluaciones a las de un nodo académico (país, nivel,
    grado, materia, tema) por el `curso_ref` de cada una; `curso_ref` a las de UN curso (la página de evaluaciones y nada más)."""
    grupo_id = grupo["id"]
    rotulo = uow.identidad.rotulos_personas([alumno_id]).get(alumno_id, alumno_id)
    modo, version = modo_del_nivel(uow, grupo["nivel_clave"] or "")

    todas = [a for a in uow.evaluacion.asignaciones_de_grupo(grupo_id) if a["estado"] != "borrador"]
    materias = materias_de(uow, todas)
    asignaciones = [a for a in todas if cur.cumple(a["curso_ref"], materia or {})]
    clasificacion = uow.clasificaciones.de([a["id"] for a in asignaciones])
    resultados = {r["asignacion_id"]: r for r in uow.resultados.de_alumno(alumno_id, grupo_id)}
    califs = uow.calificaciones.de_alumno(alumno_id, grupo_id)
    por_id = {c["id"]: c for c in califs}

    items, titulos, fechas = [], {}, {}
    for a in asignaciones:
        r = resultados.get(a["id"])
        aplicable = por_id.get(r["calificacion_aplicable_id"]) if r and r.get("calificacion_aplicable_id") else None
        estado = r["estado_calificacion"] if r else cat.PENDIENTE
        simple = r["estado_simple"] if r else cat.NO_INICIADO
        presentacion = _presentacion(aplicable, modo, version) if aplicable else None
        fecha = a.get("abre_en") or a.get("publicada_en") or a.get("creada_en")           # la fecha de la EVALUACIÓN: con ella se ordena y se compara lo reciente con lo anterior
        titulos[a["id"]], fechas[a["id"]] = a["titulo"], fecha
        tipo = clasificacion_de(a, clasificacion.get(a["id"]))["tipo_evaluacion"]          # sin una consulta por evaluación: las filas ya vienen de una vez
        items.append({
            "asignacion_id": a["id"], "titulo": a["titulo"], "curso_ref": a["curso_ref"], "curso_rotulo": a.get("curso_rotulo") or "", "materia": cur.materia_de(a["curso_ref"]),
            "tipo_evaluacion": tipo, "estado": estado, "estado_simple": simple, "publicada": bool(r and r["publicada"]), "fecha": fecha,
            "calificacion_id": aplicable["id"] if aplicable else None, "version": aplicable["version"] if aplicable else None,
            "puntaje_efectivo": pj.como_numero(aplicable["puntaje_efectivo"]) if aplicable else None,
            "ajustada": bool(aplicable and aplicable["puntaje_efectivo"] != aplicable["puntaje_fuente"]), "presentacion": presentacion,
            "bruto": bruto_de(aplicable) if aplicable else None, "retroalimentacion": (aplicable or {}).get("retroalimentacion") or {},
            "numero_intento": aplicable["numero_intento"] if aplicable else None, "intentos": r["intentos_total"] if r else 0})

    # ---- lo que lleva en total y por curso
    resumen = {"evaluaciones": len(items), "conteo": _conteo_vacio()}
    por_curso: dict[str, dict] = {}
    puntajes_por_curso: dict[str, list] = defaultdict(list)
    items_por_curso: dict[str, list] = defaultdict(list)
    puntajes = []
    for i in items:
        curso = por_curso.setdefault(i["curso_ref"], {"curso_ref": i["curso_ref"], "curso_rotulo": i["curso_rotulo"], "materia": i["materia"], "evaluaciones": 0, "conteo": _conteo_vacio()})
        curso["evaluaciones"] += 1
        items_por_curso[i["curso_ref"]].append(i)
        _contar(resumen["conteo"], i["estado"], i["estado_simple"], i["presentacion"], con_notas=modo == cat.CALIFICACIONES)
        _contar(curso["conteo"], i["estado"], i["estado_simple"], i["presentacion"], con_notas=modo == cat.CALIFICACIONES)
        if i["estado"] in CON_NOTA and i["puntaje_efectivo"] is not None:
            puntajes.append(Decimal(str(i["puntaje_efectivo"])))
            puntajes_por_curso[i["curso_ref"]].append(Decimal(str(i["puntaje_efectivo"])))
    resumen["promedio_simple"] = _media(puntajes)
    resumen["presentado"] = _presentado(version, modo, resumen["promedio_simple"])
    resumen["bruto"] = _suma_bruta(items) if modo == cat.CALIFICACIONES else {"puntos": None, "puntos_maximos": None, "porcentaje": None, "evaluaciones": 0}
    resumen["oficial"], resumen["ponderado"] = False, False
    cursos = []
    for ref, curso in sorted(por_curso.items(), key=lambda kv: (kv[1]["curso_rotulo"].lower(), kv[0])):
        curso["promedio_simple"] = _media(puntajes_por_curso.get(ref, []))
        curso["presentado"] = _presentado(version, modo, curso["promedio_simple"])
        curso["bruto"] = _suma_bruta(items_por_curso.get(ref, [])) if modo == cat.CALIFICACIONES else {"puntos": None, "puntos_maximos": None, "porcentaje": None, "evaluaciones": 0}
        cursos.append(curso)

    # ---- insights (sólo de lo registrado; sin sistema, sólo lo que se hizo)
    con_nota = [i for i in items if i["estado"] in CON_NOTA and i["puntaje_efectivo"] is not None]
    con_promedio = [c for c in cursos if c["promedio_simple"] is not None]
    insights = {
        "tendencia": _tendencia(con_nota) if modo == cat.CALIFICACIONES else {"direccion": "insuficiente", "calificaciones": 0, "minimo": MINIMO_PARA_TENDENCIA},
        "mejor_curso": None, "curso_a_reforzar": None,
        "constancia": {"completadas": resumen["conteo"]["completadas"], "evaluaciones": resumen["evaluaciones"]},
        "comentarios": _comentarios(califs, titulos, fechas) if modo == cat.CALIFICACIONES else {"fortalezas": [], "dificultades": [], "oportunidades": []},
        "informativo": True}
    if len(con_promedio) >= 2:
        mejor, peor = max(con_promedio, key=lambda c: c["promedio_simple"]), min(con_promedio, key=lambda c: c["promedio_simple"])
        if mejor["promedio_simple"] != peor["promedio_simple"]:
            forma = lambda c: {k: c[k] for k in ("curso_ref", "curso_rotulo", "promedio_simple", "presentado")}  # noqa: E731
            insights["mejor_curso"], insights["curso_a_reforzar"] = forma(mejor), forma(peor)

    # ---- lo que el profesor le recomienda (este periodo: general y por curso)
    observaciones = [salida_observacion(o) for o in uow.observaciones.de_alumno(alumno_id, grupo_id) if o["periodo"] == (grupo["periodo"] or "")]

    # ---- una página de evaluaciones
    elegidas = [i for i in items if not curso_ref or i["curso_ref"] == curso_ref]
    elegidas.sort(key=lambda i: (i["fecha"] or 0, i["asignacion_id"]), reverse=True)
    pagina = elegidas[desde:desde + limite]
    return {
        "alumno": {"id": alumno_id, "rotulo": rotulo},
        "grupo": {"id": grupo["id"], "codigo": grupo["codigo"], "nombre": grupo["nombre"], "periodo": grupo["periodo"], "nivel_clave": grupo["nivel_clave"]},
        "modo": modo, "sistema": None if version is None else sistema_de(version),
        "materias": materias, "filtro": {"materia": materia or None, "curso_ref": curso_ref or None},
        "resumen": resumen, "cursos": cursos, "insights": insights, "observaciones": observaciones, "recomendaciones_disponibles": recomendaciones_disponibles(),
        "evaluaciones": {"curso_ref": curso_ref, "total": len(elegidas), "desde": desde, "limite": limite, "items": pagina},
        "servidor_en": ahora}


class BoletinDelEstudiante(_CasoDeUso):
    def ejecutar(self, actor: Actor, alumno_id: str, grupo_id: str, *, curso_ref: str = "", desde=None, limite=None, consulta: dict | None = None) -> dict:
        ahora = self.s.reloj.ahora_ms()
        desde = _entero(desde, "desde", minimo=0, defecto=0)
        limite = _entero(limite, "limite", minimo=1, maximo=MAXIMO_POR_PAGINA, defecto=POR_PAGINA)
        materia = filtro_de_materia(consulta or {})
        if not grupo_id:
            raise DatosInvalidos("Falta `grupo_id`: el boletín de un estudiante es el de un grupo y un periodo.")
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir(actor, cat.P_READ, grupo_id=grupo_id)
            grupo = uow.identidad.grupo(grupo_id)
            if grupo is None:
                raise NoEncontrado("No existe ese grupo.", grupo_id=grupo_id)
            if grupo_id not in uow.identidad.grupos_del_alumno(alumno_id) and not uow.calificaciones.de_alumno(alumno_id, grupo_id):
                raise NoEncontrado("Ese alumno no está en ese grupo ni tiene calificaciones en él.", alumno_id=alumno_id, grupo_id=grupo_id)     # el rótulo de cualquier persona no se da
            return armar_boletin(uow, alumno_id, grupo, curso_ref=curso_ref, desde=desde, limite=limite, materia=materia, ahora=ahora)


# ================================================================================================ observaciones del docente

class RegistrarObservacion(_CasoDeUso):
    """`PUT /estudiantes/{id}/observacion/` con `{grupo_id, curso_ref?, recomendaciones: [códigos], texto?, version_esperada?}`: lo que el profesor recomienda a un estudiante en
    el periodo del grupo (la cuarta pregunta del boletín). Las recomendaciones son claves del catálogo cerrado (se tocan, no se escriben); el texto es un extra. Repetir lo mismo
    no cambia nada ni deja asiento; cada cambio real sube la versión, queda en la bitácora (quién, cuándo, de qué a qué) y publica su evento."""

    def ejecutar(self, actor: Actor, alumno_id: str, datos: dict) -> dict:
        grupo_id = str(datos.get("grupo_id") or "")
        if not grupo_id:
            raise DatosInvalidos("Falta `grupo_id`: la observación es de un estudiante en un grupo y un periodo.")
        curso_ref = str(datos.get("curso_ref") or "").strip()[:200]
        recomendaciones = datos.get("recomendaciones", [])
        if not isinstance(recomendaciones, list) or any(not isinstance(r, str) for r in recomendaciones):
            raise DatosInvalidos("`recomendaciones` debe ser una lista de códigos del catálogo.", campo="recomendaciones")
        recomendaciones = list(dict.fromkeys(r.strip() for r in recomendaciones if r.strip()))
        desconocidas = [r for r in recomendaciones if r not in cat.RECOMENDACIONES]
        if desconocidas:
            raise DatosInvalidos("Hay recomendaciones que no están en el catálogo.", campo="recomendaciones", desconocidas=desconocidas[:5], validas=list(cat.RECOMENDACIONES))
        if len(recomendaciones) > cat.MAX_RECOMENDACIONES:
            raise DatosInvalidos(f"Elige a lo sumo {cat.MAX_RECOMENDACIONES} recomendaciones.", campo="recomendaciones")
        texto = " ".join(str(datos.get("texto") or "").split())[:cat.MAX_OBSERVACION]
        esperada = version_esperada(datos, obligatorio=False)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            self.s.autorizacion.exigir(actor, cat.P_MODIFY, grupo_id=grupo_id)
            grupo = uow.identidad.grupo(grupo_id)
            if grupo is None:
                raise NoEncontrado("No existe ese grupo.", grupo_id=grupo_id)
            if grupo_id not in uow.identidad.grupos_del_alumno(alumno_id) and not uow.calificaciones.de_alumno(alumno_id, grupo_id):
                raise NoEncontrado("Ese alumno no está en ese grupo ni tiene calificaciones en él.", alumno_id=alumno_id, grupo_id=grupo_id)
            if curso_ref and all(a["curso_ref"] != curso_ref for a in uow.evaluacion.asignaciones_de_grupo(grupo_id)):
                raise DatosInvalidos("Ese curso no tiene evaluaciones en este grupo.", curso_ref=curso_ref)
            periodo = grupo["periodo"] or ""
            actual = uow.observaciones.get(alumno_id, grupo_id, periodo, curso_ref)
            quien = actor.id or "docente"
            if actual is not None and list(actual["recomendaciones"] or []) == recomendaciones and actual["texto"] == texto:
                return {"observacion": salida_observacion(actual), "cambiado": False, "servidor_en": ahora}
            if actual is None:
                nueva = uow.observaciones.crear({"id": nuevo_id(), "alumno_id": alumno_id, "grupo_id": grupo_id, "periodo": periodo, "curso_ref": curso_ref,
                                                 "recomendaciones": recomendaciones, "texto": texto, "version": 1, "actualizada_en": ahora, "actualizada_por": quien})
                anterior = None
            else:
                if esperada is not None and esperada != actual["version"]:
                    raise ConflictoDeVersion("Otra persona cambió esta observación mientras la editabas: vuelve a leerla.", version_actual=actual["version"], version_esperada=esperada)
                nueva = uow.observaciones.actualizar_si_version(actual["id"], actual["version"], recomendaciones=recomendaciones, texto=texto, actualizada_en=ahora, actualizada_por=quien)
                if nueva is None:
                    raise ConflictoDeVersion("Otra persona cambió esta observación mientras la editabas: vuelve a leerla.", version_actual=actual["version"])
                anterior = {"recomendaciones": actual["recomendaciones"], "texto": actual["texto"], "version": actual["version"]}
            self._publicar(uow, "Observacion", nueva["id"], cat.EV_OBSERVACION, {
                "observacion_id": nueva["id"], "alumno_id": alumno_id, "grupo_id": grupo_id, "periodo": periodo, "curso_ref": curso_ref, "recomendaciones": recomendaciones,
                "version": nueva["version"], "por": quien}, ahora)
            uow.auditoria.registrar(quien, cat.A_OBSERVACION, "m11_observacion", nueva["id"], anterior=anterior,
                                    nuevo={"alumno_id": alumno_id, "grupo_id": grupo_id, "periodo": periodo, "curso_ref": curso_ref, "recomendaciones": recomendaciones,
                                           "texto": texto, "version": nueva["version"]})
            return {"observacion": salida_observacion(nueva), "cambiado": True, "servidor_en": ahora}
