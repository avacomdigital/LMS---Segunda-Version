/*
 * avl_fp_collect: solo Windows. MachineGuid (registro) y la tabla SMBIOS (GetSystemFirmwareTable 'RSMB'); la interpretacion es avl_smbios_parse.
 * Sin malloc: la tabla se lee en un buffer de la pila; una tabla mas grande devuelve AVL_E_SMALL y el nodo usa la referencia.
 * Solo lectura y sin privilegios elevados (como infraestructura/huella_windows.py).
 */
#include "avacom_lic.h"

#include <string.h>

#if defined(_WIN32)

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#define AVL_SMBIOS_BUFFER (96u * 1024u)

int avl_fp_collect(avl_hw *out)
{
    if (out == NULL) { return AVL_E_ARG; }
    memset(out, 0, sizeof *out);

    wchar_t guid[64];
    DWORD size = (DWORD)sizeof guid;
    LSTATUS st = RegGetValueW(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Microsoft\\Cryptography", L"MachineGuid", RRF_RT_REG_SZ | RRF_SUBKEY_WOW6464KEY, NULL, guid, &size);
    if (st == ERROR_SUCCESS) {
        int n = WideCharToMultiByte(CP_UTF8, 0, guid, -1, out->machine_guid, (int)sizeof out->machine_guid, NULL, NULL);
        if (n <= 0) { out->machine_guid[0] = '\0'; }
    }

    static const DWORD RSMB = 0x52534D42u;      /* 'RSMB' */
    uint8_t table[AVL_SMBIOS_BUFFER];
    UINT need = GetSystemFirmwareTable(RSMB, 0, NULL, 0);
    if (need == 0) { return AVL_OK; }           /* sin tabla: la huella de instalacion se encarga (igual que la referencia) */
    if (need > sizeof table) { return AVL_E_SMALL; }
    UINT got = GetSystemFirmwareTable(RSMB, 0, table, (DWORD)sizeof table);
    if (got == 0 || got > sizeof table) { return AVL_OK; }
    return avl_smbios_parse(table, got, &out->smbios);
}

#else

int avl_fp_collect(avl_hw *out)
{
    if (out != NULL) { memset(out, 0, sizeof *out); }
    return AVL_E_UNSUPPORTED;
}

#endif
