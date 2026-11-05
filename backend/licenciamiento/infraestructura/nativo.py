r"""
La biblioteca nativa `avacom_lic` vista desde el nodo (MOD-018, Fase 4, P-20 a P-22), y SU GEMELO DE REFERENCIA en Python.

  · `Nativa`        el envoltorio de `ctypes` sobre `avacom_lic.dll` (Windows) o `libavacom_lic.so` (Android/Linux). Carga por RUTA ABSOLUTA —nunca por el directorio actual ni por el PATH— y
                    sólo después de comprobar que su ABI es la que este código espera y que su autoprueba (`avl_selftest`: RFC 8032, XChaCha20-Poly1305, HMAC) da cero.
  · `Referencia`    las mismas funciones hechas con `cryptography`, `hashlib` y el dominio de licenciamiento. Es el respaldo y el ORÁCULO de las pruebas diferenciales: la nativa y la referencia
                    deben coincidir byte a byte (`tests/test_nativa.py`, ≥ 10 000 casos aleatorios con semilla fija).
  · `Biblioteca`    la fachada que usa el nodo: la nativa si cargó; si no, la referencia. LA NATIVA NUNCA ES OBLIGATORIA: un antivirus que se lleva la DLL, un runtime que falta o una ABI que no
                    es la esperada dejan al nodo funcionando por la referencia, con un registro y con un asiento (`integridad_alterada`, secreto `biblioteca_nativa`) si la instalación SÍ debía
                    traerla. La clase nunca se detiene por esto.

DÓNDE SE BUSCA (D-30). Instalación: `<backend>\native\avacom_lic.dll` (el build del instalador copia ahí `native\avacom-lic\dist\win-x64\avacom_lic.dll`, ver `native/avacom-lic/LEEME.md`). Si la
carpeta `native` existe pero la biblioteca no carga, la instalación la esperaba y falta o está alterada: se asienta. Si la carpeta no existe (desarrollo, instalaciones anteriores) se usa la
referencia en silencio. SÓLO fuera de producción: `AVACOM_LIC_NATIVA` (ruta absoluta) y la carpeta `native\avacom-lic\dist\<plataforma>` del repositorio; un nodo de producción no lee ninguna variable
de entorno para decidir qué biblioteca cargar (P-12).

El camino caliente no carga nada: la biblioteca se carga UNA vez por proceso, al construir los servicios (`contenedor.servicios`), y se mide (≤ +200 ms, ver 03-pruebas / 04-proteccion).
"""
from __future__ import annotations

import ctypes
import hashlib
import hmac
import logging
import os
import struct
import sys
import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..dominio import firma, huella as hu, licencia as lic_mod, smbios, solicitud as sol
from ..dominio.errores import LicenciaInvalida
from ..dominio.licencia import HuellaDeLicencia

log = logging.getLogger("avacom.licenciamiento")

ABI_ESPERADA = 1
NOMBRE_DEL_SECRETO = "avacom_lic"            # lo que `NodoDeLicencia.anotar_novedad` recibe (catalogos.NOMBRES_DE_SECRETO lo traduce a `biblioteca_nativa`)
CARPETA_EN_INSTALACION = "native"
MAX_FACTORES = 16

MOTIVOS = {-1: "demasiado_grande", -2: "demasiado_corta", -3: "formato", -4: "version_no_soportada", -5: "kid_desconocido", -6: "firma_invalida",
           -7: "etiqueta_critica_desconocida", -8: "campo_faltante", -9: "campo_invalido", -10: "tipo_no_admitido", -11: "aun_no_vigente"}
E_ARG, E_UNSUPPORTED, E_AUTH, E_SMALL = -12, -13, -14, -15
TIPOS = {1: lic_mod.TIPO_PRODUCCION, 2: lic_mod.TIPO_EVALUACION, 3: lic_mod.TIPO_DESARROLLO}


class NativaNoDisponible(Exception):
    """La nativa no puede responder ESTA llamada (no existe en esta plataforma, el buffer no alcanza…): se usa la referencia. No es un fallo del archivo."""


class ClaveAjena(Exception):
    """La etiqueta de autenticación de un `unwrap` no cuadra: la llave, el contexto o el texto no son los que se envolvieron."""


# ===================================================================================================================== estructuras (idénticas a include/avacom_lic.h)
class _Key(ctypes.Structure):
    _fields_ = [("kid", ctypes.c_char * 65), ("pub", ctypes.c_uint8 * 32)]


class _Policy(ctypes.Structure):
    _fields_ = [("now_ms", ctypes.c_uint64), ("start_tolerance_ms", ctypes.c_uint64), ("flags", ctypes.c_uint32)]


class _FpCurrent(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint8), ("factor", ctypes.c_uint8 * MAX_FACTORES), ("hash", (ctypes.c_uint8 * 32) * MAX_FACTORES), ("has_installation", ctypes.c_uint8),
                ("installation_hash", ctypes.c_uint8 * 32)]


class _License(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint8 * 16), ("serie", ctypes.c_uint32), ("issued_ms", ctypes.c_uint64), ("from_ms", ctypes.c_uint64), ("until_ms", ctypes.c_uint64),
                ("grace_days", ctypes.c_uint16), ("equipos", ctypes.c_uint32), ("usuarios", ctypes.c_uint32), ("concurrent_normal", ctypes.c_uint32),
                ("concurrent_peak", ctypes.c_uint32), ("type", ctypes.c_uint8), ("flags", ctypes.c_uint32), ("release_days", ctypes.c_uint16), ("has_node_hash", ctypes.c_uint8),
                ("node_hash", ctypes.c_uint8 * 32), ("fp_k", ctypes.c_uint8), ("fp_n", ctypes.c_uint8), ("fp_factor", ctypes.c_uint8 * MAX_FACTORES),
                ("fp_hash", (ctypes.c_uint8 * 32) * MAX_FACTORES), ("caps_len", ctypes.c_uint16), ("caps", ctypes.c_uint8 * 1024), ("aula_len", ctypes.c_uint16),
                ("aula", ctypes.c_uint8 * 480), ("kid", ctypes.c_char * 65), ("fp_checked", ctypes.c_uint8), ("fp_matches", ctypes.c_uint8), ("fp_ok", ctypes.c_uint8),
                ("fp_partial", ctypes.c_uint8), ("fp_level", ctypes.c_uint8)]


class _FpResult(ctypes.Structure):
    _fields_ = [("k", ctypes.c_uint8), ("in_license", ctypes.c_uint8), ("matches", ctypes.c_uint8), ("ok", ctypes.c_uint8), ("partial", ctypes.c_uint8), ("level", ctypes.c_uint8)]


class _Smbios(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_char * 37), ("system_serial", ctypes.c_char * 256), ("board_serial", ctypes.c_char * 256), ("chassis_serial", ctypes.c_char * 256),
                ("processor_id", ctypes.c_char * 17)]


class _Hw(ctypes.Structure):
    _fields_ = [("machine_guid", ctypes.c_char * 64), ("smbios", _Smbios)]


class _RequestIn(ctypes.Structure):
    _fields_ = [("node_seed", ctypes.c_uint8 * 32), ("nonce", ctypes.c_uint8 * 16), ("version", ctypes.c_char_p), ("version_len", ctypes.c_size_t), ("created_ms", ctypes.c_uint64),
                ("level", ctypes.c_uint8), ("fp_k", ctypes.c_uint8), ("fp_n", ctypes.c_uint8), ("fp_factor", ctypes.c_uint8 * MAX_FACTORES),
                ("fp_hash", (ctypes.c_uint8 * 32) * MAX_FACTORES), ("has_license", ctypes.c_uint8), ("license_id", ctypes.c_uint8 * 16), ("aula", ctypes.c_char_p),
                ("aula_len", ctypes.c_size_t)]


# ===================================================================================================================== resultados comunes (los que comparan las pruebas)
def _normalizar_licencia(lic: lic_mod.Licencia, coincidencia: hu.Coincidencia | None) -> dict:
    """La licencia como diccionario simple: lo que la nativa y la referencia deben devolver IGUAL."""
    return {
        "id": lic.id, "serie": lic.serie, "aula": lic.aula, "emitida": lic.emitida, "desde": lic.desde, "vence": lic.vence, "gracia_dias": lic.gracia_dias,
        "limites": (lic.limites.equipos, lic.limites.usuarios, lic.limites.concurrentes_normal, lic.limites.concurrentes_pico), "capacidades": tuple(sorted(lic.capacidades)),
        "k": lic.huella.k, "factores": tuple((f, bytes(h)) for f, h in lic.huella.factores), "tipo": lic.tipo, "liberacion_pendiente": lic.liberacion_pendiente,
        "liberacion_dias": lic.liberacion_dias, "hash_clave_nodo": bytes(lic.hash_clave_nodo) if lic.hash_clave_nodo else None, "kid": lic.kid,
        "huella": None if coincidencia is None else (coincidencia.coinciden, coincidencia.ok, coincidencia.parcial, coincidencia.nivel),
    }


@dataclass(frozen=True)
class FactoresActuales:
    """Los factores de hardware válidos de este equipo (ya hasheados) y el hash del secreto de instalación, como los entrega `huella.factores_validos`."""
    factores: Mapping[int, bytes]
    instalacion: bytes | None = None


# ===================================================================================================================== el gemelo de referencia
class Referencia:
    """Todo lo que hace la nativa, hecho con las piezas de siempre (`cryptography`, `hashlib`, el dominio). El respaldo y el oráculo de las pruebas."""

    nombre = "referencia"

    def verificar(self, clave_publica: bytes, firma_: bytes, mensaje: bytes) -> bool:
        return firma.verificar_referencia(clave_publica, firma_, mensaje)

    def licencia_verificar(self, datos: bytes, claves: Mapping[str, bytes], *, ahora: int, tolerancia_inicio: int, produccion: bool, comprobar_inicio: bool,
                           actuales: FactoresActuales | None = None) -> dict:
        lic = lic_mod.leer(bytes(datos), claves, firma.verificar_referencia)
        if produccion and lic.tipo == lic_mod.TIPO_DESARROLLO:
            raise LicenciaInvalida("tipo_no_admitido")
        if comprobar_inicio and lic.desde > ahora + tolerancia_inicio:
            raise LicenciaInvalida("aun_no_vigente")
        coincidencia = hu.comparar(lic.huella, dict(actuales.factores), actuales.instalacion) if actuales is not None else None
        return _normalizar_licencia(lic, coincidencia)

    def huella_comparar(self, k: int, factores: Sequence[tuple[int, bytes]], actuales: FactoresActuales) -> tuple[int, bool, bool, str]:
        c = hu.comparar(HuellaDeLicencia(k, tuple(factores)), dict(actuales.factores), actuales.instalacion)
        return c.coinciden, c.ok, c.parcial, c.nivel

    def smbios(self, tabla: bytes) -> dict[str, str]:
        return smbios.leer_tabla(bytes(tabla))

    def construir_solicitud(self, clave_privada: bytes, *, nonce: bytes, version_nodo: str, creada: int, nivel: str, huella: HuellaDeLicencia, licencia_vigente: str | None = None,
                            aula: str = "") -> bytes:
        return sol.construir_solicitud(clave_privada, nonce=nonce, version_nodo=version_nodo, creada=creada, nivel=nivel, huella=huella, licencia_vigente=licencia_vigente, aula=aula)

    @staticmethod
    def _mac_ancla(secreto: bytes, marca: int, instalada_en: int | None) -> bytes:
        llave = hashlib.sha512(b"avl-ancla-v2|" + bytes(secreto)).digest()[:32]
        mensaje = struct.pack(">QQB", int(marca), int(instalada_en or 0), 1 if instalada_en is not None else 0)
        return hmac.new(llave, mensaje, hashlib.sha512).digest()[:32]

    def avance_de_reloj(self, secreto: bytes, marca_previa: int, mac_previo: bytes | None, instalada_en: int | None, candidata: int) -> tuple[int, bytes, bool]:
        """Ancla v2: `(marca siguiente, MAC, ¿el ancla previa cuadraba?)`. Un ancla alterada no cuenta: no aporta marca."""
        ok = True
        if mac_previo is not None:
            ok = hmac.compare_digest(self._mac_ancla(secreto, marca_previa, instalada_en), bytes(mac_previo))
        base = marca_previa if ok else 0
        siguiente = max(int(candidata), int(base))
        return siguiente, self._mac_ancla(secreto, siguiente, instalada_en), ok

    def derivar(self, secreto: bytes, sal: bytes, info: bytes, largo: int) -> bytes:
        return HKDF(algorithm=hashes.SHA512(), length=largo, salt=bytes(sal), info=bytes(info)).derive(bytes(secreto))

    @staticmethod
    def _hchacha20(llave: bytes, nonce16: bytes) -> bytes:
        def rot(v, n):
            return ((v << n) & 0xFFFFFFFF) | (v >> (32 - n))

        s = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574, *struct.unpack("<8I", llave), *struct.unpack("<4I", nonce16)]

        def cuarto(a, b, c, d):
            s[a] = (s[a] + s[b]) & 0xFFFFFFFF; s[d] = rot(s[d] ^ s[a], 16)
            s[c] = (s[c] + s[d]) & 0xFFFFFFFF; s[b] = rot(s[b] ^ s[c], 12)
            s[a] = (s[a] + s[b]) & 0xFFFFFFFF; s[d] = rot(s[d] ^ s[a], 8)
            s[c] = (s[c] + s[d]) & 0xFFFFFFFF; s[b] = rot(s[b] ^ s[c], 7)

        for _ in range(10):
            cuarto(0, 4, 8, 12); cuarto(1, 5, 9, 13); cuarto(2, 6, 10, 14); cuarto(3, 7, 11, 15)
            cuarto(0, 5, 10, 15); cuarto(1, 6, 11, 12); cuarto(2, 7, 8, 13); cuarto(3, 4, 9, 14)
        return struct.pack("<8I", *s[0:4], *s[12:16])

    def envolver(self, llave: bytes, nonce: bytes, contexto: bytes, claro: bytes) -> bytes:
        """XChaCha20-Poly1305 (borrador IRTF-CFRG): HChaCha20 + ChaCha20-Poly1305 de `cryptography`. Formato: nonce(24) · texto cifrado · etiqueta(16)."""
        sub = self._hchacha20(bytes(llave), bytes(nonce[:16]))
        return bytes(nonce) + ChaCha20Poly1305(sub).encrypt(b"\x00\x00\x00\x00" + bytes(nonce[16:24]), bytes(claro), bytes(contexto))

    def desenvolver(self, llave: bytes, contexto: bytes, envuelto: bytes) -> bytes:
        if len(envuelto) < 40:
            raise ValueError("envoltura demasiado corta")
        sub = self._hchacha20(bytes(llave), bytes(envuelto[:16]))
        try:
            return ChaCha20Poly1305(sub).decrypt(b"\x00\x00\x00\x00" + bytes(envuelto[16:24]), bytes(envuelto[24:]), bytes(contexto))
        except Exception:   # noqa: BLE001 — `cryptography` lanza InvalidTag
            raise ClaveAjena() from None

    def recolectar_hardware(self) -> tuple[str, dict[str, str]]:
        """`(MachineGuid, tabla SMBIOS interpretada)` con la lectura de siempre (`huella_windows`)."""
        from . import huella_windows as hw
        return hw.machine_guid(), smbios.leer_tabla(hw.tabla_smbios())


# ===================================================================================================================== el envoltorio de la nativa
def _texto_cadena(crudo: bytes) -> str:
    return crudo.decode("utf-8", "replace").strip()


class Nativa:
    nombre = "nativa"

    def __init__(self, dll: ctypes.CDLL, ruta: Path):
        self.ruta = ruta
        self._d = dll
        d = dll
        c = ctypes
        pu8 = c.POINTER(c.c_uint8)
        d.avl_abi_version.restype = c.c_uint32
        d.avl_abi_version.argtypes = []
        d.avl_selftest.restype = c.c_int
        d.avl_selftest.argtypes = []
        d.avl_verify_detached.restype = c.c_int
        d.avl_verify_detached.argtypes = [c.c_char_p, c.c_size_t, c.c_char_p, c.c_char_p]
        d.avl_license_verify.restype = c.c_int
        d.avl_license_verify.argtypes = [c.c_char_p, c.c_size_t, c.POINTER(_Key), c.c_size_t, c.POINTER(_Policy), c.POINTER(_FpCurrent), c.POINTER(_License)]
        d.avl_fp_match.restype = c.c_int
        d.avl_fp_match.argtypes = [c.c_uint8, c.c_uint8, c.c_void_p, c.c_void_p, c.POINTER(_FpCurrent), c.POINTER(_FpResult)]
        d.avl_smbios_parse.restype = c.c_int
        d.avl_smbios_parse.argtypes = [c.c_char_p, c.c_size_t, c.POINTER(_Smbios)]
        d.avl_fp_collect.restype = c.c_int
        d.avl_fp_collect.argtypes = [c.POINTER(_Hw)]
        d.avl_request_build.restype = c.c_int
        d.avl_request_build.argtypes = [c.POINTER(_RequestIn), c.c_void_p, c.POINTER(c.c_size_t)]
        d.avl_clock_advance.restype = c.c_int
        d.avl_clock_advance.argtypes = [c.c_char_p, c.c_size_t, c.c_uint64, c.c_char_p, c.c_uint64, c.c_uint8, c.c_uint64, c.POINTER(c.c_uint64), c.c_void_p, c.POINTER(c.c_uint8)]
        d.avl_key_derive.restype = c.c_int
        d.avl_key_derive.argtypes = [c.c_char_p, c.c_size_t, c.c_char_p, c.c_size_t, c.c_char_p, c.c_size_t, c.c_void_p, c.c_size_t]
        d.avl_key_wrap.restype = c.c_int
        d.avl_key_wrap.argtypes = [c.c_char_p, c.c_char_p, c.c_char_p, c.c_size_t, c.c_char_p, c.c_size_t, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
        d.avl_key_unwrap.restype = c.c_int
        d.avl_key_unwrap.argtypes = [c.c_char_p, c.c_char_p, c.c_size_t, c.c_char_p, c.c_size_t, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
        d.avl_wipe.restype = None
        d.avl_wipe.argtypes = [c.c_void_p, c.c_size_t]
        del pu8

    # ---- identidad
    def abi(self) -> int:
        return int(self._d.avl_abi_version())

    def selftest(self) -> int:
        return int(self._d.avl_selftest())

    # ---- firma
    def verificar(self, clave_publica: bytes, firma_: bytes, mensaje: bytes) -> bool:
        if len(clave_publica) != 32 or len(firma_) != 64:
            return False
        return self._d.avl_verify_detached(bytes(mensaje), len(mensaje), bytes(firma_), bytes(clave_publica)) == 0

    # ---- licencia
    @staticmethod
    def _actuales(actuales: FactoresActuales | None):
        if actuales is None:
            return None
        s = _FpCurrent()
        items = sorted(actuales.factores.items())
        if len(items) > MAX_FACTORES:
            raise NativaNoDisponible("demasiados factores")
        s.count = len(items)
        for i, (f, h) in enumerate(items):
            s.factor[i] = f
            ctypes.memmove(s.hash[i], bytes(h), 32)
        if actuales.instalacion is not None:
            s.has_installation = 1
            ctypes.memmove(s.installation_hash, bytes(actuales.instalacion), 32)
        return s

    def licencia_verificar(self, datos: bytes, claves: Mapping[str, bytes], *, ahora: int, tolerancia_inicio: int, produccion: bool, comprobar_inicio: bool,
                           actuales: FactoresActuales | None = None) -> dict:
        if len(claves) > 64:
            raise NativaNoDisponible("demasiadas llaves")
        arreglo = (_Key * max(len(claves), 1))()
        for i, (kid, pub) in enumerate(claves.items()):
            codigo = kid.encode("ascii", "replace")
            if len(codigo) > 64 or len(pub) != 32:
                raise NativaNoDisponible("llave fuera de rango")
            arreglo[i].kid = codigo
            ctypes.memmove(arreglo[i].pub, bytes(pub), 32)
        politica = _Policy(int(ahora), int(tolerancia_inicio), (1 if produccion else 0) | (2 if comprobar_inicio else 0))
        fp = self._actuales(actuales)
        salida = _License()
        datos = bytes(datos)
        rc = self._d.avl_license_verify(datos, len(datos), arreglo, len(claves), ctypes.byref(politica), ctypes.byref(fp) if fp is not None else None, ctypes.byref(salida))
        if rc != 0:
            if rc in MOTIVOS:
                raise LicenciaInvalida(MOTIVOS[rc])
            raise NativaNoDisponible(f"avl_license_verify devolvió {rc}")
        caps, pos, crudas = bytes(salida.caps[:salida.caps_len]), 0, []
        while pos < len(caps):
            largo = caps[pos]
            crudas.append(caps[pos + 1:pos + 1 + largo].decode("ascii"))
            pos += 1 + largo
        k, n = int(salida.fp_k), int(salida.fp_n)
        return {
            "id": str(uuid.UUID(bytes=bytes(salida.id))), "serie": int(salida.serie), "aula": bytes(salida.aula[:salida.aula_len]).decode("utf-8"), "emitida": int(salida.issued_ms),
            "desde": int(salida.from_ms), "vence": int(salida.until_ms), "gracia_dias": int(salida.grace_days),
            "limites": (int(salida.equipos), int(salida.usuarios), int(salida.concurrent_normal), int(salida.concurrent_peak)), "capacidades": tuple(sorted(crudas)), "k": k,
            "factores": tuple((int(salida.fp_factor[i]), bytes(salida.fp_hash[i])) for i in range(n)), "tipo": TIPOS[int(salida.type)],
            "liberacion_pendiente": bool(salida.flags & 1), "liberacion_dias": int(salida.release_days),
            "hash_clave_nodo": bytes(salida.node_hash) if salida.has_node_hash else None, "kid": salida.kid.decode("ascii"),
            "huella": ((int(salida.fp_matches), bool(salida.fp_ok), bool(salida.fp_partial), hu.NIVEL_INSTALACION if salida.fp_level == 2 else hu.NIVEL_HARDWARE) if salida.fp_checked
                       else None),
        }

    # ---- huella
    def huella_comparar(self, k: int, factores: Sequence[tuple[int, bytes]], actuales: FactoresActuales) -> tuple[int, bool, bool, str]:
        n = len(factores)
        if n > MAX_FACTORES:
            raise NativaNoDisponible("demasiados factores")
        fa = (ctypes.c_uint8 * MAX_FACTORES)()
        ha = ((ctypes.c_uint8 * 32) * MAX_FACTORES)()
        for i, (f, h) in enumerate(factores):
            fa[i] = f
            ctypes.memmove(ha[i], bytes(h), 32)
        cur = self._actuales(actuales)
        r = _FpResult()
        rc = self._d.avl_fp_match(k, n, ctypes.addressof(fa), ctypes.addressof(ha), ctypes.byref(cur), ctypes.byref(r))
        if rc != 0:
            raise NativaNoDisponible(f"avl_fp_match devolvió {rc}")
        return int(r.matches), bool(r.ok), bool(r.partial), hu.NIVEL_INSTALACION if r.level == 2 else hu.NIVEL_HARDWARE

    def smbios(self, tabla: bytes) -> dict[str, str]:
        s = _Smbios()
        rc = self._d.avl_smbios_parse(bytes(tabla), len(tabla), ctypes.byref(s))
        if rc != 0:
            raise NativaNoDisponible(f"avl_smbios_parse devolvió {rc}")
        return {"smbios_uuid": s.uuid.decode("ascii"), "sistema_serie": _texto_cadena(s.system_serial), "placa_serie": _texto_cadena(s.board_serial),
                "chasis_serie": _texto_cadena(s.chassis_serial), "procesador_id": s.processor_id.decode("ascii")}

    def recolectar_hardware(self) -> tuple[str, dict[str, str]]:
        hw = _Hw()
        rc = self._d.avl_fp_collect(ctypes.byref(hw))
        if rc != 0:
            raise NativaNoDisponible(f"avl_fp_collect devolvió {rc}")
        s = hw.smbios
        return hw.machine_guid.decode("utf-8", "replace"), {
            "smbios_uuid": s.uuid.decode("ascii"), "sistema_serie": _texto_cadena(s.system_serial), "placa_serie": _texto_cadena(s.board_serial),
            "chasis_serie": _texto_cadena(s.chassis_serial), "procesador_id": s.processor_id.decode("ascii")}

    # ---- solicitud
    def construir_solicitud(self, clave_privada: bytes, *, nonce: bytes, version_nodo: str, creada: int, nivel: str, huella: HuellaDeLicencia, licencia_vigente: str | None = None,
                            aula: str = "") -> bytes:
        if len(nonce) != 16 or len(clave_privada) != 32 or not 1 <= len(huella.factores) <= MAX_FACTORES or not 1 <= huella.k <= len(huella.factores):
            raise NativaNoDisponible("argumentos fuera de rango")
        e = _RequestIn()
        ctypes.memmove(e.node_seed, bytes(clave_privada), 32)
        ctypes.memmove(e.nonce, bytes(nonce), 16)
        version = version_nodo.encode("utf-8") if version_nodo else b""
        texto_aula = aula.encode("utf-8") if aula else b""
        e.version, e.version_len = (version or None), len(version)
        e.aula, e.aula_len = (texto_aula or None), len(texto_aula)
        e.created_ms = int(creada)
        e.level = {hu.NIVEL_HARDWARE: 1, hu.NIVEL_INSTALACION: 2}[nivel]
        e.fp_k, e.fp_n = huella.k, len(huella.factores)
        for i, (f, h) in enumerate(huella.factores):
            e.fp_factor[i] = f
            ctypes.memmove(e.fp_hash[i], bytes(h), 32)
        if licencia_vigente:
            e.has_license = 1
            ctypes.memmove(e.license_id, uuid.UUID(licencia_vigente).bytes, 16)
        capacidad = ctypes.c_size_t(16 * 1024)
        buf = (ctypes.c_uint8 * capacidad.value)()
        rc = self._d.avl_request_build(ctypes.byref(e), ctypes.addressof(buf), ctypes.byref(capacidad))
        if rc != 0:
            raise NativaNoDisponible(f"avl_request_build devolvió {rc}")
        return bytes(buf[:capacidad.value])

    # ---- reloj
    def avance_de_reloj(self, secreto: bytes, marca_previa: int, mac_previo: bytes | None, instalada_en: int | None, candidata: int) -> tuple[int, bytes, bool]:
        siguiente, mac, ok = ctypes.c_uint64(), (ctypes.c_uint8 * 32)(), ctypes.c_uint8()
        rc = self._d.avl_clock_advance(bytes(secreto), len(secreto), int(marca_previa), bytes(mac_previo) if mac_previo is not None else None, int(instalada_en or 0),
                                       1 if instalada_en is not None else 0, int(candidata), ctypes.byref(siguiente), ctypes.addressof(mac), ctypes.byref(ok))
        if rc != 0:
            raise NativaNoDisponible(f"avl_clock_advance devolvió {rc}")
        return int(siguiente.value), bytes(mac), bool(ok.value)

    # ---- llaves
    def derivar(self, secreto: bytes, sal: bytes, info: bytes, largo: int) -> bytes:
        salida = (ctypes.c_uint8 * largo)()
        rc = self._d.avl_key_derive(bytes(secreto), len(secreto), bytes(sal) or None, len(sal), bytes(info) or None, len(info), ctypes.addressof(salida), largo)
        if rc != 0:
            raise NativaNoDisponible(f"avl_key_derive devolvió {rc}")
        return bytes(salida)

    def envolver(self, llave: bytes, nonce: bytes, contexto: bytes, claro: bytes) -> bytes:
        salida = (ctypes.c_uint8 * (len(claro) + 40))()
        largo = ctypes.c_size_t()
        rc = self._d.avl_key_wrap(bytes(llave), bytes(nonce), bytes(contexto) or None, len(contexto), bytes(claro) or None, len(claro), ctypes.addressof(salida), len(salida),
                                  ctypes.byref(largo))
        if rc != 0:
            raise NativaNoDisponible(f"avl_key_wrap devolvió {rc}")
        return bytes(salida[:largo.value])

    def desenvolver(self, llave: bytes, contexto: bytes, envuelto: bytes) -> bytes:
        salida = (ctypes.c_uint8 * max(len(envuelto), 1))()
        largo = ctypes.c_size_t()
        rc = self._d.avl_key_unwrap(bytes(llave), bytes(contexto) or None, len(contexto), bytes(envuelto), len(envuelto), ctypes.addressof(salida), len(salida), ctypes.byref(largo))
        if rc == E_AUTH:
            raise ClaveAjena()
        if rc != 0:
            raise NativaNoDisponible(f"avl_key_unwrap devolvió {rc}")
        resultado = bytes(salida[:largo.value])
        self._d.avl_wipe(ctypes.addressof(salida), len(salida))
        return resultado


# ===================================================================================================================== la fachada
class Biblioteca:
    """La nativa si cargó y respondió; si no, la referencia. Nada de esto está en el camino de arranque de una clase: una excepción de la nativa se traga y se usa el gemelo."""

    def __init__(self, nativa: Nativa | None, motivo: str | None = None, esperada: bool = False):
        self.nativa = nativa
        self.motivo = motivo                    # por qué NO se cargó (None si cargó, o si ni se buscó)
        self.esperada = esperada                # la instalación debía traerla: si falta o falla, se asienta
        self.referencia = Referencia()
        self._avisos: set[str] = set()

    @property
    def activa(self) -> bool:
        return self.nativa is not None

    def _llamar(self, nombre: str, *args, **kwargs):
        if self.nativa is not None:
            try:
                return getattr(self.nativa, nombre)(*args, **kwargs)
            except NativaNoDisponible:
                pass
            except (OSError, ctypes.ArgumentError, ValueError, TypeError, OverflowError) as error:
                if nombre not in self._avisos:
                    self._avisos.add(nombre)
                    log.warning("La biblioteca nativa falló en %s (%s): se usa la referencia", nombre, error.__class__.__name__,
                                extra={"evento": "licencia.nativa_fallo", "ruta": "bad"})
        return getattr(self.referencia, nombre)(*args, **kwargs)

    def verificar(self, clave_publica: bytes, firma_: bytes, mensaje: bytes) -> bool:
        return self._llamar("verificar", clave_publica, firma_, mensaje)

    def licencia_verificar(self, *args, **kwargs) -> dict:
        return self._llamar("licencia_verificar", *args, **kwargs)

    def huella_comparar(self, *args, **kwargs):
        return self._llamar("huella_comparar", *args, **kwargs)

    def smbios(self, tabla: bytes) -> dict[str, str]:
        return self._llamar("smbios", tabla)

    def recolectar_hardware(self) -> tuple[str, dict[str, str]]:
        return self._llamar("recolectar_hardware")

    def construir_solicitud(self, *args, **kwargs) -> bytes:
        return self._llamar("construir_solicitud", *args, **kwargs)

    def avance_de_reloj(self, *args, **kwargs):
        return self._llamar("avance_de_reloj", *args, **kwargs)

    def derivar(self, *args, **kwargs) -> bytes:
        return self._llamar("derivar", *args, **kwargs)

    def envolver(self, *args, **kwargs) -> bytes:
        return self._llamar("envolver", *args, **kwargs)

    def desenvolver(self, *args, **kwargs) -> bytes:
        return self._llamar("desenvolver", *args, **kwargs)


# ===================================================================================================================== carga
_WIN = sys.platform == "win32"
_PLATAFORMA = "win-x64" if _WIN else "linux-x86_64"
_ARCHIVO = "avacom_lic.dll" if _WIN else "libavacom_lic.so"
LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR, LOAD_LIBRARY_SEARCH_DEFAULT_DIRS = 0x00000100, 0x00001000

_candado = threading.Lock()
_biblioteca: Biblioteca | None = None


def _raiz_backend() -> Path:
    return Path(__file__).resolve().parents[2]


def candidatas(entorno: str, raiz: Path | None = None) -> tuple[list[Path], bool]:
    """`(rutas absolutas a probar, ¿la instalación la esperaba?)`. Ninguna sale del directorio actual ni del PATH."""
    raiz = (raiz or _raiz_backend()).resolve()
    en_instalacion = raiz / CARPETA_EN_INSTALACION
    rutas = [en_instalacion / _ARCHIVO]
    if entorno != "produccion":
        propia = os.environ.get("AVACOM_LIC_NATIVA", "").strip()
        if propia and Path(propia).is_absolute():
            rutas.insert(0, Path(propia))
        rutas.append(raiz.parent / "native" / "avacom-lic" / "dist" / _PLATAFORMA / _ARCHIVO)
    return rutas, en_instalacion.is_dir()


def _cargar_ruta(ruta: Path) -> Nativa:
    if not ruta.is_absolute() or not ruta.is_file():
        raise FileNotFoundError(str(ruta))
    if _WIN:
        dll = ctypes.CDLL(str(ruta), winmode=LOAD_LIBRARY_SEARCH_DEFAULT_DIRS | LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR)     # ruta absoluta y sólo directorios del sistema como dependencias
    else:
        dll = ctypes.CDLL(str(ruta))
    nativa = Nativa(dll, ruta)
    if nativa.abi() != ABI_ESPERADA:
        raise OSError(f"ABI {nativa.abi()} (se esperaba {ABI_ESPERADA})")
    paso = nativa.selftest()
    if paso != 0:
        raise OSError(f"la autoprueba de la biblioteca falló ({paso})")
    return nativa


def cargar(entorno: str, raiz: Path | None = None) -> Biblioteca:
    """Intenta cargar la nativa; si no se puede, devuelve una `Biblioteca` que usa la referencia y dice por qué. NUNCA lanza."""
    rutas, esperada = candidatas(entorno, raiz)
    motivo = "no_encontrada"
    for ruta in rutas:
        if not ruta.is_file():
            continue
        try:
            nativa = _cargar_ruta(ruta)
            log.info("Biblioteca nativa cargada: %s", ruta.name, extra={"evento": "licencia.nativa_cargada", "ruta": "ok"})
            return Biblioteca(nativa, None, esperada)
        except Exception as error:   # noqa: BLE001 — un antivirus, una ABI distinta, una DLL dañada: se sigue con la referencia
            motivo = f"{error.__class__.__name__}"
            log.warning("La biblioteca nativa no cargó (%s): el nodo sigue con la referencia", motivo, extra={"evento": "licencia.nativa_no_cargada", "ruta": "bad"})
    if esperada:
        log.error("La instalación debía traer la biblioteca nativa y no carga (%s): se usa la referencia y se asienta", motivo,
                  extra={"evento": "licencia.nativa_no_cargada", "ruta": "bad"})
    return Biblioteca(None, motivo, esperada)


def preparar(entorno: str, raiz: Path | None = None) -> Biblioteca:
    """La biblioteca de este proceso: se carga UNA vez (fuera del camino caliente) y se engancha como verificador de firmas del dominio."""
    global _biblioteca
    with _candado:
        if _biblioteca is None:
            _biblioteca = cargar(entorno, raiz)
            firma.instalar_verificador_alterno(_biblioteca.nativa.verificar if _biblioteca.nativa is not None else None)
        return _biblioteca


def actual() -> Biblioteca | None:
    return _biblioteca


def olvidar() -> None:
    """Para las pruebas: descarta lo cargado y quita el verificador alterno."""
    global _biblioteca
    with _candado:
        _biblioteca = None
        firma.instalar_verificador_alterno(None)


def informar_al_nodo(biblioteca: Biblioteca, nodo) -> None:
    """Si la instalación esperaba la nativa y no cargó, lo deja como novedad del nodo: la evaluación lo asienta una vez como `integridad_alterada` (sin contenido ni rutas)."""
    if biblioteca.esperada and not biblioteca.activa:
        nodo.anotar_novedad(NOMBRE_DEL_SECRETO)


__all__ = ["Biblioteca", "ClaveAjena", "FactoresActuales", "Nativa", "NativaNoDisponible", "Referencia", "actual", "candidatas", "cargar", "informar_al_nodo", "olvidar", "preparar"]
