"""
Adaptadores del ORM para las tablas `m15_*`. Las ÚNICAS escrituras del módulo (crear, actualizar y el borrado de la purga) están aquí y operan sobre `nodo.models` (R-09). `publicar` es
UN `INSERT` con SQL directo en la transacción de quien llama (R-08: el ORM añadía ≈1,5 ms por fila); el contador del AUTOINCREMENT se lee y se sube en `sqlite_sequence` (P-02, P-05, P-12).
"""
from __future__ import annotations

import json

from django.db import connection
from django.db.models import Max

from .. import models as m
from ..dominio import catalogos as cat
from ..dominio.corte import Corte
from ..dominio.reintentos import SIN_REINTENTO, EstadoDeReintento
from ..dominio.sobre import Sobre

CAMPOS_EVENTO = ("secuencia", "evento_id", "tipo", "version", "modulo", "creado_en", "agregado_tipo", "agregado_id", "actor", "dispositivo_id", "correlacion_id", "clase",
                 "sensibilidad", "carga", "catalogado", "carga_omitida")
CAMPOS_SIN_CARGA = tuple(c for c in CAMPOS_EVENTO if c != "carga")


def _d(fila, campos) -> dict:
    return {campo: getattr(fila, campo) for campo in campos}


class EventosDjango:
    TABLA = "m15_evento"

    SQL_INSERTAR = ("INSERT INTO m15_evento (evento_id, tipo, version, modulo, creado_en, agregado_tipo, agregado_id, actor, dispositivo_id, correlacion_id, clase, sensibilidad, "
                    "carga, catalogado, carga_omitida) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")

    def insertar(self, sobre: Sobre) -> int:
        """UN INSERT (R-08). La carga va como el JSON que escribe `JSONField` (así el ORM la lee igual)."""
        with connection.cursor() as cursor:
            cursor.execute(self.SQL_INSERTAR, [sobre.evento_id, sobre.tipo, int(sobre.version), sobre.modulo, int(sobre.creado_en), sobre.agregado_tipo, sobre.agregado_id, sobre.actor,
                                               sobre.dispositivo_id, sobre.correlacion_id, sobre.clase, sobre.sensibilidad, json.dumps(sobre.carga, ensure_ascii=False, separators=(",", ":")),
                                               1 if sobre.catalogado else 0, 1 if sobre.carga_omitida else 0])
            return int(cursor.lastrowid)

    def leer(self, modulo: str, desde: int, limite: int, tipos: tuple[str, ...] | None) -> tuple[list[dict], int]:
        """Como el `eventos_desde` de cada módulo: `(eventos, hasta_donde_se_miró)`, con secuencia MAYOR a `desde`, en orden. Lectura pura."""
        base = m.Evento.objects.filter(modulo=modulo, secuencia__gt=int(desde))
        ultimo = base.aggregate(u=Max("secuencia"))["u"]
        if ultimo is None:
            return [], int(desde)
        filas = base.filter(secuencia__lte=ultimo)
        if tipos is not None:
            filas = filas.filter(tipo__in=list(tipos))
        filas = list(filas.order_by("secuencia")[: int(limite)])
        hasta = int(filas[-1].secuencia) if len(filas) >= int(limite) else int(ultimo)
        return [_d(f, CAMPOS_EVENTO) for f in filas], hasta

    def por_secuencia(self, secuencia: int) -> dict | None:
        fila = m.Evento.objects.filter(pk=int(secuencia)).first()
        return _d(fila, CAMPOS_EVENTO) if fila else None

    def metadatos(self, desde: int, limite: int, modulo: str | None = None) -> list[dict]:
        """Sólo el sobre, NUNCA la carga (R-13): lo que una pantalla técnica puede ver."""
        filas = m.Evento.objects.filter(secuencia__gt=int(desde))
        if modulo:
            filas = filas.filter(modulo=modulo)
        return [_d(f, CAMPOS_SIN_CARGA) for f in filas.order_by("secuencia")[: int(limite)]]

    def ultima_secuencia(self, modulo: str | None = None) -> int:
        filas = m.Evento.objects.all() if modulo is None else m.Evento.objects.filter(modulo=modulo)
        return int(filas.aggregate(u=Max("secuencia"))["u"] or 0)

    def contar(self, modulo: str | None = None) -> int:
        filas = m.Evento.objects.all() if modulo is None else m.Evento.objects.filter(modulo=modulo)
        return int(filas.count())

    def contador(self) -> int:
        with connection.cursor() as cursor:
            cursor.execute("SELECT seq FROM sqlite_sequence WHERE name = %s", [self.TABLA])
            fila = cursor.fetchone()
        return int(fila[0]) if fila else 0

    def asegurar_contador(self, minimo: int) -> int:
        """Sube el contador del AUTOINCREMENT a `minimo` si está por debajo (nunca lo baja). Va en la transacción abierta: con el corte o con el arranque."""
        minimo = int(minimo)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO sqlite_sequence(name, seq) SELECT %s, %s WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = %s)", [self.TABLA, minimo, self.TABLA])
            cursor.execute("UPDATE sqlite_sequence SET seq = MAX(seq, %s) WHERE name = %s", [minimo, self.TABLA])
        return self.contador()

    def primeros(self, limite: int) -> list[dict]:
        return [_d(f, ("secuencia", "creado_en", "clase", "tipo", "modulo")) for f in m.Evento.objects.order_by("secuencia")[: int(limite)]]

    def borrar(self, secuencias: list[int]) -> int:
        """El ÚNICO borrado de la cola (P-08, purga). BR-019 ya decidió que son contiguas desde la más baja."""
        if not secuencias:
            return 0
        borrados, _ = m.Evento.objects.filter(secuencia__in=[int(s) for s in secuencias]).delete()
        return int(borrados)

    def tamano_medio_bytes(self, muestra: int = 500) -> int | None:
        """Para estimar el crecimiento sin purga (P-08): el largo medio de la carga de los últimos `muestra` eventos."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT AVG(LENGTH(carga)) FROM (SELECT carga FROM m15_evento ORDER BY secuencia DESC LIMIT %s)", [int(muestra)])
            fila = cursor.fetchone()
        return int(fila[0]) if fila and fila[0] is not None else None


class CortesDjango:
    def get(self, modulo: str) -> Corte | None:
        fila = m.Corte.objects.filter(pk=modulo).first()
        return Corte(fila.modulo, int(fila.ultima_legada), int(fila.cortado_en)) if fila else None

    def crear(self, corte: Corte, version_contrato: int) -> None:
        m.Corte.objects.create(modulo=corte.modulo, ultima_legada=corte.ultima_legada, cortado_en=corte.cortado_en, version_contrato=version_contrato)

    def todos(self) -> list[Corte]:
        return [Corte(f.modulo, int(f.ultima_legada), int(f.cortado_en)) for f in m.Corte.objects.order_by("cortado_en", "modulo")]


class ModulosDjango:
    CAMPOS = ("nombre", "version_modulo", "version_datos", "version_contrato", "produce", "consume", "compatible", "detalle", "registrado_en", "actualizado_en")

    def registrar(self, nombre, version_modulo, version_datos, version_contrato, produce, consume, compatible, detalle, ahora) -> dict:
        fila, creado = m.Modulo.objects.update_or_create(nombre=nombre, defaults={
            "version_modulo": version_modulo, "version_datos": version_datos, "version_contrato": version_contrato, "produce": list(produce), "consume": list(consume),
            "compatible": compatible, "detalle": detalle, "actualizado_en": ahora}, create_defaults={
            "version_modulo": version_modulo, "version_datos": version_datos, "version_contrato": version_contrato, "produce": list(produce), "consume": list(consume),
            "compatible": compatible, "detalle": detalle, "registrado_en": ahora, "actualizado_en": ahora})
        return _d(fila, self.CAMPOS)

    def get(self, nombre: str) -> dict | None:
        fila = m.Modulo.objects.filter(pk=nombre).first()
        return _d(fila, self.CAMPOS) if fila else None

    def todos(self) -> list[dict]:
        return [_d(f, self.CAMPOS) for f in m.Modulo.objects.order_by("nombre")]


class ConsumidoresDjango:
    CAMPOS = ("nombre", "modulo", "fuentes", "tipos", "version_contrato", "limite_rezago", "estado", "activo", "registrado_en", "actualizado_en")

    def registrar(self, nombre, modulo, fuentes, tipos, version_contrato, limite_rezago, ahora) -> dict:
        valores = {"modulo": modulo, "fuentes": list(fuentes), "tipos": list(tipos), "version_contrato": int(version_contrato), "limite_rezago": limite_rezago, "activo": True,
                   "actualizado_en": ahora}
        fila, _ = m.Consumidor.objects.update_or_create(nombre=nombre, defaults=valores, create_defaults={**valores, "registrado_en": ahora})
        return _d(fila, self.CAMPOS)

    def get(self, nombre: str) -> dict | None:
        fila = m.Consumidor.objects.filter(pk=nombre).first()
        return _d(fila, self.CAMPOS) if fila else None

    def todos(self, activos: bool = True) -> list[dict]:
        filas = m.Consumidor.objects.order_by("nombre")
        if activos:
            filas = filas.filter(activo=True)
        return [_d(f, self.CAMPOS) for f in filas]

    def desregistrar(self, nombre: str, ahora: int) -> bool:
        return bool(m.Consumidor.objects.filter(pk=nombre, activo=True).update(activo=False, actualizado_en=ahora))

    def actualizar_estado(self, nombre: str, estado: str, ahora: int) -> bool:
        return bool(m.Consumidor.objects.filter(pk=nombre).exclude(estado=estado).update(estado=estado, actualizado_en=ahora))


class MarcasDjango:
    CAMPOS = ("consumidor", "fuente", "ultima_secuencia", "actualizada_en", "fallo_secuencia", "fallos", "proximo_intento_en", "ultimo_error", "reconstruyendose")

    @staticmethod
    def _dict(f) -> dict:
        return {"consumidor": f.consumidor, "fuente": f.fuente, "marca": int(f.ultima_secuencia), "actualizada_en": int(f.actualizada_en), "fallo_secuencia": int(f.fallo_secuencia),
                "fallos": int(f.fallos), "proximo_intento_en": int(f.proximo_intento_en), "ultimo_error": f.ultimo_error, "reconstruyendose": bool(f.reconstruyendose)}

    def estado(self, consumidor: str, fuente: str) -> tuple[int, EstadoDeReintento, bool]:
        f = m.MarcaLectura.objects.filter(consumidor=consumidor, fuente=fuente).first()
        if f is None:
            return 0, SIN_REINTENTO, False
        reintento = EstadoDeReintento(int(f.fallo_secuencia), int(f.fallos), int(f.proximo_intento_en), f.ultimo_error) if f.fallo_secuencia else SIN_REINTENTO
        return int(f.ultima_secuencia), reintento, bool(f.reconstruyendose)

    def guardar(self, consumidor: str, fuente: str, marca: int, reintento: EstadoDeReintento, ahora: int, reconstruyendose: bool | None = None) -> None:
        valores = {"ultima_secuencia": int(marca), "actualizada_en": int(ahora), "fallo_secuencia": int(reintento.secuencia), "fallos": int(reintento.intentos),
                   "proximo_intento_en": int(reintento.proximo_en), "ultimo_error": (reintento.ultimo_error or "")[: cat.MAX_ERROR]}
        if reconstruyendose is not None:
            valores["reconstruyendose"] = bool(reconstruyendose)
        m.MarcaLectura.objects.update_or_create(consumidor=consumidor, fuente=fuente, defaults=valores)

    def de_consumidor(self, consumidor: str) -> list[dict]:
        return [self._dict(f) for f in m.MarcaLectura.objects.filter(consumidor=consumidor).order_by("fuente")]

    def todas(self) -> list[dict]:
        activos = {c.nombre: c.activo for c in m.Consumidor.objects.all()}
        return [{**self._dict(f), "activo": activos.get(f.consumidor, False)} for f in m.MarcaLectura.objects.order_by("consumidor", "fuente")]

    def reiniciar(self, consumidor: str, fuente: str | None, ahora: int) -> int:
        filas = m.MarcaLectura.objects.filter(consumidor=consumidor)
        if fuente:
            filas = filas.filter(fuente=fuente)
        return int(filas.update(ultima_secuencia=0, actualizada_en=ahora, fallo_secuencia=0, fallos=0, proximo_intento_en=0, ultimo_error="", reconstruyendose=True))


class ProblemasDjango:
    CAMPOS = ("id", "consumidor", "fuente", "secuencia", "evento_id", "tipo", "intentos", "intentos_reproceso", "ultimo_error", "estado", "apartado_en", "resuelto_en", "resuelto_por")

    def apartar(self, consumidor: str, fuente: str, evento: dict, intentos: int, error: str, ahora: int) -> dict:
        fila = m.Problema.objects.create(consumidor=consumidor, fuente=fuente, secuencia=int(evento["secuencia"]), evento_id=str(evento.get("evento_id") or "")[:64],
                                         tipo=str(evento.get("tipo") or "")[: cat.MAX_TIPO], intentos=int(intentos), ultimo_error=(error or "")[: cat.MAX_ERROR], apartado_en=int(ahora))
        return _d(fila, self.CAMPOS)

    def get(self, problema_id: int) -> dict | None:
        fila = m.Problema.objects.filter(pk=int(problema_id)).first()
        return _d(fila, self.CAMPOS) if fila else None

    def listar(self, consumidor: str | None = None, estado: str | None = None, limite: int = 100) -> list[dict]:
        filas = m.Problema.objects.all()
        if consumidor:
            filas = filas.filter(consumidor=consumidor)
        if estado:
            filas = filas.filter(estado=estado)
        return [_d(f, self.CAMPOS) for f in filas.order_by("-apartado_en", "-id")[: int(limite)]]

    def contar(self, consumidor: str | None = None, estado: str | None = None) -> int:
        filas = m.Problema.objects.all()
        if consumidor:
            filas = filas.filter(consumidor=consumidor)
        if estado:
            filas = filas.filter(estado=estado)
        return int(filas.count())

    def resolver(self, problema_id: int, estado: str, ahora: int, por: str, error: str = "") -> dict | None:
        m.Problema.objects.filter(pk=int(problema_id)).update(estado=estado, resuelto_en=int(ahora), resuelto_por=(por or "")[: cat.MAX_ACTOR], ultimo_error=(error or "")[: cat.MAX_ERROR])
        return self.get(problema_id)

    def fallo_de_reproceso(self, problema_id: int, error: str, ahora: int) -> dict | None:
        fila = m.Problema.objects.filter(pk=int(problema_id)).first()
        if fila is None:
            return None
        fila.intentos_reproceso = int(fila.intentos_reproceso) + 1
        fila.ultimo_error = (error or "")[: cat.MAX_ERROR]
        fila.save(update_fields=["intentos_reproceso", "ultimo_error"])
        return _d(fila, self.CAMPOS)


class ArranquesDjango:
    CAMPOS = ("id", "iniciado_en", "cerrado_en", "pid", "version", "secuencia_al_iniciar", "ancla_secuencia", "restauracion", "contador", "detalle")

    def abrir(self, ahora, version, pid, secuencia_al_iniciar, ancla_secuencia, restauracion, contador, detalle) -> dict:
        fila = m.Arranque.objects.create(iniciado_en=int(ahora), pid=int(pid), version=str(version or "")[:32], secuencia_al_iniciar=int(secuencia_al_iniciar),
                                         ancla_secuencia=int(ancla_secuencia), restauracion=bool(restauracion), contador=int(contador), detalle=detalle)
        return _d(fila, self.CAMPOS)

    def cerrar(self, arranque_id: int, ahora: int) -> None:
        m.Arranque.objects.filter(pk=int(arranque_id), cerrado_en__isnull=True).update(cerrado_en=int(ahora))

    def ultimo(self) -> dict | None:
        fila = m.Arranque.objects.order_by("-id").first()
        return _d(fila, self.CAMPOS) if fila else None

    def anteriores_sin_cerrar(self, arranque_id: int) -> list[dict]:
        return [_d(f, self.CAMPOS) for f in m.Arranque.objects.filter(cerrado_en__isnull=True, id__lt=int(arranque_id)).order_by("id")]


class MarcaAltaDjango:
    def valor(self) -> int:
        fila = m.MarcaAlta.objects.filter(pk=1).first()
        return int(fila.valor) if fila else 0

    def subir(self, valor: int, ahora: int) -> None:
        fila, creada = m.MarcaAlta.objects.get_or_create(pk=1, defaults={"valor": int(valor), "actualizada_en": int(ahora)})
        if not creada and int(valor) > int(fila.valor):
            m.MarcaAlta.objects.filter(pk=1).update(valor=int(valor), actualizada_en=int(ahora))


class AuditoriaNodo:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`, app `audit`) dentro de la transacción en curso. Nunca lleva la carga de un evento."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or cat.SISTEMA, accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)

    def denegada(self, actor: str, permiso: str | None, metodo: str, ruta: str, codigo: str, extra: dict | None = None) -> None:
        """El INTENTO de operar la cola sin poder hacerlo deja un asiento propio, fuera de la transacción del caso de uso (que ya se revirtió)."""
        from audit import servicios as auditoria
        from audit.dominio import asiento as dom

        auditoria.anexar(actor or cat.SISTEMA, cat.A_ACCESO_DENEGADO, "m15_evento", "", resultado=dom.RESULTADO_DENEGADO,
                         nuevo={"permiso_solicitado": permiso, "metodo": metodo, "ruta": ruta, "codigo": codigo, **(extra or {})})
