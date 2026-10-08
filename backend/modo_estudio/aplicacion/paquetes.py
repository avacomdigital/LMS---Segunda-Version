"""
StudyPackageService · el paquete de estudio descargable (CAP-047, FUN-084, FUN-085, BR-054, D-7, D-8).

El paquete es la lección (vista de aula SIN claves) más los medios que referencia, con su `huella` (SHA-256 del manifiesto canónico), su
tamaño y su vigencia. La descarga para trabajar sin el nodo sólo se permite en un aparato ASIGNADO a la persona que la pide: en uno
compartido, o en el asignado a OTRA persona, el siguiente alumno podría abrirla (BR-054; D-15 deja estudiar en línea en cualquier tableta
pero no llevarse el material). Ninguna tabla guarda el manifiesto: se reconstruye leyendo la lección en vivo, y la huella guardada es la
que el aparato debe confirmar.

  SolicitarPaquete      `POST /paquetes/`: aparato compartido, asignado a otra persona o `paquete_permitido = false` → 403 `descarga_denegada`
                        (fila `denegado` con su `motivo` y evento); si no, mide los medios y deja el paquete `solicitado`. Volver a pedirlo
                        reutiliza la fila («Actualizar descarga»).
  ListarPaquetes · VerPaquete    el estado del paquete, con `vencido` ya evaluado (vigencia y versión de curso; se persiste).
  ObtenerManifiesto     `GET …/manifiesto/`: pasa a `descargandose`; 410 `paquete_vencido` si venció.
  AbrirArchivoDePaquete `GET/HEAD …/archivos/{media_ref}/` con `Range`: sólo los medios de `archivos[]`.
  ConfirmarPaquete      `POST …/confirmar/`: con la huella correcta pasa a `disponible`; con otra, 409 `huella_invalida`.
  RetirarPaquete        `DELETE …/`: el alumno borra su copia (`retirado_en`); deja de listarse.

Las lecturas de la biblioteca y la medición de los medios se hacen FUERA de la transacción: pueden tardar y no deben retener la escritura de
nadie. Y lo que se decide dentro de una transacción (que un paquete venció, que se denegó una descarga) se CONFIRMA antes de responder el
error: un error lanzado dentro deshace lo escrito.
"""
from __future__ import annotations

from ..dominio import bloques as bloques_dom
from ..dominio import catalogos as cat
from ..dominio import paquete as paquete_dom
from ..dominio import plazo as plazo_dom
from ..dominio.errores import (
    DatosInvalidos,
    DescargaDenegada,
    FuenteError,
    HuellaInvalida,
    MedioDemasiadoGrande,
    NoEncontrado,
    NoEsElTitular,
    PaqueteVencido,
)
from . import dto
from .base import Contexto, _CasoDeUso, asignacion_del_alumno, nuevo_id, resolver_contexto
from .puertos import Actor, Bytes, UnidadDeTrabajo
from .tareas import exigir_escritura, obtener_o_crear, refrescar_estructura


def semilla_de(asignacion_id: str) -> str:
    """El barajado de las opciones es el mismo cada vez que se lee la lección de esta asignación: el manifiesto (y su huella) no cambian."""
    return f"estudio|{asignacion_id}"


def clave_de_curso(asignacion: dict) -> str:
    return f"{asignacion['fuente_curso']}|{asignacion['curso_ref']}"


def evaluar_paquetes(uow: UnidadDeTrabajo, paquetes: list[dict], ahora: int, versiones: dict[str, str | None] | None = None,
                     asignaciones: dict[str, dict] | None = None) -> list[dict]:
    """`vencido` se CALCULA AL LEER (no hay tarea programada) y se persiste: la vigencia pasó o —si se sabe— el curso tiene una versión
    nueva. `versiones` dice la versión instalada de cada curso (`clave_de_curso`); sin ella (o sin dato) no vence por versión."""
    salida = []
    for p in paquetes:
        if p["estado"] in cat.PAQUETE_ACTIVO:
            instalada = None
            if versiones:
                asignacion = (asignaciones or {}).get(p["asignacion_id"]) or uow.asignaciones.por_id(p["asignacion_id"])
                instalada = versiones.get(clave_de_curso(asignacion))
            motivo = paquete_dom.evaluar_vencimiento(vigente_hasta=p["vigente_hasta"], ahora=ahora, curso_version=p["curso_version"],
                                                     version_instalada=instalada)
            if motivo:
                p = uow.paquetes.actualizar(p["id"], estado=cat.VENCIDO, motivo=motivo, actualizado_en=ahora)
        salida.append(p)
    return salida


def construir_manifiesto(paquete: dict, asignacion: dict, leida: dict) -> dict:
    """El manifiesto del paquete, con su huella, a partir de la lección leída en vivo y de los archivos ya medidos. `generado_en` es el
    instante en que se pidió el paquete (no el de esta lectura): el mismo paquete da siempre la misma huella."""
    return paquete_dom.construir_manifiesto(
        paquete_id=paquete["id"], asignacion=dto.asignacion_estable(asignacion), curso=leida["curso"], leccion_ref=asignacion["leccion_ref"],
        vigente_hasta=paquete["vigente_hasta"], generado_en=paquete["solicitado_en"], leccion=leida["leccion"],
        archivos=paquete["archivos"], no_incluidos=paquete["no_incluidos"])


def _mensaje(motivo: str) -> str:
    return cat.MENSAJE_PAQUETE_NO_PERMITIDO if motivo == cat.PAQUETE_NO_PERMITIDO else cat.MENSAJE_DESCARGA_DENEGADA


class _CasoDePaquete(_CasoDeUso):
    def _contexto(self, uow: UnidadDeTrabajo, actor: Actor, huella: str, ahora: int, *, alumno_id: str = "", registrar: bool = False,
                  comprobar_uso: bool = True) -> Contexto:
        return resolver_contexto(uow, actor, huella, ahora=ahora, declarado=alumno_id, registrar=registrar, exigir_aparato=True,
                                 comprobar_uso=comprobar_uso)

    def _paquete(self, uow: UnidadDeTrabajo, ctx: Contexto, paquete_id: str, *, con_retirados: bool = False) -> dict:
        """El paquete si es de ESTE alumno y de ESTE aparato: uno de otra persona es 403 `no_es_el_titular`; uno de otro aparato o ya
        retirado, 404."""
        paquete = uow.paquetes.por_id(paquete_id) if paquete_id else None
        if paquete is None or (paquete["retirado_en"] is not None and not con_retirados):
            raise NoEncontrado("No existe ese paquete para este aparato.", paquete_id=paquete_id)
        if paquete["alumno_id"] != ctx.alumno_id:
            raise NoEsElTitular("El paquete es de otra persona: sólo su titular lo lee o lo escribe.", paquete_id=paquete_id)
        if paquete["dispositivo_id"] != ctx.dispositivo_id:
            raise NoEncontrado("No existe ese paquete para este aparato.", paquete_id=paquete_id)
        return paquete

    def _versiones(self, asignaciones: list[dict]) -> dict[str, str | None]:
        """La versión instalada de cada curso, preguntada UNA vez por curso. Nunca lanza: sin dato, no vence por versión."""
        versiones: dict[str, str | None] = {}
        for a in asignaciones:
            clave = clave_de_curso(a)
            if clave not in versiones:
                versiones[clave] = self.s.contenido.version_instalada(a["fuente_curso"], a["curso_ref"])
        return versiones

    @staticmethod
    def _servible(paquete: dict) -> bool:
        return paquete["estado"] not in (cat.DENEGADO, cat.VENCIDO)

    @staticmethod
    def _exigir_servible(paquete: dict, ahora: int) -> None:
        """Denegado no sirve nada (403); vencido tampoco (410 `paquete_vencido`). Se llama DESPUÉS de confirmar la transacción."""
        if paquete["estado"] == cat.DENEGADO:
            raise DescargaDenegada(_mensaje(paquete["motivo"]), paquete=dto.paquete(paquete, ahora), mensaje=_mensaje(paquete["motivo"]))
        if paquete["estado"] == cat.VENCIDO:
            raise PaqueteVencido("El paquete venció: pídelo de nuevo para actualizar la descarga.", paquete_id=paquete["id"],
                                 motivo=paquete["motivo"])


class SolicitarPaquete(_CasoDePaquete):
    """FUN-084 · FUN-085 · `POST /paquetes/`. Devuelve `(paquete, creado)`: 201 la primera vez, 200 si se reutilizó la fila."""

    def ejecutar(self, actor: Actor, datos: dict) -> tuple[dict, bool]:
        self.s.autorizacion.exigir(actor, cat.P_PACKAGE_DOWNLOAD)
        asignacion_id = str(datos.get("asignacion_id") or "").strip()
        if not asignacion_id:
            raise DatosInvalidos("Falta asignacion_id: qué lección se quiere llevar.", campo="asignacion_id")
        ahora = self.s.reloj.ahora_ms()
        denegado = None
        with self.s.uow() as uow:
            ctx = self._contexto(uow, actor, datos.get("dispositivo"), ahora, alumno_id=datos.get("alumno_id") or "", registrar=True)
            asignacion = asignacion_del_alumno(uow, ctx, asignacion_id)
            motivo = (cat.DISPOSITIVO_AJENO if ctx.ajeno else cat.DISPOSITIVO_COMPARTIDO if not ctx.es_del_alumno
                      else cat.PAQUETE_NO_PERMITIDO if not asignacion["paquete_permitido"] else "")
            if motivo:
                denegado = self._denegar(uow, ctx, asignacion, motivo, ahora)
            else:
                exigir_escritura(asignacion, ahora)
        if denegado is not None:      # la fila y el evento quedan confirmados (BR-054) y DESPUÉS se responde 403 (también al ajeno: MSG-046)
            raise DescargaDenegada(_mensaje(denegado["motivo"]), paquete=dto.paquete(denegado, ahora), mensaje=_mensaje(denegado["motivo"]))

        leida = self.s.contenido.leccion(fuente=asignacion["fuente_curso"], curso_ref=asignacion["curso_ref"],
                                         leccion_ref=asignacion["leccion_ref"], asignacion_id=asignacion["id"], dispositivo=ctx.huella,
                                         alumno_id=ctx.alumno_para_url, semilla=semilla_de(asignacion["id"]))
        archivos, no_incluidos = self._medir(leida, asignacion)

        with self.s.uow() as uow:
            asignacion = refrescar_estructura(uow, uow.asignaciones.por_id(asignacion["id"]), leida["curso"], leida["leccion"])
            obtener_o_crear(uow, asignacion, ctx.alumno_id, ahora)
            existente = uow.paquetes.obtener(asignacion["id"], ctx.alumno_id, ctx.dispositivo_id)
            campos = {
                "estado": cat.SOLICITADO, "motivo": "", "curso_version": str(leida["curso"].get("version") or ""), "huella": "",
                "bytes_total": paquete_dom.bytes_total(archivos), "archivos": archivos, "no_incluidos": no_incluidos,
                "vigente_hasta": plazo_dom.vigente_hasta(fecha_limite=asignacion["fecha_limite"], gracia_ms=asignacion["gracia_ms"],
                                                         ahora=ahora, vigencia_dias=self.s.config.vigencia_dias),
                "solicitado_en": ahora, "descarga_iniciada_en": None, "disponible_en": None, "retirado_en": None, "actualizado_en": ahora}
            if existente is None:
                paquete = uow.paquetes.crear({"id": nuevo_id(), "asignacion_id": asignacion["id"], "alumno_id": ctx.alumno_id,
                                              "dispositivo_id": ctx.dispositivo_id, **campos})
            else:
                paquete = uow.paquetes.actualizar(existente["id"], **campos)
            paquete = uow.paquetes.actualizar(paquete["id"], huella=construir_manifiesto(paquete, asignacion, leida)["huella"])
            uow.asignaciones.actualizar(asignacion["id"], bytes_estimados=paquete["bytes_total"])   # «se afina al preparar el paquete»
            return dto.respuesta_de_paquete(paquete, ahora), existente is None

    def _denegar(self, uow: UnidadDeTrabajo, ctx: Contexto, asignacion: dict, motivo: str, ahora: int) -> dict:
        """FUN-085 · BR-054: deja constancia (fila `denegado` y `estudio.descarga.denegada.v1`) y la petición cuenta como contacto."""
        obtener_o_crear(uow, asignacion, ctx.alumno_id, ahora)
        vacio = {"estado": cat.DENEGADO, "motivo": motivo, "curso_version": "", "huella": "", "bytes_total": 0, "archivos": [],
                 "no_incluidos": [], "vigente_hasta": None, "solicitado_en": ahora, "descarga_iniciada_en": None, "disponible_en": None,
                 "retirado_en": None, "actualizado_en": ahora}
        existente = uow.paquetes.obtener(asignacion["id"], ctx.alumno_id, ctx.dispositivo_id)
        if existente is None:
            paquete = uow.paquetes.crear({"id": nuevo_id(), "asignacion_id": asignacion["id"], "alumno_id": ctx.alumno_id,
                                          "dispositivo_id": ctx.dispositivo_id, **vacio})
        else:
            paquete = uow.paquetes.actualizar(existente["id"], **vacio)
        self._publicar(uow, "Paquete", paquete["id"], cat.EV_DESCARGA_DENEGADA, {
            "paquete_id": paquete["id"], "asignacion_id": asignacion["id"], "alumno_id": ctx.alumno_id,
            "dispositivo_id": ctx.dispositivo_id, "motivo": motivo}, ahora)
        return paquete

    def _medir(self, leida: dict, asignacion: dict) -> tuple[list[dict], list[dict]]:
        """Lee cada medio de la lección para medirlo y calcular su SHA-256. Las simulaciones no viajan (`simulacion_requiere_nodo`,
        Q-71); un medio que la fuente no tiene o que supera el tope de tamaño se deja fuera con su motivo. Si la fuente se cae a
        mitad, todo el paquete falla (503): no se entrega un manifiesto a medias."""
        archivos: list[dict] = []
        no_incluidos: list[dict] = []
        for ref in bloques_dom.medios_de_leccion(leida["leccion"]):
            medio = (leida["medios"] or {}).get(ref) or {}
            if paquete_dom.es_simulacion(medio):
                no_incluidos.append(paquete_dom.no_incluido(ref, cat.NO_INCLUIDO_SIMULACION))
                continue
            try:
                medido = self.s.contenido.medir(leida["fuente"], asignacion["curso_ref"], ref, self.s.config.medio_max_bytes, asignacion["id"])
            except MedioDemasiadoGrande:
                no_incluidos.append(paquete_dom.no_incluido(ref, cat.NO_INCLUIDO_DEMASIADO_GRANDE))
            except (NoEncontrado, FuenteError):
                no_incluidos.append(paquete_dom.no_incluido(ref, cat.NO_INCLUIDO_NO_DISPONIBLE))
            else:
                archivos.append(paquete_dom.archivo(media_ref=ref, clase=medio.get("clase"), mime=medio.get("mime") or medido.get("mime"),
                                                    tamano=medido["bytes"], sha256=medido["sha256"]))
        return archivos, no_incluidos


class ListarPaquetes(_CasoDePaquete):
    """`GET /paquetes/?dispositivo=`: los paquetes del aparato para su dueño, con el estado ya evaluado (`vencido`)."""

    def ejecutar(self, actor: Actor, huella: str = "", alumno_id: str = "") -> dict:
        self.s.autorizacion.exigir(actor, cat.P_PACKAGE_DOWNLOAD)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self._contexto(uow, actor, huella, ahora, alumno_id=alumno_id)
            paquetes = uow.paquetes.del_aparato(ctx.alumno_id, ctx.dispositivo_id)
            asignaciones = {p["asignacion_id"]: uow.asignaciones.por_id(p["asignacion_id"]) for p in paquetes}
        versiones = self._versiones([a for a in asignaciones.values() if a])
        with self.s.uow() as uow:
            evaluados = evaluar_paquetes(uow, paquetes, ahora, versiones, asignaciones)
        return {"paquetes": [dto.paquete(p, ahora) for p in evaluados], "servidor_en": ahora}


class VerPaquete(_CasoDePaquete):
    """`GET /paquetes/{id}/`: el paquete, con su estado evaluado. Es del aparato que pregunta y de su dueño."""

    def ejecutar(self, actor: Actor, paquete_id: str, huella: str = "", alumno_id: str = "") -> dict:
        self.s.autorizacion.exigir(actor, cat.P_PACKAGE_DOWNLOAD)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self._contexto(uow, actor, huella, ahora, alumno_id=alumno_id)
            paquete = self._paquete(uow, ctx, paquete_id)
            asignacion = uow.asignaciones.por_id(paquete["asignacion_id"])
        versiones = self._versiones([asignacion])
        with self.s.uow() as uow:
            paquete = evaluar_paquetes(uow, [paquete], ahora, versiones, {asignacion["id"]: asignacion})[0]
        return dto.respuesta_de_paquete(paquete, ahora)


class ObtenerManifiesto(_CasoDePaquete):
    """FUN-084 · `GET /paquetes/{id}/manifiesto/`. Reconstruye el manifiesto leyendo la lección EN VIVO; la huella es la del paquete. Pasa
    a `descargandose`. 410 `paquete_vencido` si venció (vigencia o versión nueva del curso)."""

    def ejecutar(self, actor: Actor, paquete_id: str, huella: str = "", alumno_id: str = "") -> dict:
        self.s.autorizacion.exigir(actor, cat.P_PACKAGE_DOWNLOAD)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self._contexto(uow, actor, huella, ahora, alumno_id=alumno_id)
            paquete = evaluar_paquetes(uow, [self._paquete(uow, ctx, paquete_id)], ahora)[0]
            asignacion = uow.asignaciones.por_id(paquete["asignacion_id"])
        self._exigir_servible(paquete, ahora)
        leida = self.s.contenido.leccion(fuente=asignacion["fuente_curso"], curso_ref=asignacion["curso_ref"],
                                         leccion_ref=asignacion["leccion_ref"], asignacion_id=asignacion["id"], dispositivo=ctx.huella,
                                         alumno_id=ctx.alumno_para_url, semilla=semilla_de(asignacion["id"]))
        manifiesto = None
        with self.s.uow() as uow:
            paquete = uow.paquetes.por_id(paquete["id"])
            version = str(leida["curso"].get("version") or "")
            if paquete["curso_version"] and version and version != paquete["curso_version"]:
                paquete = uow.paquetes.actualizar(paquete["id"], estado=cat.VENCIDO, motivo=cat.VERSION_NUEVA, actualizado_en=ahora)
            else:
                manifiesto = construir_manifiesto(paquete, asignacion, leida)
                campos: dict = {}
                if paquete["estado"] != cat.DISPONIBLE and manifiesto["huella"] != paquete["huella"]:
                    campos["huella"] = manifiesto["huella"]      # la lección cambió sin cambiar de versión: la huella vigente es la nueva
                if paquete["estado"] == cat.SOLICITADO:
                    campos.update(estado=cat.DESCARGANDOSE, descarga_iniciada_en=ahora, actualizado_en=ahora)
                if campos:
                    uow.paquetes.actualizar(paquete["id"], **campos)
        if manifiesto is None:      # el curso tiene una versión nueva: el paquete venció (se confirmó arriba) y se responde 410
            self._exigir_servible(paquete, ahora)
        return manifiesto


class AbrirArchivoDePaquete(_CasoDePaquete):
    """`GET/HEAD /paquetes/{id}/archivos/{media_ref}/` (con `Range`, reanudable): los bytes de un medio de `archivos[]`. Devuelve
    `(bytes, archivo)`; `archivo["sha256"]` es el `ETag`."""

    def ejecutar(self, actor: Actor, paquete_id: str, media_ref: str, rango: str | None = None, metodo: str = "GET",
                 huella: str = "", alumno_id: str = "") -> tuple[Bytes, dict]:
        self.s.autorizacion.exigir(actor, cat.P_PACKAGE_DOWNLOAD)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self._contexto(uow, actor, huella, ahora, alumno_id=alumno_id)
            paquete = evaluar_paquetes(uow, [self._paquete(uow, ctx, paquete_id)], ahora)[0]
            asignacion = uow.asignaciones.por_id(paquete["asignacion_id"])
        self._exigir_servible(paquete, ahora)
        archivo = next((a for a in paquete["archivos"] if a["media_ref"] == media_ref), None)
        if archivo is None:
            raise NoEncontrado("Ese medio no está en el paquete.", media_ref=media_ref)
        medio = self.s.contenido.abrir_medio(asignacion["fuente_curso"], asignacion["curso_ref"], media_ref, None, rango, metodo)
        return medio, archivo


class ConfirmarPaquete(_CasoDePaquete):
    """FUN-084 · `POST /paquetes/{id}/confirmar/`: el aparato ya tiene todo y dice la huella que verificó. La correcta lo deja `disponible`
    (y emite `estudio.paquete.descargado.v1`); otra es 409 `huella_invalida` y el paquete no cambia. Confirmar lo ya disponible es idempotente."""

    def ejecutar(self, actor: Actor, paquete_id: str, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_PACKAGE_DOWNLOAD)
        ahora = self.s.reloj.ahora_ms()
        confirmada = str(datos.get("huella") or "").strip().lower()
        if not confirmada:
            raise DatosInvalidos("Falta huella: la que el aparato verificó del manifiesto.", campo="huella")
        with self.s.uow() as uow:
            ctx = self._contexto(uow, actor, datos.get("dispositivo"), ahora, alumno_id=datos.get("alumno_id") or "")
            paquete = evaluar_paquetes(uow, [self._paquete(uow, ctx, paquete_id)], ahora)[0]
            if self._servible(paquete):
                if confirmada != (paquete["huella"] or "").lower():
                    raise HuellaInvalida("La huella no es la del manifiesto entregado: el paquete no está íntegro. Vuelve a descargarlo.",
                                         paquete_id=paquete["id"])
                if paquete["estado"] != cat.DISPONIBLE:
                    paquete = uow.paquetes.actualizar(paquete["id"], estado=cat.DISPONIBLE, disponible_en=ahora, actualizado_en=ahora,
                                                      descarga_iniciada_en=paquete["descarga_iniciada_en"] or ahora)
                    bytes_ = datos.get("bytes")
                    self._publicar(uow, "Paquete", paquete["id"], cat.EV_PAQUETE_DESCARGADO, {
                        "paquete_id": paquete["id"], "asignacion_id": paquete["asignacion_id"], "alumno_id": ctx.alumno_id,
                        "dispositivo_id": ctx.dispositivo_id, "huella": paquete["huella"],
                        "bytes": bytes_ if isinstance(bytes_, int) and not isinstance(bytes_, bool) and bytes_ >= 0
                        else paquete["bytes_total"]}, ahora)
        self._exigir_servible(paquete, ahora)
        return dto.respuesta_de_paquete(paquete, ahora)


class RetirarPaquete(_CasoDePaquete):
    """`DELETE /paquetes/{id}/`: el alumno borra su copia (`retirado_en`; nada se borra, CV-05). Deja de listarse. Idempotente. Borrar debe
    poder hacerse siempre: un aparato bloqueado también libera su material."""

    def ejecutar(self, actor: Actor, paquete_id: str, huella: str = "", alumno_id: str = "") -> dict:
        self.s.autorizacion.exigir(actor, cat.P_PACKAGE_DOWNLOAD)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self._contexto(uow, actor, huella, ahora, alumno_id=alumno_id, comprobar_uso=False)
            paquete = self._paquete(uow, ctx, paquete_id, con_retirados=True)
            if paquete["retirado_en"] is None:
                uow.paquetes.actualizar(paquete["id"], retirado_en=ahora, actualizado_en=ahora)
            return {"retirado": True, "paquete_id": paquete["id"], "servidor_en": ahora}
