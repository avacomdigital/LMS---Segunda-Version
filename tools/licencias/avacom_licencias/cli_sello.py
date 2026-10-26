"""
Subcomandos del sello de dispositivo (S1): `sello emitir`, `sello ver`, `sello revocar`, `sello revocados ver`. Se enganchan al parser de `cli.py` con `registrar`.

    avacom-licencias sello emitir --solicitud <equipo.avsol> --privada <sello-2026-1.avkey> --inventario <inventario.json> --origen fabrica|entrega [--vence AAAA-MM-DD] [--reemitir] [--salida <carpeta>]
    avacom-licencias sello ver <archivo.avsello> --publica <archivo.pub | claves.json>
    avacom-licencias sello revocar --privada <…avkey> --huella <64 hex> [--huella …] [--previa <.avrev>] [--salida <carpeta>]
    avacom-licencias sello revocados ver <archivo.avrev> --publica …

Sin red. La frase de paso se pide sin eco (o AVACOM_EMISOR_FRASE). El sello NUNCA se firma con una llave de licencias: el `kid` debe empezar por «sello-».
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import archivos, llaves, sellos
from .dominio_nodo import errores, sello


def _cli():
    from . import cli
    return cli


def _abrir_privada(ruta: str) -> llaves.LlaveAbierta:
    c = _cli()
    r = Path(archivos.limpiar(ruta))
    if not r.is_file():
        raise c.ErrorDeUso(f"No se encontró la llave privada «{r}».")
    kid = c._kid_de(r)
    if not kid.startswith("sello-"):
        raise c.ErrorDeUso(f"La llave «{kid}» no es una llave de sello: el sello se firma sólo con una llave «sello-…» (SP-07), nunca con la de licencias ni la de publicación.")
    return llaves.abrir(r.read_bytes(), c._frase(f"Frase de paso de {kid}: "))


def _fecha_ms(valor: str | None) -> int:
    if not valor:
        return 0
    try:
        d = datetime.strptime(valor, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999000, tzinfo=timezone.utc)
    except ValueError as error:
        raise _cli().ErrorDeUso("La fecha va como AAAA-MM-DD.") from error
    return int(d.timestamp() * 1000)


def _salida(a, nombre: str) -> Path:
    carpeta = Path(archivos.limpiar(a.salida)) if a.salida else _cli().SALIDA_POR_OMISION
    return carpeta / nombre


def cmd_sello_emitir(a) -> int:
    c = _cli()
    ahora = c._ahora_ms()
    ruta_sol = Path(archivos.limpiar(a.solicitud))
    ruta_inv = Path(archivos.limpiar(a.inventario))
    for r, n in ((ruta_sol, "la solicitud"), (ruta_inv, "el inventario")):
        if not r.is_file():
            raise c.ErrorDeUso(f"No se encontró {n} «{r}».")
    inventario = sellos.Inventario.leer(ruta_inv.read_text(encoding="utf-8-sig"))
    llave = _abrir_privada(a.privada)
    datos, s, renglon = sellos.emitir_sello(ruta_sol.read_bytes(), llave.privada, llave.kid, inventario, c._registro(a.registro), a.origen, ahora, _fecha_ms(a.vence), a.reemitir)
    destino = _salida(a, f"{s.serie}.avsello")
    archivos.escribir(destino, datos)
    c._p(f"Sello emitido para la serie {s.serie} ({s.origen}, evidencia: {s.evidencia}).")
    c._p(f"  Archivo ............ {destino}")
    c._p(f"  Vence .............. {'no vence' if not s.vence else c._iso(s.vence)}")
    c._p(f"  Registro ........... renglón {renglon['n']}")
    return 0


def _claves(a) -> dict[str, bytes]:
    if not a.publica and not getattr(a, "publicas", None):
        # Por omisión las de SELLO de producción, jamás las de licencias (SP-07).
        ruta = _cli().RAIZ.parents[1] / "backend" / "licenciamiento" / "claves" / "sello" / "produccion.json"
        claves = llaves.leer_claves_del_nodo(ruta.read_text(encoding="utf-8-sig")) if ruta.is_file() else {}
        if not claves:
            raise _cli().ErrorDeUso("Indica la llave pública del sello (--publica archivo.pub): las de producción del sello todavía no se publicaron (ceremonia pendiente).")
        return claves
    return _cli()._claves_publicas(a.publica, getattr(a, "publicas", None))


def cmd_sello_ver(a) -> int:
    c = _cli()
    datos, _ = archivos.cargar(a.archivo, sello.MAGIC_SELLO, "el sello")
    try:
        s = sello.leer_sello(datos, _claves(a))
    except errores.LicenciaInvalida as error:
        raise c.ErrorDeUso(f"El sello NO es válido: {error.detalle} (motivo: {error.motivo}).") from error
    c._p(f"Sello {s.id}: serie {s.serie} · {s.modelo} · origen {s.origen} · evidencia {s.evidencia}")
    c._p(f"  Emitido {c._iso(s.emitido)} · {'no vence' if not s.vence else 'vence ' + c._iso(s.vence)} · llave {s.kid}")
    c._p(f"  Huella de la clave del equipo: {s.clave_huella.hex()}")
    c._p("La firma es válida.")
    return 0


def cmd_sello_revocar(a) -> int:
    c = _cli()
    huellas = []
    for h in a.huella:
        try:
            b = bytes.fromhex(h)
        except ValueError:
            b = b""
        if len(b) != 32:
            raise c.ErrorDeUso("Cada --huella son 64 hexadecimales (la huella de la clave del equipo, que sale en «sello ver»).")
        huellas.append(b)
    llave = _abrir_privada(a.privada)
    previa = Path(archivos.limpiar(a.previa)).read_bytes() if a.previa else None
    datos, numero = sellos.emitir_revocados(llave.privada, llave.kid, huellas, previa, {llave.kid: llave.publica}, c._registro(a.registro), c._ahora_ms())
    destino = _salida(a, f"revocados-{numero:04d}.avrev")
    archivos.escribir(destino, datos)
    c._p(f"Lista de revocados número {numero}: {destino}")
    c._p("Entrégala junto a la próxima licencia o actualización (el nodo guarda la más nueva que ve).")
    return 0


def cmd_revocados_ver(a) -> int:
    c = _cli()
    datos = Path(archivos.limpiar(a.archivo)).read_bytes()
    try:
        numero, huellas = sello.leer_revocados(datos, _claves(a))
    except errores.LicenciaInvalida as error:
        raise c.ErrorDeUso(f"La lista NO es válida: {error.detalle} (motivo: {error.motivo}).") from error
    c._p(f"Lista número {numero}: {len(huellas)} huella(s) revocada(s). La firma es válida.")
    for h in sorted(huellas):
        c._p(f"  {h.hex()}")
    return 0


def registrar(sub) -> None:
    s = sub.add_parser("sello", help="Sello de dispositivo AVACOM (aprovisionamiento y revocación)")
    ss = s.add_subparsers(dest="sub", required=True)
    e = ss.add_parser("emitir", help="Firma el sello de un equipo a partir de su .avsol y el inventario")
    e.add_argument("--solicitud", required=True)
    e.add_argument("--privada", required=True, help="La llave de sello (sello-….avkey)")
    e.add_argument("--inventario", required=True, help="El inventario JSON de AVACOM (las series de fábrica)")
    e.add_argument("--origen", required=True, choices=["fabrica", "entrega"])
    e.add_argument("--vence", help="AAAA-MM-DD; sin esto el sello no vence (SQ-05)")
    e.add_argument("--reemitir", action="store_true", help="Reemplaza el sello de una serie que ya tiene (y revoca la clave anterior)")
    e.add_argument("--salida")
    e.add_argument("--registro")
    e.set_defaults(func=cmd_sello_emitir)
    v = ss.add_parser("ver", help="Comprueba un sello con la llave pública")
    v.add_argument("archivo")
    v.add_argument("--publica", action="append", help="Un .pub o un JSON con llaves públicas (se puede repetir)")
    v.add_argument("--publicas", help="Carpeta con llaves públicas")
    v.set_defaults(func=cmd_sello_ver)
    r = ss.add_parser("revocar", help="Emite la lista de revocados siguiente")
    r.add_argument("--privada", required=True)
    r.add_argument("--huella", action="append", required=True)
    r.add_argument("--previa", help="La lista anterior (.avrev): se parte de ella")
    r.add_argument("--salida")
    r.add_argument("--registro")
    r.set_defaults(func=cmd_sello_revocar)
    rv = ss.add_parser("revocados", help="Ver una lista de revocados")
    rvs = rv.add_subparsers(dest="sub2", required=True)
    ver = rvs.add_parser("ver")
    ver.add_argument("archivo")
    ver.add_argument("--publica", action="append")
    ver.add_argument("--publicas")
    ver.set_defaults(func=cmd_revocados_ver)
