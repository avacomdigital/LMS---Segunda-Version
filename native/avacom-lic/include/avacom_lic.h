/*
 * avacom_lic · biblioteca nativa de licenciamiento de AVACOM LMS (MOD-018, Fase 4, P-20).
 *
 * Una sola implementacion del formato y de la verificacion para tres consumidores: el backend (ctypes), el Host y Core (P/Invoke).
 * Criptografia vendida y fijada: Monocypher 4.0.2 (EdDSA con SHA-512 = RFC 8032, XChaCha20-Poly1305, BLAKE2b, HKDF-SHA-512).
 *
 * Reglas: C11, sin malloc, sin estado global, sin cadenas de error (todo error es un entero), simbolos ocultos salvo avl_*.
 * LA NATIVA NUNCA ES OBLIGATORIA: cada funcion tiene un gemelo de referencia (Python en backend/licenciamiento/infraestructura/nativo.py,
 * C# en Core) y si esta biblioteca no carga el nodo sigue por la referencia. Por eso el contrato esta escrito aqui con precision:
 * el gemelo y la nativa deben coincidir byte a byte (pruebas diferenciales en backend/licenciamiento/tests/test_nativa.py).
 *
 * Convenciones: enteros multi-byte del formato en orden de red (big endian); los de las estructuras, en el orden de la maquina.
 * Retorno: 0 = correcto; negativo = error (AVL_E_*). Un puntero nulo con largo cero es una entrada vacia valida donde se dice.
 */
#ifndef AVACOM_LIC_H
#define AVACOM_LIC_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#  define AVL_API __declspec(dllexport)
#elif defined(__GNUC__)
#  define AVL_API __attribute__((visibility("default")))
#else
#  define AVL_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define AVL_ABI_VERSION 1u

/* ---- errores (los de licencia coinciden con los `motivo` de dominio/errores.py) ------------------------------------------------- */
#define AVL_OK                         0
#define AVL_E_TOO_BIG                 -1   /* demasiado_grande */
#define AVL_E_TOO_SHORT               -2   /* demasiado_corta */
#define AVL_E_FORMAT                  -3   /* formato */
#define AVL_E_VERSION                 -4   /* version_no_soportada */
#define AVL_E_KID_UNKNOWN             -5   /* kid_desconocido */
#define AVL_E_SIGNATURE               -6   /* firma_invalida */
#define AVL_E_CRITICAL_TAG            -7   /* etiqueta_critica_desconocida */
#define AVL_E_MISSING                 -8   /* campo_faltante */
#define AVL_E_FIELD                   -9   /* campo_invalido */
#define AVL_E_TYPE_NOT_ALLOWED       -10   /* tipo_no_admitido */
#define AVL_E_NOT_YET                -11   /* aun_no_vigente */
#define AVL_E_ARG                    -12   /* argumento fuera de rango */
#define AVL_E_UNSUPPORTED            -13   /* no existe en esta plataforma */
#define AVL_E_AUTH                   -14   /* la etiqueta de autenticacion no cuadra */
#define AVL_E_SMALL                  -15   /* el buffer de salida es corto */
#define AVL_E_SELFTEST               -16   /* base de selftest: -16 - paso */
/* Un selftest que falla devuelve AVL_E_SELFTEST - n, con n el numero del paso (1..). */

/* ---- topes del formato (los mismos de dominio/tlv.py) ----------------------------------------------------------------------------- */
#define AVL_MAX_FILE   (16u * 1024u)
#define AVL_MAX_VALUE  4096u
#define AVL_MAX_FIELDS 32u
#define AVL_MAX_KID    64u
#define AVL_SIG_SIZE   64u
#define AVL_MAX_FACTORS 16u

#define AVL_LICENSE_MAGIC "AVLC"

#define AVL_TYPE_PRODUCTION 1u
#define AVL_TYPE_EVALUATION 2u
#define AVL_TYPE_DEVELOPMENT 3u
#define AVL_FLAG_RELEASE_PENDING 1u
#define AVL_LEVEL_HARDWARE 1u
#define AVL_LEVEL_INSTALLATION 2u
#define AVL_FACTOR_INSTALLATION 6u

/* ---- identidad y autoprueba ------------------------------------------------------------------------------------------------------ */
AVL_API uint32_t avl_abi_version(void);

/* Vectores conocidos (RFC 8032 prueba 1, XChaCha20-Poly1305 del borrador IRTF-CFRG, HKDF, HMAC): 0 si todo coincide. */
AVL_API int avl_selftest(void);

/* ---- firma separada (manifiestos del despliegue y licencias) -------------------------------------------------------------------- */
/* 0 si la firma Ed25519 (RFC 8032) de `msg` con la publica `pub` es valida; AVL_E_SIGNATURE si no. Nunca lee mas alla de los largos dados. */
AVL_API int avl_verify_detached(const uint8_t *msg, size_t msg_len, const uint8_t sig[64], const uint8_t pub[32]);

/* ---- licencia (.avlic) ----------------------------------------------------------------------------------------------------------- */
typedef struct avl_key {
    char    kid[AVL_MAX_KID + 1];   /* terminado en cero, [a-z0-9._-]{1,64} */
    uint8_t pub[32];
} avl_key;

typedef struct avl_policy {
    uint64_t now_ms;               /* el instante confiable que decide el llamador (la funcion no lee ningun reloj) */
    uint64_t start_tolerance_ms;   /* tolerancia de inicio (politica.tolerancia_inicio_ms) */
    uint32_t flags;                /* AVL_P_* */
} avl_policy;
#define AVL_P_PRODUCTION  1u       /* una licencia de tipo desarrollo se rechaza (tipo_no_admitido) */
#define AVL_P_CHECK_START 2u       /* una licencia que empieza mas alla de now + tolerancia se rechaza (aun_no_vigente) */

typedef struct avl_fp_current {    /* los factores de hardware validos de ESTE equipo, ya hasheados con la clave de producto */
    uint8_t  count;                /* 0..AVL_MAX_FACTORS */
    uint8_t  factor[AVL_MAX_FACTORS];
    uint8_t  hash[AVL_MAX_FACTORS][32];
    uint8_t  has_installation;     /* 1 si `installation_hash` vale */
    uint8_t  installation_hash[32];
} avl_fp_current;

typedef struct avl_license {
    uint8_t  id[16];
    uint32_t serie;
    uint64_t issued_ms, from_ms, until_ms;
    uint16_t grace_days;
    uint32_t equipos, usuarios, concurrent_normal, concurrent_peak;
    uint8_t  type;                 /* AVL_TYPE_* */
    uint32_t flags;                /* AVL_FLAG_* */
    uint16_t release_days;
    uint8_t  has_node_hash;
    uint8_t  node_hash[32];
    uint8_t  fp_k, fp_n;
    uint8_t  fp_factor[AVL_MAX_FACTORS];
    uint8_t  fp_hash[AVL_MAX_FACTORS][32];
    uint16_t caps_len;             /* bytes validos de `caps`: lista de (largo u8 + texto ASCII), en orden y sin repetir */
    uint8_t  caps[1024];
    uint16_t aula_len;             /* bytes UTF-8 de `aula` (ya validada: <=120 caracteres, sin controles, sin espacios en los extremos) */
    uint8_t  aula[480];
    char     kid[AVL_MAX_KID + 1];
    /* Resultado del cotejo con `fp` (si se entrego): */
    uint8_t  fp_checked;
    uint8_t  fp_matches;
    uint8_t  fp_ok;                /* matches >= k */
    uint8_t  fp_partial;           /* ok pero no todos */
    uint8_t  fp_level;             /* AVL_LEVEL_* segun los factores de la licencia */
} avl_license;

/*
 * Verifica y lee un .avlic. Pura: el orden de las comprobaciones es el de dominio/licencia.py (cabecera -> kid -> firma -> campos -> forma -> politica),
 * asi el motivo del rechazo coincide con el de la referencia. `fp` puede ser NULL. Con error, `out` no es de fiar.
 */
AVL_API int avl_license_verify(const uint8_t *data, size_t len, const avl_key *keys, size_t nkeys, const avl_policy *policy,
                               const avl_fp_current *fp, avl_license *out);

/* ---- huella ---------------------------------------------------------------------------------------------------------------------- */
typedef struct avl_fp_result {
    uint8_t k, in_license, matches, ok, partial, level;
} avl_fp_result;

/* Cuantos factores de la licencia coinciden con los de este equipo (comparacion en tiempo constante). Gemelo de huella.comparar. */
AVL_API int avl_fp_match(uint8_t k, uint8_t n, const uint8_t *factor, const uint8_t hash[][32], const avl_fp_current *current, avl_fp_result *out);

/* Tabla SMBIOS (buffer RawSMBIOSData) -> cadenas crudas (sin recortar espacios ni filtrar basura: eso lo hace quien hashea). Gemelo de dominio/smbios.py. */
typedef struct avl_smbios {
    char uuid[37];                 /* 36 caracteres en mayusculas con guiones, o vacio */
    char system_serial[256], board_serial[256], chassis_serial[256];
    char processor_id[17];         /* 16 hexadecimales en mayusculas (ProcessorId, 8 bytes), o vacio */
} avl_smbios;
AVL_API int avl_smbios_parse(const uint8_t *buf, size_t len, avl_smbios *out);

/* Solo Windows: MachineGuid (registro) + tabla SMBIOS del equipo. En otras plataformas devuelve AVL_E_UNSUPPORTED. */
typedef struct avl_hw {
    char machine_guid[64];
    avl_smbios smbios;
} avl_hw;
AVL_API int avl_fp_collect(avl_hw *out);

/* ---- solicitud (.avreq) ---------------------------------------------------------------------------------------------------------- */
typedef struct avl_request_in {
    uint8_t         node_seed[32];     /* llave privada Ed25519 del nodo (semilla de 32 bytes) */
    uint8_t         nonce[16];
    const uint8_t  *version;           /* utf-8, sin terminador; se recorta a 32 bytes; NULL/0 = sin campo */
    size_t          version_len;
    uint64_t        created_ms;
    uint8_t         level;             /* AVL_LEVEL_* */
    uint8_t         fp_k, fp_n;
    uint8_t         fp_factor[AVL_MAX_FACTORS];
    uint8_t         fp_hash[AVL_MAX_FACTORS][32];
    uint8_t         has_license;
    uint8_t         license_id[16];
    const uint8_t  *aula;              /* utf-8; se recorta a 480 bytes; NULL/0 = sin campo */
    size_t          aula_len;
} avl_request_in;

/* Escribe el .avreq firmado (identico byte a byte a solicitud.construir_solicitud). *out_len = capacidad al entrar, tamano escrito al salir. */
AVL_API int avl_request_build(const avl_request_in *in, uint8_t *out, size_t *out_len);

/* ---- reloj ----------------------------------------------------------------------------------------------------------------------- */
/*
 * Ancla v2 de la marca alta: MAC = HMAC-SHA-512( SHA-512("avl-ancla-v2|" || secreto)[0..32], marca(u64 BE) || instalada_en(u64 BE, 0 si no hay) || flag(u8) )[0..32].
 * `avl_clock_advance` devuelve la marca siguiente (monotona: max(actual, candidata)) y el MAC de esa marca. Si `prev_mac` no es NULL se verifica antes
 * contra `prev_mark`: *prev_ok = 1 si cuadra, 0 si no (un ancla alterada no cuenta: no sube la marca).
 */
AVL_API int avl_clock_advance(const uint8_t *secret, size_t secret_len, uint64_t prev_mark, const uint8_t *prev_mac, uint64_t installed_ms, uint8_t has_installed,
                              uint64_t candidate, uint64_t *next_mark, uint8_t next_mac[32], uint8_t *prev_ok);

/* ---- llaves ---------------------------------------------------------------------------------------------------------------------- */
/* HKDF-SHA-512 (RFC 5869): derivar una llave de `out_len` (1..255*64) bytes. Gemelo: cryptography HKDF(SHA512). */
AVL_API int avl_key_derive(const uint8_t *secret, size_t secret_len, const uint8_t *salt, size_t salt_len, const uint8_t *info, size_t info_len,
                           uint8_t *out, size_t out_len);

/* Envoltura XChaCha20-Poly1305 con el contexto como dato asociado. Formato: nonce(24) || texto cifrado || etiqueta(16). */
#define AVL_WRAP_OVERHEAD 40u
AVL_API int avl_key_wrap(const uint8_t key[32], const uint8_t nonce[24], const uint8_t *ctx, size_t ctx_len, const uint8_t *plain, size_t plain_len,
                         uint8_t *out, size_t out_cap, size_t *out_len);
AVL_API int avl_key_unwrap(const uint8_t key[32], const uint8_t *ctx, size_t ctx_len, const uint8_t *wrapped, size_t wrapped_len, uint8_t *out, size_t out_cap,
                           size_t *out_len);

/* ---- varios ---------------------------------------------------------------------------------------------------------------------- */
/* Borra de forma que el compilador no lo elimine. */
AVL_API void avl_wipe(void *p, size_t n);

#ifdef __cplusplus
}
#endif
#endif
