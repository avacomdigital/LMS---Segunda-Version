"""
Los VECTORES del sello de dispositivo: los mismos archivos los leen el backend (Python) y el Host (C#, `tests/Avacom.Ops.Host.Tests/SelloTests.cs`) y deben dar el mismo veredicto y el mismo motivo
(prueba diferencial, como la de la biblioteca nativa). El archivo `vectores.json` vive junto a las pruebas del Host.

  · Normal: la prueba COMPRUEBA que el archivo que hay en el repositorio sigue dando lo que dice (si cambia el formato, falla aquí primero).
  · Para regenerarlo:   set AVACOM_CAPTURAR_SELLO=1   y correr esta prueba.   Es determinista (llaves de desarrollo y semilla fija) salvo la firma ECDSA de la solicitud, que no se incluye.
"""
from __future__ import annotations

import base64
import json
import os
import random
from pathlib import Path

from django.test import SimpleTestCase

from licenciamiento.dominio import firma, sello as s
from licenciamiento.dominio.errores import LicenciaInvalida

from . import emisor_sello

RUTA = Path(__file__).resolve().parents[3] / "tests" / "Avacom.Ops.Host.Tests" / "Fixtures" / "sello" / "vectores.json"
AHORA = 1_790_000_000_000
H = bytes(range(32))
OTRA = bytes(range(1, 33))
KID = emisor_sello.KID_SELLO_DEV_1
PRIV = emisor_sello.clave_privada()
CLAVES = emisor_sello.claves_publicas()


def sello(**c) -> s.Sello:
    base = dict(id="0a0b0c0d-0e0f-1011-1213-141516171819", serie="OPS-0001", modelo="Panel 86", origen="fabrica", clave_huella=H, cifrado_huella=b"\x11" * 32, ek_huella=b"\x22" * 32,
                emitido=AHORA - 1000, vence=0, lote="L-01", mac="00:11:22:33:44:55", evidencia="inventario", kid="", sha256="")
    base.update(c)
    return s.Sello(**base)


def emitir(x: s.Sello, kid=KID) -> bytes:
    return s.codificar_sello(kid, x, lambda m: firma.firmar(PRIV, m))


def revocados(*huellas: bytes) -> bytes:
    return s.codificar_revocados(KID, 3, AHORA, list(huellas), lambda m: firma.firmar(PRIV, m))


def casos() -> list[dict]:
    valido = emitir(sello())
    mal_firma = bytearray(valido)
    mal_firma[-1] ^= 1
    mal_cuerpo = bytearray(valido)
    mal_cuerpo[30] ^= 1
    azar = random.Random(20261026)
    lista: list[dict] = [
        dict(nombre="valido", sello=valido, equipo=H, posesion=True),
        dict(nombre="vence_en_el_limite", sello=emitir(sello(vence=AHORA)), equipo=H, posesion=True),
        dict(nombre="vencido", sello=emitir(sello(vence=AHORA - 1)), equipo=H, posesion=True, ahora=AHORA),
        dict(nombre="sin_sello", sello=None, equipo=H, posesion=True),
        dict(nombre="firma_alterada", sello=bytes(mal_firma), equipo=H, posesion=True),
        dict(nombre="cuerpo_alterado", sello=bytes(mal_cuerpo), equipo=H, posesion=True),
        dict(nombre="kid_desconocido", sello=emitir(sello(), kid="sello-ajeno"), equipo=H, posesion=True),
        dict(nombre="otra_clave", sello=valido, equipo=OTRA, posesion=True),
        dict(nombre="sin_clave", sello=valido, equipo=None, posesion=None),
        dict(nombre="no_firmo", sello=valido, equipo=H, posesion=None),
        dict(nombre="firma_de_reto_mala", sello=valido, equipo=H, posesion=False),
        dict(nombre="revocado", sello=valido, equipo=H, posesion=True, revocados=[H]),
        dict(nombre="mac_distinta_no_decide", sello=emitir(sello(mac="AA:BB:CC:DD:EE:FF", serie="OTRA")), equipo=H, posesion=True),
        dict(nombre="sin_opcionales", sello=emitir(sello(cifrado_huella=None, ek_huella=None, mac="", lote="", modelo="", serie="")), equipo=H, posesion=True),
        dict(nombre="con_identificador_uefi", sello=emitir(sello(uefi_id="AVACOM-OPS-00001234")), equipo=H, posesion=True),
        dict(nombre="identificador_uefi_mal_formado", sello=emitir(sello(uefi_id="DS2015")), equipo=H, posesion=True),
        dict(nombre="identificador_uefi_en_minusculas", sello=emitir(sello(uefi_id="avacom-ops-00001234")), equipo=H, posesion=True),
        dict(nombre="licencia_no_es_sello", sello=b"AVLC" + valido[4:], equipo=H, posesion=True),
        dict(nombre="truncado", sello=valido[:100], equipo=H, posesion=True),
    ]
    for i in range(300):
        datos = bytearray(valido)
        if azar.random() < 0.2:
            datos = datos[:azar.randrange(len(datos))]
        else:
            datos[azar.randrange(len(datos))] ^= 1 << azar.randrange(8)
        lista.append(dict(nombre=f"mutacion_{i:03d}", sello=bytes(datos), equipo=H, posesion=True))
    return lista


def veredicto_de(caso: dict) -> tuple[str, str]:
    v = s.evaluar(caso["sello"], CLAVES, caso["equipo"], caso["posesion"], frozenset(caso.get("revocados", [])), caso.get("ahora", AHORA))
    return v.estado, v.motivo


def cuerpo() -> dict:
    salida = []
    for c in casos():
        estado, motivo = veredicto_de(c)
        salida.append({"nombre": c["nombre"], "sello": None if c["sello"] is None else base64.b64encode(c["sello"]).decode(), "equipo": None if c["equipo"] is None else c["equipo"].hex(),
                       "posesion": c["posesion"], "revocados": [h.hex() for h in c.get("revocados", [])], "ahora": c.get("ahora", AHORA), "estado": estado, "motivo": motivo})
    lista_valida = revocados(H, OTRA)
    return {"nota": "Generado por licenciamiento.tests.test_vectores_sello; lo lee Avacom.Ops.Host.Tests.SelloTests", "kid": KID, "publica": CLAVES[KID].hex(), "casos": salida,
            "revocados": {"archivo": base64.b64encode(lista_valida).decode(), "numero": 3, "huellas": sorted([H.hex(), OTRA.hex()])},
            "revocados_alterado": base64.b64encode(lista_valida[:-1] + bytes([lista_valida[-1] ^ 1])).decode()}


class VectoresDelSelloTests(SimpleTestCase):
    def test_el_archivo_de_vectores_esta_al_dia(self):
        nuevo = cuerpo()
        if os.environ.get("AVACOM_CAPTURAR_SELLO") == "1":
            RUTA.parent.mkdir(parents=True, exist_ok=True)
            RUTA.write_text(json.dumps(nuevo, indent=1) + "\n", encoding="utf-8")
        self.assertTrue(RUTA.is_file(), f"falta {RUTA}: corre con AVACOM_CAPTURAR_SELLO=1")
        guardado = json.loads(RUTA.read_text(encoding="utf-8"))
        self.assertEqual(guardado, nuevo)

    def test_las_mutaciones_nunca_se_aceptan(self):
        aceptadas = [c for c in cuerpo()["casos"] if c["nombre"].startswith("mutacion_") and c["estado"] == s.AUTENTICADO]
        self.assertEqual(aceptadas, [])

    def test_los_revocados_del_vector_son_validos(self):
        d = cuerpo()["revocados"]
        self.assertEqual(s.leer_revocados(base64.b64decode(d["archivo"]), CLAVES), (3, frozenset(bytes.fromhex(h) for h in d["huellas"])))
        with self.assertRaises(LicenciaInvalida):
            s.leer_revocados(base64.b64decode(cuerpo()["revocados_alterado"]), CLAVES)


class SolicitudDelHostTests(SimpleTestCase):
    def test_la_solicitud_que_escribe_el_host_en_csharp_la_lee_el_backend(self):
        """La `.avsol` que produce `Verbos.Solicitar` (C#, firma ECDSA de CNG/.NET en P1363) verifica con el lector de Python: mismas etiquetas, misma firma."""
        ruta = RUTA.parent / "solicitud-csharp.avsol"
        self.assertTrue(ruta.is_file(), "regenera con AVACOM_CAPTURAR_SELLO=1 dotnet test tests/Avacom.Ops.Host.Tests")
        sol = s.leer_solicitud(ruta.read_bytes())
        self.assertEqual(sol.serie, "OPS-0001")
        self.assertEqual(sol.uefi_id, "AVACOM-OPS-00001234")             # el identificador que el equipo leyo de su firmware viaja firmado en la solicitud
        self.assertIsNotNone(sol.cifrado_publica)
        self.assertEqual(len(sol.clave_huella), 32)
