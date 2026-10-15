"""
Las escalas de calificación de la institución (FUN-124, «Sistema de calificaciones internacionales configurables»).

  PlantillasDeEscalas   el catálogo de plantillas orientativas (países y genéricas), sin adoptar
  ListarEscalas · VerEscala  las escalas que la institución adoptó, con sus versiones
  AdoptarPlantilla      la institución revisa una plantilla, la ajusta si hace falta y la ADOPTA: nace la escala y su versión 1
  CrearEscala           una escala propia, sin plantilla
  NuevaVersionDeEscala  cambiar una escala es publicar OTRA versión: las anteriores no se editan, y lo ya publicado se interpreta con la que tenía
  VistaPreviaDeEscala   cómo se vería una conversión, para decidir antes de adoptarla o cambiarla

Una conversión sólo existe dentro de una escala adoptada y validada: no hay equivalencias nacionales implícitas. Una plantilla NO se usa para presentar nada
mientras no se adopte (y, para presentar, mientras ningún nivel la use en modo calificaciones).
"""
from __future__ import annotations

import re
from decimal import Decimal

from ..dominio import catalogos as cat
from ..dominio import escala as esc
from ..dominio import plantillas_escalas as plantillas
from ..dominio import puntaje as pj
from ..dominio.errores import DatosInvalidos, NoEncontrado
from .base import _CasoDeUso, exigir_nodo_instalado, nuevo_id
from .puertos import Actor, UnidadDeTrabajo

_CODIGO = re.compile(r"^[a-z0-9][a-z0-9\-_.]{1,46}[a-z0-9]$")
VALORES_DE_MUESTRA = ("0", "25", "40", "50", "60", "70", "75", "80", "90", "100")


def version_a_salida(v: dict) -> dict:
    return {"id": v["id"], "escala_id": v["escala_id"], "numero": v["numero"], "definicion": esc.a_dict(v["definicion"]), "huella": v["huella"], "nota": v["nota"],
            "vigente_desde": v["vigente_desde"], "creada_por": v["creada_por"]}


def escala_a_salida(e: dict, versiones: list[dict] | None = None, ultima: dict | None = None) -> dict:
    salida = {"id": e["id"], "codigo": e["codigo"], "nombre": e["nombre"], "tipo": e["tipo"], "pais": e["pais"], "jurisdiccion": e["jurisdiccion"],
              "plantilla_origen": e["plantilla_origen"], "activa": e["activa"], "creada_en": e["creada_en"], "creada_por": e["creada_por"]}
    if versiones is not None:
        salida["versiones"] = [version_a_salida(v) for v in versiones]
    if ultima is not None:
        salida["ultima_version"] = {"id": ultima["id"], "numero": ultima["numero"], "huella": ultima["huella"]}
    return salida


def _definicion(datos: dict | None) -> esc.DefinicionEscala:
    """Lee y valida la definición que llega: `EscalaInvalida` con TODOS los problemas, uno por regla incumplida."""
    return esc.exigir_valida(esc.desde_dict(datos))


class PlantillasDeEscalas(_CasoDeUso):
    def ejecutar(self, actor: Actor, pais: str = "") -> dict:
        self.s.autorizacion.exigir(actor, cat.P_READ)
        return {"plantillas": plantillas.listar(pais), "advertencia": plantillas.ADVERTENCIA, "servidor_en": self.s.reloj.ahora_ms()}


class ListarEscalas(_CasoDeUso):
    def ejecutar(self, actor: Actor) -> dict:
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir(actor, cat.P_READ)
            return {"escalas": [escala_a_salida(e, ultima=uow.escalas.ultima_version(e["id"])) for e in uow.escalas.listar()], "servidor_en": self.s.reloj.ahora_ms()}


class VerEscala(_CasoDeUso):
    def ejecutar(self, actor: Actor, escala_id: str) -> dict:
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir(actor, cat.P_READ)
            e = uow.escalas.por_id(escala_id)
            if e is None:
                raise NoEncontrado("No existe esa escala.", escala_id=escala_id)
            return {**escala_a_salida(e, uow.escalas.versiones_de(escala_id)), "servidor_en": self.s.reloj.ahora_ms()}


class _Escritor(_CasoDeUso):
    def _version(self, uow: UnidadDeTrabajo, e: dict, definicion: esc.DefinicionEscala, nota: str, actor: Actor, ahora: int) -> dict:
        if definicion.tipo != e["tipo"]:
            raise DatosInvalidos(f"La escala es de tipo {e['tipo']}: una versión nueva no cambia el tipo (los boletines ya expedidos se interpretarían distinto).",
                                 tipo_escala=e["tipo"], tipo_definicion=definicion.tipo)
        return uow.escalas.crear_version(e["id"], definicion, huella=esc.huella(definicion), nota=nota, creada_por=actor.id or "admin", vigente_desde=ahora)

    def _alta(self, uow: UnidadDeTrabajo, actor: Actor, datos: dict, definicion: esc.DefinicionEscala, *, plantilla: str, ahora: int) -> dict:
        codigo = str(datos.get("codigo") or plantilla or "").strip().lower()
        if not _CODIGO.match(codigo):
            raise DatosInvalidos("`codigo` debe tener de 3 a 48 caracteres: minúsculas, números, guion, punto o guion bajo.", codigo_escala=codigo)
        if uow.escalas.por_codigo(codigo) is not None:
            raise DatosInvalidos(f"Ya existe una escala con el código «{codigo}»: usa otro, o crea una versión nueva de la existente.", codigo_escala=codigo)
        nombre = str(datos.get("nombre") or "").strip()
        if not nombre:
            raise DatosInvalidos("Falta `nombre` de la escala.")
        pais = str(datos.get("pais") or "").strip().upper()
        if pais and not re.fullmatch(r"[A-Z]{2}", pais):
            raise DatosInvalidos("`pais` debe ser un código ISO de dos letras.", pais=pais)
        e = uow.escalas.crear_escala({"id": nuevo_id(), "codigo": codigo, "nombre": nombre[:120], "tipo": definicion.tipo, "pais": pais,
                                      "jurisdiccion": str(datos.get("jurisdiccion") or "").strip()[:120], "plantilla_origen": plantilla, "activa": True,
                                      "creada_en": ahora, "creada_por": actor.id or "admin"})
        v = self._version(uow, e, definicion, str(datos.get("nota") or "").strip()[:300], actor, ahora)
        self._publicar(uow, "Escala", e["id"], cat.EV_ESCALA_ADOPTADA, {
            "escala_id": e["id"], "codigo": e["codigo"], "version_id": v["id"], "numero": v["numero"], "tipo": e["tipo"], "plantilla": plantilla, "pais": pais,
            "huella": v["huella"]}, ahora)
        uow.auditoria.registrar(actor.id or "admin", cat.A_ESCALA_ADOPTADA, "m11_escala", e["id"],
                                nuevo={"codigo": e["codigo"], "numero": v["numero"], "plantilla": plantilla, "huella": v["huella"]})
        return {**escala_a_salida(e, [v]), "servidor_en": ahora}


class AdoptarPlantilla(_Escritor):
    """`datos`: `{plantilla, codigo?, nombre?, jurisdiccion?, nota?, definicion?}`. Con `definicion`, la institución adopta la plantilla CON sus ajustes (se
    valida igual). Adoptar es la decisión institucional explícita que exige la regla fundamental: queda quién, cuándo y la huella de lo adoptado."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            self.s.autorizacion.exigir(actor, cat.P_MODE_SET)
            exigir_nodo_instalado(uow)
            codigo = str(datos.get("plantilla") or "").strip()
            base = plantillas.plantilla(codigo)
            if base is None:
                raise DatosInvalidos(f"La plantilla «{codigo}» no existe.", plantilla=codigo, disponibles=[p.codigo for p in plantillas.PLANTILLAS])
            definicion = _definicion(datos["definicion"]) if datos.get("definicion") else esc.exigir_valida(base.definicion)
            propios = {"codigo": codigo, "nombre": base.nombre, "pais": base.pais, "jurisdiccion": base.jurisdiccion,
                       "nota": f"Adoptada de la plantilla orientativa «{codigo}». {base.referencia}"[:300], **{k: v for k, v in datos.items() if v not in (None, "")}}
            return self._alta(uow, actor, propios, definicion, plantilla=codigo, ahora=ahora)


class CrearEscala(_Escritor):
    """`datos`: `{codigo, nombre, pais?, jurisdiccion?, nota?, definicion}`: una escala propia, sin plantilla."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            self.s.autorizacion.exigir(actor, cat.P_MODE_SET)
            exigir_nodo_instalado(uow)
            return self._alta(uow, actor, datos, _definicion(datos.get("definicion")), plantilla="", ahora=ahora)


class NuevaVersionDeEscala(_Escritor):
    """`datos`: `{definicion, nota?}`. Una versión nueva de una escala existente. Las versiones anteriores NO cambian: lo que ya se publicó con ellas sigue
    significando lo que significó. Los niveles que usan la escala siguen en la versión que tenían hasta que se les asigne la nueva."""

    def ejecutar(self, actor: Actor, escala_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            self.s.autorizacion.exigir(actor, cat.P_MODE_SET)
            e = uow.escalas.por_id(escala_id)
            if e is None:
                raise NoEncontrado("No existe esa escala.", escala_id=escala_id)
            definicion = _definicion(datos.get("definicion"))
            ultima = uow.escalas.ultima_version(e["id"])
            if ultima is not None and ultima["huella"] == esc.huella(definicion):
                # Idempotente: la misma definición no es otra versión (un reintento tras perder la respuesta no duplica la versión ni el evento).
                return {**escala_a_salida(e, uow.escalas.versiones_de(e["id"])), "reintento": True, "servidor_en": ahora}
            v = self._version(uow, e, definicion, str(datos.get("nota") or "").strip()[:300], actor, ahora)
            self._publicar(uow, "Escala", e["id"], cat.EV_ESCALA_ADOPTADA, {
                "escala_id": e["id"], "codigo": e["codigo"], "version_id": v["id"], "numero": v["numero"], "tipo": e["tipo"], "plantilla": e["plantilla_origen"],
                "pais": e["pais"], "huella": v["huella"]}, ahora)
            uow.auditoria.registrar(actor.id or "admin", cat.A_ESCALA_ADOPTADA, "m11_escala", e["id"], nuevo={"codigo": e["codigo"], "numero": v["numero"], "huella": v["huella"]})
            return {**escala_a_salida(e, uow.escalas.versiones_de(e["id"])), "servidor_en": ahora}


class VistaPreviaDeEscala(_CasoDeUso):
    """`datos`: una de `{definicion}`, `{escala_version_id}` o `{plantilla}`, y `valores` (resultados internos de muestra; por omisión una tabla de 0 a 100).
    Convierte sin guardar nada: es lo que el administrador revisa antes de adoptar una escala o ponerla en un nivel."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir(actor, cat.P_READ)
            if datos.get("definicion"):
                definicion = _definicion(datos["definicion"])
            elif datos.get("escala_version_id"):
                v = uow.escalas.version(str(datos["escala_version_id"]))
                if v is None:
                    raise NoEncontrado("No existe esa versión de escala.", escala_version_id=datos["escala_version_id"])
                definicion = v["definicion"]
            elif datos.get("plantilla"):
                base = plantillas.plantilla(str(datos["plantilla"]))
                if base is None:
                    raise DatosInvalidos(f"La plantilla «{datos['plantilla']}» no existe.", plantilla=datos["plantilla"])
                definicion = esc.exigir_valida(base.definicion)
            else:
                raise DatosInvalidos("Manda `definicion`, `escala_version_id` o `plantilla`.")
            crudos = datos.get("valores") or list(VALORES_DE_MUESTRA)
            if not isinstance(crudos, list) or len(crudos) > 200:
                raise DatosInvalidos("`valores` debe ser una lista de hasta 200 resultados internos.")
            internos: list[Decimal] = [pj.validar_interno(v, campo="valores") for v in crudos]
            return {"conversiones": [esc.presentacion_a_dict(p) for p in esc.vista_previa(definicion, internos)], "definicion": esc.a_dict(definicion),
                    "servidor_en": self.s.reloj.ahora_ms()}
