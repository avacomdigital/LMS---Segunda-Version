"""
Adaptadores de los puertos de MOD-011 sobre Django: los repositorios de `m11_*` (ORM), la cola de salida y la auditoría (bitácora encadenada de MOD-019).

Los casos de uso reciben y devuelven dicts planos; aquí se traducen a filas. Nada se borra (CV-05) salvo lo DERIVADO (`m11_resultado`, `m11_agregado_periodo`), que
se puede reconstruir. `m11_calificacion_version` y `m11_revision` son de SÓLO INSERCIÓN: este archivo no tiene ninguna operación que las actualice o las borre
(una prueba lo comprueba). Las versiones de escala y sus tramos son INMUTABLES: tampoco tienen operación de cambio.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Max

from .. import models as m
from ..dominio import catalogos as cat
from ..dominio import escala as esc
from ..dominio.escala import DefinicionEscala, Tramo

CAMPOS_CALIFICACION = (
    "id", "intento_id", "asignacion_id", "alumno_id", "grupo_id", "nivel_clave", "periodo", "curso_ref", "numero_intento", "puntaje_original", "puntaje_efectivo",
    "puntaje_fuente", "aciertos", "preguntas", "regla_puntuacion", "origen", "evaluador_id", "estado", "version", "escala_version_id", "presentacion",
    "desempeno_docente", "desempeno_motivo", "retroalimentacion", "adaptacion", "publicada_en", "publicada_por", "registrada_en", "actualizada_en",
)
CAMPOS_VERSION = ("calificacion_id", "numero", "tipo", "puntaje_anterior", "puntaje_nuevo", "estado_anterior", "estado_nuevo", "motivo", "actor_id", "en", "solicitud_id", "datos")
CAMPOS_REVISION = ("intento_id", "pregunta_ref", "numero", "tipo", "forma", "puntaje", "puntaje_maximo", "criterios", "comentario", "evidencias", "revisor_id", "revisada_en", "solicitud_id")
CAMPOS_RESULTADO = ("asignacion_id", "alumno_id", "grupo_id", "periodo", "curso_ref", "estado_simple", "estado_calificacion", "calificacion_aplicable_id", "puntaje_aplicable",
                    "politica_intentos", "intentos_total", "intentos_registrados", "cuenta", "publicada", "actualizado_en")
CAMPOS_AGREGADO = ("alumno_id", "grupo_id", "periodo", "curso_ref", "calificaciones", "promedio_simple", "pendientes", "provisionales", "publicadas", "actualizado_en")


def _d(fila, campos) -> dict:
    return {campo: getattr(fila, campo) for campo in campos}


def _filtrado(datos: dict, campos: tuple[str, ...]) -> dict:
    return {k: v for k, v in datos.items() if k in campos}


class CalificacionesDjango:
    def crear(self, datos: dict) -> dict:
        return _d(m.Calificacion.objects.create(**_filtrado(datos, CAMPOS_CALIFICACION)), CAMPOS_CALIFICACION)

    def por_id(self, calificacion_id: str) -> dict | None:
        fila = m.Calificacion.objects.filter(pk=calificacion_id).first()
        return _d(fila, CAMPOS_CALIFICACION) if fila else None

    def por_intento(self, intento_id: str) -> dict | None:
        fila = m.Calificacion.objects.filter(intento_id=intento_id).first()
        return _d(fila, CAMPOS_CALIFICACION) if fila else None

    def de_asignacion(self, asignacion_id: str, alumno_id: str | None = None) -> list[dict]:
        filas = m.Calificacion.objects.filter(asignacion_id=asignacion_id)
        if alumno_id:
            filas = filas.filter(alumno_id=alumno_id)
        return [_d(f, CAMPOS_CALIFICACION) for f in filas.order_by("alumno_id", "numero_intento")]

    def de_grupo(self, grupo_id: str) -> list[dict]:
        return [_d(f, CAMPOS_CALIFICACION) for f in m.Calificacion.objects.filter(grupo_id=grupo_id).order_by("asignacion_id", "alumno_id", "numero_intento")]

    def de_alumno(self, alumno_id: str, grupo_id: str | None = None) -> list[dict]:
        filas = m.Calificacion.objects.filter(alumno_id=alumno_id)
        if grupo_id:
            filas = filas.filter(grupo_id=grupo_id)
        return [_d(f, CAMPOS_CALIFICACION) for f in filas.order_by("registrada_en", "id")]

    def todas(self) -> list[dict]:
        return [_d(f, CAMPOS_CALIFICACION) for f in m.Calificacion.objects.order_by("registrada_en", "id")]

    def actualizar_si_version(self, calificacion_id: str, version_esperada: int, **campos) -> dict | None:
        """Compara y cambia en UNA sentencia (`UPDATE … WHERE id = ? AND version = ?`): la base decide quién se adelantó, no una lectura previa."""
        cambiados = m.Calificacion.objects.filter(pk=calificacion_id, version=version_esperada).update(version=F("version") + 1, **_filtrado(campos, CAMPOS_CALIFICACION))
        return self.por_id(calificacion_id) if cambiados else None


class VersionesDjango:
    """SÓLO INSERCIÓN (BR-070): ni `actualizar` ni `borrar`."""

    def anexar(self, calificacion_id: str, tipo: str, *, actor_id: str, en: int, puntaje_anterior: Decimal | None = None, puntaje_nuevo: Decimal | None = None,
               estado_anterior: str = "", estado_nuevo: str = "", motivo: str = "", solicitud_id: str = "", datos: dict | None = None) -> dict:
        siguiente = (m.VersionCalificacion.objects.filter(calificacion_id=calificacion_id).aggregate(n=Max("numero"))["n"] or 0) + 1
        fila = m.VersionCalificacion.objects.create(
            calificacion_id=calificacion_id, numero=siguiente, tipo=tipo, puntaje_anterior=puntaje_anterior, puntaje_nuevo=puntaje_nuevo, estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo, motivo=motivo, actor_id=actor_id, en=en, solicitud_id=solicitud_id, datos=datos or {})
        return _d(fila, CAMPOS_VERSION)

    def de(self, calificacion_id: str) -> list[dict]:
        return [_d(f, CAMPOS_VERSION) for f in m.VersionCalificacion.objects.filter(calificacion_id=calificacion_id).order_by("numero")]

    def por_solicitud(self, calificacion_id: str, solicitud_id: str) -> dict | None:
        fila = m.VersionCalificacion.objects.filter(calificacion_id=calificacion_id, solicitud_id=solicitud_id).first() if solicitud_id else None
        return _d(fila, CAMPOS_VERSION) if fila else None


class RevisionesDjango:
    """SÓLO INSERCIÓN."""

    def anexar(self, datos: dict) -> dict:
        return _d(m.Revision.objects.create(**_filtrado(datos, CAMPOS_REVISION)), CAMPOS_REVISION)

    def por_solicitud(self, intento_id: str, solicitud_id: str) -> dict | None:
        fila = m.Revision.objects.filter(intento_id=intento_id, solicitud_id=solicitud_id).first() if solicitud_id else None
        return _d(fila, CAMPOS_REVISION) if fila else None

    def de_intento(self, intento_id: str) -> list[dict]:
        return [_d(f, CAMPOS_REVISION) for f in m.Revision.objects.filter(intento_id=intento_id).order_by("revisada_en", "id")]


# ------------------------------------------------------------------------------------------------- escalas

def _a_decimal(texto) -> Decimal:
    return Decimal(str(texto))


def _definicion_de(version: m.EscalaVersion) -> DefinicionEscala:
    return DefinicionEscala(
        tipo=version.escala.tipo, conversion=version.conversion, decimales=version.decimales, redondeo=version.redondeo, valor_min=version.valor_min,
        valor_max=version.valor_max, puntos=tuple((_a_decimal(x), _a_decimal(y)) for x, y in (version.puntos or [])), aprobacion_minima=version.aprobacion_minima,
        tramos=tuple(Tramo(orden=t.orden, clave=t.clave, etiqueta=t.etiqueta, desde=t.desde, hasta=t.hasta, nivel_desempeno=t.nivel_desempeno, aprueba=t.aprueba,
                           descripcion=t.descripcion) for t in version.tramos.order_by("orden")))


def _version_a_dict(version: m.EscalaVersion) -> dict:
    return {"id": version.id, "escala_id": version.escala_id, "codigo": version.escala.codigo, "nombre": version.escala.nombre, "activa": version.escala.activa,
            "pais": version.escala.pais, "jurisdiccion": version.escala.jurisdiccion, "numero": version.numero, "definicion": _definicion_de(version), "huella": version.huella, "nota": version.nota, "vigente_desde": version.vigente_desde,
            "creada_por": version.creada_por}


CAMPOS_ESCALA = ("id", "codigo", "nombre", "tipo", "pais", "jurisdiccion", "plantilla_origen", "activa", "creada_en", "creada_por")


class EscalasDjango:
    """Las versiones de escala y sus tramos son INMUTABLES: sólo se crean."""

    def crear_escala(self, datos: dict) -> dict:
        return _d(m.Escala.objects.create(**_filtrado(datos, CAMPOS_ESCALA)), CAMPOS_ESCALA)

    def por_id(self, escala_id: str) -> dict | None:
        fila = m.Escala.objects.filter(pk=escala_id).first()
        return _d(fila, CAMPOS_ESCALA) if fila else None

    def por_codigo(self, codigo: str) -> dict | None:
        fila = m.Escala.objects.filter(codigo=codigo).first()
        return _d(fila, CAMPOS_ESCALA) if fila else None

    def listar(self) -> list[dict]:
        return [_d(f, CAMPOS_ESCALA) for f in m.Escala.objects.order_by("pais", "codigo")]

    def crear_version(self, escala_id: str, definicion: DefinicionEscala, *, huella: str, nota: str, creada_por: str, vigente_desde: int) -> dict:
        from uuid import uuid4
        siguiente = (m.EscalaVersion.objects.filter(escala_id=escala_id).aggregate(n=Max("numero"))["n"] or 0) + 1
        datos = esc.a_dict(definicion)
        version = m.EscalaVersion.objects.create(
            id=str(uuid4()), escala_id=escala_id, numero=siguiente, conversion=definicion.conversion, valor_min=definicion.valor_min, valor_max=definicion.valor_max,
            puntos=datos["puntos"], decimales=definicion.decimales, redondeo=definicion.redondeo, aprobacion_minima=definicion.aprobacion_minima, nota=nota,
            huella=huella, vigente_desde=vigente_desde, creada_por=creada_por)
        m.EscalaTramo.objects.bulk_create([
            m.EscalaTramo(version=version, orden=t.orden, clave=t.clave, etiqueta=t.etiqueta, desde=t.desde, hasta=t.hasta, nivel_desempeno=t.nivel_desempeno,
                          aprueba=t.aprueba, descripcion=t.descripcion) for t in definicion.tramos])
        return _version_a_dict(m.EscalaVersion.objects.select_related("escala").get(pk=version.pk))

    def version(self, version_id: str) -> dict | None:
        fila = m.EscalaVersion.objects.select_related("escala").filter(pk=version_id).first()
        return _version_a_dict(fila) if fila else None

    def ultima_version(self, escala_id: str) -> dict | None:
        fila = m.EscalaVersion.objects.select_related("escala").filter(escala_id=escala_id).order_by("-numero").first()
        return _version_a_dict(fila) if fila else None

    def versiones_de(self, escala_id: str) -> list[dict]:
        return [_version_a_dict(f) for f in m.EscalaVersion.objects.select_related("escala").filter(escala_id=escala_id).order_by("numero")]


# ---------------------------------------------------------------------------------- configuración institucional

def _nivel(fila: m.ConfigNivel) -> dict:
    return {"nivel_clave": fila.nivel_clave, "modo": fila.modo, "escala_version_id": fila.escala_version_id, "version": fila.version,
            "actualizada_en": fila.actualizada_en, "actualizada_por": fila.actualizada_por, "modo_desde": fila.modo_desde}


class NivelesDjango:
    def get(self, nivel_clave: str) -> dict | None:
        fila = m.ConfigNivel.objects.filter(pk=nivel_clave).first()
        return _nivel(fila) if fila else None

    def todos(self) -> list[dict]:
        return [_nivel(f) for f in m.ConfigNivel.objects.order_by("nivel_clave")]

    def guardar(self, nivel_clave: str, modo: str, escala_version_id: str | None, por: str, ahora: int, version_esperada: int | None) -> dict | None:
        fila = m.ConfigNivel.objects.filter(pk=nivel_clave).first()
        if fila is None:
            try:
                with transaction.atomic():
                    fila = m.ConfigNivel.objects.create(nivel_clave=nivel_clave, modo=modo, escala_version_id=escala_version_id, version=1, actualizada_en=ahora, actualizada_por=por,
                                                        modo_desde=ahora)
            except IntegrityError:               # dos administradores crean el mismo nivel a la vez: gana el primero
                return None
            return _nivel(fila)
        if version_esperada is not None and fila.version != version_esperada:
            return None
        # `modo_desde` es desde cuándo rige el MODO: cambiar sólo la escala de un nivel que ya calificaba no lo mueve (y por eso no deja sin registrar lo que MOD-010
        # calificó antes y el libro aún no había leído).
        cambiados = m.ConfigNivel.objects.filter(pk=nivel_clave, version=fila.version).update(
            modo=modo, escala_version_id=escala_version_id, version=F("version") + 1, actualizada_en=ahora, actualizada_por=por,
            modo_desde=ahora if modo != fila.modo else fila.modo_desde)
        return _nivel(m.ConfigNivel.objects.get(pk=nivel_clave)) if cambiados else None


class PoliticaDjango:
    def get(self) -> dict:
        fila = m.Politica.objects.filter(pk="institucional").first()
        if fila is None:
            return {"id": "institucional", "pais": "", "jurisdiccion": "", "institucion": "", "politica_intentos": cat.POLITICA_PROVISIONAL, "ponderaciones": {},
                    "version": 0, "actualizada_en": None, "actualizada_por": ""}
        return _d(fila, ("id", "pais", "jurisdiccion", "institucion", "politica_intentos", "ponderaciones", "version", "actualizada_en", "actualizada_por"))

    def guardar(self, datos: dict, por: str, ahora: int) -> dict:
        previa = m.Politica.objects.filter(pk="institucional").first()
        valores = {"pais": datos["pais"], "jurisdiccion": datos["jurisdiccion"], "institucion": datos["institucion"], "politica_intentos": datos["politica_intentos"],
                   "ponderaciones": datos["ponderaciones"], "actualizada_en": ahora, "actualizada_por": por}
        if previa is None:
            m.Politica.objects.create(id="institucional", version=1, **valores)
        else:
            m.Politica.objects.filter(pk="institucional").update(version=F("version") + 1, **valores)
        return self.get()


class ClasificacionesDjango:
    CAMPOS = ("asignacion_id", "tipo_evaluacion", "afecta_oficial", "objetivos", "actualizada_en", "actualizada_por")

    def get(self, asignacion_id: str) -> dict | None:
        fila = m.Clasificacion.objects.filter(pk=asignacion_id).first()
        return _d(fila, self.CAMPOS) if fila else None

    def de(self, asignacion_ids: list[str]) -> dict[str, dict]:
        return {f.asignacion_id: _d(f, self.CAMPOS) for f in m.Clasificacion.objects.filter(asignacion_id__in=asignacion_ids)}

    def guardar(self, asignacion_id: str, tipo_evaluacion: str, afecta_oficial: bool, objetivos: list, por: str, ahora: int) -> dict:
        fila, _ = m.Clasificacion.objects.update_or_create(asignacion_id=asignacion_id, defaults={
            "tipo_evaluacion": tipo_evaluacion, "afecta_oficial": afecta_oficial, "objetivos": objetivos, "actualizada_en": ahora, "actualizada_por": por})
        return _d(fila, self.CAMPOS)


# ------------------------------------------------------------------------------------------------ lo derivado

class ResultadosDjango:
    def get(self, asignacion_id: str, alumno_id: str) -> dict | None:
        fila = m.ResultadoAsignacion.objects.filter(asignacion_id=asignacion_id, alumno_id=alumno_id).first()
        return _d(fila, CAMPOS_RESULTADO) if fila else None

    def guardar(self, datos: dict) -> dict:
        clave = {"asignacion_id": datos["asignacion_id"], "alumno_id": datos["alumno_id"]}
        fila, _ = m.ResultadoAsignacion.objects.update_or_create(**clave, defaults={k: v for k, v in _filtrado(datos, CAMPOS_RESULTADO).items() if k not in clave})
        return _d(fila, CAMPOS_RESULTADO)

    def de_grupo(self, grupo_id: str) -> list[dict]:
        return [_d(f, CAMPOS_RESULTADO) for f in m.ResultadoAsignacion.objects.filter(grupo_id=grupo_id)]

    def de_asignacion(self, asignacion_id: str) -> list[dict]:
        return [_d(f, CAMPOS_RESULTADO) for f in m.ResultadoAsignacion.objects.filter(asignacion_id=asignacion_id)]

    def de_alumno(self, alumno_id: str, grupo_id: str | None = None, periodo: str | None = None, curso_ref: str | None = None) -> list[dict]:
        filas = m.ResultadoAsignacion.objects.filter(alumno_id=alumno_id)
        if grupo_id is not None:
            filas = filas.filter(grupo_id=grupo_id)
        if periodo is not None:
            filas = filas.filter(periodo=periodo)
        if curso_ref is not None:
            filas = filas.filter(curso_ref=curso_ref)
        return [_d(f, CAMPOS_RESULTADO) for f in filas]

    def borrar_todo(self) -> int:
        return m.ResultadoAsignacion.objects.all().delete()[0]


class AgregadosDjango:
    def get(self, alumno_id: str, grupo_id: str, periodo: str, curso_ref: str) -> dict | None:
        fila = m.AgregadoPeriodo.objects.filter(alumno_id=alumno_id, grupo_id=grupo_id, periodo=periodo, curso_ref=curso_ref).first()
        return _d(fila, CAMPOS_AGREGADO) if fila else None

    def guardar(self, datos: dict) -> dict:
        clave = {k: datos[k] for k in ("alumno_id", "grupo_id", "periodo", "curso_ref")}
        fila, _ = m.AgregadoPeriodo.objects.update_or_create(**clave, defaults={k: v for k, v in _filtrado(datos, CAMPOS_AGREGADO).items() if k not in clave})
        return _d(fila, CAMPOS_AGREGADO)

    def de_grupo(self, grupo_id: str, periodo: str | None = None) -> list[dict]:
        filas = m.AgregadoPeriodo.objects.filter(grupo_id=grupo_id)
        if periodo:
            filas = filas.filter(periodo=periodo)
        return [_d(f, CAMPOS_AGREGADO) for f in filas.order_by("curso_ref", "alumno_id")]

    def de_alumno(self, alumno_id: str) -> list[dict]:
        return [_d(f, CAMPOS_AGREGADO) for f in m.AgregadoPeriodo.objects.filter(alumno_id=alumno_id).order_by("periodo", "curso_ref")]

    def borrar_todo(self) -> int:
        return m.AgregadoPeriodo.objects.all().delete()[0]


class MarcasDjango:
    def get(self, consumidor: str) -> int:
        fila = m.MarcaConsumidor.objects.filter(pk=consumidor).first()
        return fila.ultima_secuencia if fila else 0

    def estado(self, consumidor: str) -> dict:
        """La marca y el fallo que la retiene: `{secuencia, fallo_secuencia, fallos}`."""
        fila = m.MarcaConsumidor.objects.filter(pk=consumidor).first()
        return {"secuencia": fila.ultima_secuencia, "fallo_secuencia": fila.secuencia_fallida, "fallos": fila.fallos_seguidos} if fila \
            else {"secuencia": 0, "fallo_secuencia": 0, "fallos": 0}

    def guardar(self, consumidor: str, fuente: str, secuencia: int, ahora: int, *, fallo_secuencia: int = 0, fallos: int = 0) -> None:
        m.MarcaConsumidor.objects.update_or_create(consumidor=consumidor, defaults={
            "fuente": fuente, "ultima_secuencia": secuencia, "actualizada_en": ahora, "secuencia_fallida": fallo_secuencia, "fallos_seguidos": fallos})


class OutboxDjango:
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None:
        if tipo_evento not in cat.EVENTOS:
            raise ValueError(f"Evento fuera del catálogo de MOD-011: {tipo_evento}")
        m.EventoSalida.objects.create(agregado_tipo=agregado_tipo, agregado_id=str(agregado_id), tipo_evento=tipo_evento, carga=carga)


class AuditoriaGradebook:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`, app `audit`) dentro de la transacción del caso de uso."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or cat.SISTEMA, accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)

    def denegada(self, actor: str, permiso: str | None, metodo: str, ruta: str, codigo: str, extra: dict | None = None) -> None:
        """TST-069 / TST-072: el INTENTO de modificar (o exportar) sin autorización deja un asiento propio, con quién, qué permiso pedía y sobre qué ruta. Va
        FUERA de la transacción del caso de uso, que ya se revirtió: un intento denegado también es un hecho."""
        from audit import servicios as auditoria
        from audit.dominio import asiento as dom

        auditoria.anexar(actor or cat.SISTEMA, cat.A_DENEGADA, "m11_calificacion", "", resultado=dom.RESULTADO_DENEGADO,
                         nuevo={"permiso_solicitado": permiso, "metodo": metodo, "ruta": ruta, "codigo": codigo, **(extra or {})})
