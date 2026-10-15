"""
La exportación a archivo (FUN-146 · CAP-084), pensada para quien lleva el reporte en una memoria USB a otra computadora, sin internet y sin teclado:

  AlcanceDeExportacion   ANTES de confirmar: qué se va a guardar (cuántos alumnos, qué trae, hasta qué instante), si lleva nombres de personas y qué destinos permite el colegio
  AutorizarExportacion   1.er tiempo: valida permiso, alcance y política, GENERA el archivo (xlsx o csv), lo deja registrado como «autorizada» (sin confirmar) y lo entrega con su huella
  ConfirmarExportacion   2.º tiempo: el cliente dice qué pasó al escribir (guardado o fallido), en qué tipo de destino y la huella que verificó releyendo; sólo entonces queda «entregada»
  CaducarVencidas        una exportación que nadie confirma caduca a los 15 minutos y NO cuenta como entregada

Por qué en dos tiempos (así la bitácora no miente): quien exporta escribe el archivo en SU equipo, el nodo no puede saber si llegó a la memoria. El asiento «exportado» y el evento
`reporte.exportado.v1` salen del segundo tiempo, con la huella que el cliente comprobó. Un intento fallido se anota y NO cierra la exportación: el profesor puede elegir otro destino
sin generar de nuevo. El nodo nunca guarda el archivo, su contenido, la ruta donde quedó ni un nombre de persona en la bitácora.

Qué se exporta es EXACTAMENTE lo que se ve: el archivo sale del mismo reporte que la pantalla (`armar`), con su cabecera de corte e integración (BR-083), el umbral de privacidad aplicado
(BR-086) y las mismas cifras (`dominio/documento.py`). Todo se genera en el nodo (BR-084).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ..dominio import archivo as arch
from ..dominio import catalogos as cat
from ..dominio import documento as doc
from ..dominio import texto as tx
from ..dominio.errores import (
    CapacidadReservada,
    DatosInvalidos,
    DestinoNoPermitido,
    ExportacionCaducada,
    ExportacionYaConfirmada,
    HuellaDistinta,
    MotivoRequerido,
    NoEncontrado,
    SinPermiso,
)
from .base import _CasoDeUso, exigir_nodo_instalado, nuevo_id
from .consumidor import ConsumirEventos
from .puertos import Actor, ArchivoGenerado
from .reportes import ReporteDeAlumno, ReporteDeClase, ReporteDeGrupo, ReporteDeUso

log = logging.getLogger("avacom.reporting.exportar")

_HUELLA = re.compile(r"^[0-9a-f]{64}$")
_INCLUYE = {
    cat.CLASE: ["participación", "aciertos"],
    cat.GRUPO: ["asistencia", "participación", "aciertos", "evaluaciones", "estudio"],
    cat.ALUMNO: ["asistencia", "participación", "aciertos", "evaluaciones y calificaciones", "estudio"],
    cat.USO: ["uso de equipos"],
}
ADVERTENCIA_NOMINAL = "El archivo incluirá nombres de alumnos. Una vez fuera de este equipo, el colegio ya no controla quién lo abre."
ADVERTENCIA_AGREGADA = "Sin datos de personas."


def _frase(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def _formato(cuerpo: dict) -> str:
    formato = str(cuerpo.get("formato") or cat.XLSX).lower()
    if formato not in cat.FORMATOS:
        raise DatosInvalidos(f"El formato debe ser uno de: {', '.join(cat.FORMATOS)}.", formato=formato[:10], formatos=list(cat.FORMATOS))
    return formato


class _Exportador(_CasoDeUso):
    def _al_dia(self) -> None:
        """Como en cada reporte: antes de armar, se pone al día con lo que los módulos ya publicaron. Si no se puede (por ejemplo «database is locked» en plena clase), la exportación
        sigue con lo que hay y el archivo dice su corte con la antigüedad que tenga: no se vuelve un error 500."""
        if not self.s.config.sincronizar_al_consultar:
            return
        try:
            ConsumirEventos(self.s).hasta_vaciar(paginas=5)
        except Exception:   # noqa: BLE001
            log.exception("Reportes no pudo ponerse al día antes de exportar")

    # ------------------------------------------------------------------------------------------------------------- armar el reporte
    def _armar(self, actor: Actor, descriptor: Any) -> tuple[str, dict, dict]:
        """`(tipo, parámetros, reporte)`: se arma con los MISMOS casos de uso que la pantalla —con su permiso y su alcance—, así que no se puede exportar lo que no se puede ver."""
        if not isinstance(descriptor, dict):
            raise DatosInvalidos("Falta `reporte`: qué reporte se exporta ({tipo, …}).")
        tipo = str(descriptor.get("tipo") or "")
        if tipo in cat.TIPOS_RESERVADOS:
            raise CapacidadReservada(f"El reporte de {tipo} llega en una versión posterior: todavía no se puede exportar.", tipo=tipo)
        if tipo not in cat.TIPOS:
            raise DatosInvalidos(f"El tipo de reporte debe ser uno de: {', '.join(cat.TIPOS)}.", tipo=tipo[:20], tipos=list(cat.TIPOS))
        consulta = {k: v for k, v in descriptor.items() if k != "tipo" and v not in (None, "")}
        nodo = ReporteDeGrupo._parametros_de_nodo(consulta)
        if tipo == cat.CLASE:
            sesion_id = str(consulta.get("sesion_id") or "")
            return tipo, {"sesion_id": sesion_id}, ReporteDeClase(self.s).armar(actor, sesion_id)
        if tipo == cat.GRUPO:
            grupo_id = str(consulta.get("grupo_id") or "")
            return tipo, {"grupo_id": grupo_id, **nodo}, ReporteDeGrupo(self.s).armar(actor, grupo_id, consulta)
        if tipo == cat.ALUMNO:
            alumno_id = str(consulta.get("alumno_id") or "")
            return tipo, {"alumno_id": alumno_id, **({"grupo_id": consulta["grupo_id"]} if consulta.get("grupo_id") else {}), **nodo}, ReporteDeAlumno(self.s).armar(actor, alumno_id, consulta)
        reporte = ReporteDeUso(self.s).armar(actor, consulta)
        return tipo, {"desde": reporte["periodo"]["desde"], "hasta": reporte["periodo"]["hasta"], **({"grupo_id": consulta["grupo_id"]} if consulta.get("grupo_id") else {})}, reporte

    def _exigir_exportar(self, actor: Actor, tipo: str, reporte: dict) -> None:
        """`reports.export` sobre los grupos del reporte (un profesor exporta lo de SUS grupos; reportes y administración, toda la organización)."""
        if tipo == cat.CLASE:
            grupos = [g["id"] for g in [reporte["clase"].get("grupo")] if g]
        elif tipo == cat.GRUPO:
            grupos = [reporte["grupo"]["id"]]
        elif tipo == cat.ALUMNO:
            grupos = [g["grupo"]["id"] for g in reporte["grupos"]]
        else:
            grupos = []
        if not grupos:
            self.s.autorizacion.exigir(actor, cat.P_EXPORT, organizacion=(tipo == cat.USO))
        for g in grupos:
            self.s.autorizacion.exigir(actor, cat.P_EXPORT, grupo_id=g)

    # ----------------------------------------------------------------------------------------------------------------- el documento
    def _documento(self, tipo: str, reporte: dict, ahora: int) -> tuple[doc.Documento, dict]:
        local = self.s.reloj.a_local
        ctx = {"titulo": reporte["titulo"], "generado_por": reporte["generado_por"]["rotulo"] or reporte["generado_por"]["id"] or "—",
               "generado_el": tx.fecha_larga(local(ahora)), "corte_texto": tx.fecha_larga(local(reporte["corte"]["en"])) + " (hora del nodo)",
               "version_nodo": self.s.config.version_del_nodo, "fecha": lambda ms: tx.fecha_larga(local(ms))}
        documento = doc.de_reporte(tipo, reporte, ctx)
        return documento, ctx

    def _nombre(self, tipo: str, documento: doc.Documento, reporte: dict, formato: str) -> str:
        return arch.nombre_del_reporte(tipo, documento.sujeto, self.s.reloj.a_local(reporte["corte"]["en"]), cat.EXTENSION_DE[formato])

    @staticmethod
    def _salida(e: dict) -> dict:
        return {"id": e["id"], "tipo": e["tipo"], "formato": e["formato"], "estado": e["estado"], "nominal": e["nominal"], "umbral_aplicado": e["umbral_aplicado"], "filas": e["filas"],
                "bytes": e["bytes_total"], "huella": e["huella"], "nombre_archivo": e["nombre_archivo"], "corte_en": e["corte_en"], "autorizada_en": e["autorizada_en"],
                "expira_en": e["expira_en"], "confirmada_en": e["confirmada_en"], "destino_autorizado": e["destino_autorizado"], "destino_tipo": e["destino_tipo"] or None,
                "razon_codigo": e["razon_codigo"] or None, "intentos": e["intentos"]}


# =================================================================================================================== antes de confirmar

class AlcanceDeExportacion(_Exportador):
    """El alcance declarado ANTES de confirmar (el Maestro: «con su alcance declarado antes de confirmar»): lo que el nodo va a entregar, dicho en lenguaje llano. No genera nada."""

    def ejecutar(self, actor: Actor, cuerpo: dict) -> dict:
        formato = _formato(cuerpo)
        self._al_dia()
        tipo, params, reporte = self._armar(actor, cuerpo.get("reporte"))
        self._exigir_exportar(actor, tipo, reporte)
        ahora = self.s.reloj.ahora_ms()
        documento, _ = self._documento(tipo, reporte, ahora)
        with self.s.uow(lectura=True) as uow:
            config = uow.config.get()
        nominal = bool(reporte["nominal"])
        if tipo == cat.CLASE:
            g = reporte["clase"].get("grupo") or {}
            alumnos, que = reporte["clase"]["participantes"], f"el reporte de la clase de {g.get('codigo') or g.get('nombre') or 'una clase sin grupo'}"
        elif tipo == cat.GRUPO:
            alumnos, que = reporte["totales"]["alumnos"], f"el reporte del grupo {reporte['grupo']['codigo'] or reporte['grupo']['nombre']}"
        elif tipo == cat.ALUMNO:
            alumnos = 1
            que = "el reporte de un alumno del grupo " + " y ".join(g["grupo"]["codigo"] or g["grupo"]["nombre"] for g in reporte["grupos"])
        else:
            alumnos, que = 0, "el reporte de uso de equipos"
        detalle = []
        if alumnos:
            detalle.append(f"{alumnos} {'alumno' if alumnos == 1 else 'alumnos'}")
        detalle.append(_frase(_INCLUYE[tipo]))
        detalle.append(reporte["corte"]["texto"].replace("Datos al", "datos al"))
        return {
            "tipo": tipo, "formato": formato, "titulo": reporte["titulo"], "alumnos": alumnos, "filas": documento.filas, "incluye": _INCLUYE[tipo], "nominal": nominal,
            "umbral_aplicado": bool(reporte["privacidad"]["aplicada"]), "texto_alcance": f"Vas a guardar {que} ({', '.join(detalle)})",
            "advertencia": ADVERTENCIA_NOMINAL if nominal else ADVERTENCIA_AGREGADA, "corte": reporte["corte"], "privacidad": reporte["privacidad"],
            "nombre_sugerido": self._nombre(tipo, documento, reporte, formato), "formatos": list(cat.FORMATOS),
            "politica": {"extraibles_permitidos": config["extraibles_permitidos"], "exigir_razon": config["exigir_razon"],
                         "razones": [{"codigo": c, "etiqueta": e} for c, e in cat.RAZONES_DE_EXPORTACION.items()]}, "servidor_en": ahora}


# =================================================================================================================== 1.er tiempo

class AutorizarExportacion(_Exportador):
    def ejecutar(self, actor: Actor, cuerpo: dict) -> dict:
        """Devuelve `{exportacion, archivo}`: el registro de la exportación (autorizada, sin confirmar) y el `ArchivoGenerado` con su contenido (quien lo recibe lo cierra)."""
        formato = _formato(cuerpo)
        destino = str(cuerpo.get("destino_tipo") or "")
        if destino not in cat.DESTINOS:
            raise DatosInvalidos(f"`destino_tipo` debe ser uno de: {', '.join(cat.DESTINOS)}.", destino_tipo=destino[:20], destinos=list(cat.DESTINOS))
        razon = str(cuerpo.get("razon_codigo") or "")
        if razon and razon not in cat.RAZONES_DE_EXPORTACION:
            raise DatosInvalidos("La razón debe ser una de la lista.", razon_codigo=razon[:40], razones=list(cat.RAZONES_DE_EXPORTACION))
        self._al_dia()
        tipo, params, reporte = self._armar(actor, cuerpo.get("reporte"))
        self._exigir_exportar(actor, tipo, reporte)
        with self.s.uow(lectura=True) as uow:
            exigir_nodo_instalado(uow)
            config = uow.config.get()
        if not arch.destino_permitido(destino, config["extraibles_permitidos"]):
            raise DestinoNoPermitido("El administrador del colegio no permite guardar reportes en memorias extraíbles. Elige una carpeta de este equipo o de la red.",
                                     permiso=cat.P_EXPORT, destino_tipo=destino)
        if config["exigir_razon"] and not razon:
            raise MotivoRequerido("Elige para qué vas a guardar este reporte.", razones=[{"codigo": c, "etiqueta": e} for c, e in cat.RAZONES_DE_EXPORTACION.items()])
        ahora = self.s.reloj.ahora_ms()
        documento, _ = self._documento(tipo, reporte, ahora)
        if documento.filas > cat.MAX_FILAS_EXPORTABLES:
            raise DatosInvalidos("Este reporte es demasiado grande para exportarlo de una vez: acota el periodo o el grupo.", filas=documento.filas)
        archivo: ArchivoGenerado = self.s.escritor.escribir(documento, formato)
        try:
            nombre = self._nombre(tipo, documento, reporte, formato)
            with self.s.uow() as uow:
                fila = uow.exportaciones.crear({
                    "id": nuevo_id(), "tipo": tipo, "parametros": params, "formato": formato, "actor_id": actor.id, "actor_rol": actor.rol, "nominal": bool(reporte["nominal"]),
                    "umbral_aplicado": bool(reporte["privacidad"]["aplicada"]), "filas": documento.filas, "bytes_total": archivo.bytes_total, "huella": archivo.huella,
                    "nombre_archivo": nombre, "corte_en": reporte["corte"]["en"], "integracion": reporte["corte"]["integracion"], "destino_autorizado": destino,
                    "razon_codigo": razon, "estado": cat.EXP_AUTORIZADA, "intentos": [], "autorizada_en": ahora, "expira_en": ahora + self.s.config.ttl_exportacion_ms})
                if actor.id:
                    uow.recientes.registrar(actor.id, tipo, params, ahora)              # lo que se exporta también es «reciente»: se vuelve a abrir y a exportar sin repetir filtros
                uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_EXPORT_AUTORIZADA, "m13_exportacion", fila["id"], nuevo={
                    "reporte": tipo, "alcance": params, "formato": formato, "filas": documento.filas, "huella": archivo.huella, "nominal": bool(reporte["nominal"]),
                    "destino_tipo": destino, "razon": razon or None, "resultado": "autorizada", "rol": actor.rol or None})
        except Exception:
            archivo.cerrar()
            raise
        return {"exportacion": self._salida(fila), "archivo": archivo}


# =================================================================================================================== 2.º tiempo

class ConfirmarExportacion(_Exportador):
    def ejecutar(self, actor: Actor, exportacion_id: str, cuerpo: dict) -> dict:
        resultado = str(cuerpo.get("resultado") or "")
        if resultado not in cat.RESULTADOS:
            raise DatosInvalidos(f"`resultado` debe ser uno de: {', '.join(cat.RESULTADOS)}.", resultado=resultado[:20], resultados=list(cat.RESULTADOS))
        destino = str(cuerpo.get("destino_tipo") or "")
        if destino not in cat.DESTINOS:
            raise DatosInvalidos(f"`destino_tipo` debe ser uno de: {', '.join(cat.DESTINOS)}.", destino_tipo=destino[:20], destinos=list(cat.DESTINOS))
        motivo = str(cuerpo.get("motivo") or "")
        if resultado == cat.RES_FALLIDO:
            motivo = motivo or "otro"
            if motivo not in cat.MOTIVOS_DE_FALLO:
                raise DatosInvalidos("El motivo del fallo debe ser uno de la lista.", motivo=motivo[:40], motivos=list(cat.MOTIVOS_DE_FALLO))
        huella = str(cuerpo.get("huella_verificada") or "").lower()
        if resultado == cat.RES_GUARDADO and not _HUELLA.match(huella):
            raise DatosInvalidos("Para dar el archivo por guardado hace falta la huella SHA-256 que se comprobó al releerlo (`huella_verificada`).")
        ahora = self.s.reloj.ahora_ms()
        diferido = None
        with self.s.uow() as uow:
            e = uow.exportaciones.por_id(exportacion_id) if exportacion_id else None
            if e is None or (actor.id and e["actor_id"] and e["actor_id"] != actor.id):
                raise NoEncontrado("No existe esa exportación.", exportacion_id=exportacion_id)           # lo ajeno y lo inexistente responden igual
            if e["estado"] == cat.EXP_ENTREGADA:
                if resultado == cat.RES_GUARDADO and huella == e["huella_verificada"]:
                    return {"exportacion": self._salida(e), "reintento": True}
                raise ExportacionYaConfirmada("Esa exportación ya quedó entregada.", exportacion_id=exportacion_id)
            if e["estado"] == cat.EXP_CADUCADA or ahora >= e["expira_en"]:
                fila = uow.exportaciones.caducar(exportacion_id, ahora)
                if fila is not None:
                    self._asiento_de_caducidad(uow, fila, ahora)
                diferido = ExportacionCaducada("Esa exportación caducó sin confirmarse: genera el reporte de nuevo.", exportacion_id=exportacion_id)
            elif resultado == cat.RES_FALLIDO:
                intento = {"en": ahora, "resultado": cat.RES_FALLIDO, "motivo": motivo, "destino_tipo": destino}
                fila = uow.exportaciones.anotar_intento_fallido(exportacion_id, intento) or e
                uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_EXPORT_FALLIDA, "m13_exportacion", exportacion_id, nuevo={
                    "reporte": e["tipo"], "alcance": e["parametros"], "formato": e["formato"], "filas": e["filas"], "huella": e["huella"], "destino_tipo": destino, "motivo": motivo,
                    "resultado": cat.RES_FALLIDO, "rol": actor.rol or None})
                return {"exportacion": self._salida(fila), "reintento": False}
            elif huella != e["huella"]:
                uow.exportaciones.anotar_intento_fallido(exportacion_id, {"en": ahora, "resultado": cat.RES_FALLIDO, "motivo": "verificacion_fallida", "destino_tipo": destino})
                uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_EXPORT_FALLIDA, "m13_exportacion", exportacion_id, nuevo={
                    "reporte": e["tipo"], "alcance": e["parametros"], "huella": e["huella"], "huella_verificada": huella, "destino_tipo": destino,
                    "motivo": "verificacion_fallida", "resultado": cat.RES_FALLIDO, "rol": actor.rol or None})
                diferido = HuellaDistinta("El archivo guardado no coincide con el que entregó el nodo: no se da por entregado. Guárdalo de nuevo.", exportacion_id=exportacion_id)
            else:
                fila = uow.exportaciones.entregar(exportacion_id, destino_tipo=destino, huella_verificada=huella, ahora=ahora,
                                                   intento={"en": ahora, "resultado": cat.RES_GUARDADO, "motivo": "", "destino_tipo": destino})
                if fila is None:                                   # otro la confirmó o caducó entre tanto
                    diferido = ExportacionYaConfirmada("Esa exportación ya no está pendiente de confirmar.", exportacion_id=exportacion_id)
                else:
                    uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_EXPORTADO, "m13_exportacion", exportacion_id, nuevo={
                        "reporte": e["tipo"], "alcance": e["parametros"], "formato": e["formato"], "filas": e["filas"], "huella": e["huella"], "nominal": e["nominal"],
                        "destino_tipo": destino, "destino_autorizado": e["destino_autorizado"], "razon": e["razon_codigo"] or None, "resultado": cat.RES_GUARDADO,
                        "rol": actor.rol or None})
                    self._publicar(uow, "Exportacion", exportacion_id, cat.EV_EXPORTADO, {
                        "exportacion_id": exportacion_id, "tipo": e["tipo"], "formato": e["formato"], "filas": e["filas"], "huella": e["huella"], "destino_tipo": destino,
                        "nominal": e["nominal"], "por": actor.id}, ahora)
                    if actor.id:
                        uow.recientes.marcar_exportado(actor.id, e["tipo"], e["parametros"], ahora)
                    return {"exportacion": self._salida(fila), "reintento": False}
        raise diferido

    @staticmethod
    def _asiento_de_caducidad(uow, fila: dict, ahora: int) -> None:
        uow.auditoria.registrar(cat.SISTEMA, cat.A_EXPORT_CADUCADA, "m13_exportacion", fila["id"], nuevo={
            "reporte": fila["tipo"], "alcance": fila["parametros"], "formato": fila["formato"], "filas": fila["filas"], "huella": fila["huella"],
            "intentos_fallidos": len(fila["intentos"]), "resultado": "sin_confirmar", "autorizada_en": fila["autorizada_en"]})


class VerExportacion(_Exportador):
    def ejecutar(self, actor: Actor, exportacion_id: str) -> dict:
        CaducarVencidas(self.s).ejecutar()
        with self.s.uow(lectura=True) as uow:
            e = uow.exportaciones.por_id(exportacion_id) if exportacion_id else None
            if e is None or (actor.id and e["actor_id"] and e["actor_id"] != actor.id):
                raise NoEncontrado("No existe esa exportación.", exportacion_id=exportacion_id)
            return {"exportacion": self._salida(e), "servidor_en": self.s.reloj.ahora_ms()}


class MisExportaciones(_Exportador):
    def ejecutar(self, actor: Actor) -> dict:
        CaducarVencidas(self.s).ejecutar()
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir(actor, cat.P_EXPORT)
            filas = uow.exportaciones.de_actor(actor.id, 20) if actor.id else []
            return {"exportaciones": [self._salida(e) for e in filas], "servidor_en": self.s.reloj.ahora_ms()}


class CaducarVencidas(_Exportador):
    """Las exportaciones autorizadas que nadie confirmó a tiempo pasan a `caducada` (con su asiento) y no cuentan como entregadas. Lo hace el hilo del nodo y cualquier consulta de
    exportaciones, así que el estado nunca queda viejo."""

    def ejecutar(self) -> int:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            hay = bool(uow.exportaciones.vencidas(ahora))
        if not hay:
            return 0
        n = 0
        with self.s.uow() as uow:
            for e in uow.exportaciones.vencidas(ahora):
                fila = uow.exportaciones.caducar(e["id"], ahora)
                if fila is not None:
                    ConfirmarExportacion._asiento_de_caducidad(uow, fila, ahora)
                    n += 1
        return n
