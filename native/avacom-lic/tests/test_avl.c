/*
 * Pruebas en C de avacom_lic (Fase 4, P-20/P-21).
 *
 *   test_avl                         vectores (RFC 8032, XChaCha20-Poly1305 del borrador IRTF-CFRG, HMAC-SHA-512 RFC 4231) y casos de borde
 *   test_avl --mutate corpus.bin [N [semilla]]
 *                                    harness de mutacion: N (por omision 100000) alteraciones con semilla fija de licencias VALIDAS; 0 aceptadas
 *   test_avl --shape corpus.bin [N [semilla]]
 *                                    cuerpos alterados y RE-FIRMADOS (llaves de desarrollo): ejercita el lector de campos; sin fallos de memoria ni invariantes rotos
 *
 * Se compila junto con las fuentes (no contra la DLL) para poder correr con ASan (MSVC /fsanitize=address) y UBSan (clang del NDK).
 */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "avacom_lic.h"
#include "monocypher.h"
#include "monocypher-ed25519.h"
#include "vectors.h"

static int g_fail = 0, g_checks = 0;
#define CHECK(cond, ...) do { g_checks++; if (!(cond)) { g_fail++; printf("  FALLA %s:%d  ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

/* ------------------------------------------------------------------------------------------------------------------------------ vectores */
static void test_rfc8032(void)
{
    struct { const uint8_t *seed, *pub, *msg, *sig; size_t msg_len; } v[] = {
        {RFC8032_0_seed, RFC8032_0_pub, RFC8032_0_msg, RFC8032_0_sig, RFC8032_0_msg_len},
        {RFC8032_1_seed, RFC8032_1_pub, RFC8032_1_msg, RFC8032_1_sig, RFC8032_1_msg_len},
        {RFC8032_2_seed, RFC8032_2_pub, RFC8032_2_msg, RFC8032_2_sig, RFC8032_2_msg_len},
    };
    for (size_t i = 0; i < sizeof v / sizeof v[0]; i++) {
        const uint8_t *msg = v[i].msg_len ? v[i].msg : NULL;
        CHECK(avl_verify_detached(msg, v[i].msg_len, v[i].sig, v[i].pub) == AVL_OK, "RFC 8032 vector %zu: la firma valida no verifico", i);
        /* firmar desde la semilla da exactamente la firma de la norma y la misma publica */
        uint8_t seed[32], sk[64], pk[32], sig[64];
        memcpy(seed, v[i].seed, 32);
        crypto_ed25519_key_pair(sk, pk, seed);
        crypto_ed25519_sign(sig, sk, v[i].msg, v[i].msg_len);
        CHECK(memcmp(pk, v[i].pub, 32) == 0, "RFC 8032 vector %zu: la publica derivada no coincide", i);
        CHECK(memcmp(sig, v[i].sig, 64) == 0, "RFC 8032 vector %zu: la firma generada no coincide", i);
        /* cualquier bit cambiado en mensaje, firma o llave se rechaza */
        for (size_t b = 0; b < 64 * 8; b += 13) {
            uint8_t s2[64];
            memcpy(s2, v[i].sig, 64);
            s2[b / 8] ^= (uint8_t)(1u << (b % 8));
            CHECK(avl_verify_detached(msg, v[i].msg_len, s2, v[i].pub) != AVL_OK, "RFC 8032 vector %zu: firma alterada (bit %zu) aceptada", i, b);
        }
        for (size_t b = 0; b < 32 * 8; b += 7) {
            uint8_t p2[32];
            memcpy(p2, v[i].pub, 32);
            p2[b / 8] ^= (uint8_t)(1u << (b % 8));
            CHECK(avl_verify_detached(msg, v[i].msg_len, v[i].sig, p2) != AVL_OK, "RFC 8032 vector %zu: llave alterada (bit %zu) aceptada", i, b);
        }
        if (v[i].msg_len > 0) {
            uint8_t m2[128];
            memcpy(m2, v[i].msg, v[i].msg_len);
            m2[0] ^= 1u;
            CHECK(avl_verify_detached(m2, v[i].msg_len, v[i].sig, v[i].pub) != AVL_OK, "RFC 8032 vector %zu: mensaje alterado aceptado", i);
        }
        /* S + L es la misma firma «escrita de otra forma» (maleabilidad): se rechaza */
        uint8_t big[64];
        memcpy(big, v[i].sig, 64);
        uint16_t carry = 0;
        static const uint8_t L[32] = {0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14,
                                      0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10};
        for (int j = 0; j < 32; j++) { carry = (uint16_t)(carry + big[32 + j] + L[j]); big[32 + j] = (uint8_t)carry; carry >>= 8; }
        CHECK(avl_verify_detached(msg, v[i].msg_len, big, v[i].pub) != AVL_OK, "RFC 8032 vector %zu: S+L aceptada (maleabilidad)", i);
    }
    CHECK(avl_verify_detached(NULL, 0, NULL, NULL) == AVL_E_ARG, "argumentos nulos");
}

static void test_xchacha(void)
{
    uint8_t out[sizeof XCHACHA_PT + AVL_WRAP_OVERHEAD];
    size_t n = 0;
    CHECK(avl_key_wrap(XCHACHA_KEY, XCHACHA_NONCE, XCHACHA_AAD, XCHACHA_AAD_len, XCHACHA_PT, XCHACHA_PT_len, out, sizeof out, &n) == AVL_OK, "wrap");
    CHECK(n == XCHACHA_PT_len + AVL_WRAP_OVERHEAD, "largo de la envoltura");
    CHECK(memcmp(out, XCHACHA_NONCE, 24) == 0, "la envoltura empieza con el nonce");
    CHECK(memcmp(out + 24, XCHACHA_CT, XCHACHA_CT_len) == 0, "texto cifrado = vector A.3.1 del borrador IRTF-CFRG");
    CHECK(memcmp(out + 24 + XCHACHA_PT_len, XCHACHA_TAG, 16) == 0, "etiqueta = vector A.3.1");
    uint8_t back[sizeof XCHACHA_PT];
    size_t bn = 0;
    CHECK(avl_key_unwrap(XCHACHA_KEY, XCHACHA_AAD, XCHACHA_AAD_len, out, n, back, sizeof back, &bn) == AVL_OK && bn == XCHACHA_PT_len && memcmp(back, XCHACHA_PT, bn) == 0,
          "unwrap devuelve el texto claro");
    /* el contexto es dato asociado: otro contexto, otra llave, un bit del texto o de la etiqueta no abren */
    CHECK(avl_key_unwrap(XCHACHA_KEY, XCHACHA_AAD, XCHACHA_AAD_len - 1, out, n, back, sizeof back, &bn) == AVL_E_AUTH, "otro contexto");
    CHECK(avl_key_unwrap(XCHACHA_KEY, NULL, 0, out, n, back, sizeof back, &bn) == AVL_E_AUTH, "sin contexto");
    uint8_t other[32];
    memcpy(other, XCHACHA_KEY, 32);
    other[5] ^= 1u;
    CHECK(avl_key_unwrap(other, XCHACHA_AAD, XCHACHA_AAD_len, out, n, back, sizeof back, &bn) == AVL_E_AUTH, "otra llave");
    for (size_t i = 0; i < n; i += 11) {
        uint8_t w[sizeof out];
        memcpy(w, out, n);
        w[i] ^= 0x01u;
        CHECK(avl_key_unwrap(XCHACHA_KEY, XCHACHA_AAD, XCHACHA_AAD_len, w, n, back, sizeof back, &bn) == AVL_E_AUTH, "bit alterado en %zu", i);
    }
    CHECK(avl_key_unwrap(XCHACHA_KEY, NULL, 0, out, 10, back, sizeof back, &bn) == AVL_E_FORMAT, "envoltura demasiado corta");
    CHECK(avl_key_unwrap(XCHACHA_KEY, XCHACHA_AAD, XCHACHA_AAD_len, out, n, back, 3, &bn) == AVL_E_SMALL, "buffer corto");
    /* texto vacio y sin contexto */
    uint8_t nonce[24] = {1}, empty[AVL_WRAP_OVERHEAD];
    CHECK(avl_key_wrap(XCHACHA_KEY, nonce, NULL, 0, NULL, 0, empty, sizeof empty, &n) == AVL_OK && n == AVL_WRAP_OVERHEAD, "wrap vacio");
    CHECK(avl_key_unwrap(XCHACHA_KEY, NULL, 0, empty, n, back, sizeof back, &bn) == AVL_OK && bn == 0, "unwrap vacio");
}

static void test_hmac_hkdf(void)
{
    uint8_t mac[64];
    crypto_sha512_hmac(mac, HMAC512_KEY, HMAC512_KEY_len, HMAC512_MSG, HMAC512_MSG_len);
    CHECK(memcmp(mac, HMAC512_OUT, 64) == 0, "HMAC-SHA-512 RFC 4231 caso 1");
    uint8_t a[42], b[42];
    CHECK(avl_key_derive(HMAC512_KEY, 20, NULL, 0, NULL, 0, a, sizeof a) == AVL_OK, "derive");
    CHECK(avl_key_derive(HMAC512_KEY, 20, NULL, 0, NULL, 0, b, sizeof b) == AVL_OK && memcmp(a, b, sizeof a) == 0, "derive es determinista");
    CHECK(avl_key_derive(HMAC512_KEY, 20, (const uint8_t *)"s", 1, NULL, 0, b, sizeof b) == AVL_OK && memcmp(a, b, sizeof a) != 0, "la sal cambia la llave");
    CHECK(avl_key_derive(HMAC512_KEY, 20, NULL, 0, (const uint8_t *)"ctx", 3, b, sizeof b) == AVL_OK && memcmp(a, b, sizeof a) != 0, "el contexto cambia la llave");
    CHECK(avl_key_derive(NULL, 0, NULL, 0, NULL, 0, a, sizeof a) == AVL_E_ARG, "derive sin secreto");
    CHECK(avl_key_derive(HMAC512_KEY, 20, NULL, 0, NULL, 0, a, 0) == AVL_E_ARG, "derive de largo cero");
}

/* ------------------------------------------------------------------------------------------------------------------------------ huella / reloj / smbios */
static void test_misc(void)
{
    CHECK(avl_abi_version() == AVL_ABI_VERSION, "ABI");
    CHECK(avl_selftest() == 0, "avl_selftest devolvio %d", avl_selftest());

    /* fp_match: 3 de 4 coinciden */
    uint8_t factor[4] = {1, 2, 3, 4};
    uint8_t hash[4][32];
    avl_fp_current cur;
    memset(&cur, 0, sizeof cur);
    for (int i = 0; i < 4; i++) { memset(hash[i], 0x10 + i, 32); }
    cur.count = 4;
    for (int i = 0; i < 4; i++) { cur.factor[i] = factor[i]; memcpy(cur.hash[i], hash[i], 32); }
    memset(cur.hash[3], 0xEE, 32);
    avl_fp_result r;
    CHECK(avl_fp_match(3, 4, factor, (const uint8_t (*)[32])hash, &cur, &r) == AVL_OK && r.matches == 3 && r.ok && r.partial && r.level == AVL_LEVEL_HARDWARE, "fp 3 de 4");
    CHECK(avl_fp_match(4, 4, factor, (const uint8_t (*)[32])hash, &cur, &r) == AVL_OK && r.matches == 3 && !r.ok && !r.partial, "fp exige 4");
    uint8_t f2[1] = {AVL_FACTOR_INSTALLATION};
    uint8_t h2[1][32];
    memset(h2[0], 0x77, 32);
    cur.has_installation = 1;
    memset(cur.installation_hash, 0x77, 32);
    CHECK(avl_fp_match(1, 1, f2, (const uint8_t (*)[32])h2, &cur, &r) == AVL_OK && r.ok && !r.partial && r.level == AVL_LEVEL_INSTALLATION, "fp de instalacion");
    cur.has_installation = 0;
    CHECK(avl_fp_match(1, 1, f2, (const uint8_t (*)[32])h2, &cur, &r) == AVL_OK && !r.ok, "fp de instalacion ausente");

    /* ancla del reloj: la marca no baja; un MAC alterado no cuenta */
    uint8_t secret[32], mac1[32], mac2[32], ok = 9;
    memset(secret, 0x42, sizeof secret);
    uint64_t next = 0;
    CHECK(avl_clock_advance(secret, sizeof secret, 0, NULL, 0, 0, 1000, &next, mac1, &ok) == AVL_OK && next == 1000 && ok == 1, "ancla: primera marca");
    CHECK(avl_clock_advance(secret, sizeof secret, 1000, mac1, 0, 0, 500, &next, mac2, &ok) == AVL_OK && next == 1000 && ok == 1 && memcmp(mac1, mac2, 32) == 0, "ancla: la marca no baja");
    mac1[3] ^= 1u;
    CHECK(avl_clock_advance(secret, sizeof secret, 1000, mac1, 0, 0, 500, &next, mac2, &ok) == AVL_OK && ok == 0 && next == 500, "ancla alterada: no cuenta, no sube la marca");
    CHECK(avl_clock_advance(NULL, 0, 0, NULL, 0, 0, 1, &next, mac2, &ok) == AVL_E_ARG, "ancla sin secreto");

    /* smbios: una tabla fabricada con sistema (UUID y serie) y placa; luego una rota */
    uint8_t t[8 + 64] = {0};
    size_t p = 8;
    t[p++] = 1; t[p++] = 25; t[p++] = 0; t[p++] = 0;                 /* tipo 1, largo 25, handle */
    for (int i = 4; i < 25; i++) { t[p + (size_t)(i - 4)] = 0; }
    t[8 + 4 + 3] = 0;                                                  /* sin fabricante: indices 0 */
    t[8 + 7] = 1;                                                      /* serie = cadena 1 */
    for (int i = 0; i < 16; i++) { t[8 + 8 + i] = (uint8_t)(i + 1); }
    p = 8 + 25;
    t[p++] = 'S'; t[p++] = 'N'; t[p++] = '1'; t[p++] = 0; t[p++] = 0;
    uint8_t tail[2] = {127, 4};
    t[p++] = tail[0]; t[p++] = tail[1]; t[p++] = 0; t[p++] = 0; t[p++] = 0; t[p++] = 0;
    t[4] = (uint8_t)(p - 8);
    avl_smbios sm;
    CHECK(avl_smbios_parse(t, p, &sm) == AVL_OK, "smbios parse");
    CHECK(strcmp(sm.system_serial, "SN1") == 0, "serie del sistema: '%s'", sm.system_serial);
    CHECK(strcmp(sm.uuid, "04030201-0605-0807-090A-0B0C0D0E0F10") == 0, "uuid en formato mixto: '%s'", sm.uuid);
    CHECK(avl_smbios_parse(t, 3, &sm) == AVL_OK && sm.uuid[0] == 0, "tabla demasiado corta: vacia");
    uint8_t basura[256];
    for (size_t i = 0; i < sizeof basura; i++) { basura[i] = (uint8_t)(i * 31u + 7u); }
    CHECK(avl_smbios_parse(basura, sizeof basura, &sm) == AVL_OK, "tabla de basura no revienta");

    /* solicitud: firmada, verificable con su propia llave, y el mismo resultado dos veces (Ed25519 es determinista) */
    avl_request_in in;
    memset(&in, 0, sizeof in);
    memset(in.node_seed, 0x33, 32);
    memset(in.nonce, 0x55, 16);
    in.created_ms = 1790000000000ull;
    in.level = AVL_LEVEL_HARDWARE;
    in.fp_k = 2; in.fp_n = 2;
    in.fp_factor[0] = 1; in.fp_factor[1] = 3;
    memset(in.fp_hash[0], 0xA1, 32); memset(in.fp_hash[1], 0xB2, 32);
    in.version = (const uint8_t *)"2.15.0";
    in.version_len = 6;
    uint8_t req1[1024], req2[1024];
    size_t l1 = sizeof req1, l2 = sizeof req2;
    CHECK(avl_request_build(&in, req1, &l1) == AVL_OK && avl_request_build(&in, req2, &l2) == AVL_OK && l1 == l2 && memcmp(req1, req2, l1) == 0, "solicitud determinista");
    CHECK(memcmp(req1, "AVRQ", 4) == 0 && req1[6] == 64, "cabecera de la solicitud");
    uint8_t seed[32], sk[64], pk[32];
    memset(seed, 0x33, 32);
    crypto_ed25519_key_pair(sk, pk, seed);
    CHECK(avl_verify_detached(req1, l1 - 64, req1 + l1 - 64, pk) == AVL_OK, "la solicitud verifica con la llave del nodo");
    size_t tiny = 20;
    CHECK(avl_request_build(&in, req2, &tiny) == AVL_E_SMALL, "buffer corto");
    in.fp_k = 3;
    l2 = sizeof req2;
    CHECK(avl_request_build(&in, req2, &l2) == AVL_E_ARG, "k mayor que n");

    /* avl_license_verify: entradas hostiles */
    avl_policy pol = {0, 0, 0};
    avl_license lic;
    uint8_t junk[200];
    memset(junk, 0, sizeof junk);
    CHECK(avl_license_verify(NULL, 0, NULL, 0, &pol, NULL, &lic) == AVL_E_ARG, "datos nulos");
    CHECK(avl_license_verify(junk, 10, NULL, 0, &pol, NULL, &lic) == AVL_E_TOO_SHORT, "demasiado corta");
    CHECK(avl_license_verify(junk, 100, NULL, 0, &pol, NULL, &lic) == AVL_E_FORMAT, "sin magic");
    memcpy(junk, "AVLC", 4);
    CHECK(avl_license_verify(junk, 100, NULL, 0, &pol, NULL, &lic) == AVL_E_VERSION, "version 0");
    uint8_t *grande = (uint8_t *)calloc(AVL_MAX_FILE + 1, 1);
    CHECK(grande != NULL && avl_license_verify(grande, AVL_MAX_FILE + 1, NULL, 0, &pol, NULL, &lic) == AVL_E_TOO_BIG, "demasiado grande");
    free(grande);

    avl_wipe(secret, sizeof secret);
    CHECK(secret[0] == 0 && secret[31] == 0, "avl_wipe");
}

/* ------------------------------------------------------------------------------------------------------------------------------ mutacion */
static uint64_t g_state = 1;
static uint64_t rnd(void)
{
    g_state ^= g_state >> 12; g_state ^= g_state << 25; g_state ^= g_state >> 27;
    return g_state * 0x2545F4914F6CDD1Dull;
}
static size_t rnd_below(size_t n) { return n == 0 ? 0 : (size_t)(rnd() % n); }

typedef struct entry { char kid[AVL_MAX_KID + 1]; uint8_t pub[32]; uint8_t seed[32]; uint8_t data[AVL_MAX_FILE]; size_t len; } entry;

static int load_corpus(const char *path, entry **out, size_t *count)
{
    FILE *f = fopen(path, "rb");
    if (f == NULL) { return 0; }
    uint8_t h[4];
    if (fread(h, 1, 4, f) != 4) { fclose(f); return 0; }
    size_t n = ((size_t)h[0] << 24) | ((size_t)h[1] << 16) | ((size_t)h[2] << 8) | h[3];
    entry *e = (entry *)calloc(n, sizeof *e);
    if (e == NULL) { fclose(f); return 0; }
    for (size_t i = 0; i < n; i++) {
        uint8_t kl;
        uint8_t l2[2];
        if (fread(&kl, 1, 1, f) != 1 || kl > AVL_MAX_KID || fread(e[i].kid, 1, kl, f) != kl || fread(e[i].pub, 1, 32, f) != 32 || fread(e[i].seed, 1, 32, f) != 32 || fread(l2, 1, 2, f) != 2) { fclose(f); free(e); return 0; }
        e[i].len = ((size_t)l2[0] << 8) | l2[1];
        if (e[i].len > sizeof e[i].data || fread(e[i].data, 1, e[i].len, f) != e[i].len) { fclose(f); free(e); return 0; }
    }
    fclose(f);
    *out = e;
    *count = n;
    return 1;
}

static size_t mutate(const entry *e, uint8_t *m)
{
    size_t n = e->len;
    size_t cap = AVL_MAX_FILE + 64;
    for (;;) {
        memcpy(m, e->data, n);
        size_t len = n;
        switch (rnd_below(11)) {
        case 0: m[rnd_below(len)] ^= (uint8_t)(1u << rnd_below(8)); break;
        case 1: for (size_t k = 2 + rnd_below(15); k > 0; k--) { m[rnd_below(len)] ^= (uint8_t)(1u << rnd_below(8)); } break;
        case 2: m[rnd_below(len)] = (uint8_t)rnd(); break;
        case 3: { size_t a = rnd_below(len), b = a + 1 + rnd_below(32); if (b > len) { b = len; } for (size_t k = a; k < b; k++) { m[k] = (uint8_t)rnd(); } break; }
        case 4: { size_t i = rnd_below(len + 1), add = 1 + rnd_below(16); if (len + add <= cap) { memmove(m + i + add, m + i, len - i); for (size_t k = 0; k < add; k++) { m[i + k] = (uint8_t)rnd(); } len += add; } break; }
        case 5: { size_t i = rnd_below(len), del = 1 + rnd_below(16); if (i + del > len) { del = len - i; } memmove(m + i, m + i + del, len - i - del); len -= del; break; }
        case 6: len = rnd_below(len); break;                                                                             /* truncar */
        case 7: { size_t add = 1 + rnd_below(64); if (len + add <= cap) { for (size_t k = 0; k < add; k++) { m[len + k] = (uint8_t)rnd(); } len += add; } break; }   /* bytes sobrantes */
        case 8: { size_t a = rnd_below(len), b = rnd_below(len); uint8_t t = m[a]; m[a] = m[b]; m[b] = t; break; }
        case 9: { size_t a = rnd_below(len), c = 1 + rnd_below(24); if (a + c <= len && len + c <= cap) { memmove(m + a + c, m + a, len - a); len += c; } break; }  /* duplica un tramo */
        default: { size_t i = rnd_below(len); m[i] = (uint8_t)(m[i] + 1u); break; }
        }
        if (len != n || memcmp(m, e->data, n) != 0) { return len; }
    }
}

static int run_mutation(const char *corpus, long total, uint64_t seed)
{
    entry *entries = NULL;
    size_t n = 0;
    if (!load_corpus(corpus, &entries, &n) || n == 0) { printf("No se pudo leer el corpus '%s'\n", corpus); return 2; }
    avl_key *keys = (avl_key *)calloc(n, sizeof *keys);
    size_t nk = 0;
    for (size_t i = 0; i < n; i++) {
        int dup = 0;
        for (size_t j = 0; j < nk; j++) { if (strcmp(keys[j].kid, entries[i].kid) == 0) { dup = 1; } }
        if (!dup) { memcpy(keys[nk].kid, entries[i].kid, strlen(entries[i].kid) + 1); memcpy(keys[nk].pub, entries[i].pub, 32); nk++; }
    }
    avl_policy pol = {1790000000000ull, 86400000ull, 0};
    avl_license lic;
    int bad = 0;
    for (size_t i = 0; i < n; i++) {
        if (avl_license_verify(entries[i].data, entries[i].len, keys, nk, &pol, NULL, &lic) != AVL_OK) { bad++; }
    }
    printf("Corpus: %zu licencias validas, %zu llaves; originales rechazados: %d\n", n, nk, bad);
    if (bad != 0) { return 1; }
    g_state = seed ? seed : 1;
    uint8_t *m = (uint8_t *)malloc(AVL_MAX_FILE + 128);
    long accepted = 0, by_code[20] = {0};
    for (long i = 0; i < total; i++) {
        const entry *e = &entries[rnd_below(n)];
        size_t len = mutate(e, m);
        int rc = avl_license_verify(m, len, keys, nk, &pol, NULL, &lic);
        if (rc == AVL_OK) { accepted++; }
        int idx = rc < 0 ? -rc : 0;
        by_code[idx < 20 ? idx : 19]++;
    }
    printf("Mutaciones: %ld (semilla %" PRIu64 ") · aceptadas: %ld\n", total, seed, accepted);
    printf("  rechazos por codigo:");
    for (int c = 1; c < 20; c++) { if (by_code[c]) { printf(" [%d]=%ld", -c, by_code[c]); } }
    printf("\n");
    free(m); free(keys); free(entries);
    return accepted == 0 ? 0 : 1;
}

/* Mutacion del CUERPO re-firmado (con la semilla de DESARROLLO del corpus): la firma es valida y lo que se ejercita es el lector de campos y las reglas de forma.
 * No hay veredicto «correcto» que comparar aqui (eso lo hacen las pruebas diferenciales contra la referencia en Python); lo que se exige es que NO haya fallo de memoria
 * ni comportamiento indefinido (ASan/UBSan) y que, cuando se acepta, el resultado cumpla los invariantes de forma. */
static int check_invariants(const avl_license *l)
{
    return l->serie >= 1u && l->grace_days <= 365u && l->issued_ms > 0 && l->issued_ms < ((uint64_t)1 << 62) && l->from_ms > 0 && l->from_ms < l->until_ms &&
           l->until_ms < ((uint64_t)1 << 62) && l->until_ms - l->from_ms <= (uint64_t)25 * 366 * 86400000ull && l->equipos >= 1u && l->usuarios >= 1u && l->concurrent_normal >= 1u &&
           l->concurrent_normal <= l->concurrent_peak && l->type >= 1u && l->type <= 3u && l->fp_n >= 1u && l->fp_n <= AVL_MAX_FACTORS && l->fp_k >= 1u && l->fp_k <= l->fp_n &&
           l->aula_len <= 480u && l->caps_len <= 1024u && strlen(l->kid) >= 1u;
}

static int run_shape(const char *corpus, long total, uint64_t seed)
{
    entry *entries = NULL;
    size_t n = 0;
    if (!load_corpus(corpus, &entries, &n) || n == 0) { printf("No se pudo leer el corpus '%s'\n", corpus); return 2; }
    avl_key *keys = (avl_key *)calloc(n, sizeof *keys);
    size_t nk = 0;
    for (size_t i = 0; i < n; i++) {
        int dup = 0;
        for (size_t j = 0; j < nk; j++) { if (strcmp(keys[j].kid, entries[i].kid) == 0) { dup = 1; } }
        if (!dup) { memcpy(keys[nk].kid, entries[i].kid, strlen(entries[i].kid) + 1); memcpy(keys[nk].pub, entries[i].pub, 32); nk++; }
    }
    avl_policy pol = {1790000000000ull, 86400000ull, AVL_P_CHECK_START};
    avl_license lic;
    g_state = seed ? seed : 1;
    uint8_t *m = (uint8_t *)malloc(AVL_MAX_FILE + 128);
    long accepted = 0, bad_invariant = 0, by_code[20] = {0};
    for (long i = 0; i < total; i++) {
        const entry *e = &entries[rnd_below(n)];
        size_t klen = strlen(e->kid);
        size_t head = 7 + klen;
        size_t blen = e->len - head - 64;
        memcpy(m, e->data, head + blen);
        size_t len = head + blen;
        for (size_t ops = 1 + rnd_below(4); ops > 0; ops--) {
            size_t body = len - head;
            switch (rnd_below(9)) {
            case 0: if (body > 0) { m[head + rnd_below(body)] ^= (uint8_t)(1u << rnd_below(8)); } break;
            case 1: if (body > 0) { m[head + rnd_below(body)] = (uint8_t)rnd(); } break;
            case 2: if (body > 0) { size_t a = rnd_below(body), b = a + 1 + rnd_below(8); if (b > body) { b = body; } for (size_t k = a; k < b; k++) { m[head + k] = (uint8_t)rnd(); } } break;
            case 3: if (body > 0) { size_t cut = rnd_below(body); len = head + cut; } break;
            case 4: { size_t add = 1 + rnd_below(24); if (len + add + 64 <= AVL_MAX_FILE) { for (size_t k = 0; k < add; k++) { m[len + k] = (uint8_t)rnd(); } len += add; } break; }
            case 5: if (body > 4) { size_t i2 = head + rnd_below(body - 1); m[i2] ^= 0x80u; } break;                  /* bit critico o alto de un largo */
            case 6: if (body > 4) { size_t i2 = head + rnd_below(body - 1); m[i2] = 0xFFu; } break;                    /* 0xFF: largos y topes en el borde */
            case 7: if (body > 4) { size_t i2 = head + rnd_below(body - 1); m[i2] = 0x00u; } break;
            default: if (body > 8) { size_t a = head + rnd_below(body - 4), b = head + rnd_below(body - 4); memcpy(m + a, m + b, 4); } break;
            }
        }
        uint8_t sk[64], pk[32], sd[32];
        memcpy(sd, e->seed, 32);
        crypto_ed25519_key_pair(sk, pk, sd);
        crypto_ed25519_sign(m + len, sk, m, len);
        crypto_wipe(sk, sizeof sk);
        int rc = avl_license_verify(m, len + 64, keys, nk, &pol, NULL, &lic);
        if (rc == AVL_OK) {
            accepted++;
            if (!check_invariants(&lic)) { bad_invariant++; }
        }
        int idx = rc < 0 ? -rc : 0;
        by_code[idx < 20 ? idx : 19]++;
    }
    printf("Cuerpos re-firmados: %ld (semilla %" PRIu64 ") · aceptados: %ld · invariantes rotos: %ld\n", total, seed, accepted, bad_invariant);
    printf("  resultados por codigo:");
    for (int c = 1; c < 20; c++) { if (by_code[c]) { printf(" [%d]=%ld", -c, by_code[c]); } }
    printf("\n");
    free(m); free(keys); free(entries);
    return bad_invariant == 0 ? 0 : 1;
}

int main(int argc, char **argv)
{
    if (argc >= 3 && strcmp(argv[1], "--shape") == 0) {
        long total = argc >= 4 ? atol(argv[3]) : 100000L;
        uint64_t seed = argc >= 5 ? (uint64_t)strtoull(argv[4], NULL, 10) : 20261023ull;
        return run_shape(argv[2], total, seed);
    }
    if (argc >= 3 && strcmp(argv[1], "--mutate") == 0) {
        long total = argc >= 4 ? atol(argv[3]) : 100000L;
        uint64_t seed = argc >= 5 ? (uint64_t)strtoull(argv[4], NULL, 10) : 20261022ull;
        return run_mutation(argv[2], total, seed);
    }
    test_rfc8032();
    test_xchacha();
    test_hmac_hkdf();
    test_misc();
    printf("%d comprobaciones, %d fallas\n", g_checks, g_fail);
    return g_fail == 0 ? 0 : 1;
}
