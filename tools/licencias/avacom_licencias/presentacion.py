"""
Lo que se le muestra a quien opera: resúmenes de la solicitud, de la licencia y de la liberación, y la hoja de entrega que acompaña al `.avlic`. Todo en español claro; nada de
hashes crudos de la huella (sólo cuántas piezas), y los hashes de archivo son los SHA-256 de los archivos mismos.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .dominio_nodo import catalogos, huella, licencia

ETIQUETA_TIPO = {licencia.TIPO_PRODUCCION: "producción", licencia.TIPO_EVALUACION: "evaluación", licencia.TIPO_DESARROLLO: "desarrollo"}


def fecha(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def fecha_hora(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def limite(n: int) -> str:
    return "sin tope" if n == licencia.ILIMITADO else str(n)


def modulos(capacidades) -> str:
    if catalogos.TODAS in capacidades:
        return "todos (*)"
    return ", ".join(catalogos.ETIQUETAS_DE_CAPACIDAD.get(c, c) for c in sorted(capacidades))


def limites(lim) -> str:
    return (f"{limite(lim.equipos)} equipos · {limite(lim.usuarios)} usuarios · {limite(lim.concurrentes_normal)} concurrentes normales · "
            f"{limite(lim.concurrentes_pico)} en pico")


def huella_texto(h: licencia.HuellaDeLicencia, nivel: str | None = None) -> str:
    nivel_texto = {huella.NIVEL_HARDWARE: "hardware", huella.NIVEL_INSTALACION: "instalación"}.get(nivel or "", None)
    base = f"{h.k} de {len(h.factores)} piezas"
    return f"nivel {nivel_texto} · {base}" if nivel_texto else base


def _fila(etiqueta: str, valor: str, ancho: int = 17) -> str:
    return f"  {etiqueta + ' ':.<{ancho}} {valor}"


def resumen(lic: licencia.Licencia, *, kid: str, clase: str, nivel: str, avisos: list[str] | None = None) -> str:
    filas = [
        "RESUMEN DE LA LICENCIA",
        _fila("Aula", lic.aula or "(sin nombre)"),
        _fila("Tipo", ETIQUETA_TIPO.get(lic.tipo, lic.tipo)),
        _fila("Licencia", f"{lic.id[:8]}… · serie {lic.serie} ({clase})"),
        _fila("Vigencia", f"{fecha(lic.desde)} → {fecha(lic.vence)} (UTC)"),
        _fila("Gracia", f"{lic.gracia_dias} días"),
        _fila("Límites", limites(lic.limites)),
        _fila("Módulos", modulos(lic.capacidades)),
        _fila("Huella", huella_texto(lic.huella, nivel)),
        _fila("Llave", kid),
    ]
    if lic.liberacion_pendiente:
        filas.append(_fila("Liberación", f"PENDIENTE · {lic.liberacion_dias} días para confirmar"))
    if avisos:
        filas.append("AVISOS")
        filas += [f"  ! {a}" for a in avisos]
    return "\n".join(filas)


def solicitud(sol, avisos: list[str] | None = None) -> str:
    filas = [
        "SOLICITUD",
        _fila("Firma", "válida (la firmó la llave del equipo que la pide)"),
        _fila("Nivel de huella", {huella.NIVEL_HARDWARE: "hardware", huella.NIVEL_INSTALACION: "instalación (más débil)"}.get(sol.nivel, sol.nivel)),
        _fila("Piezas", f"{sol.huella.k} de {len(sol.huella.factores)}"),
        _fila("Versión del nodo", sol.version_nodo or "(no dice)"),
        _fila("Aula", sol.aula or "(no dice)"),
        _fila("Creada", fecha_hora(sol.creada)),
        _fila("Licencia vigente", f"{sol.licencia_vigente[:8]}… (renovación)" if sol.licencia_vigente else "ninguna (licencia nueva)"),
        _fila("Nonce", sol.nonce.hex()[:12] + "…"),
        _fila("SHA-256", sol.sha256[:16] + "…"),
    ]
    if avisos:
        filas.append("AVISOS")
        filas += [f"  ! {a}" for a in avisos]
    return "\n".join(filas)


def licencia_leida(lic: licencia.Licencia) -> str:
    filas = [
        "LICENCIA",
        _fila("Aula", lic.aula or "(sin nombre)"),
        _fila("Tipo", ETIQUETA_TIPO.get(lic.tipo, lic.tipo)),
        _fila("Licencia", f"{lic.id} · serie {lic.serie}"),
        _fila("Emitida", fecha_hora(lic.emitida)),
        _fila("Vigencia", f"{fecha(lic.desde)} → {fecha(lic.vence)} (UTC)"),
        _fila("Gracia", f"{lic.gracia_dias} días"),
        _fila("Límites", limites(lic.limites)),
        _fila("Módulos", modulos(lic.capacidades)),
        _fila("Huella", huella_texto(lic.huella)),
        _fila("Llave", lic.kid),
        _fila("SHA-256", lic.sha256),
    ]
    if lic.liberacion_pendiente:
        filas.append(_fila("Liberación", f"PENDIENTE · {lic.liberacion_dias} días"))
    return "\n".join(filas)


def liberacion(lib) -> str:
    return "\n".join([
        "LIBERACIÓN",
        _fila("Firma", "válida (la firmó el equipo que deja la licencia)"),
        _fila("Licencia", f"{lib.licencia_id} · serie {lib.serie}"),
        _fila("Liberada", fecha_hora(lib.liberada)),
        _fila("Nonce", lib.nonce.hex()[:12] + "…"),
        _fila("SHA-256", lib.sha256[:16] + "…"),
    ])


def hoja_de_entrega(lic: licencia.Licencia, *, nombre_archivo: str, sha256: str, texto: str) -> str:
    return "\n".join([
        "AVACOM · Hoja de entrega de la licencia",
        "=======================================",
        "",
        _fila("Aula", lic.aula or "(sin nombre)"),
        _fila("Licencia", f"{lic.id} · serie {lic.serie}"),
        _fila("Vigencia", f"del {fecha(lic.desde)} al {fecha(lic.vence)} (UTC)"),
        _fila("Gracia", f"{lic.gracia_dias} días"),
        _fila("Límites", limites(lic.limites)),
        _fila("Módulos", modulos(lic.capacidades)),
        _fila("Archivo", nombre_archivo),
        _fila("SHA-256", sha256),
        "",
        "Cómo activarla (sin internet y sin escribir nada):",
        "  1. Copia el archivo .avlic a una memoria USB (o a la carpeta Descargas del computador maestro).",
        "  2. En AVACOM OPS entra a «Licencia» y toca «Cargar la licencia».",
        "  3. Toca la tarjeta de tu licencia, revisa el resumen y toca «Activar».",
        "  4. Compara el SHA-256 que muestra la pantalla con el de esta hoja.",
        "",
        "Si no puedes mover el archivo, este es el texto de la licencia (cópialo completo, sin espacios):",
        texto,
        "",
        "Esta hoja no es secreta, pero la licencia sirve para un solo computador: el computador maestro de esta aula.",
        "",
    ])
