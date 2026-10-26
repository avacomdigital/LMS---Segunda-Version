"""
Genera `tests/vectors.h` con vectores de prueba CONOCIDOS para las pruebas en C.

Los vectores de las normas (RFC 8032 §7.1, borrador IRTF-CFRG XChaCha §A.3.1, RFC 4231 caso 1) se escriben aquí a mano, tal como los publican las normas, y cada uno se
CONTRASTA antes de emitirse con una implementación independiente (`cryptography`: OpenSSL para Ed25519, HMAC y ChaCha20-Poly1305; HChaCha20 hecho aquí). Si alguno no coincide
con la implementación independiente, este script se detiene y NO emite el archivo: así un vector mal transcrito no puede pasar por «vector oficial».

Uso:  python tools/gen_vectors.py          (desde native/avacom-lic; usa el Python del backend, que ya trae `cryptography`)
"""
from __future__ import annotations

import hashlib
import hmac
import struct
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

# --------------------------------------------------------------------------------------------------------------------------- RFC 8032 §7.1
RFC8032 = [
    ("test 1", "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("test 2", "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("test SHA(abc)", "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42", "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
     "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
     "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b58909351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704"),
]

# --------------------------------------------------------------------------------------------------------------------------- XChaCha20-Poly1305 (draft-irtf-cfrg-xchacha §A.3.1)
XC_KEY = "808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f"
XC_NONCE = "404142434445464748494a4b4c4d4e4f5051525354555657"
XC_AAD = "50515253c0c1c2c3c4c5c6c7"
XC_PT = b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, sunscreen would be it."
XC_CT = ("bd6d179d3e83d43b9576579493c0e939572a1700252bfaccbed2902c21396cbb731c7f1b0b4aa6440bf3a82f4eda7e39ae64c6708c54c216cb96b72e1213b4522f8c9ba40db5d945b11b69b982c1bb9"
         "e3f3fac2bc369488f76b2383565d3fff921f9664c97637da9768812f615c68b13b52e")
XC_TAG = "c0875924c1c7987947deafd8780acf49"

# --------------------------------------------------------------------------------------------------------------------------- RFC 4231 caso 1 (HMAC-SHA-512)
HMAC_KEY = "0b" * 20
HMAC_MSG = b"Hi There"
HMAC_OUT = "87aa7cdea5ef619d4ff0b4241a1d6cb02379f4e2ce4ec2787ad0b30545e17cdedaa833b7d6b8a702038b274eaea3f4e4be9d914eeb61f1702e696c203a126854"


def hchacha20(key: bytes, nonce16: bytes) -> bytes:
    def rot(v, n):
        return ((v << n) & 0xFFFFFFFF) | (v >> (32 - n))
    s = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574, *struct.unpack("<8I", key), *struct.unpack("<4I", nonce16)]

    def q(a, b, c, d):
        s[a] = (s[a] + s[b]) & 0xFFFFFFFF; s[d] = rot(s[d] ^ s[a], 16)
        s[c] = (s[c] + s[d]) & 0xFFFFFFFF; s[b] = rot(s[b] ^ s[c], 12)
        s[a] = (s[a] + s[b]) & 0xFFFFFFFF; s[d] = rot(s[d] ^ s[a], 8)
        s[c] = (s[c] + s[d]) & 0xFFFFFFFF; s[b] = rot(s[b] ^ s[c], 7)
    for _ in range(10):
        q(0, 4, 8, 12); q(1, 5, 9, 13); q(2, 6, 10, 14); q(3, 7, 11, 15)
        q(0, 5, 10, 15); q(1, 6, 11, 12); q(2, 7, 8, 13); q(3, 4, 9, 14)
    return struct.pack("<8I", *s[0:4], *s[12:16])


def c_array(nombre: str, datos: bytes) -> str:
    cuerpo = ", ".join(f"0x{b:02x}" for b in datos) if datos else "0"
    return f"static const uint8_t {nombre}[{max(len(datos), 1)}] = {{{cuerpo}}};\nstatic const size_t {nombre}_len = {len(datos)};\n"


def main() -> int:
    salida = ["/* GENERADO por tools/gen_vectors.py: no editar a mano. Cada vector se contrasto con una implementacion independiente antes de emitirse. */\n"]
    for i, (nombre, semilla, publica, mensaje, firma) in enumerate(RFC8032):
        llave = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(semilla))
        pub_real = llave.public_key().public_bytes_raw().hex()
        firma_real = llave.sign(bytes.fromhex(mensaje)).hex()
        if pub_real != publica or firma_real != firma:
            print(f"RFC 8032 · {nombre}: NO coincide con la implementacion independiente "
                  f"(publica {'ok' if pub_real == publica else 'distinta'}, firma {'ok' if firma_real == firma else 'distinta'}); el vector se descarta")
            continue
        salida.append(f"/* RFC 8032 sec. 7.1 - {nombre} */\n")
        for campo, valor in (("seed", semilla), ("pub", publica), ("msg", mensaje), ("sig", firma)):
            salida.append(c_array(f"RFC8032_{i}_{campo}", bytes.fromhex(valor)))
        print(f"RFC 8032 · {nombre}: confirmado")
    sub = hchacha20(bytes.fromhex(XC_KEY), bytes.fromhex(XC_NONCE)[:16])
    cifrado = ChaCha20Poly1305(sub).encrypt(b"\x00\x00\x00\x00" + bytes.fromhex(XC_NONCE)[16:], XC_PT, bytes.fromhex(XC_AAD))
    if cifrado[:-16].hex() != XC_CT or cifrado[-16:].hex() != XC_TAG:
        print("XChaCha20-Poly1305 A.3.1: NO coincide con la implementacion independiente; se detiene")
        return 1
    print("XChaCha20-Poly1305 A.3.1: confirmado")
    for campo, valor in (("KEY", bytes.fromhex(XC_KEY)), ("NONCE", bytes.fromhex(XC_NONCE)), ("AAD", bytes.fromhex(XC_AAD)), ("PT", XC_PT), ("CT", bytes.fromhex(XC_CT)),
                         ("TAG", bytes.fromhex(XC_TAG))):
        salida.append(c_array(f"XCHACHA_{campo}", valor))
    if hmac.new(bytes.fromhex(HMAC_KEY), HMAC_MSG, hashlib.sha512).hexdigest() != HMAC_OUT:
        print("HMAC-SHA-512 RFC 4231 caso 1: NO coincide; se detiene")
        return 1
    print("HMAC-SHA-512 RFC 4231 caso 1: confirmado")
    for campo, valor in (("KEY", bytes.fromhex(HMAC_KEY)), ("MSG", HMAC_MSG), ("OUT", bytes.fromhex(HMAC_OUT))):
        salida.append(c_array(f"HMAC512_{campo}", valor))
    destino = Path(__file__).resolve().parent.parent / "tests" / "vectors.h"
    destino.write_text("".join(salida), encoding="ascii")
    print(f"-> {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
