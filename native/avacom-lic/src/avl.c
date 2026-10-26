/*
 * avacom_lic · implementacion (ver include/avacom_lic.h para el contrato).
 * Sin malloc, sin estado global: todo lo que cambia vive en la pila o en las estructuras del llamador.
 */
#include "avacom_lic.h"

#include <string.h>

#include "monocypher.h"
#include "monocypher-ed25519.h"

/* ====================================================================================================================================
 * utilidades de bytes
 * ================================================================================================================================== */
static uint16_t rd16(const uint8_t *p) { return (uint16_t)(((unsigned)p[0] << 8) | (unsigned)p[1]); }
static uint32_t rd32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3]; }
static uint64_t rd64(const uint8_t *p) { return ((uint64_t)rd32(p) << 32) | (uint64_t)rd32(p + 4); }
static void wr16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void wr64(uint8_t *p, uint64_t v) { for (int i = 0; i < 8; i++) { p[7 - i] = (uint8_t)(v >> (8 * i)); } }

uint32_t avl_abi_version(void) { return AVL_ABI_VERSION; }

void avl_wipe(void *p, size_t n) { if (p != NULL && n > 0) { crypto_wipe(p, n); } }

/* ====================================================================================================================================
 * firma separada
 * ================================================================================================================================== */
/* L = 2^252 + 27742317777372353535851937790883648493, en little endian. Una S >= L es la misma firma «escrita de otra forma»: se rechaza (maleabilidad). */
static const uint8_t ED_L[32] = {
    0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10};

static int scalar_is_canonical(const uint8_t s[32])
{
    for (int i = 31; i >= 0; i--) {
        if (s[i] < ED_L[i]) { return 1; }
        if (s[i] > ED_L[i]) { return 0; }
    }
    return 0;   /* igual a L: tampoco */
}

/*
 * Puntos de ORDEN PEQUENO (D-33). La ecuacion de Ed25519 de la RFC 8032 es la «cofactorizada»: con una llave publica A y un R de orden pequeno y S = 0 se cumple para CUALQUIER mensaje
 * (una «firma universal»). No sirve contra nuestras llaves fijas, pero el `kid` de una solicitud o una liberacion ES la llave que el solicitante escoge: se rechazan A y R de orden pequeno.
 * Sus codificaciones (con y sin el bit de signo) tienen y = 0, 1, p-1, las dos de orden 8, y las no canonicas p y p+1; p = 2^255 - 19. Verificado con aritmetica de curva en Python
 * (la lista completa de y de orden | 8 con y < 19 y p-1) y contra OpenSSL en las pruebas diferenciales.
 */
static const uint8_t SMALL_ORDER_Y[7][32] = {
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0xec, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x7f},
    {0xed, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x7f},
    {0xee, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x7f},
    {0xc7, 0x17, 0x6a, 0x70, 0x3d, 0x4d, 0xd8, 0x4f, 0xba, 0x3c, 0x0b, 0x76, 0x0d, 0x10, 0x67, 0x0f, 0x2a, 0x20, 0x53, 0xfa, 0x2c, 0x39, 0xcc, 0xc6, 0x4e, 0xc7, 0xfd, 0x77, 0x92, 0xac, 0x03, 0x7a},
    {0x26, 0xe8, 0x95, 0x8f, 0xc2, 0xb2, 0x27, 0xb0, 0x45, 0xc3, 0xf4, 0x89, 0xf2, 0xef, 0x98, 0xf0, 0xd5, 0xdf, 0xac, 0x05, 0xd3, 0xc6, 0x33, 0x39, 0xb1, 0x38, 0x02, 0x88, 0x6d, 0x53, 0xfc, 0x05},
};

static int has_small_order(const uint8_t enc[32])
{
    uint8_t y[32];
    memcpy(y, enc, 32);
    y[31] &= 0x7Fu;                                   /* el bit de signo no cambia el orden */
    int found = 0;
    for (size_t i = 0; i < sizeof SMALL_ORDER_Y / sizeof SMALL_ORDER_Y[0]; i++) {
        found |= (memcmp(y, SMALL_ORDER_Y[i], 32) == 0);
    }
    return found;
}

int avl_verify_detached(const uint8_t *msg, size_t msg_len, const uint8_t sig[64], const uint8_t pub[32])
{
    static const uint8_t vacio = 0;
    if (sig == NULL || pub == NULL || (msg == NULL && msg_len != 0)) { return AVL_E_ARG; }
    if (!scalar_is_canonical(sig + 32) || has_small_order(pub) || has_small_order(sig)) { return AVL_E_SIGNATURE; }
    return crypto_ed25519_check(sig, pub, msg != NULL ? msg : &vacio, msg_len) == 0 ? AVL_OK : AVL_E_SIGNATURE;
}

/* ====================================================================================================================================
 * UTF-8 estricto (como bytes.decode("utf-8") de Python) y el texto del aula
 * ================================================================================================================================== */
/* Devuelve el largo de la secuencia y el punto de codigo, o 0 si es invalida (sobrelargas, sustitutos y > U+10FFFF incluidos). */
static size_t utf8_next(const uint8_t *s, size_t n, uint32_t *cp)
{
    if (n == 0) { return 0; }
    uint32_t c = s[0];
    if (c < 0x80u) { *cp = c; return 1; }
    if (c >= 0xC2u && c <= 0xDFu) {
        if (n < 2 || (s[1] & 0xC0u) != 0x80u) { return 0; }
        *cp = ((c & 0x1Fu) << 6) | (s[1] & 0x3Fu);
        return 2;
    }
    if (c >= 0xE0u && c <= 0xEFu) {
        if (n < 3 || (s[1] & 0xC0u) != 0x80u || (s[2] & 0xC0u) != 0x80u) { return 0; }
        uint32_t v = ((c & 0x0Fu) << 12) | ((uint32_t)(s[1] & 0x3Fu) << 6) | (s[2] & 0x3Fu);
        if (v < 0x800u || (v >= 0xD800u && v <= 0xDFFFu)) { return 0; }
        *cp = v;
        return 3;
    }
    if (c >= 0xF0u && c <= 0xF4u) {
        if (n < 4 || (s[1] & 0xC0u) != 0x80u || (s[2] & 0xC0u) != 0x80u || (s[3] & 0xC0u) != 0x80u) { return 0; }
        uint32_t v = ((c & 0x07u) << 18) | ((uint32_t)(s[1] & 0x3Fu) << 12) | ((uint32_t)(s[2] & 0x3Fu) << 6) | (s[3] & 0x3Fu);
        if (v < 0x10000u || v > 0x10FFFFu) { return 0; }
        *cp = v;
        return 4;
    }
    return 0;
}

/* Los caracteres que str.strip() de Python recorta (los de control ya se rechazan antes). */
static int is_space(uint32_t c)
{
    return c == 0x20u || c == 0x85u || c == 0xA0u || c == 0x1680u || (c >= 0x2000u && c <= 0x200Au) || c == 0x2028u || c == 0x2029u || c == 0x202Fu ||
           c == 0x205Fu || c == 0x3000u;
}

/* Gemelo de licencia._texto(valor, 120): UTF-8 valido, <= max_chars caracteres, sin controles (<32, 127) y sin espacios en los extremos. */
static int aula_valid(const uint8_t *s, size_t n, size_t max_chars)
{
    size_t pos = 0, chars = 0;
    uint32_t first = 0, last = 0, cp = 0;
    while (pos < n) {
        size_t l = utf8_next(s + pos, n - pos, &cp);
        if (l == 0) { return 0; }
        if (cp < 32u || cp == 127u) { return 0; }
        if (chars == 0) { first = cp; }
        last = cp;
        chars++;
        if (chars > max_chars) { return 0; }
        pos += l;
    }
    if (chars > 0 && (is_space(first) || is_space(last))) { return 0; }
    return 1;
}

/* ====================================================================================================================================
 * huella
 * ================================================================================================================================== */
int avl_fp_match(uint8_t k, uint8_t n, const uint8_t *factor, const uint8_t hash[][32], const avl_fp_current *current, avl_fp_result *out)
{
    if (out == NULL || current == NULL || n > AVL_MAX_FACTORS || (n > 0 && (factor == NULL || hash == NULL)) || current->count > AVL_MAX_FACTORS) { return AVL_E_ARG; }
    unsigned matches = 0;
    uint8_t level = AVL_LEVEL_HARDWARE;
    for (unsigned i = 0; i < n; i++) {
        const uint8_t *today = NULL;
        if (factor[i] == AVL_FACTOR_INSTALLATION) {
            level = AVL_LEVEL_INSTALLATION;
            if (current->has_installation) { today = current->installation_hash; }
        } else {
            for (unsigned j = 0; j < current->count; j++) {
                if (current->factor[j] == factor[i]) { today = current->hash[j]; break; }
            }
        }
        if (today != NULL && crypto_verify32(today, hash[i]) == 0) { matches++; }
    }
    out->k = k;
    out->in_license = n;
    out->matches = (uint8_t)matches;
    out->ok = (uint8_t)(matches >= k);
    out->partial = (uint8_t)(out->ok && matches < n);
    out->level = level;
    return AVL_OK;
}

/* ====================================================================================================================================
 * licencia (.avlic): los mismos pasos y el mismo orden que dominio/tlv.py + dominio/licencia.py
 * ================================================================================================================================== */
enum { T_ID = 1, T_SERIE, T_AULA, T_EMITIDA, T_DESDE, T_VENCE, T_GRACIA, T_LIMITES, T_CAPACIDADES, T_HUELLA, T_TIPO, T_BANDERAS, T_HASH_NODO, T_COUNT };

typedef struct known_tag { uint16_t max_len; uint8_t critical; } known_tag;
static const known_tag KNOWN[T_COUNT] = {
    [0] = {0, 0},
    [T_ID] = {16, 1}, [T_SERIE] = {4, 1}, [T_AULA] = {480, 0}, [T_EMITIDA] = {8, 1}, [T_DESDE] = {8, 1}, [T_VENCE] = {8, 1}, [T_GRACIA] = {2, 1},
    [T_LIMITES] = {16, 1}, [T_CAPACIDADES] = {1024, 1}, [T_HUELLA] = {2 + 16 * 33, 1}, [T_TIPO] = {1, 1}, [T_BANDERAS] = {6, 1}, [T_HASH_NODO] = {32, 0},
};
static const uint8_t REQUIRED[] = {T_ID, T_SERIE, T_EMITIDA, T_DESDE, T_VENCE, T_GRACIA, T_LIMITES, T_CAPACIDADES, T_HUELLA, T_TIPO};

#define MAX_GRACE_DAYS 365u
#define MAX_VALIDITY_MS ((uint64_t)25u * 366u * 86400000u)
#define MAX_CAPS 64u
#define TWO62 ((uint64_t)1 << 62)

typedef struct field_ref { const uint8_t *p; uint16_t len; uint8_t present; } field_ref;

static int kid_char_ok(uint8_t c) { return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-'; }

/* leer_campos: un solo pase, el primer error en el orden del archivo. */
static int read_fields(const uint8_t *body, size_t len, field_ref refs[T_COUNT])
{
    size_t pos = 0, total = 0;
    unsigned last = 0;
    while (pos < len) {
        total++;
        if (total > AVL_MAX_FIELDS || pos + 4 > len) { return AVL_E_FORMAT; }
        unsigned tag = rd16(body + pos);
        unsigned vlen = rd16(body + pos + 2);
        pos += 4;
        unsigned number = tag & 0x7FFFu;
        int critical = (tag & 0x8000u) != 0;
        if (number == 0 || number <= last) { return AVL_E_FORMAT; }
        last = number;
        if (vlen > AVL_MAX_VALUE || pos + vlen > len) { return AVL_E_FORMAT; }
        const uint8_t *value = body + pos;
        pos += vlen;
        if (number < T_COUNT) {
            if (critical != (KNOWN[number].critical != 0)) { return AVL_E_FORMAT; }
            if (vlen > KNOWN[number].max_len) { return AVL_E_FIELD; }
            refs[number].p = value;
            refs[number].len = (uint16_t)vlen;
            refs[number].present = 1;
        } else if (critical) {
            return AVL_E_CRITICAL_TAG;
        }
    }
    return AVL_OK;
}

static int decode_fingerprint(const field_ref *f, avl_license *out)
{
    if (f->len < 2) { return AVL_E_FIELD; }
    unsigned k = f->p[0], n = f->p[1];
    if (n < 1 || n > AVL_MAX_FACTORS || k < 1 || k > n || f->len != 2u + 33u * n) { return AVL_E_FIELD; }
    unsigned previous = 0;
    for (unsigned i = 0; i < n; i++) {
        const uint8_t *base = f->p + 2 + 33u * i;
        unsigned factor = base[0];
        if (factor <= previous || factor > 32u) { return AVL_E_FIELD; }
        previous = factor;
        out->fp_factor[i] = (uint8_t)factor;
        memcpy(out->fp_hash[i], base + 1, 32);
    }
    out->fp_k = (uint8_t)k;
    out->fp_n = (uint8_t)n;
    return AVL_OK;
}

/* Capacidades: (largo u8 + texto [a-z0-9_*]{1,24}) en orden estricto, hasta 64. */
static int decode_caps(const field_ref *f)
{
    size_t pos = 0, count = 0;
    const uint8_t *prev = NULL;
    size_t prev_len = 0;
    while (pos < f->len) {
        size_t l = f->p[pos++];
        if (l == 0 || l > 24 || pos + l > f->len || count >= MAX_CAPS) { return AVL_E_FIELD; }
        const uint8_t *code = f->p + pos;
        for (size_t i = 0; i < l; i++) {
            uint8_t c = code[i];
            if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '*')) { return AVL_E_FIELD; }
        }
        if (prev != NULL) {   /* orden de las cadenas: comparacion por bytes, como str en ASCII */
            size_t m = prev_len < l ? prev_len : l;
            int c = memcmp(code, prev, m);
            if (c < 0 || (c == 0 && l <= prev_len)) { return AVL_E_FIELD; }
        }
        prev = code;
        prev_len = l;
        pos += l;
        count++;
    }
    return AVL_OK;
}

static int shape_from_fields(const field_ref refs[T_COUNT], avl_license *out)
{
    for (size_t i = 0; i < sizeof REQUIRED; i++) {
        if (!refs[REQUIRED[i]].present) { return AVL_E_MISSING; }
    }
    /* _entero: el largo tiene que ser exacto (las etiquetas con largo fijo) */
    if (refs[T_ID].len != 16 || refs[T_SERIE].len != 4 || refs[T_EMITIDA].len != 8 || refs[T_DESDE].len != 8 || refs[T_VENCE].len != 8 || refs[T_GRACIA].len != 2 ||
        refs[T_LIMITES].len != 16 || refs[T_TIPO].len != 1) { return AVL_E_FIELD; }
    memcpy(out->id, refs[T_ID].p, 16);
    out->serie = rd32(refs[T_SERIE].p);
    out->issued_ms = rd64(refs[T_EMITIDA].p);
    out->from_ms = rd64(refs[T_DESDE].p);
    out->until_ms = rd64(refs[T_VENCE].p);
    out->grace_days = rd16(refs[T_GRACIA].p);
    if (out->serie < 1u || out->grace_days > MAX_GRACE_DAYS || !(out->issued_ms > 0 && out->issued_ms < TWO62) ||
        !(out->from_ms > 0 && out->from_ms < out->until_ms && out->until_ms < TWO62) || out->until_ms - out->from_ms > MAX_VALIDITY_MS) { return AVL_E_FIELD; }
    out->equipos = rd32(refs[T_LIMITES].p);
    out->usuarios = rd32(refs[T_LIMITES].p + 4);
    out->concurrent_normal = rd32(refs[T_LIMITES].p + 8);
    out->concurrent_peak = rd32(refs[T_LIMITES].p + 12);
    /* Un limite en 0 no limita: DETIENE (D-17). Ninguna licencia puede detener una clase. */
    uint32_t smallest = out->equipos;
    if (out->usuarios < smallest) { smallest = out->usuarios; }
    if (out->concurrent_normal < smallest) { smallest = out->concurrent_normal; }
    if (out->concurrent_peak < smallest) { smallest = out->concurrent_peak; }
    if (out->concurrent_normal > out->concurrent_peak || smallest < 1u) { return AVL_E_FIELD; }
    out->type = refs[T_TIPO].p[0];
    if (out->type < AVL_TYPE_PRODUCTION || out->type > AVL_TYPE_DEVELOPMENT) { return AVL_E_FIELD; }
    out->flags = 0;
    out->release_days = 0;
    if (refs[T_BANDERAS].present) {
        if (refs[T_BANDERAS].len != 6) { return AVL_E_FIELD; }
        uint32_t bits = rd32(refs[T_BANDERAS].p);
        uint16_t days = rd16(refs[T_BANDERAS].p + 4);
        if ((bits & ~AVL_FLAG_RELEASE_PENDING) != 0 || days > MAX_GRACE_DAYS) { return AVL_E_FIELD; }
        if ((bits & AVL_FLAG_RELEASE_PENDING) == 0 && days != 0) { return AVL_E_FIELD; }
        out->flags = bits;
        out->release_days = days;
    }
    out->has_node_hash = 0;
    if (refs[T_HASH_NODO].present) {
        if (refs[T_HASH_NODO].len != 32) { return AVL_E_FIELD; }
        out->has_node_hash = 1;
        memcpy(out->node_hash, refs[T_HASH_NODO].p, 32);
    }
    out->aula_len = 0;
    if (refs[T_AULA].present) {
        if (!aula_valid(refs[T_AULA].p, refs[T_AULA].len, 120)) { return AVL_E_FIELD; }
        out->aula_len = refs[T_AULA].len;
        memcpy(out->aula, refs[T_AULA].p, refs[T_AULA].len);
    }
    int rc = decode_caps(&refs[T_CAPACIDADES]);
    if (rc != AVL_OK) { return rc; }
    out->caps_len = refs[T_CAPACIDADES].len;
    memcpy(out->caps, refs[T_CAPACIDADES].p, refs[T_CAPACIDADES].len);
    return decode_fingerprint(&refs[T_HUELLA], out);
}

int avl_license_verify(const uint8_t *data, size_t len, const avl_key *keys, size_t nkeys, const avl_policy *policy, const avl_fp_current *fp, avl_license *out)
{
    if (data == NULL || out == NULL || policy == NULL || (nkeys > 0 && keys == NULL)) { return AVL_E_ARG; }
    memset(out, 0, sizeof *out);
    /* ---- cabecera (leer_cabecera) ---- */
    if (len > AVL_MAX_FILE) { return AVL_E_TOO_BIG; }
    if (len < 4u + 2u + 1u + 1u + AVL_SIG_SIZE) { return AVL_E_TOO_SHORT; }
    if (memcmp(data, AVL_LICENSE_MAGIC, 4) != 0) { return AVL_E_FORMAT; }
    if (rd16(data + 4) != 1u) { return AVL_E_VERSION; }
    size_t kid_len = data[6];
    if (kid_len < 1u || kid_len > AVL_MAX_KID || 7u + kid_len + AVL_SIG_SIZE > len) { return AVL_E_FORMAT; }
    for (size_t i = 0; i < kid_len; i++) {
        if (!kid_char_ok(data[7 + i])) { return AVL_E_FORMAT; }
    }
    size_t fields_at = 7u + kid_len;
    /* ---- llave por kid ---- */
    const avl_key *key = NULL;
    for (size_t i = 0; i < nkeys; i++) {
        size_t l = strnlen(keys[i].kid, AVL_MAX_KID + 1);
        if (l == kid_len && memcmp(keys[i].kid, data + 7, kid_len) == 0) { key = &keys[i]; break; }
    }
    if (key == NULL) { return AVL_E_KID_UNKNOWN; }
    /* ---- firma ANTES de mirar un solo campo ---- */
    int rc = avl_verify_detached(data, len - AVL_SIG_SIZE, data + len - AVL_SIG_SIZE, key->pub);
    if (rc != AVL_OK) { return AVL_E_SIGNATURE; }
    /* ---- campos y forma ---- */
    field_ref refs[T_COUNT];
    memset(refs, 0, sizeof refs);
    rc = read_fields(data + fields_at, len - AVL_SIG_SIZE - fields_at, refs);
    if (rc != AVL_OK) { return rc; }
    rc = shape_from_fields(refs, out);
    if (rc != AVL_OK) { return rc; }
    {
        size_t kl = kid_len < AVL_MAX_KID ? kid_len : AVL_MAX_KID;
        memcpy(out->kid, data + 7, kl);
        out->kid[kl] = '\0';
    }
    /* ---- politica ---- */
    if ((policy->flags & AVL_P_PRODUCTION) != 0 && out->type == AVL_TYPE_DEVELOPMENT) { return AVL_E_TYPE_NOT_ALLOWED; }
    if ((policy->flags & AVL_P_CHECK_START) != 0) {
        /* desde > ahora + tolerancia, sin desbordar */
        uint64_t limit = policy->now_ms + policy->start_tolerance_ms;
        if (limit < policy->now_ms) { limit = UINT64_MAX; }
        if (out->from_ms > limit) { return AVL_E_NOT_YET; }
    }
    if (fp != NULL) {
        avl_fp_result r;
        rc = avl_fp_match(out->fp_k, out->fp_n, out->fp_factor, (const uint8_t (*)[32])out->fp_hash, fp, &r);
        if (rc != AVL_OK) { return rc; }
        out->fp_checked = 1;
        out->fp_matches = r.matches;
        out->fp_ok = r.ok;
        out->fp_partial = r.partial;
        out->fp_level = r.level;
    }
    return AVL_OK;
}

/* ====================================================================================================================================
 * SMBIOS (gemelo de dominio/smbios.py)
 * ================================================================================================================================== */
#define SMBIOS_STRUCT_LIMIT 4096u

typedef struct sm_struct { uint8_t type; size_t formatted_len; const uint8_t *formatted; const uint8_t *strings; size_t strings_len; } sm_struct;

/* Siguiente estructura de la tabla; 0 cuando se acaba. Misma regla que _estructuras: nunca lanza por una tabla rota. */
static int sm_next(const uint8_t *table, size_t n, size_t *pos, sm_struct *s)
{
    if (*pos + 4 > n) { return 0; }
    uint8_t type = table[*pos], flen = table[*pos + 1];
    if (flen < 4 || *pos + flen > n) { return 0; }
    s->type = type;
    s->formatted = table + *pos;
    s->formatted_len = flen;
    size_t start = *pos + flen;
    size_t next;
    if (start + 2 <= n && table[start] == 0 && table[start + 1] == 0) {
        s->strings = table + start;
        s->strings_len = 0;
        next = start + 2;
    } else {
        size_t end = start;
        int found = 0;
        while (end + 1 < n) {
            if (table[end] == 0 && table[end + 1] == 0) { found = 1; break; }
            end++;
        }
        if (!found) { return 0; }
        s->strings = table + start;
        s->strings_len = end + 1 - start;
        next = end + 2;
    }
    *pos = next;
    return type == 127 ? 2 : 1;      /* 2 = esta es la ultima */
}

/* _cadena: la cadena (base 1) a la que apunta el byte que hay en `offset` del area formateada; copia cruda terminada en cero (hasta cap-1 bytes). */
static void sm_string(const sm_struct *s, size_t offset, char *dst, size_t cap)
{
    dst[0] = '\0';
    if (offset >= s->formatted_len) { return; }
    unsigned index = s->formatted[offset];
    if (index == 0) { return; }
    /* partes = cadenas.split(b"\0"): hay (ceros + 1) partes; la indice-esima (base 1) existe si index <= ceros */
    size_t part = 1, from = 0;
    for (size_t i = 0; i < s->strings_len; i++) {
        if (s->strings[i] == 0) {
            if (part == index) {
                size_t l = i - from;
                if (l > cap - 1) { l = cap - 1; }
                memcpy(dst, s->strings + from, l);
                dst[l] = '\0';
                return;
            }
            part++;
            from = i + 1;
        }
    }
    /* sin mas ceros: la cadena `index` seria la ultima parte (sin terminador), que _cadena descarta (index > len(partes)-1) */
}

/* ¿La cadena cruda, ya decodificada y recortada con str.strip() de Python, quedaria vacia? Solo espacios (ASCII, C1 y los de Unicode) o nada. UTF-8 invalido no es blanco. */
static int raw_is_blank(const char *text)
{
    const uint8_t *s = (const uint8_t *)text;
    size_t n = strlen(text), pos = 0;
    while (pos < n) {
        uint32_t cp = 0;
        size_t l = utf8_next(s + pos, n - pos, &cp);
        if (l == 0 || !(is_space(cp) || (cp >= 9u && cp <= 13u) || (cp >= 0x1Cu && cp <= 0x1Fu))) { return 0; }
        pos += l;
    }
    return 1;
}

static void hex_upper(char *dst, const uint8_t *src, size_t n)
{
    static const char H[] = "0123456789ABCDEF";
    for (size_t i = 0; i < n; i++) { dst[2 * i] = H[src[i] >> 4]; dst[2 * i + 1] = H[src[i] & 15u]; }
}

int avl_smbios_parse(const uint8_t *buf, size_t len, avl_smbios *out)
{
    if (out == NULL || (buf == NULL && len != 0)) { return AVL_E_ARG; }
    memset(out, 0, sizeof *out);
    if (len < 8) { return AVL_OK; }
    size_t table_len = (size_t)buf[4] | ((size_t)buf[5] << 8) | ((size_t)buf[6] << 16) | ((size_t)buf[7] << 24);
    const uint8_t *table = buf + 8;
    size_t avail = len - 8;
    size_t n = (table_len != 0 && table_len < avail) ? table_len : avail;
    size_t pos = 0;
    sm_struct s;
    for (unsigned i = 0; i < SMBIOS_STRUCT_LIMIT; i++) {
        int r = sm_next(table, n, &pos, &s);
        if (r == 0) { break; }
        if (s.type == 1 && out->uuid[0] == '\0') {
            sm_string(&s, 7, out->system_serial, sizeof out->system_serial);
            if (s.formatted_len >= 24) {
                const uint8_t *u = s.formatted + 8;
                uint8_t g[16];
                g[0] = u[3]; g[1] = u[2]; g[2] = u[1]; g[3] = u[0];     /* los tres primeros campos en little endian */
                g[4] = u[5]; g[5] = u[4];
                g[6] = u[7]; g[7] = u[6];
                memcpy(g + 8, u + 8, 8);
                char *d = out->uuid;
                hex_upper(d, g, 4); d += 8; *d++ = '-';
                hex_upper(d, g + 4, 2); d += 4; *d++ = '-';
                hex_upper(d, g + 6, 2); d += 4; *d++ = '-';
                hex_upper(d, g + 8, 2); d += 4; *d++ = '-';
                hex_upper(d, g + 10, 6); d += 12; *d = '\0';
            }
        } else if (s.type == 2 && raw_is_blank(out->board_serial)) {
            sm_string(&s, 7, out->board_serial, sizeof out->board_serial);
        } else if (s.type == 3 && raw_is_blank(out->chassis_serial)) {
            sm_string(&s, 7, out->chassis_serial, sizeof out->chassis_serial);
        } else if (s.type == 4 && out->processor_id[0] == '\0' && s.formatted_len >= 16) {
            uint8_t rev[8];
            for (int j = 0; j < 8; j++) { rev[j] = s.formatted[8 + 7 - j]; }
            hex_upper(out->processor_id, rev, 8);
            out->processor_id[16] = '\0';
        }
        if (r == 2) { break; }
    }
    return AVL_OK;
}

/* ====================================================================================================================================
 * solicitud (.avreq): tlv.escribir + tlv.sellar de solicitud.construir_solicitud
 * ================================================================================================================================== */
enum { R_NONCE = 1, R_VERSION, R_CREADA, R_NIVEL, R_HUELLA, R_CLAVE_NODO, R_LICENCIA, R_AULA };

typedef struct writer { uint8_t *p; size_t cap; size_t len; int err; } writer;

static void w_bytes(writer *w, const void *src, size_t n)
{
    if (w->err || w->len + n > w->cap) { w->err = 1; return; }
    if (n > 0) { memcpy(w->p + w->len, src, n); }
    w->len += n;
}
static void w_u8(writer *w, uint8_t v) { w_bytes(w, &v, 1); }
static void w_field(writer *w, unsigned tag, int critical, const uint8_t *value, size_t n)
{
    uint8_t h[4];
    wr16(h, (uint16_t)(tag | (critical ? 0x8000u : 0u)));
    wr16(h + 2, (uint16_t)n);
    w_bytes(w, h, 4);
    w_bytes(w, value, n);
}

int avl_request_build(const avl_request_in *in, uint8_t *out, size_t *out_len)
{
    static const char HEX[] = "0123456789abcdef";
    if (in == NULL || out == NULL || out_len == NULL) { return AVL_E_ARG; }
    if ((in->level != AVL_LEVEL_HARDWARE && in->level != AVL_LEVEL_INSTALLATION) || in->fp_n < 1 || in->fp_n > AVL_MAX_FACTORS || in->fp_k < 1 || in->fp_k > in->fp_n ||
        (in->version == NULL && in->version_len != 0) || (in->aula == NULL && in->aula_len != 0)) { return AVL_E_ARG; }
    uint8_t secret[64], pub[32], seed[32];
    memcpy(seed, in->node_seed, 32);
    crypto_ed25519_key_pair(secret, pub, seed);          /* borra `seed`: es nuestra copia */

    writer w = {out, *out_len, 0, 0};
    char kid[64];
    for (int i = 0; i < 32; i++) { kid[2 * i] = HEX[pub[i] >> 4]; kid[2 * i + 1] = HEX[pub[i] & 15u]; }
    w_bytes(&w, "AVRQ", 4);
    uint8_t v[2] = {0, 1};
    w_bytes(&w, v, 2);
    w_u8(&w, 64);
    w_bytes(&w, kid, 64);

    w_field(&w, R_NONCE, 1, in->nonce, 16);
    if (in->version_len > 0) { w_field(&w, R_VERSION, 0, in->version, in->version_len > 32 ? 32 : in->version_len); }
    uint8_t c8[8];
    wr64(c8, in->created_ms);
    w_field(&w, R_CREADA, 1, c8, 8);
    uint8_t lvl = in->level;
    w_field(&w, R_NIVEL, 1, &lvl, 1);
    uint8_t fp[2 + 16 * 33];
    size_t fl = 0;
    fp[fl++] = in->fp_k;
    fp[fl++] = in->fp_n;
    for (unsigned i = 0; i < in->fp_n; i++) {
        fp[fl++] = in->fp_factor[i];
        memcpy(fp + fl, in->fp_hash[i], 32);
        fl += 32;
    }
    w_field(&w, R_HUELLA, 1, fp, fl);
    w_field(&w, R_CLAVE_NODO, 1, pub, 32);
    if (in->has_license) { w_field(&w, R_LICENCIA, 0, in->license_id, 16); }
    if (in->aula_len > 0) { w_field(&w, R_AULA, 0, in->aula, in->aula_len > 480 ? 480 : in->aula_len); }

    int rc = AVL_OK;
    if (w.err) {
        rc = AVL_E_SMALL;
    } else {
        uint8_t sig[64];
        crypto_ed25519_sign(sig, secret, out, w.len);
        w_bytes(&w, sig, 64);
        if (w.err || w.len > AVL_MAX_FILE) { rc = AVL_E_SMALL; }
    }
    crypto_wipe(secret, sizeof secret);
    crypto_wipe(seed, sizeof seed);
    if (rc == AVL_OK) { *out_len = w.len; }
    return rc;
}

/* ====================================================================================================================================
 * reloj: ancla v2 de la marca alta
 * ================================================================================================================================== */
static void anchor_mac(const uint8_t *secret, size_t secret_len, uint64_t mark, uint64_t installed, uint8_t has_installed, uint8_t mac[32])
{
    static const uint8_t PREFIX[] = "avl-ancla-v2|";
    crypto_sha512_ctx h;
    uint8_t key[64], full[64], msg[17];
    crypto_sha512_init(&h);
    crypto_sha512_update(&h, PREFIX, sizeof PREFIX - 1);
    crypto_sha512_update(&h, secret, secret_len);
    crypto_sha512_final(&h, key);
    wr64(msg, mark);
    wr64(msg + 8, has_installed ? installed : 0u);
    msg[16] = has_installed ? 1u : 0u;
    crypto_sha512_hmac(full, key, 32, msg, sizeof msg);
    memcpy(mac, full, 32);
    crypto_wipe(key, sizeof key);
    crypto_wipe(full, sizeof full);
    crypto_wipe(&h, sizeof h);
}

int avl_clock_advance(const uint8_t *secret, size_t secret_len, uint64_t prev_mark, const uint8_t *prev_mac, uint64_t installed_ms, uint8_t has_installed,
                      uint64_t candidate, uint64_t *next_mark, uint8_t next_mac[32], uint8_t *prev_ok)
{
    if (secret == NULL || secret_len == 0 || next_mark == NULL || next_mac == NULL) { return AVL_E_ARG; }
    int ok = 1;
    if (prev_mac != NULL) {
        uint8_t check[32];
        anchor_mac(secret, secret_len, prev_mark, installed_ms, has_installed, check);
        ok = crypto_verify32(check, prev_mac) == 0;
        crypto_wipe(check, sizeof check);
    }
    if (prev_ok != NULL) { *prev_ok = (uint8_t)ok; }
    uint64_t base = ok ? prev_mark : 0u;                 /* un ancla alterada no cuenta: no aporta marca */
    *next_mark = candidate > base ? candidate : base;
    anchor_mac(secret, secret_len, *next_mark, installed_ms, has_installed, next_mac);
    return AVL_OK;
}

/* ====================================================================================================================================
 * llaves
 * ================================================================================================================================== */
int avl_key_derive(const uint8_t *secret, size_t secret_len, const uint8_t *salt, size_t salt_len, const uint8_t *info, size_t info_len, uint8_t *out, size_t out_len)
{
    static const uint8_t z = 0;
    if (secret == NULL || out == NULL || out_len < 1 || out_len > 255u * 64u || (salt == NULL && salt_len != 0) || (info == NULL && info_len != 0)) { return AVL_E_ARG; }
    crypto_sha512_hkdf(out, out_len, secret, secret_len, salt != NULL ? salt : &z, salt_len, info != NULL ? info : &z, info_len);
    return AVL_OK;
}

int avl_key_wrap(const uint8_t key[32], const uint8_t nonce[24], const uint8_t *ctx, size_t ctx_len, const uint8_t *plain, size_t plain_len, uint8_t *out, size_t out_cap,
                 size_t *out_len)
{
    static const uint8_t z = 0;
    if (key == NULL || nonce == NULL || out == NULL || out_len == NULL || (ctx == NULL && ctx_len != 0) || (plain == NULL && plain_len != 0)) { return AVL_E_ARG; }
    if (plain_len > AVL_MAX_FILE || out_cap < plain_len + AVL_WRAP_OVERHEAD) { return AVL_E_SMALL; }
    memcpy(out, nonce, 24);
    crypto_aead_lock(out + 24, out + 24 + plain_len, key, nonce, ctx != NULL ? ctx : &z, ctx_len, plain != NULL ? plain : &z, plain_len);
    *out_len = plain_len + AVL_WRAP_OVERHEAD;
    return AVL_OK;
}

int avl_key_unwrap(const uint8_t key[32], const uint8_t *ctx, size_t ctx_len, const uint8_t *wrapped, size_t wrapped_len, uint8_t *out, size_t out_cap, size_t *out_len)
{
    static const uint8_t z = 0;
    if (key == NULL || wrapped == NULL || out == NULL || out_len == NULL || (ctx == NULL && ctx_len != 0)) { return AVL_E_ARG; }
    if (wrapped_len < AVL_WRAP_OVERHEAD || wrapped_len > AVL_MAX_FILE + AVL_WRAP_OVERHEAD) { return AVL_E_FORMAT; }
    size_t n = wrapped_len - AVL_WRAP_OVERHEAD;
    if (out_cap < n) { return AVL_E_SMALL; }
    const uint8_t *nonce = wrapped;
    const uint8_t *ct = wrapped + 24;
    const uint8_t *mac = wrapped + 24 + n;
    if (crypto_aead_unlock(out, mac, key, nonce, ctx != NULL ? ctx : &z, ctx_len, ct, n) != 0) {
        crypto_wipe(out, n);
        return AVL_E_AUTH;
    }
    *out_len = n;
    return AVL_OK;
}

/* ====================================================================================================================================
 * autoprueba: vectores conocidos
 * ================================================================================================================================== */
static int hexval(char c) { return (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : -1; }
static int unhex(const char *h, uint8_t *dst, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        int a = hexval(h[2 * i]), b = hexval(h[2 * i + 1]);
        if (a < 0 || b < 0) { return 0; }
        dst[i] = (uint8_t)((a << 4) | b);
    }
    return 1;
}

int avl_selftest(void)
{
    /* 1 · RFC 8032 prueba 1 (mensaje vacio): la firma valida, y la misma con un bit cambiado no. */
    uint8_t pub[32], sig[64];
    if (!unhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", pub, 32) ||
        !unhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b", sig, 64)) {
        return AVL_E_SELFTEST - 1;
    }
    if (avl_verify_detached(NULL, 0, sig, pub) != AVL_OK) { return AVL_E_SELFTEST - 2; }
    sig[10] ^= 1u;
    if (avl_verify_detached(NULL, 0, sig, pub) != AVL_E_SIGNATURE) { return AVL_E_SELFTEST - 3; }
    /* 2 · RFC 8032 prueba 2 (un byte, 0x72) y firmar a partir de la semilla da la misma firma */
    uint8_t seed[32], sk[64], pk[32], msg = 0x72, mine[64], want[64];
    if (!unhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", seed, 32) ||
        !unhex("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00", want, 64) ||
        !unhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", pub, 32)) {
        return AVL_E_SELFTEST - 4;
    }
    crypto_ed25519_key_pair(sk, pk, seed);
    crypto_ed25519_sign(mine, sk, &msg, 1);
    crypto_wipe(sk, sizeof sk);
    if (memcmp(pk, pub, 32) != 0 || memcmp(mine, want, 64) != 0 || avl_verify_detached(&msg, 1, want, pub) != AVL_OK) { return AVL_E_SELFTEST - 5; }
    /* 3 · XChaCha20-Poly1305: vector A.3.1 del borrador draft-irtf-cfrg-xchacha */
    static const char PT_TXT[] = "Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, sunscreen would be it.";
    uint8_t key[32], nonce[24], ad[12], ct[sizeof PT_TXT - 1], tag[16], exp_tag[16], exp_ct[4];
    if (!unhex("808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f", key, 32) ||
        !unhex("404142434445464748494a4b4c4d4e4f5051525354555657", nonce, 24) || !unhex("50515253c0c1c2c3c4c5c6c7", ad, 12) ||
        !unhex("c0875924c1c7987947deafd8780acf49", exp_tag, 16) || !unhex("bd6d179d", exp_ct, 4)) {
        return AVL_E_SELFTEST - 6;
    }
    crypto_aead_lock(ct, tag, key, nonce, ad, sizeof ad, (const uint8_t *)PT_TXT, sizeof PT_TXT - 1);
    if (memcmp(tag, exp_tag, 16) != 0 || memcmp(ct, exp_ct, 4) != 0) { return AVL_E_SELFTEST - 7; }
    uint8_t back[sizeof PT_TXT - 1];
    if (crypto_aead_unlock(back, tag, key, nonce, ad, sizeof ad, ct, sizeof ct) != 0 || memcmp(back, PT_TXT, sizeof back) != 0) { return AVL_E_SELFTEST - 8; }
    ct[0] ^= 1u;
    if (crypto_aead_unlock(back, tag, key, nonce, ad, sizeof ad, ct, sizeof ct) == 0) { return AVL_E_SELFTEST - 9; }
    /* 4 · HMAC-SHA-512 (RFC 4231, caso 1) */
    uint8_t hkey[20], mac[64], exp_mac[8];
    memset(hkey, 0x0b, sizeof hkey);
    crypto_sha512_hmac(mac, hkey, sizeof hkey, (const uint8_t *)"Hi There", 8);
    if (!unhex("87aa7cdea5ef619d", exp_mac, 8) || memcmp(mac, exp_mac, 8) != 0) { return AVL_E_SELFTEST - 10; }
    return AVL_OK;
}
