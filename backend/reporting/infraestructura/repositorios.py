"""
Adaptadores de los puertos de MOD-013 sobre Django: los repositorios de `m13_*` (ORM), la cola de salida y la auditoría (bitácora encadenada de MOD-019).

Los casos de uso reciben y devuelven dicts planos; aquí se traducen a filas. Lo DERIVADO (clase, avance, estado de los equipos, marcas) se puede borrar y reconstruir; lo PROPIO
(configuración, exportaciones, recientes, cola de salida) no. Reporting nunca escribe en tablas de otro módulo: este archivo sólo toca `m13_*` (una prueba lo comprueba).
"""
from __future__ import annotations

import hashlib
import json

from django.db.models import F, Q

from .. import models as m
from ..dominio import catalogos as cat

CAMPOS_CLASE = ("sesion_id", "grupo_id", "profesor_id", "periodo", "nivel_clave", "curso_ref", "leccion_ref", "iniciada_en", "finalizada_en", "duracion_ms", "participantes",
                "actividades", "equipos", "promedio_participacion", "promedio_aciertos", "senales", "estado_integracion", "corte_en", "huella")
CAMPOS_CLASE_ALUMNO = ("alumno_id", "estado", "dispositivo_id", "ingreso_en", "salida_en", "presente_ms", "actividades_recibidas", "actividades_entregadas", "calificadas", "aciertos",
                       "puntos", "puntos_maximos", "porcentaje_participacion", "porcentaje_aciertos", "entregas_por_cola")
CAMPOS_AVANCE_GRUPO = ("grupo_id", "periodo", "nivel_clave", "modo", "escala", "alumnos", "clases", "evaluaciones", "estudios", "en_atencion", "promedio_participacion",
                       "promedio_aciertos", "estado_integracion", "motivos_integracion", "desactualizado", "desactualizado_en", "corte_en")
CAMPOS_AVANCE_ALUMNO = ("grupo_id", "alumno_id", "clases_total", "clases_asistidas", "actividades_recibidas", "actividades_entregadas", "porcentaje_aciertos", "evaluaciones_total",
                        "evaluaciones_presentadas", "evaluaciones_sin_presentar", "estudios_total", "estudios_completados", "estudios_vencidos", "avance_estudio", "atencion",
                        "ultima_actividad_en", "detalle", "corte_en")
CAMPOS_EXPORTACION = ("id", "tipo", "parametros", "formato", "actor_id", "actor_rol", "nominal", "umbral_aplicado", "filas", "bytes_total", "huella", "nombre_archivo", "corte_en",
                      "integracion", "destino_autorizado", "razon_codigo", "estado", "intentos", "destino_tipo", "huella_verificada", "autorizada_en", "expira_en", "confirmada_en")
CAMPOS_RECIENTE = ("actor_id", "tipo", "parametros", "ultima_vez_en", "veces", "ultima_exportacion_en")
MAX_RECIENTES_GUARDADAS = 30


def _d(fila, campos) -> dict:
    return {campo: getattr(fila, campo) for campo in campos}


def _filtrado(datos: dict, campos: tuple[str, ...]) -> dict:
    return {k: v for k, v in datos.items() if k in campos}


# ------------------------------------------------------------------------------------------------------------------ lo derivado

class ClasesDjango:
    def guardar(self, clase: dict, alumnos: list[dict]) -> bool:
        previa = m.Clase.objects.filter(pk=clase["sesion_id"]).values_list("huella", flat=True).first()
        if previa is not None and previa == clase["huella"]:
            return False                                        # lo recalculado es idéntico: no se escribe nada
        m.Clase.objects.update_or_create(sesion_id=clase["sesion_id"], defaults={k: v for k, v in _filtrado(clase, CAMPOS_CLASE).items() if k != "sesion_id"})
        m.ClaseAlumno.objects.filter(sesion_id=clase["sesion_id"]).delete()
        m.ClaseAlumno.objects.bulk_create([m.ClaseAlumno(sesion_id=clase["sesion_id"], **_filtrado(a, CAMPOS_CLASE_ALUMNO)) for a in alumnos])
        return True

    def get(self, sesion_id: str) -> dict | None:
        fila = m.Clase.objects.filter(pk=sesion_id).first() if sesion_id else None
        return _d(fila, CAMPOS_CLASE) if fila else None

    def alumnos(self, sesion_id: str) -> list[dict]:
        return [_d(f, CAMPOS_CLASE_ALUMNO) for f in m.ClaseAlumno.objects.filter(sesion_id=sesion_id).order_by("ingreso_en", "alumno_id")]

    def alumnos_de_clases(self, sesion_ids: list[str]) -> dict[str, dict[str, dict]]:
        salida: dict[str, dict[str, dict]] = {}
        if not sesion_ids:
            return salida
        for f in m.ClaseAlumno.objects.filter(sesion_id__in=sesion_ids):
            salida.setdefault(f.sesion_id, {})[f.alumno_id] = _d(f, CAMPOS_CLASE_ALUMNO)
        return salida

    def listar(self, *, grupo_ids: list[str] | None = None, profesor_id: str = "", desde: int | None = None, hasta: int | None = None, limite: int = 50) -> list[dict]:
        filas = m.Clase.objects.all()
        if grupo_ids is not None:
            filtro = Q(grupo_id__in=grupo_ids)
            if profesor_id:
                filtro |= Q(profesor_id=profesor_id)
            filas = filas.filter(filtro)
        if desde is not None:
            filas = filas.filter(finalizada_en__gte=desde)
        if hasta is not None:
            filas = filas.filter(finalizada_en__lte=hasta)
        return [_d(f, CAMPOS_CLASE) for f in filas.order_by("-finalizada_en", "sesion_id")[:limite]]

    def de_grupo(self, grupo_id: str) -> list[dict]:
        return [_d(f, CAMPOS_CLASE) for f in m.Clase.objects.filter(grupo_id=grupo_id).order_by("finalizada_en", "sesion_id")]

    def filas_de_alumno(self, alumno_id: str, sesion_ids: list[str]) -> list[dict]:
        if not sesion_ids:
            return []
        return [_d(f, CAMPOS_CLASE_ALUMNO) for f in m.ClaseAlumno.objects.filter(alumno_id=alumno_id, sesion_id__in=sesion_ids)]

    def contar(self) -> int:
        return m.Clase.objects.count()

    def con_senales(self) -> list[dict]:
        return [_d(f, CAMPOS_CLASE) for f in m.Clase.objects.filter(estado_integracion="incompleta")]

    def eliminar(self, sesion_id: str) -> None:
        m.ClaseAlumno.objects.filter(sesion_id=sesion_id).delete()
        m.Clase.objects.filter(pk=sesion_id).delete()


class AvancesDjango:
    def grupo(self, grupo_id: str) -> dict | None:
        fila = m.AvanceGrupo.objects.filter(pk=grupo_id).first() if grupo_id else None
        return _d(fila, CAMPOS_AVANCE_GRUPO) if fila else None

    def guardar_grupo(self, datos: dict) -> None:
        m.AvanceGrupo.objects.update_or_create(grupo_id=datos["grupo_id"], defaults={k: v for k, v in _filtrado(datos, CAMPOS_AVANCE_GRUPO).items() if k != "grupo_id"})

    def marcar_sucio(self, grupo_id: str, ahora: int) -> None:
        if not m.AvanceGrupo.objects.filter(pk=grupo_id).update(desactualizado=True, desactualizado_en=ahora):
            m.AvanceGrupo.objects.get_or_create(grupo_id=grupo_id, defaults={"desactualizado": True, "desactualizado_en": ahora})

    def marcar_todos_sucios(self, grupo_ids: list[str], ahora: int) -> None:
        ids = sorted(set(grupo_ids))
        if not ids:
            return
        m.AvanceGrupo.objects.filter(pk__in=ids).update(desactualizado=True, desactualizado_en=ahora)
        existentes = set(m.AvanceGrupo.objects.filter(pk__in=ids).values_list("grupo_id", flat=True))
        m.AvanceGrupo.objects.bulk_create([m.AvanceGrupo(grupo_id=g, desactualizado=True, desactualizado_en=ahora) for g in ids if g not in existentes])

    def sucios(self) -> list[str]:
        return list(m.AvanceGrupo.objects.filter(desactualizado=True).order_by("grupo_id").values_list("grupo_id", flat=True))

    def alumnos(self, grupo_id: str) -> list[dict]:
        return [_d(f, CAMPOS_AVANCE_ALUMNO) for f in m.AvanceAlumno.objects.filter(grupo_id=grupo_id).order_by("alumno_id")]

    def alumno(self, grupo_id: str, alumno_id: str) -> dict | None:
        fila = m.AvanceAlumno.objects.filter(grupo_id=grupo_id, alumno_id=alumno_id).first()
        return _d(fila, CAMPOS_AVANCE_ALUMNO) if fila else None

    def de_alumno(self, alumno_id: str) -> list[dict]:
        return [_d(f, CAMPOS_AVANCE_ALUMNO) for f in m.AvanceAlumno.objects.filter(alumno_id=alumno_id).order_by("grupo_id")]

    def guardar_alumnos(self, grupo_id: str, filas: list[dict]) -> None:
        m.AvanceAlumno.objects.filter(grupo_id=grupo_id).delete()
        m.AvanceAlumno.objects.bulk_create([m.AvanceAlumno(**_filtrado({**f, "grupo_id": grupo_id}, CAMPOS_AVANCE_ALUMNO)) for f in filas])

    def eliminar_grupo(self, grupo_id: str) -> None:
        m.AvanceAlumno.objects.filter(grupo_id=grupo_id).delete()
        m.AvanceGrupo.objects.filter(pk=grupo_id).delete()


class EstadoDeEquiposDjango:
    def fijar(self, alumno_id: str, dispositivo_id: str, cola_pendiente: int, ahora: int) -> None:
        m.EstadoDispositivo.objects.update_or_create(alumno_id=alumno_id, dispositivo_id=dispositivo_id, defaults={"cola_pendiente": cola_pendiente, "avisada_en": ahora})

    def pendientes_de(self, alumno_ids: list[str]) -> list[dict]:
        if not alumno_ids:
            return []
        return [{"alumno_id": f.alumno_id, "dispositivo_id": f.dispositivo_id, "cola_pendiente": f.cola_pendiente, "avisada_en": f.avisada_en}
                for f in m.EstadoDispositivo.objects.filter(alumno_id__in=alumno_ids, cola_pendiente__gt=0).order_by("dispositivo_id", "alumno_id")]


class MarcasDjango:
    def get(self, fuente: str) -> int:
        fila = m.MarcaConsumidor.objects.filter(pk=fuente).first()
        return fila.ultima_secuencia if fila else 0

    def estado(self, fuente: str) -> dict:
        """La marca y el fallo que la retiene: `{secuencia, fallo_secuencia, fallos}`."""
        fila = m.MarcaConsumidor.objects.filter(pk=fuente).first()
        return {"secuencia": fila.ultima_secuencia, "fallo_secuencia": fila.secuencia_fallida, "fallos": fila.fallos_seguidos} if fila else {"secuencia": 0, "fallo_secuencia": 0, "fallos": 0}

    def guardar(self, fuente: str, secuencia: int, ahora: int, *, fallo_secuencia: int = 0, fallos: int = 0) -> None:
        m.MarcaConsumidor.objects.update_or_create(fuente=fuente, defaults={"ultima_secuencia": secuencia, "actualizada_en": ahora, "secuencia_fallida": fallo_secuencia, "fallos_seguidos": fallos})


class EstadoDjango:
    ID = "reportes"

    def get(self) -> dict:
        fila = m.EstadoProyeccion.objects.filter(pk=self.ID).first()
        if fila is None:
            return {"reconstruyendose": False, "reconstruccion_iniciada_en": None, "reconstruida_en": None, "reconstruida_por": "", "actualizada_en": None, "ultimo_error": ""}
        return _d(fila, ("reconstruyendose", "reconstruccion_iniciada_en", "reconstruida_en", "reconstruida_por", "actualizada_en", "ultimo_error"))

    def empezar_reconstruccion(self, ahora: int, por: str) -> None:
        m.EstadoProyeccion.objects.update_or_create(id=self.ID, defaults={"reconstruyendose": True, "reconstruccion_iniciada_en": ahora, "reconstruida_por": por, "ultimo_error": ""})

    def terminar_reconstruccion(self, ahora: int, por: str, error: str = "") -> None:
        valores = {"reconstruyendose": False, "reconstruida_por": por, "ultimo_error": error[:300]}
        if not error:
            valores["reconstruida_en"] = ahora
        m.EstadoProyeccion.objects.update_or_create(id=self.ID, defaults=valores)

    def anotar_actualizacion(self, ahora: int) -> None:
        m.EstadoProyeccion.objects.update_or_create(id=self.ID, defaults={"actualizada_en": ahora})


class ProyeccionesDjango:
    def borrar_derivadas(self) -> dict[str, int]:
        """BR-007: TODA tabla derivada. Nunca toca `m13_config`, `m13_exportacion`, `m13_reciente` ni `m13_evento_salida`."""
        cuentas = {}
        for modelo in (m.ClaseAlumno, m.Clase, m.AvanceAlumno, m.AvanceGrupo, m.EstadoDispositivo, m.MarcaConsumidor, m.EstadoProyeccion):
            cuentas[modelo._meta.db_table] = modelo.objects.count()
            modelo.objects.all().delete()
        return cuentas


# ------------------------------------------------------------------------------------------------------------------ lo propio

class ConfigDjango:
    ID = "nodo"
    DE_FABRICA = {"umbral_privacidad": False, "extraibles_permitidos": True, "exigir_razon": False, "plantilla_boletin": cat.PLANTILLA_AUTO, "periodos_boletin": [],
                  "leyenda_boletin": "", "version": 0, "actualizada_en": None, "actualizada_por": ""}

    def get(self) -> dict:
        fila = m.Config.objects.filter(pk=self.ID).first()
        return _d(fila, tuple(self.DE_FABRICA)) if fila else dict(self.DE_FABRICA)

    def guardar(self, datos: dict, por: str, ahora: int, version_esperada: int | None) -> dict | None:
        actual = self.get()
        if version_esperada is not None and version_esperada != actual["version"]:
            return None
        valores = {"umbral_privacidad": bool(datos["umbral_privacidad"]), "extraibles_permitidos": bool(datos["extraibles_permitidos"]), "exigir_razon": bool(datos["exigir_razon"]),
                   "plantilla_boletin": str(datos.get("plantilla_boletin") or cat.PLANTILLA_AUTO), "periodos_boletin": list(datos.get("periodos_boletin") or []),
                   "leyenda_boletin": str(datos.get("leyenda_boletin") or ""), "actualizada_en": ahora, "actualizada_por": por}
        if actual["version"] == 0:
            m.Config.objects.create(id=self.ID, version=1, **valores)
        elif not m.Config.objects.filter(pk=self.ID, version=actual["version"]).update(version=F("version") + 1, **valores):
            return None                                         # otro escritor se adelantó: compara y cambia en UNA sentencia
        return self.get()


class ExportacionesDjango:
    def crear(self, datos: dict) -> dict:
        return _d(m.Exportacion.objects.create(**_filtrado(datos, CAMPOS_EXPORTACION)), CAMPOS_EXPORTACION)

    def por_id(self, exportacion_id: str) -> dict | None:
        fila = m.Exportacion.objects.filter(pk=exportacion_id).first() if exportacion_id else None
        return _d(fila, CAMPOS_EXPORTACION) if fila else None

    def anotar_intento_fallido(self, exportacion_id: str, intento: dict) -> dict | None:
        fila = m.Exportacion.objects.filter(pk=exportacion_id, estado=cat.EXP_AUTORIZADA).first()
        if fila is None:
            return None
        fila.intentos = [*fila.intentos, intento]
        fila.save(update_fields=["intentos"])
        return _d(fila, CAMPOS_EXPORTACION)

    def entregar(self, exportacion_id: str, *, destino_tipo: str, huella_verificada: str, ahora: int, intento: dict) -> dict | None:
        cambiadas = m.Exportacion.objects.filter(pk=exportacion_id, estado=cat.EXP_AUTORIZADA).update(
            estado=cat.EXP_ENTREGADA, destino_tipo=destino_tipo, huella_verificada=huella_verificada, confirmada_en=ahora)
        if not cambiadas:
            return None
        fila = m.Exportacion.objects.get(pk=exportacion_id)
        fila.intentos = [*fila.intentos, intento]
        fila.save(update_fields=["intentos"])
        return _d(fila, CAMPOS_EXPORTACION)

    def caducar(self, exportacion_id: str, ahora: int) -> dict | None:
        if not m.Exportacion.objects.filter(pk=exportacion_id, estado=cat.EXP_AUTORIZADA, expira_en__lte=ahora).update(estado=cat.EXP_CADUCADA):
            return None
        return self.por_id(exportacion_id)

    def vencidas(self, ahora: int) -> list[dict]:
        return [_d(f, CAMPOS_EXPORTACION) for f in m.Exportacion.objects.filter(estado=cat.EXP_AUTORIZADA, expira_en__lte=ahora).order_by("expira_en", "id")]

    def de_actor(self, actor_id: str, limite: int = 20) -> list[dict]:
        return [_d(f, CAMPOS_EXPORTACION) for f in m.Exportacion.objects.filter(actor_id=actor_id).order_by("-autorizada_en", "id")[:limite]]


class RecientesDjango:
    @staticmethod
    def _clave(tipo: str, parametros: dict) -> str:
        return hashlib.sha1(json.dumps({"t": tipo, "p": parametros}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:40]

    def registrar(self, actor_id: str, tipo: str, parametros: dict, ahora: int) -> None:
        clave = self._clave(tipo, parametros)
        fila, creada = m.Reciente.objects.get_or_create(actor_id=actor_id, clave=clave, defaults={"tipo": tipo, "parametros": parametros, "ultima_vez_en": ahora, "veces": 1})
        if not creada:
            m.Reciente.objects.filter(pk=fila.pk).update(veces=F("veces") + 1, ultima_vez_en=ahora)
        sobrantes = list(m.Reciente.objects.filter(actor_id=actor_id).order_by("-ultima_vez_en", "-id").values_list("pk", flat=True)[MAX_RECIENTES_GUARDADAS:])
        if sobrantes:
            m.Reciente.objects.filter(pk__in=sobrantes).delete()

    def marcar_exportado(self, actor_id: str, tipo: str, parametros: dict, ahora: int) -> None:
        m.Reciente.objects.filter(actor_id=actor_id, clave=self._clave(tipo, parametros)).update(ultima_exportacion_en=ahora)

    def de(self, actor_id: str, limite: int) -> list[dict]:
        return [_d(f, CAMPOS_RECIENTE) for f in m.Reciente.objects.filter(actor_id=actor_id).order_by("-ultima_vez_en", "-id")[:limite]]


class OutboxDjango:
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None:
        if tipo_evento not in cat.EVENTOS or tipo_evento in cat.EVENTOS_RESERVADOS:
            raise ValueError(f"Evento fuera del catálogo de MOD-013 (o reservado y sin emitir): {tipo_evento}")
        m.EventoSalida.objects.create(agregado_tipo=agregado_tipo, agregado_id=str(agregado_id)[:64], tipo_evento=tipo_evento, carga=carga)


class AuditoriaReporting:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`, app `audit`) dentro de la transacción del caso de uso. Nunca lleva la ruta de un archivo, el nombre de una
    persona ni el contenido de un reporte."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or cat.SISTEMA, accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)

    def denegada(self, actor: str, permiso: str | None, metodo: str, ruta: str, codigo: str, extra: dict | None = None) -> None:
        """TST-069: el INTENTO de leer o exportar datos académicos sin poder hacerlo (también el rol técnico) deja un asiento propio. Va FUERA de la transacción del caso de uso,
        que ya se revirtió: un intento denegado también es un hecho."""
        from audit import servicios as auditoria
        from audit.dominio import asiento as dom

        auditoria.anexar(actor or cat.SISTEMA, cat.A_ACCESO_DENEGADO, "m13_reporte", "", resultado=dom.RESULTADO_DENEGADO,
                         nuevo={"permiso_solicitado": permiso, "metodo": metodo, "ruta": ruta, "codigo": codigo, **(extra or {})})
