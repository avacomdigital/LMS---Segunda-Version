r"""
La línea de comandos del Emisor de Paquetes de Actualización (uso interno de AVACOM, sin red).

    avacom-actualizacion llaves nueva  --kid upd-2026-1 --salida F:\claves          crea upd-2026-1.avkey (cifrada) y upd-2026-1.pub
    avacom-actualizacion llaves nodo   --publica upd-2026-1.pub                     imprime la entrada para backend\actualizacion\claves\produccion.json
    avacom-actualizacion emitir        --descripcion paquete.json --privada F:\claves\upd-2026-1.avkey --salida reportes-1.4.0.avupd [--origen backend]
    avacom-actualizacion verificar     reportes-1.4.0.avupd --publica upd-2026-1.pub
    avacom-actualizacion ver           reportes-1.4.0.avupd
    avacom-actualizacion plantilla     > paquete.json

La frase de paso de la llave se pide en la consola (no se muestra); para automatizar una prueba existe AVACOM_FRASE_LLAVE, que NO debe usarse con una llave de producción.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, llaves
from .dominio_nodo import RAIZ
from .dominio_nodo import firma
from .emision import ErrorDeEmision, emitir, verificar
from .dominio_nodo import manifiesto as mf

PLANTILLA = {
    "nombre": "Reportes 1.4.0 · corrección del boletín",
    "version_producto": "2.13.0",
    "version_minima": "2.12.0",
    "nota": "Qué cambia, en una frase que el administrador entienda.",
    "requisitos": {"contrato_biblioteca": 2, "cliente_minimo": "2.12.0", "espacio_bytes": 0, "contrato_red": None},
    "modulos": [{
        "nombre": "reporting", "version": "1.4.0", "version_datos": 4, "version_contrato": 1, "serie": 7, "cambia_contrato": False, "requiere": {"nodo": 1},
        "migraciones": [{"nombre": "0004_boletin", "reverso": "0003_corte_cola_unica"}],
        "archivos": ["reporting/dominio/boletin.py", "reporting/migrations/0004_boletin.py"],
    }],
    "archivos_extra": ["avacom_lms/modulos.json"],
}


def _frase(mensaje: str) -> str:
    return os.environ.get("AVACOM_FRASE_LLAVE") or getpass.getpass(mensaje)


def _cmd_llaves_nueva(a) -> int:
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    kid = llaves.kid_valido(a.kid)
    for sufijo in (".avkey", ".pub"):
        if (salida / (kid + sufijo)).exists():
            raise llaves.ErrorDeLlave(f"Ya existe {kid}{sufijo} en {salida}: no se sobrescribe una llave.")
    frase = _frase("Frase de paso (mínimo 16 caracteres): ")
    if not os.environ.get("AVACOM_FRASE_LLAVE") and getpass.getpass("Repite la frase de paso: ") != frase:
        raise llaves.ErrorDeLlave("Las dos frases no coinciden.")
    avkey, pub, _ = llaves.generar(kid, frase, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    (salida / (kid + ".avkey")).write_bytes(avkey)
    (salida / (kid + ".pub")).write_text(pub, encoding="utf-8")
    print(f"Llave creada: {salida / (kid + '.avkey')} (PRIVADA: guárdala en su memoria USB, nunca en el repositorio) y {salida / (kid + '.pub')} (pública).")
    return 0


def _cmd_llaves_nodo(a) -> int:
    kid, publica = llaves.leer_publica(Path(a.publica).read_text(encoding="utf-8"))
    print(llaves.entrada_para_el_nodo(kid, publica, a.estado), end="")
    return 0


def _cmd_emitir(a) -> int:
    descripcion = json.loads(Path(a.descripcion).read_text(encoding="utf-8-sig"))
    origen = Path(a.origen) if a.origen else RAIZ.parents[1] / "backend"
    llave = llaves.abrir(Path(a.privada).read_bytes(), _frase("Frase de paso de la llave: "))
    datos, m = emitir(descripcion, origen, llave.kid, llave.privada)
    salida = Path(a.salida)
    if salida.exists() and not a.sobrescribir:
        raise ErrorDeEmision(f"{salida} ya existe (usa --sobrescribir si de verdad quieres reemplazarlo).")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_bytes(datos)
    print(f"Paquete emitido: {salida}")
    print(f"  id {m.paquete_id} · {m.nombre} · producto {m.version_producto} (mínimo {m.version_minima}) · serie {m.serie}")
    print(f"  módulos: {', '.join(m.nombres_de_modulos)} · {len(m.archivos)} archivo(s), {m.bytes_total} bytes · firmado con {llave.kid}")
    print("  El paquete se verificó como lo verifica un nodo antes de guardarlo.")
    return 0


def _claves_para(a) -> dict[str, bytes]:
    if a.publica:
        kid, publica = llaves.leer_publica(Path(a.publica).read_text(encoding="utf-8"))
        return {kid: publica}
    return llaves.leer_claves_del_nodo(Path(a.claves).read_text(encoding="utf-8-sig"))


def _cmd_verificar(a) -> int:
    p = verificar(Path(a.paquete).read_bytes(), _claves_para(a))
    print(f"Paquete válido: firmado con {p.kid}, {len(p.manifiesto.archivos)} archivo(s), SHA-256 {p.sha256}.")
    return 0


def _cmd_ver(a) -> int:
    datos = Path(a.paquete).read_bytes()
    # `ver` no firma ni verifica nada: sólo muestra lo que dice el manifiesto (la firma se comprueba con `verificar`).
    from .dominio_nodo import contenedor, catalogos as cat
    entradas = {e.nombre: e for e in contenedor.abrir(datos)}
    m = mf.leer(contenedor.leer(datos, entradas[cat.NOMBRE_MANIFIESTO], cat.MAX_MANIFIESTO_BYTES))
    print(json.dumps(mf.resumen(m), ensure_ascii=False, indent=2))
    print("(la firma NO se comprobó: usa «verificar» con la llave pública)")
    return 0


def _cmd_plantilla(a) -> int:
    print(json.dumps(PLANTILLA, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="avacom-actualizacion", description=f"Emisor de Paquetes de Actualización de AVACOM {__version__} (uso interno, sin red)")
    sub = p.add_subparsers(dest="orden", required=True)

    ll = sub.add_parser("llaves", help="generar y publicar llaves de publicación").add_subparsers(dest="sub", required=True)
    n = ll.add_parser("nueva", help="crea el par de llaves (la privada cifrada con una frase de paso)")
    n.add_argument("--kid", required=True)
    n.add_argument("--salida", required=True)
    n.set_defaults(f=_cmd_llaves_nueva)
    nd = ll.add_parser("nodo", help="imprime la entrada de la llave pública para claves/produccion.json")
    nd.add_argument("--publica", required=True)
    nd.add_argument("--estado", choices=("vigente", "siguiente", "retirada"), default="vigente")
    nd.set_defaults(f=_cmd_llaves_nodo)

    e = sub.add_parser("emitir", help="arma y firma un paquete .avupd")
    e.add_argument("--descripcion", required=True)
    e.add_argument("--privada", required=True)
    e.add_argument("--salida", required=True)
    e.add_argument("--origen", help="carpeta backend de donde salen los archivos (por defecto, la del repositorio)")
    e.add_argument("--sobrescribir", action="store_true")
    e.set_defaults(f=_cmd_emitir)

    v = sub.add_parser("verificar", help="verifica un paquete como lo hace el nodo")
    v.add_argument("paquete")
    g = v.add_mutually_exclusive_group(required=True)
    g.add_argument("--publica", help="un .pub")
    g.add_argument("--claves", help="un archivo en el formato de produccion.json")
    v.set_defaults(f=_cmd_verificar)

    ve = sub.add_parser("ver", help="muestra el manifiesto de un paquete (sin comprobar la firma)")
    ve.add_argument("paquete")
    ve.set_defaults(f=_cmd_ver)

    pl = sub.add_parser("plantilla", help="imprime una descripción de ejemplo")
    pl.set_defaults(f=_cmd_plantilla)

    a = p.parse_args(argv)
    try:
        return a.f(a)
    except (ErrorDeEmision, llaves.ErrorDeLlave) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 3
    except Exception as error:      # noqa: BLE001 — el rechazo de un paquete que no es un paquete
        if error.__class__.__name__ in {"PaqueteRechazado", "FirmaInvalida"}:
            print(f"ERROR: el archivo no es un paquete válido: {getattr(error, 'motivo', error)}", file=sys.stderr)
            return 2
        raise
