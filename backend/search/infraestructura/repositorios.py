"""
Los adaptadores de almacenamiento de Search sobre Django y SQLite: el índice de texto completo (FTS5), las marcas de lectura, el estado del índice, los sinónimos, la cola
de salida y la bitácora.

El SQL del índice es PARAMETRIZADO de punta a punta: lo único que se arma con texto son los `?` de las listas `IN (…)`, y su cantidad sale de un `len()`. Ni la consulta del
usuario ni un identificador se concatenan jamás; la expresión `MATCH` llega como un parámetro más (y ya viene normalizada y entre comillas desde el dominio).
"""
from __future__ import annotations

from django.db import connection
from django.db.models import Count

from .. import models as m
from ..aplicacion.puertos import Regla
from ..dominio import catalogos as cat
from ..dominio import texto
from ..dominio.documento import Documento

_PESOS = ", ".join(str(float(cat.PESOS[c])) for c in ("titulo", "palabras", "descripcion", "contexto"))
_COLUMNAS = "d.tipo, d.entidad_id, d.subtipo, d.titulo, d.descripcion, d.palabras, d.contexto, d.grupo_id, d.profesor_id, d.curso_ref, d.estado, d.referencia"


def _marcas(n: int) -> str:
    return ", ".join(["%s"] * n)


class IndiceFts5:
    """`m21_documento` (la proyección) + `m21_documento_fts` (las raíces para el texto completo). Escribe SIEMPRE las dos juntas."""

    # ------------------------------------------------------------------------------------------------ consulta
    def buscar(self, expresion: str, reglas: list[Regla], *, grupo_ids: list[str] | None, curso_refs: list[str] | None, tope: int) -> list[dict]:
        parametros: list = [expresion]
        permitidas: list[str] = []
        for regla in reglas:
            if regla.alcance == cat.ORGANIZACION:
                permitidas.append("d.tipo = %s")
                parametros.append(regla.tipo)
                continue
            partes: list[str] = []
            adicionales: list = []
            if regla.grupos:
                partes.append(f"d.grupo_id IN ({_marcas(len(regla.grupos))})")
                adicionales += list(regla.grupos)
            if regla.persona_id:
                partes.append("(d.grupo_id = '' AND d.profesor_id = %s)")
                adicionales.append(regla.persona_id)
            if not partes:
                continue                                       # un alcance de grupos sin ningún grupo ni dueño no puede ver nada de este tipo
            permitidas.append(f"(d.tipo = %s AND ({' OR '.join(partes)}))")
            parametros.append(regla.tipo)
            parametros += adicionales
        if not permitidas:
            return []
        sql = (f"SELECT {_COLUMNAS}, bm25(m21_documento_fts, {_PESOS}) AS bm25 FROM m21_documento_fts JOIN m21_documento d ON d.id = m21_documento_fts.rowid "
               f"WHERE m21_documento_fts MATCH %s AND ({' OR '.join(permitidas)})")
        if grupo_ids is not None:
            sql += f" AND d.grupo_id IN ({_marcas(len(grupo_ids))})"
            parametros += list(grupo_ids)
        if curso_refs is not None:
            sql += f" AND d.curso_ref IN ({_marcas(len(curso_refs))})"
            parametros += list(curso_refs)
        sql += " ORDER BY bm25, d.id LIMIT %s"
        parametros.append(int(tope))
        with connection.cursor() as cursor:
            cursor.execute(sql, parametros)
            columnas = [c[0] for c in cursor.description]
            filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        return filas

    # ------------------------------------------------------------------------------------------------ escritura
    def guardar(self, documento: Documento, ahora: int) -> str:
        huella = documento.huella()
        fila = m.Documento.objects.filter(tipo=documento.tipo, entidad_id=documento.entidad_id).first()
        if fila is not None and fila.huella == huella:
            return "igual"
        campos = dict(subtipo=documento.subtipo, titulo=documento.titulo[:300], descripcion=documento.descripcion, palabras=documento.palabras,
                      contexto=documento.contexto[:400], grupo_id=documento.grupo_id, profesor_id=documento.profesor_id, curso_ref=documento.curso_ref,
                      estado=documento.estado, referencia=documento.referencia, huella=huella, origen_actualizado_en=documento.origen_actualizado_en, indexado_en=ahora)
        if fila is None:
            fila = m.Documento.objects.create(tipo=documento.tipo, entidad_id=documento.entidad_id, **campos)
            resultado = "nuevo"
        else:
            for nombre, valor in campos.items():
                setattr(fila, nombre, valor)
            fila.save()
            resultado = "actualizado"
        self._texto_completo(fila.id, documento)
        return resultado

    @staticmethod
    def _texto_completo(rowid: int, documento: Documento) -> None:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM m21_documento_fts WHERE rowid = %s", [rowid])
            cursor.execute("INSERT INTO m21_documento_fts(rowid, titulo, palabras, descripcion, contexto) VALUES (%s, %s, %s, %s, %s)",
                           [rowid, texto.para_el_indice(documento.titulo), texto.para_el_indice(documento.palabras),
                            texto.para_el_indice(documento.descripcion), texto.para_el_indice(f"{documento.contexto} {documento.etiquetas}")])

    def quitar(self, tipo: str, entidad_id: str) -> bool:
        return self.quitar_ids(tipo, [entidad_id]) > 0

    def quitar_ids(self, tipo: str, entidad_ids: list[str]) -> int:
        if not entidad_ids:
            return 0
        ids = list(m.Documento.objects.filter(tipo=tipo, entidad_id__in=entidad_ids).values_list("id", flat=True))
        if not ids:
            return 0
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM m21_documento_fts WHERE rowid IN ({_marcas(len(ids))})", ids)
        m.Documento.objects.filter(id__in=ids).delete()
        return len(ids)

    def vaciar(self) -> int:
        n = m.Documento.objects.count()
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM m21_documento_fts")
        m.Documento.objects.all().delete()
        return n

    def contar(self) -> dict[str, int]:
        filas = m.Documento.objects.values("tipo").annotate(n=Count("id"))
        cuenta = {t: 0 for t in cat.TIPOS_LOCALES}
        cuenta.update({f["tipo"]: f["n"] for f in filas})
        return cuenta

    def ids_de(self, tipo: str) -> set[str]:
        return set(m.Documento.objects.filter(tipo=tipo).values_list("entidad_id", flat=True))


class MarcasDjango:
    def estado(self, fuente: str) -> dict:
        fila = m.MarcaDeLectura.objects.filter(pk=fuente).first()
        if fila is None:
            return {"secuencia": 0, "fallo_secuencia": 0, "fallos": 0, "actualizada_en": None}
        return {"secuencia": fila.secuencia, "fallo_secuencia": fila.fallo_secuencia, "fallos": fila.fallos, "actualizada_en": fila.actualizada_en}

    def guardar(self, fuente: str, secuencia: int, ahora: int, *, fallo_secuencia: int = 0, fallos: int = 0) -> None:
        m.MarcaDeLectura.objects.update_or_create(fuente=fuente, defaults={"secuencia": secuencia, "fallo_secuencia": fallo_secuencia, "fallos": fallos,
                                                                           "actualizada_en": ahora})

    def todas(self) -> dict[str, dict]:
        return {f.fuente: {"secuencia": f.secuencia, "fallo_secuencia": f.fallo_secuencia, "fallos": f.fallos, "actualizada_en": f.actualizada_en}
                for f in m.MarcaDeLectura.objects.all()}


class EstadoDjango:
    def leer(self) -> dict:
        fila = m.EstadoIndice.objects.filter(pk="indice").first()
        if fila is None:
            return {"estado": cat.CONSTRUYENDOSE, "construido_en": None, "sincronizado_en": None, "error": "", "error_en": None, "reconstruccion_desde": None}
        return {"estado": fila.estado, "construido_en": fila.construido_en, "sincronizado_en": fila.sincronizado_en, "error": fila.error, "error_en": fila.error_en,
                "reconstruccion_desde": fila.reconstruccion_desde}

    def escribir(self, **campos) -> None:
        m.EstadoIndice.objects.update_or_create(pk="indice", defaults=campos)


class SinonimosDjango:
    def grupos(self) -> list[list[str]]:
        return [list(f.palabras) for f in m.Sinonimo.objects.order_by("id")]

    def mapa(self) -> dict[str, list[str]]:
        mapa: dict[str, list[str]] = {}
        for grupo in self.grupos():
            for palabra in grupo:
                if " " in palabra:
                    continue                                   # una frase no es la clave de una palabra; sí puede ser equivalente de otra
                clave = texto.raiz(palabra)
                existentes = mapa.setdefault(clave, [])
                existentes += [otra for otra in grupo if otra != palabra and otra not in existentes]
        return mapa

    def reemplazar(self, grupos: list[list[str]], ahora: int, actor_id: str) -> None:
        m.Sinonimo.objects.all().delete()
        m.Sinonimo.objects.bulk_create([m.Sinonimo(palabras=g, actualizado_en=ahora, actualizado_por=actor_id[:64]) for g in grupos])


class OutboxDjango:
    _AGREGADO = {cat.EV_ENTIDAD_INDEXADA: "Documento", cat.EV_ENTRADAS_PURGADAS: "Documento", cat.EV_REINDEXACION_INCREMENTAL: "Fuente",
                 cat.EV_INDICE_RECONSTRUIDO: "Indice"}

    def publicar(self, tipo_evento: str, agregado_id: str, carga: dict) -> None:
        if tipo_evento not in cat.EVENTOS_QUE_SE_EMITEN:
            raise ValueError(f"Evento que MOD-021 no emite todavía o fuera de su catálogo: {tipo_evento}")
        m.EventoSalida.objects.create(agregado_tipo=self._AGREGADO[tipo_evento], agregado_id=str(agregado_id)[:80], tipo_evento=tipo_evento, carga=carga)


class AuditoriaBusqueda:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`, app `audit`) dentro de la transacción del caso de uso."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or cat.SISTEMA, accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)

    def denegada(self, actor: str, permiso: str | None, objeto: dict) -> None:
        from audit import servicios as auditoria
        from audit.dominio import asiento as dom

        auditoria.anexar(actor or cat.SISTEMA, cat.A_APERTURA_DENEGADA, "m21_documento", str(objeto.get("entity_id") or ""), resultado=dom.RESULTADO_DENEGADO,
                         nuevo={"permiso_solicitado": permiso, **{k: v for k, v in objeto.items() if k in ("entity_type", "entity_id")}})
