# Monocypher (criptografía vendida y fijada)

| | |
|---|---|
| Biblioteca | **Monocypher 4.0.2** (Loup Vaillant), BSD-2-Clause o CC0 (a elegir) |
| Origen | https://github.com/LoupVaillant/Monocypher/archive/refs/tags/4.0.2.tar.gz (descargado el 2026-10-22) |
| Qué se usa | EdDSA **con SHA-512 (RFC 8032)** de `optional/monocypher-ed25519`, XChaCha20-Poly1305 (`crypto_aead_*`), BLAKE2b, comparaciones en tiempo constante, `crypto_wipe`, HMAC-SHA-512 y HKDF-SHA-512 |
| Trampa | La EdDSA por defecto de Monocypher (`crypto_eddsa_*`) usa BLAKE2b y **no** verifica firmas de `cryptography`. Aquí sólo se llama a `crypto_ed25519_*`; las pruebas lo demuestran con los vectores del RFC 8032 y con firmas reales de Python |
| Modificaciones | **Ninguna.** Los archivos son los del tarball, byte a byte |

SHA-256 de cada archivo (si cambia un solo byte, `Build-Native.ps1` no debe usarse hasta saber por qué):

| Archivo | SHA-256 |
|---|---|
| `monocypher.c` | `02174117935699d418443c75a558a287deb06ef8cf7c1adced61d9047d2f323d` |
| `monocypher.h` | `fcaf6ed771358bb4f40fba016f6518ae86ec02b1b877d2cc35ad92d3a26fd7b3` |
| `monocypher-ed25519.c` | `97d581639dfa72be08a6d57deb7d79b736be001cb416819cab196d22559d242b` |
| `monocypher-ed25519.h` | `3a3035181f991a158d0e1c7567258f0bae8ba0f1f23c5512b4a1db1b3c9730ce` |
| `LICENCE.md` | `a5781770269d2516e52ba4863f790c10a16da4089a1e81823aee19ff1e9026b0` |

Para comprobarlo: `Get-FileHash vendor\*.c, vendor\*.h, vendor\LICENCE.md -Algorithm SHA256`.

Para actualizar Monocypher: sustituir los cuatro archivos por los de la versión nueva, anotar aquí versión y hashes, y volver a pasar `Probar-Native.ps1` y `manage.py test licenciamiento.tests.test_nativa` completos
(los vectores y los 35 000 casos diferenciales son lo que detecta un cambio de comportamiento).
