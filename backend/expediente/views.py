"""
Vistas del expediente: inscripción, cursos del estudiante, progreso, aperturas del
visor, intentos, resultados, consolidado docente, auditoría y rechazos.

Las vistas sólo traducen HTTP ↔ servicios. La estructura del curso se pide a la
biblioteca a través del cliente único; si no está, el expediente sigue legible.
"""
from __future__ import annotations

from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from biblioteca import cliente
from biblioteca.views import respuesta_de_error

from . import servicios
from .models import AperturaMaterial, Inscripcion, Intento, ProgresoLeccion


def _texto(datos, clave, obligatorio=False, maximo=250) -> str:
    valor = (datos or {}).get(clave)
    if valor is None or str(valor).strip() == "":
        if obligatorio:
            raise ValueError(f"Falta {clave}.")
        return ""
    return str(valor).strip()[:maximo]


def _estructura_si_hay(curso_ref: str) -> dict | None:
    """La estructura vigente si la biblioteca contesta; None si «no se pudo comprobar»."""
    if not curso_ref:
        return None
    try:
        return cliente.curso(curso_ref)
    except (cliente.BibliotecaNoDisponible, cliente.BibliotecaError):
        return None


class VistaExpediente(APIView):
    def handle_exception(self, exc):
        if isinstance(exc, (cliente.BibliotecaNoDisponible, cliente.BibliotecaError)):
            return respuesta_de_error(exc)
        if isinstance(exc, ValueError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)


class HealthView(VistaExpediente):
    """Lo que consultan los clientes al conectar. Incluye el estado de la biblioteca."""

    def get(self, request):
        return Response({
            "status": "ok",
            "componente": "avacom-lms-backend",
            "administra_cursos": False,
            "dueno_de_los_cursos": "AVACOM Biblioteca",
            "biblioteca": cliente.estado(),
            "acceso": self._estado_acceso(),
        })

    @staticmethod
    def _estado_acceso() -> dict:
        """Estado del módulo de acceso: si el nodo está instalado y si las claves son las derivadas del prototipo."""
        try:
            from acceso.aplicacion.casos_uso import ConsultarConfiguracion
            from acceso.infraestructura.contenedor import servicios
            configuracion = ConsultarConfiguracion(servicios()).ejecutar()
            # RB-42: el estado del PIN maestro sin fechas (`configurado | vencido | sin_configurar`); el instalador lo muestra en su resumen final.
            pin = configuracion.get("pin_maestro") or {}
            estado_pin = "sin_configurar" if not pin.get("configurado") else ("vencido" if pin.get("vencido") else "configurado")
            return {"instalado": configuracion["instalado"], "claves_derivadas": configuracion["claves_derivadas"], "pin_maestro": estado_pin}
        except Exception as error:  # el health nunca falla por el módulo de acceso
            return {"instalado": False, "claves_derivadas": None, "pin_maestro": "sin_configurar", "error": str(error)}


# ------------------------------------------------------------- inscripción

def _inscripcion_a_dict(i: Inscripcion) -> dict:
    return {
        "id": i.id,
        "curso_ref": i.curso_ref,
        "persona_id": i.persona_id,
        "persona_rotulo": i.persona_rotulo,
        "curso_rotulo": i.curso_rotulo,
        "inscrito_en": i.inscrito_en,
        "retirado_en": i.retirado_en,
    }


class InscripcionesView(VistaExpediente):
    def get(self, request):
        filas = Inscripcion.objects.all().order_by("curso_ref", "persona_rotulo")
        curso_ref = request.query_params.get("curso_ref")
        persona = request.query_params.get("persona")
        if curso_ref:
            filas = filas.filter(curso_ref=curso_ref)
        if persona:
            filas = filas.filter(persona_id=persona)
        return Response([_inscripcion_a_dict(i) for i in filas])

    def post(self, request):
        datos = request.data or {}
        inscripcion, creada = servicios.inscribir(
            _texto(datos, "curso_ref", obligatorio=True, maximo=200),
            _texto(datos, "persona_id", obligatorio=True, maximo=64),
            _texto(datos, "persona_rotulo"),
            _texto(datos, "curso_rotulo"),
            actor=_texto(datos, "actor", maximo=64) or "docente",
        )
        return Response(_inscripcion_a_dict(inscripcion), status=201 if creada else 200)


class InscripcionView(VistaExpediente):
    def get(self, request, pk: int):
        fila = Inscripcion.objects.filter(pk=pk).first()
        if not fila:
            return Response({"detail": "No existe esa inscripción."}, status=404)
        return Response(_inscripcion_a_dict(fila))

    def delete(self, request, pk: int):
        """Retiro lógico: sella fecha, no borra."""
        fila = Inscripcion.objects.filter(pk=pk).first()
        if not fila:
            return Response({"detail": "No existe esa inscripción."}, status=404)
        return Response(_inscripcion_a_dict(servicios.retirar_inscripcion(fila, actor="docente")))


# ------------------------------------------------------ cursos del estudiante

class StudentCoursesView(VistaExpediente):
    """Cursos de una persona con progreso, disponibilidad y explicación.

    Con la biblioteca encendida: la oferta vigente completa (el estudiante puede
    entrar a cualquier curso ofrecido) más los cursos en los que está inscrito y
    ya no se ofrecen, con la memoria de la última revisión.
    Con la biblioteca cerrada: 200 con el expediente y un aviso; nunca 503.
    """

    def get(self, request, persona: str):
        aviso = None
        disponible = True
        vivos: list[dict] = []
        try:
            datos = cliente.cursos()
            vivos = datos["cursos"]
            servicios.revisar_disponibilidad([c.get("curso_ref", "") for c in vivos])
        except (cliente.BibliotecaNoDisponible, cliente.BibliotecaError) as error:
            disponible = False
            aviso = error.motivo if isinstance(error, cliente.BibliotecaNoDisponible) else error.detalle

        inscripciones = {
            i.curso_ref: i for i in Inscripcion.objects.filter(persona_id=persona, retirado_en__isnull=True)
        }
        salida = []
        refs_vivas = set()
        for curso in vivos:
            ref = curso.get("curso_ref", "")
            refs_vivas.add(ref)
            salida.append({
                **curso,
                "disponible": True,
                "inscrito": ref in inscripciones,
                "progreso": float(servicios.promedio_curso(ref, persona, None)),
                "aviso": None,
            })
        for ref, inscripcion in inscripciones.items():
            if ref in refs_vivas:
                continue
            memoria = servicios.memoria_disponibilidad(ref)
            if disponible:
                texto = "Este curso ya no se ofrece en este equipo."
                if memoria and memoria.get("desaparecido_en"):
                    texto += f" No disponible desde {memoria['desaparecido_en']} (ms desde 1970)."
                estado_curso = False
            else:
                texto = "No se pudo comprobar la disponibilidad: la biblioteca está cerrada."
                estado_curso = None
            salida.append({
                "curso_ref": ref,
                "titulo": inscripcion.curso_rotulo or ref,
                "version_vigente": None,
                "disponible": estado_curso,
                "inscrito": True,
                "progreso": float(servicios.promedio_curso(ref, persona, None)),
                "aviso": texto,
                "ultima_revision": memoria,
            })
        return Response({"disponible": disponible, "aviso": aviso, "persona_id": persona, "cursos": salida})


class StudentCourseProgressView(VistaExpediente):
    def get(self, request, persona: str, curso_ref: str):
        detalle = _estructura_si_hay(curso_ref)
        secciones = [
            {
                "leccion_codigo": p.leccion_codigo,
                "leccion_rotulo": p.leccion_rotulo,
                "porcentaje": float(p.porcentaje),
                "estado": p.estado,
                "version_observada": p.version_observada,
                "iniciado_en": p.iniciado_en,
                "actualizado_en": p.actualizado_en,
                "completado_en": p.completado_en,
            }
            for p in ProgresoLeccion.objects.filter(curso_ref=curso_ref, persona_id=persona).order_by("leccion_codigo")
        ]
        aperturas = [
            {
                "id": a.id,
                "elemento_ref": a.elemento_ref,
                "elemento_rotulo": a.elemento_rotulo,
                "tipo": a.tipo,
                "leccion_codigo": a.leccion_codigo,
                "abierto_en": a.abierto_en,
                "cerrado_en": a.cerrado_en,
                "segundos": a.segundos,
                "progreso_pct": a.progreso_pct,
            }
            for a in AperturaMaterial.objects.filter(curso_ref=curso_ref, persona_id=persona).order_by("-abierto_en")[:200]
        ]
        intentos = [servicios.resumen_intento(i) for i in Intento.objects.filter(curso_ref=curso_ref, persona_id=persona).order_by("-iniciado_en")]
        return Response({
            "curso_ref": curso_ref,
            "persona_id": persona,
            "estructura_disponible": detalle is not None,
            "progreso": float(servicios.promedio_curso(curso_ref, persona, detalle)),
            "secciones": secciones,
            "aperturas": aperturas,
            "intentos": intentos,
        })

    def post(self, request, persona: str, curso_ref: str):
        """Upsert monotónico explícito (por ejemplo, avance dentro de una lección completa)."""
        datos = request.data or {}
        codigo = _texto(datos, "leccion_codigo", obligatorio=True, maximo=120)
        try:
            porcentaje = float(datos.get("porcentaje", 0))
        except (TypeError, ValueError):
            raise ValueError("porcentaje debe ser numérico.")
        fila = servicios.actualizar_progreso(
            curso_ref, persona, codigo, porcentaje,
            leccion_rotulo=_texto(datos, "leccion_rotulo"),
            version_observada=_texto(datos, "version_observada", maximo=32),
            actor=persona,
        )
        return Response({
            "leccion_codigo": fila.leccion_codigo,
            "porcentaje": float(fila.porcentaje),
            "estado": fila.estado,
            "progreso_curso": float(servicios.promedio_curso(curso_ref, persona, None)),
        })


# --------------------------------------------------------------- aperturas

class AperturasView(VistaExpediente):
    """Registra que una persona abrió un material en el visor del LMS."""

    def post(self, request):
        datos = request.data or {}
        curso_ref = _texto(datos, "curso_ref", obligatorio=True, maximo=200)
        persona = _texto(datos, "persona_id", obligatorio=True, maximo=64)
        elemento_ref = _texto(datos, "elemento_ref", obligatorio=True, maximo=200)
        detalle = _estructura_si_hay(curso_ref)
        apertura = servicios.registrar_apertura(
            curso_ref=curso_ref,
            persona_id=persona,
            elemento_ref=elemento_ref,
            leccion_codigo=_texto(datos, "leccion_codigo", maximo=120),
            version_elemento=_texto(datos, "version_elemento", maximo=32),
            tipo=_texto(datos, "tipo", maximo=32),
            elemento_rotulo=_texto(datos, "elemento_rotulo"),
            dispositivo=_texto(datos, "dispositivo", maximo=64),
            persona_rotulo=_texto(datos, "persona_rotulo"),
            curso_rotulo=_texto(datos, "curso_rotulo") or (detalle or {}).get("titulo", ""),
            origen=_texto(datos, "origen", maximo=16) or "student",
            detalle=detalle,
        )
        seccion = ProgresoLeccion.objects.filter(
            curso_ref=curso_ref, persona_id=persona, leccion_codigo=apertura.leccion_codigo
        ).first()
        return Response({
            "id": apertura.id,
            "abierto_en": apertura.abierto_en,
            "estructura_disponible": detalle is not None,
            "progreso_seccion": float(seccion.porcentaje) if seccion else 0.0,
            "progreso_curso": float(servicios.promedio_curso(curso_ref, persona, detalle)),
        }, status=201)


class AperturaCerrarView(VistaExpediente):
    def post(self, request, pk: int):
        apertura = AperturaMaterial.objects.filter(pk=pk).first()
        if not apertura:
            return Response({"detail": "No existe esa apertura."}, status=404)
        pct = (request.data or {}).get("progreso_pct")
        try:
            pct = int(pct) if pct is not None else None
        except (TypeError, ValueError):
            raise ValueError("progreso_pct debe ser entero.")
        apertura = servicios.cerrar_apertura(apertura, pct)
        return Response({"id": apertura.id, "cerrado_en": apertura.cerrado_en, "segundos": apertura.segundos,
                         "progreso_pct": apertura.progreso_pct})


# ---------------------------------------------------------------- intentos

def _intento_o_404(pk):
    intento = Intento.objects.filter(pk=pk).first()
    if not intento:
        raise LookupError("No existe ese intento.")
    return intento


class IntentoStartView(VistaExpediente):
    """Crea o reanuda un intento. Las preguntas se piden a la biblioteca (capacidad
    `evaluacion`) y se entregan sin ningún indicador de corrección."""

    def post(self, request):
        datos = request.data or {}
        evaluacion_ref = _texto(datos, "evaluacion_ref", obligatorio=True, maximo=200)
        persona = _texto(datos, "persona_id", obligatorio=True, maximo=64)
        evaluacion = cliente.evaluacion(evaluacion_ref)   # 501 explicativo sin capacidad
        preguntas = evaluacion.get("preguntas", [])
        curso_ref = _texto(datos, "curso_ref", maximo=200)
        intento, creado = servicios.iniciar_intento(
            evaluacion_ref=evaluacion_ref,
            persona_id=persona,
            preguntas=preguntas,
            curso_ref=curso_ref,
            leccion_codigo=_texto(datos, "leccion_codigo", maximo=120),
            version_observada=str(evaluacion.get("version") or _texto(datos, "version_observada", maximo=32)),
            evaluacion_rotulo=str(evaluacion.get("titulo") or _texto(datos, "evaluacion_rotulo")),
            persona_rotulo=_texto(datos, "persona_rotulo"),
            dispositivo=_texto(datos, "dispositivo", maximo=64),
            curso_rotulo=_texto(datos, "curso_rotulo"),
        )
        respondidas = {r.pregunta_ref: r for r in intento.respuestas.all()}
        salida = servicios.resumen_intento(intento)
        salida["creado"] = creado
        salida["titulo"] = evaluacion.get("titulo")
        salida["tipo"] = evaluacion.get("tipo")
        salida["puede_corregir"] = cliente.CAPACIDAD_COMPROBAR in (evaluacion.get("capacidades") or []) or \
            cliente.CAPACIDAD_COMPROBAR in cliente.capacidades()
        salida["preguntas"] = [
            {
                **p,
                "respondida": p.get("ref") in respondidas,
                "acierta": respondidas[p["ref"]].acierta if p.get("ref") in respondidas else None,
                "retroalimentacion": respondidas[p["ref"]].retroalimentacion_rotulo if p.get("ref") in respondidas else None,
            }
            for p in preguntas
        ]
        return Response(cliente.sin_claves(salida), status=201 if creado else 200)


class IntentoAnswerView(VistaExpediente):
    """Idempotente por (intento, pregunta). Delega la corrección a la biblioteca."""

    def post(self, request):
        datos = request.data or {}
        try:
            intento = _intento_o_404(datos.get("intento_id"))
        except LookupError as error:
            return Response({"detail": str(error)}, status=404)
        pregunta_ref = _texto(datos, "pregunta_ref", obligatorio=True, maximo=200)
        respuesta = str(datos.get("respuesta", "")).strip()
        if intento.estado != Intento.ABIERTO:
            return Response({"detail": "El intento ya está cerrado."}, status=409)
        if not intento.preguntas.filter(pregunta_ref=pregunta_ref).exists():
            return Response({"detail": "Esa pregunta no pertenece al intento."}, status=400)

        pregunta = intento.preguntas.get(pregunta_ref=pregunta_ref)
        veredicto = None
        motivo = None
        if pregunta.corregible:
            try:
                veredicto = cliente.comprobar(intento.evaluacion_ref, pregunta_ref, respuesta)
            except cliente.BibliotecaError as error:
                if error.estado != 501:
                    raise
                motivo = error.detalle  # sin capacidad: se guarda la respuesta y queda pendiente
            except cliente.BibliotecaNoDisponible as error:
                motivo = error.motivo
        else:
            motivo = "Pregunta abierta: la califica el docente con la rúbrica."
        fila = servicios.responder(intento, pregunta_ref, respuesta, veredicto)
        return Response({
            "intento_id": intento.id,
            "pregunta_ref": pregunta_ref,
            "acierta": fila.acierta,
            "retroalimentacion": fila.retroalimentacion_rotulo,
            "corregida": fila.acierta is not None,
            "motivo": motivo,
            "pregunta_actual": intento.pregunta_actual,
        })


class IntentoFinishView(VistaExpediente):
    """Idempotente. Calcula la nota y alimenta el progreso del curso."""

    def post(self, request):
        datos = request.data or {}
        try:
            intento = _intento_o_404(datos.get("intento_id"))
        except LookupError as error:
            return Response({"detail": str(error)}, status=404)
        detalle = _estructura_si_hay(intento.curso_ref)
        try:
            puede_corregir = cliente.CAPACIDAD_COMPROBAR in cliente.capacidades()
        except (cliente.BibliotecaNoDisponible, cliente.BibliotecaError):
            puede_corregir = False   # sin biblioteca no se castiga lo no respondido: queda pendiente
        intento = servicios.finalizar(intento, detalle, sin_responder_es_error=puede_corregir)
        salida = servicios.resumen_intento(intento)
        salida["progreso_curso"] = float(servicios.promedio_curso(intento.curso_ref, intento.persona_id, detalle)) if intento.curso_ref else None
        return Response(salida)


class ResultadosView(VistaExpediente):
    def get(self, request):
        filas = Intento.objects.all().order_by("-iniciado_en")
        for clave in ("curso_ref", "persona_id", "evaluacion_ref"):
            valor = request.query_params.get(clave) or request.query_params.get("persona" if clave == "persona_id" else clave)
            if valor:
                filas = filas.filter(**{clave: valor})
        return Response([servicios.resumen_intento(i) for i in filas[:500]])


class ResultadoDetalleView(VistaExpediente):
    def get(self, request, pk: int):
        try:
            intento = _intento_o_404(pk)
        except LookupError as error:
            return Response({"detail": str(error)}, status=404)
        salida = servicios.resumen_intento(intento)
        respuestas = {r.pregunta_ref: r for r in intento.respuestas.all()}
        salida["preguntas"] = [
            {
                "pregunta_ref": p.pregunta_ref,
                "orden": p.orden,
                "peso": float(p.peso),
                "corregible": p.corregible,
                "respuesta": respuestas[p.pregunta_ref].respuesta if p.pregunta_ref in respuestas else None,
                "acierta": respuestas[p.pregunta_ref].acierta if p.pregunta_ref in respuestas else None,
                "retroalimentacion": respuestas[p.pregunta_ref].retroalimentacion_rotulo if p.pregunta_ref in respuestas else None,
            }
            for p in intento.preguntas.all()
        ]
        return Response(salida)


# ------------------------------------------------------------- consolidado

class ConsolidadoView(VistaExpediente):
    """Lo que ve el docente en OPS Master: por estudiante, progreso, aperturas, tiempo y notas."""

    def get(self, request, curso_ref: str):
        detalle = _estructura_si_hay(curso_ref)
        salida = servicios.consolidado_curso(curso_ref, detalle)
        salida["estructura_disponible"] = detalle is not None
        salida["titulo"] = (detalle or {}).get("titulo")
        return Response(salida)


# ---------------------------------------------------------------- rechazos

class RechazoAdministracionView(APIView):
    """Las rutas de administración de curso se retiraron a propósito. Responden con
    una explicación que nombra al dueño, no con un 404 misterioso (RF-003)."""

    def _rechazar(self, request, *args, **kwargs):
        operacion = f"{request.method} {request.path}"
        servicios.auditar("cliente", "administracion.rechazada", nuevo={"operacion": operacion})
        return Response({
            "error": "administracion_no_permitida",
            "detail": "Los cursos y su contenido se administran en AVACOM Biblioteca. "
                      "Este backend registra únicamente el progreso del estudiante.",
            "dueno": "AVACOM Biblioteca",
            "operacion": operacion,
        }, status=status.HTTP_409_CONFLICT)

    get = post = put = patch = delete = _rechazar
