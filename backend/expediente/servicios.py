"""
Servicios de dominio del expediente. Aquí vive la lógica; las vistas sólo traducen HTTP.

Principio: la estructura del curso se resuelve EN VIVO contra la biblioteca y
sólo se usa para mostrar y para calcular; el expediente se escribe contra la
identidad lógica (curso_ref, leccion_codigo, elemento_ref, pregunta_ref).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import (
    AperturaMaterial,
    DisponibilidadObservada,
    Inscripcion,
    Intento,
    IntentoPregunta,
    IntentoRespuesta,
    ProgresoLeccion,
    ahora_ms,
)

# Tipos que no se dan en el aula: no cuentan para el progreso ni se ofrecen al estudiante.
TIPOS_NO_VISIBLES = frozenset({"banco", "scorm"})
# Tipos cuya «apertura» no basta: se completan al finalizar un intento.
TIPOS_EVALUABLES = frozenset({"evaluacion", "actividad"})


def _dec(valor) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def auditar(actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`). `extra`: motivo, resultado, dispositivo_id, evento_id."""
    from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
    auditoria.anexar(actor or "", accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)


# ------------------------------------------------------------- inscripción

def inscribir(curso_ref: str, persona_id: str, persona_rotulo: str = "", curso_rotulo: str = "",
              actor: str = "") -> tuple[Inscripcion, bool]:
    """Idempotente. Reactiva una inscripción retirada en vez de duplicarla."""
    inscripcion, creada = Inscripcion.objects.get_or_create(
        curso_ref=curso_ref,
        persona_id=persona_id,
        defaults={"persona_rotulo": persona_rotulo, "curso_rotulo": curso_rotulo, "creado_por": actor},
    )
    cambios = []
    if not creada and inscripcion.retirado_en is not None:
        inscripcion.retirado_en = None
        cambios.append("retirado_en")
    if persona_rotulo and not inscripcion.persona_rotulo:
        inscripcion.persona_rotulo = persona_rotulo
        cambios.append("persona_rotulo")
    if curso_rotulo and not inscripcion.curso_rotulo:
        inscripcion.curso_rotulo = curso_rotulo
        cambios.append("curso_rotulo")
    if cambios:
        inscripcion.save(update_fields=cambios)
    if creada:
        auditar(actor or persona_id, "inscripcion.creada", "m05_inscripcion", inscripcion.id,
                nuevo={"curso_ref": curso_ref, "persona_id": persona_id})
    return inscripcion, creada


def retirar_inscripcion(inscripcion: Inscripcion, actor: str = "") -> Inscripcion:
    if inscripcion.retirado_en is None:
        inscripcion.retirado_en = ahora_ms()
        inscripcion.save(update_fields=["retirado_en"])
        auditar(actor, "inscripcion.retirada", "m05_inscripcion", inscripcion.id,
                nuevo={"retirado_en": inscripcion.retirado_en})
    return inscripcion


# ---------------------------------------------------------------- progreso

def items_visibles(seccion: dict) -> list[dict]:
    return [i for i in seccion.get("items", []) if i.get("tipo") not in TIPOS_NO_VISIBLES]


def estados_de_intentos(curso_ref: str, persona_id: str) -> dict[str, dict]:
    """Por evaluación: el mejor estado conocido (finalizado > pendiente > abierto) y su puntaje."""
    orden = {Intento.FINALIZADO: 3, Intento.PENDIENTE: 2, Intento.ABIERTO: 1}
    salida: dict[str, dict] = {}
    for intento in Intento.objects.filter(curso_ref=curso_ref, persona_id=persona_id).order_by("iniciado_en"):
        actual = salida.get(intento.evaluacion_ref)
        if actual is None or orden[intento.estado] >= orden[actual["estado"]]:
            salida[intento.evaluacion_ref] = {
                "estado": intento.estado,
                "puntaje": intento.puntaje,
                "intento_id": intento.id,
            }
    return salida


def item_completado(item: dict, abiertos: set[str], intentos: dict[str, dict]) -> bool:
    ref = item.get("elemento_ref", "")
    if item.get("tipo") in TIPOS_EVALUABLES:
        estado = intentos.get(ref, {}).get("estado")
        return estado in (Intento.FINALIZADO, Intento.PENDIENTE)
    return ref in abiertos


def porcentaje_seccion(seccion: dict, abiertos: set[str], intentos: dict[str, dict]) -> Decimal:
    visibles = items_visibles(seccion)
    if not visibles:
        return Decimal("0.00")
    hechos = sum(1 for i in visibles if item_completado(i, abiertos, intentos))
    return _dec(Decimal(hechos) * 100 / Decimal(len(visibles)))


def actualizar_progreso(curso_ref: str, persona_id: str, leccion_codigo: str, porcentaje,
                        leccion_rotulo: str = "", version_observada: str = "", actor: str = "") -> ProgresoLeccion:
    """Upsert MONOTÓNICO: un avance atrasado no reduce; 100 % sella la sección."""
    nuevo = max(Decimal("0"), min(Decimal("100"), _dec(porcentaje)))
    ahora = ahora_ms()
    with transaction.atomic():
        fila, creada = ProgresoLeccion.objects.select_for_update().get_or_create(
            curso_ref=curso_ref,
            persona_id=persona_id,
            leccion_codigo=leccion_codigo,
            defaults={
                "leccion_rotulo": leccion_rotulo,
                "version_observada": version_observada,
                "porcentaje": Decimal("0"),
                "estado": ProgresoLeccion.NO_INICIADA,
                "iniciado_en": None,
                "actualizado_en": ahora,
            },
        )
        anterior = fila.porcentaje
        if nuevo < anterior:
            return fila  # no se reduce nunca
        campos = []
        if nuevo != anterior or creada:
            fila.porcentaje = nuevo
            campos.append("porcentaje")
        if fila.iniciado_en is None and nuevo > 0:
            fila.iniciado_en = ahora
            campos.append("iniciado_en")
        estado = (
            ProgresoLeccion.COMPLETADA if nuevo >= 100
            else ProgresoLeccion.EN_CURSO if nuevo > 0
            else ProgresoLeccion.NO_INICIADA
        )
        if estado != fila.estado:
            fila.estado = estado
            campos.append("estado")
        if estado == ProgresoLeccion.COMPLETADA and fila.completado_en is None:
            fila.completado_en = ahora
            campos.append("completado_en")
        if leccion_rotulo and not fila.leccion_rotulo:
            fila.leccion_rotulo = leccion_rotulo
            campos.append("leccion_rotulo")
        if version_observada and version_observada != fila.version_observada:
            fila.version_observada = version_observada
            campos.append("version_observada")
        if campos:
            fila.actualizado_en = ahora
            campos.append("actualizado_en")
            fila.save(update_fields=campos)
            if "porcentaje" in campos and nuevo != anterior:
                auditar(actor or persona_id, "progreso.actualizado", "m05_progreso_leccion", fila.id,
                        anterior={"porcentaje": str(anterior)}, nuevo={"porcentaje": str(nuevo)})
    return fila


def recalcular_progreso(curso_ref: str, persona_id: str, detalle: dict | None, actor: str = "") -> None:
    """Recalcula cada sección del curso contra la estructura VIGENTE (si se pudo
    obtener). Sin estructura no se escribe nada: no se puede saber el total."""
    if not detalle:
        return
    abiertos = set(
        AperturaMaterial.objects.filter(curso_ref=curso_ref, persona_id=persona_id)
        .values_list("elemento_ref", flat=True)
    )
    intentos = estados_de_intentos(curso_ref, persona_id)
    version = str(detalle.get("version", ""))
    # Se escribe una fila por CADA sección vigente (aunque esté en 0 %): así el promedio
    # que se calcula sin biblioteca coincide con el que se calcula con ella.
    for seccion in detalle.get("secciones", []):
        if not items_visibles(seccion):
            continue
        pct = porcentaje_seccion(seccion, abiertos, intentos)
        actualizar_progreso(curso_ref, persona_id, seccion.get("codigo", ""), pct,
                            leccion_rotulo=seccion.get("titulo", ""), version_observada=version, actor=actor)


def promedio_curso(curso_ref: str, persona_id: str, detalle: dict | None) -> Decimal:
    """Promedio sobre las secciones VIGENTES. Sin estructura, sobre lo registrado."""
    filas = {
        p.leccion_codigo: p.porcentaje
        for p in ProgresoLeccion.objects.filter(curso_ref=curso_ref, persona_id=persona_id)
    }
    if detalle:
        codigos = [s.get("codigo", "") for s in detalle.get("secciones", []) if items_visibles(s)]
        if not codigos:
            return Decimal("0.00")
        return _dec(sum((filas.get(c, Decimal("0")) for c in codigos), Decimal("0")) / Decimal(len(codigos)))
    if not filas:
        return Decimal("0.00")
    return _dec(sum(filas.values(), Decimal("0")) / Decimal(len(filas)))


def proyectar_curso(detalle: dict, persona_id: str | None) -> dict:
    """Anota la estructura vigente con el expediente de una persona. NO escribe."""
    salida = dict(detalle)
    curso_ref = detalle.get("curso_ref", "")
    abiertos: set[str] = set()
    intentos: dict[str, dict] = {}
    progreso_filas: dict[str, ProgresoLeccion] = {}
    if persona_id:
        abiertos = set(
            AperturaMaterial.objects.filter(curso_ref=curso_ref, persona_id=persona_id)
            .values_list("elemento_ref", flat=True)
        )
        intentos = estados_de_intentos(curso_ref, persona_id)
        progreso_filas = {
            p.leccion_codigo: p
            for p in ProgresoLeccion.objects.filter(curso_ref=curso_ref, persona_id=persona_id)
        }
    secciones = []
    for seccion in detalle.get("secciones", []):
        fila = progreso_filas.get(seccion.get("codigo", ""))
        items = []
        for item in seccion.get("items", []):
            ref = item.get("elemento_ref", "")
            intento = intentos.get(ref)
            items.append({
                **item,
                "visible": item.get("tipo") not in TIPOS_NO_VISIBLES,
                "abierto": ref in abiertos,
                "completado": item_completado(item, abiertos, intentos) if persona_id else False,
                "estado_intento": intento["estado"] if intento else None,
                "puntaje": float(intento["puntaje"]) if intento and intento["puntaje"] is not None else None,
                "intento_id": intento["intento_id"] if intento else None,
            })
        secciones.append({
            **seccion,
            "items": items,
            "progreso": float(fila.porcentaje) if fila else (float(porcentaje_seccion(seccion, abiertos, intentos)) if persona_id else 0.0),
            "estado": fila.estado if fila else ProgresoLeccion.NO_INICIADA,
        })
    salida["secciones"] = secciones
    salida["progreso"] = float(promedio_curso(curso_ref, persona_id, detalle)) if persona_id else 0.0
    return salida


# --------------------------------------------------------------- aperturas

def registrar_apertura(*, curso_ref: str, persona_id: str, elemento_ref: str, leccion_codigo: str = "",
                       version_elemento: str = "", tipo: str = "", elemento_rotulo: str = "",
                       dispositivo: str = "", persona_rotulo: str = "", curso_rotulo: str = "",
                       origen: str = "student", detalle: dict | None = None) -> AperturaMaterial:
    """Registra que alguien abrió un material, inscribe si hacía falta y recalcula el progreso."""
    with transaction.atomic():
        inscribir(curso_ref, persona_id, persona_rotulo, curso_rotulo, actor=persona_id)
        apertura = AperturaMaterial.objects.create(
            curso_ref=curso_ref,
            persona_id=persona_id,
            leccion_codigo=leccion_codigo,
            elemento_ref=elemento_ref,
            version_elemento=version_elemento,
            tipo=tipo,
            elemento_rotulo=elemento_rotulo,
            dispositivo=dispositivo,
            origen=origen or "student",
        )
        auditar(persona_id, "apertura.registrada", "m05_apertura_material", apertura.id,
                nuevo={"curso_ref": curso_ref, "elemento_ref": elemento_ref, "version": version_elemento})
        recalcular_progreso(curso_ref, persona_id, detalle, actor=persona_id)
    return apertura


def cerrar_apertura(apertura: AperturaMaterial, progreso_pct: int | None = None) -> AperturaMaterial:
    if apertura.cerrado_en is None:
        apertura.cerrado_en = ahora_ms()
        apertura.segundos = max(0, (apertura.cerrado_en - apertura.abierto_en) // 1000)
    if progreso_pct is not None:
        apertura.progreso_pct = max(0, min(100, int(progreso_pct)))
    apertura.save(update_fields=["cerrado_en", "segundos", "progreso_pct"])
    return apertura


# ---------------------------------------------------------------- intentos

def iniciar_intento(*, evaluacion_ref: str, persona_id: str, preguntas: list[dict], curso_ref: str = "",
                    leccion_codigo: str = "", version_observada: str = "", evaluacion_rotulo: str = "",
                    persona_rotulo: str = "", dispositivo: str = "", curso_rotulo: str = "") -> tuple[Intento, bool]:
    """Crea o REANUDA el intento abierto de (evaluación, persona, dispositivo)."""
    with transaction.atomic():
        if curso_ref:
            inscribir(curso_ref, persona_id, persona_rotulo, curso_rotulo, actor=persona_id)
        abierto = Intento.objects.filter(
            evaluacion_ref=evaluacion_ref, persona_id=persona_id, dispositivo=dispositivo or "", estado=Intento.ABIERTO
        ).first()
        if abierto:
            return abierto, False
        intento = Intento.objects.create(
            evaluacion_ref=evaluacion_ref,
            curso_ref=curso_ref,
            leccion_codigo=leccion_codigo,
            version_observada=version_observada,
            evaluacion_rotulo=evaluacion_rotulo,
            persona_id=persona_id,
            persona_rotulo=persona_rotulo,
            dispositivo=dispositivo or "",
            total_preguntas=len(preguntas),
        )
        for indice, pregunta in enumerate(preguntas, start=1):
            IntentoPregunta.objects.create(
                intento=intento,
                pregunta_ref=str(pregunta.get("ref") or pregunta.get("pregunta_ref") or f"p{indice}"),
                elemento_ref=evaluacion_ref,
                version_elemento=version_observada,
                orden=int(pregunta.get("orden") or indice),
                peso=_dec(pregunta.get("peso") or 1),
                corregible=bool(pregunta.get("corregible", True)),
            )
        auditar(persona_id, "intento.iniciado", "m10_intento", intento.id,
                nuevo={"evaluacion_ref": evaluacion_ref, "preguntas": len(preguntas)})
    return intento, True


def responder(intento: Intento, pregunta_ref: str, respuesta: str, veredicto: dict | None) -> IntentoRespuesta:
    """Idempotente por (intento, pregunta). `veredicto` viene de la biblioteca o es None si no se pudo corregir."""
    if intento.estado != Intento.ABIERTO:
        raise ValueError("El intento ya está cerrado.")
    with transaction.atomic():
        fila, _ = IntentoRespuesta.objects.update_or_create(
            intento=intento,
            pregunta_ref=pregunta_ref,
            defaults={
                "respuesta": respuesta,
                "acierta": None if veredicto is None else bool(veredicto.get("acierta")),
                "corregido_en": None if veredicto is None else ahora_ms(),
                "retroalimentacion_rotulo": None if veredicto is None else veredicto.get("retroalimentacion"),
                "respondido_en": ahora_ms(),
            },
        )
        pregunta = intento.preguntas.filter(pregunta_ref=pregunta_ref).first()
        if pregunta and pregunta.orden > intento.pregunta_actual:
            intento.pregunta_actual = pregunta.orden
            intento.save(update_fields=["pregunta_actual"])
    return fila


def finalizar(intento: Intento, detalle: dict | None = None, sin_responder_es_error: bool = True) -> Intento:
    """Idempotente. Calcula la nota ponderada y alimenta el progreso.

    - Pregunta con veredicto: cuenta con su peso (acierta o no).
    - Pregunta corregible SIN responder: cuenta como error si la biblioteca podía
      corregir (`sin_responder_es_error`); si no había capacidad, queda pendiente.
    - Pregunta abierta o respondida sin veredicto: pendiente de corrección docente.
    """
    if intento.estado != Intento.ABIERTO:
        return intento
    with transaction.atomic():
        respuestas = {r.pregunta_ref: r for r in intento.respuestas.all()}
        total_peso = Decimal("0")
        peso_acertado = Decimal("0")
        pendientes = 0
        aciertos = 0
        for pregunta in intento.preguntas.all():
            respuesta = respuestas.get(pregunta.pregunta_ref)
            if respuesta is None and pregunta.corregible and sin_responder_es_error:
                total_peso += pregunta.peso      # no contestó: cuenta como error, no como pendiente
                continue
            if respuesta is None or respuesta.acierta is None:
                pendientes += 1
                continue
            total_peso += pregunta.peso
            if respuesta.acierta:
                peso_acertado += pregunta.peso
                aciertos += 1
        intento.aciertos = aciertos
        intento.pendientes = pendientes
        intento.puntaje = _dec(peso_acertado * 100 / total_peso) if total_peso > 0 else None
        intento.estado = Intento.FINALIZADO if pendientes == 0 else Intento.PENDIENTE
        intento.finalizado_en = ahora_ms()
        intento.save(update_fields=["aciertos", "pendientes", "puntaje", "estado", "finalizado_en"])
        auditar(intento.persona_id, "intento.finalizado", "m10_intento", intento.id,
                nuevo={"estado": intento.estado, "puntaje": str(intento.puntaje) if intento.puntaje is not None else None})
        if intento.curso_ref:
            recalcular_progreso(intento.curso_ref, intento.persona_id, detalle, actor=intento.persona_id)
    return intento


def resumen_intento(intento: Intento) -> dict:
    respondidas = intento.respuestas.count()
    return {
        "id": intento.id,
        "evaluacion_ref": intento.evaluacion_ref,
        "evaluacion_rotulo": intento.evaluacion_rotulo,
        "curso_ref": intento.curso_ref,
        "leccion_codigo": intento.leccion_codigo,
        "persona_id": intento.persona_id,
        "persona_rotulo": intento.persona_rotulo,
        "dispositivo": intento.dispositivo,
        "estado": intento.estado,
        "puntaje": float(intento.puntaje) if intento.puntaje is not None else None,
        "aciertos": intento.aciertos,
        "total_preguntas": intento.total_preguntas,
        "respondidas": respondidas,
        "pendientes": intento.total_preguntas - respondidas if intento.estado == Intento.ABIERTO else intento.pendientes,
        "pregunta_actual": intento.pregunta_actual,
        "version_observada": intento.version_observada,
        "iniciado_en": intento.iniciado_en,
        "finalizado_en": intento.finalizado_en,
    }


# ----------------------------------------------------------- disponibilidad

def revisar_disponibilidad(cursos_vigentes: list[str], actor: str = "sistema") -> dict:
    """Actualiza la memoria de la última revisión de cada curso conocido por el
    expediente. SÓLO se llama con una oferta válida: sin catálogo no se escribe."""
    ahora = ahora_ms()
    vigentes = set(cursos_vigentes)
    conocidos = set(Inscripcion.objects.values_list("curso_ref", flat=True).distinct()) | vigentes
    desaparecidos, reaparecidos = [], []
    for referencia in conocidos:
        disponible = referencia in vigentes
        fila, creada = DisponibilidadObservada.objects.get_or_create(
            referencia=referencia,
            clase=DisponibilidadObservada.CURSO,
            defaults={
                "disponible_ultima_revision": disponible,
                "revisado_en": ahora,
                "desaparecido_en": None if disponible else ahora,
            },
        )
        if creada:
            if not disponible:
                # Primera observación y ya no está: es una desaparición y se audita.
                desaparecidos.append(referencia)
                auditar(actor, "disponibilidad.desaparecio", "m05_disponibilidad_observada", fila.id,
                        nuevo={"referencia": referencia, "desaparecido_en": ahora})
            continue
        if fila.disponible_ultima_revision and not disponible:
            fila.desaparecido_en = ahora
            desaparecidos.append(referencia)
            auditar(actor, "disponibilidad.desaparecio", "m05_disponibilidad_observada", fila.id,
                    nuevo={"referencia": referencia, "desaparecido_en": ahora})
        elif not fila.disponible_ultima_revision and disponible:
            fila.desaparecido_en = None
            reaparecidos.append(referencia)
            auditar(actor, "disponibilidad.reaparecio", "m05_disponibilidad_observada", fila.id,
                    nuevo={"referencia": referencia, "revisado_en": ahora})
        fila.disponible_ultima_revision = disponible
        fila.revisado_en = ahora
        fila.save(update_fields=["disponible_ultima_revision", "revisado_en", "desaparecido_en"])
    return {"revisado_en": ahora, "desaparecidos": desaparecidos, "reaparecidos": reaparecidos}


def memoria_disponibilidad(referencia: str) -> dict | None:
    fila = DisponibilidadObservada.objects.filter(referencia=referencia, clase=DisponibilidadObservada.CURSO).first()
    if not fila:
        return None
    return {
        "disponible_ultima_revision": fila.disponible_ultima_revision,
        "revisado_en": fila.revisado_en,
        "desaparecido_en": fila.desaparecido_en,
    }


# ------------------------------------------------------------- consolidado

def consolidado_curso(curso_ref: str, detalle: dict | None) -> dict:
    """Lo que ve el docente: por estudiante, progreso, aperturas, última actividad y notas."""
    estudiantes = []
    for inscripcion in Inscripcion.objects.filter(curso_ref=curso_ref, retirado_en__isnull=True).order_by("persona_rotulo", "persona_id"):
        persona = inscripcion.persona_id
        aperturas = AperturaMaterial.objects.filter(curso_ref=curso_ref, persona_id=persona)
        ultima = max(
            [a.abierto_en for a in aperturas] +
            [i.finalizado_en or i.iniciado_en for i in Intento.objects.filter(curso_ref=curso_ref, persona_id=persona)],
            default=None,
        )
        notas = [
            {"evaluacion_ref": i.evaluacion_ref, "evaluacion_rotulo": i.evaluacion_rotulo, "estado": i.estado,
             "puntaje": float(i.puntaje) if i.puntaje is not None else None, "finalizado_en": i.finalizado_en}
            for i in Intento.objects.filter(curso_ref=curso_ref, persona_id=persona).order_by("-iniciado_en")
        ]
        estudiantes.append({
            "persona_id": persona,
            "persona_rotulo": inscripcion.persona_rotulo or persona,
            "inscrito_en": inscripcion.inscrito_en,
            "progreso": float(promedio_curso(curso_ref, persona, detalle)),
            "aperturas": aperturas.count(),
            "segundos": sum(a.segundos or 0 for a in aperturas),
            "ultima_actividad": ultima,
            "secciones": [
                {"leccion_codigo": p.leccion_codigo, "leccion_rotulo": p.leccion_rotulo, "porcentaje": float(p.porcentaje), "estado": p.estado}
                for p in ProgresoLeccion.objects.filter(curso_ref=curso_ref, persona_id=persona).order_by("leccion_codigo")
            ],
            "notas": notas,
        })
    promedio = (
        _dec(sum(Decimal(str(e["progreso"])) for e in estudiantes) / Decimal(len(estudiantes))) if estudiantes else Decimal("0")
    )
    return {
        "curso_ref": curso_ref,
        "resumen": {
            "estudiantes": len(estudiantes),
            "promedio_progreso": float(promedio),
            "aperturas": sum(e["aperturas"] for e in estudiantes),
            "intentos_finalizados": Intento.objects.filter(curso_ref=curso_ref).exclude(estado=Intento.ABIERTO).count(),
        },
        "estudiantes": estudiantes,
    }
