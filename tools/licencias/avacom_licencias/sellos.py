"""
La ESTACIÓN DE APROVISIONAMIENTO (S1): de una solicitud `.avsol` de un equipo y el inventario de AVACOM a un sello `.avsello`, y la lista de revocados `.avrev`.

Qué comprueba antes de firmar (y qué NO puede comprobar: está dicho en `09-segunda-proteccion.md`):

  · La solicitud trae la prueba de posesión de la clave de identidad (la firmó el equipo con ella).
  · La SERIE está en el INVENTARIO de AVACOM (el que entrega la fábrica o el que arma quien entrega). Sin inventario no se firma: «equipo ajeno» = sin serie conocida.
  · Si el inventario trae la huella de la EKPub del TPM de esa serie, la solicitud debe traer una EKPub con esa huella.
  · Una serie se sella UNA vez: volver a sellarla (cambio de placa, TPM borrado) exige `reemitir`, y entonces la huella de la clave anterior queda para REVOCAR.
  · La solicitud declara que la clave vive en el TPM (`en_tpm`). Es lo que DICE el equipo; la estación no puede verificarlo sin la activación de credencial del TPM (evidencia 3, pendiente).
    Por eso, mientras tanto, la evidencia del sello es «inventario» (1): el sello prueba que AVACOM autorizó ESA serie con ESA clave, no que el hardware sea el de la fábrica.

El inventario es un JSON que AVACOM custodia (no viaja en ningún instalador):
    {"version": 1, "lote": "L-2026-10", "modelo": "Panel 86", "series": {"OPS-0001": {"ek_huella": "<64 hex>|null", "modelo": "Panel 86"}, ...}}
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from . import registro as reg
from .dominio_nodo import errores, firma, sello

SERIE = re.compile(r"^[A-Za-z0-9._-]{1,64}\Z")


class ErrorDeSello(ValueError):
    """Algo de lo pedido no se puede sellar. El mensaje se le muestra tal cual a quien opera."""


@dataclass(frozen=True)
class Inventario:
    lote: str
    series: dict[str, dict]

    @staticmethod
    def leer(texto: str) -> Inventario:
        try:
            d = json.loads(texto)
            series = d["series"]
            if not isinstance(series, dict):
                raise TypeError
        except (ValueError, KeyError, TypeError) as error:
            raise ErrorDeSello("El inventario no es un JSON con «series».") from error
        limpio = {}
        for serie, datos in series.items():
            if not SERIE.match(str(serie)):
                raise ErrorDeSello(f"La serie «{serie}» no es válida en el inventario.")
            datos = datos or {}
            ek = datos.get("ek_huella")
            if ek is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", str(ek)):
                raise ErrorDeSello(f"La huella de la EKPub de «{serie}» no mide 64 hexadecimales.")
            limpio[str(serie)] = {"ek_huella": None if ek is None else str(ek).lower(), "modelo": str(datos.get("modelo", d.get("modelo", "")))[:64]}
        return Inventario(str(d.get("lote", ""))[:32], limpio)


def emitir_sello(solicitud_bytes: bytes, privada: bytes, kid: str, inventario: Inventario, registro: reg.Registro, origen: str, ahora_ms: int,
                 vence_ms: int = 0, reemitir: bool = False) -> tuple[bytes, sello.Sello, dict]:
    """`(bytes del .avsello, el sello, el renglón del registro)`. Lo escrito se VUELVE A LEER con el lector del nodo: un sello que no verifica no se entrega."""
    if origen not in ("fabrica", "entrega"):
        raise ErrorDeSello("El origen es «fabrica» o «entrega».")
    try:
        sol = sello.leer_solicitud(solicitud_bytes)
    except errores.LicenciaInvalida as error:
        raise ErrorDeSello(f"La solicitud no es válida ({error.motivo}): se rechaza.") from error
    if not sol.serie:
        raise ErrorDeSello("La solicitud no trae serie: sin serie no se puede comprobar contra el inventario.")
    entrada = inventario.series.get(sol.serie)
    if entrada is None:
        raise ErrorDeSello(f"La serie «{sol.serie}» no está en el inventario de AVACOM: no es un dispositivo AVACOM conocido.")
    if entrada["ek_huella"] is not None:
        if sol.ek_publica is None or sello.huella_de_spki(sol.ek_publica).hex() != entrada["ek_huella"]:
            raise ErrorDeSello(f"La EKPub del TPM de la solicitud no es la que el inventario registra para «{sol.serie}».")
    bien, mensaje, _ = registro.verificar()
    if not bien:
        raise ErrorDeSello(f"El registro de emisiones está alterado ({mensaje}). No se firma nada: avisa al CTO.")
    previos = [r for r in registro.renglones() if r.get("accion") == "sello" and r.get("serie") == sol.serie]
    if previos and not reemitir:
        raise ErrorDeSello(f"La serie «{sol.serie}» ya tiene sello (renglón {previos[-1]['n']}). Para reemplazarlo (cambio de placa, TPM borrado) usa --reemitir y REVOCA la clave anterior.")
    if vence_ms and vence_ms <= ahora_ms:
        raise ErrorDeSello("El vencimiento ya pasó.")
    nuevo = sello.Sello(str(uuid.uuid4()), sol.serie, entrada["modelo"] or sol.modelo, origen, sol.clave_huella,
                        sello.huella_de_spki(sol.cifrado_publica) if sol.cifrado_publica else None,
                        sello.huella_de_spki(sol.ek_publica) if sol.ek_publica else None, ahora_ms, vence_ms, inventario.lote, sol.mac, "inventario", kid, "")
    datos = sello.codificar_sello(kid, nuevo, lambda m: firma.firmar(privada, m))
    leido = sello.leer_sello(datos, {kid: firma.publica_de(privada)})
    if (leido.clave_huella, leido.serie, leido.origen) != (sol.clave_huella, sol.serie, origen):
        raise ErrorDeSello("Lo escrito no coincide con lo pedido: no se entrega.")
    renglon = registro.anadir({"accion": "sello", "serie": sol.serie, "sello_id": leido.id, "kid": kid, "origen": origen, "evidencia": leido.evidencia, "lote": inventario.lote,
                               "emitido": ahora_ms, "vence": vence_ms, "sha256": leido.sha256, "clave_huella_sha256": leido.clave_huella.hex()[:16],
                               "reemite": bool(previos)})
    return datos, leido, renglon


def emitir_revocados(privada: bytes, kid: str, huellas_nuevas: list[bytes], previa: bytes | None, claves: dict[str, bytes], registro: reg.Registro, ahora_ms: int) -> tuple[bytes, int]:
    """La lista siguiente: la anterior (verificada) + las huellas nuevas, con el número subido. `(bytes, numero)`."""
    numero, conjunto = 0, set()
    if previa:
        try:
            numero, existentes = sello.leer_revocados(previa, claves)
        except errores.LicenciaInvalida as error:
            raise ErrorDeSello(f"La lista anterior no es válida ({error.motivo}): no se parte de una lista dudosa.") from error
        conjunto |= existentes
    conjunto |= set(huellas_nuevas)
    if len(conjunto) > 128:
        raise ErrorDeSello("Una lista cabe hasta 128 huellas; pásese a un formato con varias partes (no hace falta con 55 equipos por aula).")
    bien, mensaje, _ = registro.verificar()
    if not bien:
        raise ErrorDeSello(f"El registro de emisiones está alterado ({mensaje}).")
    datos = sello.codificar_revocados(kid, numero + 1, ahora_ms, sorted(conjunto), lambda m: firma.firmar(privada, m))
    registro.anadir({"accion": "revocar", "kid": kid, "numero": numero + 1, "cantidad": len(conjunto), "nuevas": [h.hex()[:16] for h in huellas_nuevas], "emitido": ahora_ms})
    return datos, numero + 1
