"""
La línea de comandos del emisor de licencias. Cada subcomando hace lo que dice `guia-usuario-interno.md`; el modo guiado (`guiado.py`) arma estos mismos comandos con preguntas.

    avacom-licencias claves generar --kid prod-2026-1 --salida <carpeta>
    avacom-licencias claves ver --privada <archivo.avkey>
    avacom-licencias solicitud ver <archivo.avreq | AVQ1.…>
    avacom-licencias emitir --solicitud … --privada … [--aula …] [--plan …] [--hasta AAAA-MM-DD | --meses N] [--reemplaza <.avrel> | --liberacion-pendiente DIAS] …
    avacom-licencias verificar <archivo.avlic | AVL1.…> --publica <archivo.pub> [--solicitud …]
    avacom-licencias liberacion ver <archivo.avrel | AVR1.…>
    avacom-licencias registro ver
    avacom-licencias planes

Códigos de salida: 0 bien · 1 error (se explica qué pasó) · 2 cancelado por quien opera.

Sin red: no se abre ninguna conexión. La frase de paso se pide sin eco (o sale de AVACOM_EMISOR_FRASE, sólo para automatizar pruebas).
"""
from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from . import __version__, archivos, emision, llaves, registro as reg
from . import planes as pl
from . import presentacion as pres
from .dominio_nodo import RAIZ, errores, firma, huella, licencia
from .dominio_nodo import solicitud as dom_sol

REGISTRO_POR_OMISION = RAIZ / "datos" / "registro-emisiones.jsonl"
SALIDA_POR_OMISION = RAIZ / "salida"
PALABRA = "EMITIR"
PALABRA_SIN_TOPE = "SIN TOPE"
VARIABLE_FRASE = "AVACOM_EMISOR_FRASE"
PLAN_POR_OMISION = "anual-aula"

# Costuras: las pruebas y el modo guiado cambian cómo se pregunta, cómo se pide la frase y qué hora es.
_leer = input
_leer_frase = getpass.getpass


def _ahora_ms() -> int:
    return int(time.time() * 1000)


class ErrorDeUso(Exception):
    """Algo que quien opera puede corregir (un archivo que falta, una opción mal puesta). Se muestra tal cual."""


class Cancelado(Exception):
    """Quien opera decidió no firmar."""


def _p(texto: str = "") -> None:
    print(texto)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _frase(pregunta: str) -> str:
    if VARIABLE_FRASE in os.environ:
        print(f"AVISO: la frase de paso sale de la variable {VARIABLE_FRASE}. Úsalo sólo para pruebas.", file=sys.stderr)
        return os.environ[VARIABLE_FRASE]
    return _leer_frase(pregunta)


def _operador() -> str:
    try:
        return getpass.getuser()
    except Exception:       # noqa: BLE001
        return "desconocido"


def _registro(ruta: str | None) -> reg.Registro:
    return reg.Registro(Path(archivos.limpiar(ruta)) if ruta else REGISTRO_POR_OMISION)


def _solicitud(valor: str):
    datos, _ = archivos.cargar(valor, archivos.MAGIC_SOLICITUD, "la solicitud")
    try:
        return dom_sol.leer_solicitud(datos)
    except errores.LicenciaInvalida as error:
        raise ErrorDeUso(f"La solicitud no es válida: {error.detalle} Pide una nueva al colegio.") from error


ARCHIVO_DE_DESARROLLO = "desarrollo.json"      # las llaves de desarrollo del nodo: esta herramienta NUNCA las toma por buenas


def _claves_publicas(publicas: list[str] | None, carpeta: str | None) -> dict[str, bytes]:
    """Las llaves con las que se verifica: `--publica` (un `.pub` o un archivo en el formato de `produccion.json`), `--publicas <carpeta>` o, si no se da nada, las de
    `backend/licenciamiento/claves/produccion.json` y las de `claves-publicas/`."""
    rutas: list[Path] = [Path(archivos.limpiar(r)) for r in (publicas or [])]
    if not rutas:
        if carpeta:
            carpetas = [Path(archivos.limpiar(carpeta))]
        else:
            produccion = RAIZ.parents[1] / "backend" / "licenciamiento" / "claves" / "produccion.json"
            rutas += [produccion] if produccion.is_file() else []
            carpetas = [RAIZ / "claves-publicas"]
        for c in carpetas:
            if c.is_dir():
                rutas += sorted(c.glob("*.pub")) + sorted(p for p in c.glob("*.json") if p.name != ARCHIVO_DE_DESARROLLO)
    claves: dict[str, bytes] = {}
    for ruta in rutas:
        if not ruta.is_file():
            raise ErrorDeUso(f"No se encontró la llave pública «{ruta}».")
        try:
            texto = ruta.read_text(encoding="utf-8-sig")
            if ruta.suffix.lower() == ".json":
                claves.update(llaves.leer_claves_del_nodo(texto))
            else:
                kid, publica = llaves.leer_publica(texto)
                claves[kid] = publica
        except llaves.ErrorDeLlave as error:
            raise ErrorDeUso(f"«{ruta.name}»: {error}") from error
    if not claves:
        raise ErrorDeUso("Indica la llave pública con la que se firmó (--publica archivo.pub, o --publicas <carpeta>).")
    return claves


# ====================================================================================================================== claves
def cmd_claves_generar(a) -> int:
    kid = llaves.kid_valido(a.kid)
    salida = Path(archivos.limpiar(a.salida))
    ruta_privada, ruta_publica, ruta_nodo = salida / f"{kid}.avkey", salida / f"{kid}.pub", salida / f"{kid}.produccion.json"
    for ruta in (ruta_privada, ruta_publica, ruta_nodo):
        if ruta.exists():
            raise ErrorDeUso(f"Ya existe «{ruta}»: una llave no se sobrescribe. Elige otro nombre (kid) u otra carpeta.")
    frase = _frase(f"Elige la frase de paso (mínimo {llaves.MIN_FRASE} caracteres): ")
    if len(frase) < llaves.MIN_FRASE:
        raise ErrorDeUso(f"La frase de paso debe tener al menos {llaves.MIN_FRASE} caracteres.")
    if _frase("Escríbela otra vez: ") != frase:
        raise ErrorDeUso("Las dos frases de paso no coinciden. No se creó ninguna llave.")
    avkey, texto_publica, publica = llaves.generar(kid, frase, _iso(_ahora_ms()))
    salida.mkdir(parents=True, exist_ok=True)
    archivos.escribir(ruta_privada, avkey)
    archivos.escribir(ruta_publica, texto_publica.encode("utf-8"))
    archivos.escribir(ruta_nodo, llaves.entrada_para_el_nodo(kid, publica).encode("utf-8"))
    _p(f"Llave creada: {kid}")
    _p(f"  Privada (cifrada) .. {ruta_privada}")
    _p(f"  Pública ............ {ruta_publica}")
    _p(f"  Para el nodo ....... {ruta_nodo}   (el formato de backend/licenciamiento/claves/produccion.json)")
    _p(f"  Huella pública ..... {llaves.huella_de_publica(publica)}")
    _p("")
    _p("Ahora: 1) comprueba la llave con «claves ver»; 2) guarda DOS copias de la privada en memorias distintas y lugares distintos;")
    _p("       3) guarda la frase de paso APARTE; 4) entrega sólo la pública (el .pub y el .produccion.json) al equipo de desarrollo.")
    return 0


def cmd_claves_ver(a) -> int:
    ruta = Path(archivos.limpiar(a.privada))
    if not ruta.is_file():
        raise ErrorDeUso(f"No se encontró la llave «{ruta}».")
    llave = llaves.abrir(ruta.read_bytes(), _frase("Frase de paso: "))
    prueba = secrets.token_bytes(32)
    firmo = firma.verificar(llave.publica, firma.firmar(llave.privada, prueba), prueba)
    _p(f"Llave {llave.kid}: abre con la frase de paso.")
    _p(f"  Huella pública ..... {llaves.huella_de_publica(llave.publica)}")
    _p(f"  Firma de prueba .... {'correcta' if firmo else 'FALLÓ'}")
    return 0 if firmo else 1


# ====================================================================================================================== solicitud y liberación
def cmd_solicitud_ver(a) -> int:
    sol = _solicitud(a.archivo)
    _p(pres.solicitud(sol, emision.advertencias_de_solicitud(sol, _ahora_ms(), huella.NIVEL_INSTALACION)))
    return 0


def cmd_liberacion_ver(a) -> int:
    datos, _ = archivos.cargar(a.archivo, archivos.MAGIC_LIBERACION, "la liberación")
    try:
        lib = dom_sol.leer_liberacion(datos)
    except errores.LicenciaInvalida as error:
        raise ErrorDeUso(f"La liberación no es válida: {error.detalle}") from error
    _p(pres.liberacion(lib))
    return 0


# ====================================================================================================================== emitir
def _limite(valor, plan_valor: int, nombre: str) -> int:
    return plan_valor if valor is None else pl.numero_de_limite(valor, nombre)


def _fecha(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        raise ErrorDeUso("La fecha debe ser AAAA-MM-DD, por ejemplo 2027-10-31.") from None


def _peticion(a, plan: pl.Plan) -> emision.Peticion:
    hasta = _fecha(a.hasta)
    if hasta is not None and a.meses is not None:
        raise ErrorDeUso("Indica la vigencia con --hasta o con --meses, no con las dos.")
    try:
        capacidades = frozenset(pl.validar_capacidades(a.capacidades.split(","))) if a.capacidades else frozenset(plan.capacidades)
        return emision.Peticion(
            aula=a.aula or "", tipo=a.tipo or plan.tipo, gracia_dias=plan.gracia_dias if a.gracia is None else int(a.gracia),
            equipos=_limite(a.equipos, plan.equipos, "equipos"), usuarios=_limite(a.usuarios, plan.usuarios, "usuarios"),
            normal=_limite(a.normal, plan.concurrentes_normal, "concurrentes normales"), pico=_limite(a.pico, plan.concurrentes_pico, "concurrentes en pico"),
            capacidades=capacidades, hasta=hasta, meses=None if hasta is not None else (a.meses if a.meses is not None else plan.meses),
            liberacion_dias=a.liberacion_pendiente)
    except (pl.ErrorDePlan, ValueError) as error:
        raise ErrorDeUso(str(error)) from error


def _respuesta(texto: str) -> str:
    return (texto or "").replace("﻿", "").strip()


def _confirmar(sin_tope: bool) -> None:
    if sin_tope:
        if _respuesta(_leer(f"Esta licencia NO tiene tope en algún límite. Escribe {PALABRA_SIN_TOPE} para continuar: ")) != PALABRA_SIN_TOPE:
            raise Cancelado()
    if _respuesta(_leer(f"Para firmar, escribe {PALABRA} y pulsa Intro: ")) != PALABRA:
        raise Cancelado()


def cmd_emitir(a) -> int:
    ahora = _ahora_ms()
    sol = _solicitud(a.solicitud)
    ruta_privada = Path(archivos.limpiar(a.privada))
    if not ruta_privada.is_file():
        raise ErrorDeUso(f"No se encontró la llave privada «{ruta_privada}».")
    try:
        plan = pl.obtener(a.plan or PLAN_POR_OMISION, a.planes)
        reglas = pl.cargar_reglas(a.planes)
    except pl.ErrorDePlan as error:
        raise ErrorDeUso(str(error)) from error
    if a.liberacion_pendiente is not None and a.reemplaza:
        raise ErrorDeUso("Usa --reemplaza (el equipo viejo entregó su .avrel) o --liberacion-pendiente (no enciende), no las dos.")
    peticion = _peticion(a, plan)
    registro = _registro(a.registro)
    bien, mensaje, _ = registro.verificar()
    if not bien:
        raise ErrorDeUso(f"El registro de emisiones está alterado ({mensaje}). No se emite nada: avisa al CTO.")
    previos = registro.por_nonce(sol.nonce.hex())
    if previos and not a.reemitir:
        raise ErrorDeUso("Esa solicitud ya se atendió (mira «registro ver»). Si de verdad hace falta otra licencia para la misma solicitud, usa --reemitir: saldrá con una serie nueva.")

    # --- liberación del equipo viejo (JRN-020)
    liberacion = None
    if a.reemplaza:
        datos_lib, _ = archivos.cargar(a.reemplaza, archivos.MAGIC_LIBERACION, "la liberación")
        try:
            liberacion = dom_sol.leer_liberacion(datos_lib)
        except errores.LicenciaInvalida as error:
            raise ErrorDeUso(f"La liberación no es válida: {error.detalle}") from error
        if liberacion.clave_nodo == sol.clave_nodo:
            raise ErrorDeUso("La liberación es del MISMO equipo que pide la licencia: debe ser la del equipo viejo.")
        emitida = [r for r in registro.de_licencia(liberacion.licencia_id) if int(r.get("serie", 0)) == liberacion.serie]
        if registro.de_licencia(liberacion.licencia_id) and not emitida:
            raise ErrorDeUso(f"La liberación habla de la serie {liberacion.serie}, que este registro no emitió.")
        if emitida and emitida[-1].get("hash_clave_nodo") != firma.huella_de_clave(liberacion.clave_nodo).hex():
            raise ErrorDeUso("La liberación no es del equipo al que se emitió esa serie: no es la prueba del equipo viejo.")

    # --- qué licencia es y qué serie toca
    if a.licencia:
        try:
            licencia_id = str(uuid.UUID(a.licencia))
        except ValueError:
            raise ErrorDeUso("El código de licencia (--licencia) no es válido.") from None
    elif liberacion is not None:
        licencia_id = liberacion.licencia_id
    elif sol.licencia_vigente:
        licencia_id = sol.licencia_vigente
    elif previos:
        licencia_id = previos[-1]["licencia_id"]        # --reemitir sobre la misma solicitud: la misma licencia, con una serie nueva
    else:
        licencia_id = str(uuid.uuid4())
    ultima = registro.ultima_serie(licencia_id)
    nueva = ultima == 0 and not (a.licencia or liberacion or sol.licencia_vigente)
    if ultima:
        if a.serie is not None and a.serie <= ultima:
            raise ErrorDeUso(f"La serie debe ser mayor que la última emitida para esa licencia ({ultima}).")
        serie = a.serie or ultima + 1
    elif nueva:
        serie = a.serie or 1
    else:
        if a.serie is None:
            raise ErrorDeUso("Este registro no conoce esa licencia (se emitió desde otro equipo o el registro es nuevo): indica la serie que toca con --serie.")
        serie = a.serie
    if liberacion is not None:
        clase, codigo = "cambio de equipo · definitiva", "cambio_definitiva"
    elif peticion.liberacion_dias is not None:
        clase, codigo = "cambio de equipo · liberación pendiente", "cambio_pendiente"
    elif nueva:
        clase, codigo = "licencia nueva", "nueva"
    else:
        clase, codigo = "renovación o ampliación", "renovacion"

    # --- construir, mostrar y confirmar
    try:
        lic = emision.construir(sol, peticion, licencia_id=licencia_id, serie=serie, ahora_ms=ahora, reglas=reglas)
    except emision.ErrorDeEmision as error:
        raise ErrorDeUso(str(error)) from error
    avisos = emision.advertencias_de_solicitud(sol, ahora, huella.NIVEL_INSTALACION)
    if lic.tipo == licencia.TIPO_EVALUACION:
        avisos.append("Es una licencia de EVALUACIÓN: vence pronto. No se la mandes a un cliente de producción por error.")
    if peticion.sin_tope:
        avisos.append("Algún límite NO tiene tope.")
    # --- dónde se escribe: se comprueba ANTES de mostrar el resumen, de firmar y de registrar (nunca se pisa un archivo)
    base = emision.nombre_de_archivo(lic.aula, ahora, serie)
    salida = Path(archivos.limpiar(a.salida)) if a.salida else SALIDA_POR_OMISION
    ruta_licencia, ruta_hoja = salida / (base + ".avlic"), salida / (base + ".txt")
    existentes = [r for r in (ruta_licencia, ruta_hoja) if r.exists()]
    if existentes:
        raise ErrorDeUso(f"Ya existe «{existentes[0].name}» en la carpeta de salida: no se pisa. Elige otra carpeta (--salida). No se firmó ni se registró nada.")
    _p(pres.resumen(lic, kid=_kid_de(ruta_privada), clase=clase, nivel=sol.nivel, avisos=avisos))
    if not a.yo_confirmo:
        _confirmar(peticion.sin_tope or plan.confirmacion_extra)

    # --- firmar, verificar lo firmado, registrar y escribir
    llave = llaves.abrir(ruta_privada.read_bytes(), _frase("Frase de paso: "))
    datos = emision.firmar(lic, llave.kid, llave.privada)
    leida = emision.verificar_salida(datos, llave.kid, llave.publica, lic)
    hoja = pres.hoja_de_entrega(lic, nombre_archivo=base + ".avlic", sha256=leida.sha256, texto=licencia.a_texto(datos))
    renglon = registro.anadir({
        "en": _iso(ahora), "accion": "emitir", "operador": _operador(), "licencia_id": lic.id, "serie": lic.serie, "clase": codigo, "kid": llave.kid, "aula": lic.aula,
        "tipo": lic.tipo, "desde": lic.desde, "vence": lic.vence, "gracia_dias": lic.gracia_dias,
        "limites": [lic.limites.equipos, lic.limites.usuarios, lic.limites.concurrentes_normal, lic.limites.concurrentes_pico], "capacidades": sorted(lic.capacidades),
        "liberacion_dias": lic.liberacion_dias, "sha256_licencia": leida.sha256, "sha256_solicitud": sol.sha256, "nonce": sol.nonce.hex(),
        "hash_clave_nodo": lic.hash_clave_nodo.hex(), "reemplaza_sha256": liberacion.sha256 if liberacion else None, "archivo": base + ".avlic"})
    try:
        archivos.escribir(ruta_licencia, datos)
        ruta_hoja.parent.mkdir(parents=True, exist_ok=True)
        with ruta_hoja.open("xb") as archivo:
            archivo.write(b"\xef\xbb\xbf" + hoja.encode("utf-8"))
    except FileExistsError as error:
        raise ErrorDeUso(f"Ya existe «{error.filename}» en la carpeta de salida. La emisión QUEDÓ REGISTRADA (renglón {renglon['n']}); elige otra carpeta (--salida) y usa --reemitir.") from error
    _p("")
    _p(f"Licencia emitida y verificada (renglón {renglon['n']} del registro).")
    _p(f"  Licencia ........... {ruta_licencia}")
    _p(f"  Hoja de entrega .... {ruta_hoja}")
    _p(f"  SHA-256 ............ {leida.sha256}")
    _p("Entrega el .avlic y la hoja al colegio (no son secretos) y pídele que compare el SHA-256 al cargarla.")
    return 0


def _kid_de(ruta_privada: Path) -> str:
    """El nombre de la llave, que está en claro en el .avkey (para el resumen, ANTES de pedir la frase de paso)."""
    try:
        import json
        return llaves.kid_valido(json.loads(ruta_privada.read_text(encoding="utf-8"))["kid"])
    except Exception as error:      # noqa: BLE001
        raise ErrorDeUso("El archivo de la llave está dañado o no es una llave de AVACOM.") from error


# ====================================================================================================================== verificar, registro y planes
def cmd_verificar(a) -> int:
    claves = _claves_publicas(a.publica, a.publicas)
    datos, _ = archivos.cargar(a.archivo, archivos.MAGIC_LICENCIA, "la licencia")
    try:
        lic = licencia.leer(datos, claves)
    except errores.LicenciaInvalida as error:
        raise ErrorDeUso(f"La licencia NO es válida: {error.detalle} (motivo: {error.motivo}).") from error
    _p(pres.licencia_leida(lic))
    _p("")
    _p("La firma es válida.")
    if a.solicitud:
        sol = _solicitud(a.solicitud)
        coincide = lic.huella == sol.huella and lic.hash_clave_nodo in (None, firma.huella_de_clave(sol.clave_nodo))
        _p("La huella corresponde a la solicitud." if coincide else "ATENCIÓN: la huella de la licencia NO corresponde a esa solicitud.")
        return 0 if coincide else 1
    return 0


def cmd_registro_ver(a) -> int:
    registro = _registro(a.registro)
    bien, mensaje, cuantos = registro.verificar()
    renglones = registro.renglones() if bien or cuantos else []
    mostrar = renglones if a.todos else renglones[-20:]
    if a.json:
        import json
        _p(json.dumps(mostrar, ensure_ascii=False, indent=2))
    else:
        _p(f"Registro de emisiones: {registro.ruta}")
        if not mostrar:
            _p("  (todavía no hay emisiones)")
        for r in mostrar:
            vence = pres.fecha(int(r["vence"])) if "vence" in r else "-"
            _p(f"  {r.get('n', '?'):>4}  {str(r.get('en', ''))[:19]}  {str(r.get('accion', ''))[:8]:<8}  serie {r.get('serie', '-'):<3} {str(r.get('aula', ''))[:30]:<30}  "
               f"{str(r.get('tipo', ''))[:10]:<10} hasta {vence}  {str(r.get('sha256_licencia', ''))[:10]}…")
    _p(mensaje if bien else f"ATENCIÓN: {mensaje} Avisa al CTO.")
    return 0 if bien else 1


def cmd_planes(a) -> int:
    try:
        todos = pl.cargar(a.planes)
        reglas = pl.cargar_reglas(a.planes)
    except pl.ErrorDePlan as error:
        raise ErrorDeUso(str(error)) from error
    if not todos:
        _p("No hay planes en la carpeta planes/.")
    for plan in todos.values():
        _p(f"{plan.nombre}")
        _p(f"  {plan.descripcion}")
        _p(f"  {pres.ETIQUETA_TIPO.get(plan.tipo, plan.tipo)} · {plan.meses} {'mes' if plan.meses == 1 else 'meses'} · gracia {plan.gracia_dias} días · "
           f"{pres.limites(licencia.Limites(plan.equipos, plan.usuarios, plan.concurrentes_normal, plan.concurrentes_pico))} · módulos: {pres.modulos(frozenset(plan.capacidades))}")
    _p(f"Reglas del CTO (planes/{pl.ARCHIVO_DE_REGLAS}): {reglas.descripcion()}. Ninguna opción de «emitir» las contradice.")
    _p("Lo demás de los planes (concurrentes, módulos, meses) sigue siendo provisional (Q-L1).")
    return 0


# ====================================================================================================================== el analizador
def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="avacom-licencias", description="AVACOM Emisor de Licencias (uso interno de AVACOM). Sin argumentos abre el modo guiado.")
    p.add_argument("--version", action="version", version=f"avacom-licencias {__version__}")
    sub = p.add_subparsers(dest="comando")

    c = sub.add_parser("claves", help="Ceremonia de llaves")
    cs = c.add_subparsers(dest="sub", required=True)
    g = cs.add_parser("generar", help="Crea el par de llaves de emisión (la privada, cifrada con una frase de paso)")
    g.add_argument("--kid", required=True, help="Nombre de la llave, por ejemplo prod-2026-1")
    g.add_argument("--salida", required=True, help="Carpeta donde se escriben <kid>.avkey y <kid>.pub (mejor una memoria USB)")
    g.set_defaults(func=cmd_claves_generar)
    v = cs.add_parser("ver", help="Comprueba que la privada abre y firma")
    v.add_argument("--privada", required=True)
    v.set_defaults(func=cmd_claves_ver)

    s = sub.add_parser("solicitud", help="Ver una solicitud del colegio")
    ss = s.add_subparsers(dest="sub", required=True)
    sv = ss.add_parser("ver")
    sv.add_argument("archivo", help="Ruta del .avreq o su texto AVQ1.…")
    sv.set_defaults(func=cmd_solicitud_ver)

    e = sub.add_parser("emitir", help="Firma una licencia a partir de una solicitud")
    e.add_argument("--solicitud", required=True, help="Ruta del .avreq o su texto AVQ1.…")
    e.add_argument("--privada", required=True, help="Ruta de la llave privada (.avkey)")
    e.add_argument("--aula", help="Nombre del aula (por omisión, el de la solicitud)")
    e.add_argument("--plan", help=f"Plan (por omisión «{PLAN_POR_OMISION}»); mira «planes»")
    e.add_argument("--hasta", help="Último día de vigencia, AAAA-MM-DD (UTC)")
    e.add_argument("--meses", type=int, help="Meses de vigencia desde hoy (si no se da --hasta, manda el plan)")
    e.add_argument("--gracia", type=int, help="Días de gracia (la regla del CTO, en planes/reglas.json, es de 30 días corridos exactos: otro valor se rechaza)")
    e.add_argument("--equipos", help="Límite de equipos (un número; el máximo de un aula lo fija planes/reglas.json)")
    e.add_argument("--usuarios", help="Límite de usuarios (un número; el máximo de un aula lo fija planes/reglas.json)")
    e.add_argument("--normal", help="Concurrentes en operación normal (número o sin_tope)")
    e.add_argument("--pico", help="Concurrentes en pico (número o sin_tope)")
    e.add_argument("--capacidades", help="Módulos separados por coma (por omisión los del plan; * = todos)")
    e.add_argument("--tipo", choices=list(pl.TIPOS_EMITIBLES), help="produccion o evaluacion")
    e.add_argument("--serie", type=int, help="Serie (sólo si el registro no la conoce)")
    e.add_argument("--licencia", help="Código de la licencia que continúa (cambio de equipo sin que la solicitud lo traiga)")
    e.add_argument("--reemplaza", help="La liberación (.avrel) del equipo viejo: emite la licencia DEFINITIVA para el equipo nuevo")
    e.add_argument("--liberacion-pendiente", type=int, metavar="DIAS", help="El equipo viejo no enciende: licencia con liberación pendiente por esos días")
    e.add_argument("--salida", help="Carpeta donde se escribe el .avlic y la hoja de entrega")
    e.add_argument("--registro", help="Ruta del registro de emisiones (por omisión datos/registro-emisiones.jsonl)")
    e.add_argument("--planes", help="Carpeta de planes (por omisión planes/)")
    e.add_argument("--reemitir", action="store_true", help="Permite emitir otra vez sobre una solicitud ya atendida (sale con serie nueva)")
    e.add_argument("--yo-confirmo", action="store_true", help="SÓLO para automatizar pruebas: omite la confirmación escrita")
    e.set_defaults(func=cmd_emitir)

    ve = sub.add_parser("verificar", help="Comprueba una licencia con las llaves públicas")
    ve.add_argument("archivo", help="Ruta del .avlic o su texto AVL1.…")
    ve.add_argument("--publica", action="append", help="Llave pública: un .pub o un archivo en el formato de produccion.json del nodo; se puede repetir")
    ve.add_argument("--publicas", help="Carpeta con llaves públicas (*.pub y *.json; el desarrollo.json del nodo se ignora siempre)")
    ve.add_argument("--solicitud", help="Comprueba además que la huella corresponde a esa solicitud")
    ve.set_defaults(func=cmd_verificar)

    li = sub.add_parser("liberacion", help="Ver la prueba de liberación del equipo viejo")
    ls = li.add_subparsers(dest="sub", required=True)
    lv = ls.add_parser("ver")
    lv.add_argument("archivo", help="Ruta del .avrel o su texto AVR1.…")
    lv.set_defaults(func=cmd_liberacion_ver)

    r = sub.add_parser("registro", help="El registro de emisiones")
    rs = r.add_subparsers(dest="sub", required=True)
    rv = rs.add_parser("ver", help="Muestra las emisiones y comprueba la cadena")
    rv.add_argument("--registro", help="Ruta del registro")
    rv.add_argument("--todos", action="store_true", help="Todas las emisiones (por omisión, las últimas 20)")
    rv.add_argument("--json", action="store_true", help="En JSON")
    rv.set_defaults(func=cmd_registro_ver)

    from . import cli_sello
    cli_sello.registrar(sub)

    pl_ = sub.add_parser("planes", help="Lista los planes")
    pl_.add_argument("--planes", help="Carpeta de planes")
    pl_.set_defaults(func=cmd_planes)
    return p


def _consola_utf8() -> None:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:       # noqa: BLE001 — un flujo que no se puede reconfigurar (pruebas) se deja como está
            pass


def main(argv: list[str] | None = None) -> int:
    _consola_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        from . import guiado
        return guiado.principal()
    args = _parser().parse_args(argv)
    if not getattr(args, "func", None):
        _parser().print_help()
        return 1
    try:
        return args.func(args)
    except Cancelado:
        _p("Cancelado: no se creó ningún archivo ni ningún renglón del registro.")
        return 2
    except KeyboardInterrupt:
        _p("\nCancelado.")
        return 2
    except (ErrorDeUso, llaves.ErrorDeLlave, archivos.ErrorDeArchivo, emision.ErrorDeEmision, pl.ErrorDePlan, reg.RegistroAlterado) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except errores.ErrorLicencia as error:
        print(f"ERROR: {error.detalle}", file=sys.stderr)
        return 1
