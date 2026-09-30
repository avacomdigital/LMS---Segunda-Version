"""
Genera los SVG de iconos de las pantallas (Student y OPS) a partir de la fuente SVG de Phosphor Icons que vive en
`phospor-icons/Fonts/<peso>/…` (licencia MIT, https://phosphoricons.com).

Por qué un generador y no copiar los archivos: los `MauiImage` no admiten `currentColor`, así que cada icono necesita SU color
incorporado, y la fuente trae los glifos en el sistema de coordenadas de la fuente (1024 uem, eje Y hacia arriba). Aquí se voltean
a un lienzo de 256 × 256 (el de Phosphor), se convierten a comandos absolutos M/L/C/Z sin arcos ni segmentos de longitud cero
(Win2D falla con geometrías degeneradas, ver la nota de `win2d-path-nan-cascada`) y se escriben con el color pedido.

Uso (desde la raíz del repositorio):
    python tools/gen_iconos_phosphor.py                 # escribe los iconos del modo de estudio
    python tools/gen_iconos_phosphor.py --geometria graduation-cap regular   # imprime el `Data` de un Path (IconGeometry de un hexágono)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = {
    "regular": RAIZ / "phospor-icons" / "Fonts" / "regular" / "Phosphor.svg",
    "bold": RAIZ / "phospor-icons" / "Fonts" / "bold" / "Phosphor-Bold.svg",
    "fill": RAIZ / "phospor-icons" / "Fonts" / "fill" / "Phosphor-Fill.svg",
    "light": RAIZ / "phospor-icons" / "Fonts" / "light" / "Phosphor-Light.svg",
    "thin": RAIZ / "phospor-icons" / "Fonts" / "thin" / "Phosphor-Thin.svg",
}
SALIDA_ESTUDIO = RAIZ / "src" / "Avacom.Lms.Student" / "Resources" / "Images"

ESCALA = 0.25      # 1024 uem → 256
ASCENSO = 960      # el eje Y de la fuente sube desde la línea base; el de SVG baja desde arriba

_cache: dict[str, str] = {}


def _texto(peso: str) -> str:
    if peso not in _cache:
        _cache[peso] = FUENTES[peso].read_text(encoding="utf-8")
    return _cache[peso]


def glifo(nombre: str, peso: str = "regular") -> str:
    """El atributo `d` del glifo tal como está en la fuente."""
    buscado = nombre if peso == "regular" else f"{nombre}-{peso}"
    m = re.search(r'<glyph[^>]*glyph-name="' + re.escape(buscado) + r'"[^>]*\sd="([^"]+)"', _texto(peso))
    if m is None:
        m = re.search(r'<glyph[^>]*\sd="([^"]+)"[^>]*glyph-name="' + re.escape(buscado) + '"', _texto(peso))
    if m is None:
        raise SystemExit(f"No existe el icono «{buscado}» en la fuente {peso}.")
    return m.group(1)


# ---------------------------------------------------------------------------------- análisis del trazo

def _fichas(d: str):
    for m in re.finditer(r"([MmLlHhVvCcSsQqTtZzAa])|(-?\d*\.?\d+(?:e-?\d+)?)", d):
        yield m.group(1) if m.group(1) else float(m.group(2))


def _segmentos(d: str) -> list[tuple]:
    fichas = list(_fichas(d))
    i = 0
    cmd = None
    x = y = sx = sy = 0.0
    ultimo_control = None
    salida: list[tuple] = []

    def num() -> float:
        nonlocal i
        v = fichas[i]
        i += 1
        return v

    while i < len(fichas):
        if isinstance(fichas[i], str):
            cmd = fichas[i]
            i += 1
            if cmd in "Zz":
                salida.append(("Z",))
                x, y = sx, sy
                ultimo_control = None
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            nx, ny = num(), num()
            if rel:
                nx, ny = nx + x, ny + y
            x, y = nx, ny
            sx, sy = x, y
            salida.append(("M", x, y))
            cmd = "l" if rel else "L"
            ultimo_control = None
        elif c == "L":
            nx, ny = num(), num()
            if rel:
                nx, ny = nx + x, ny + y
            x, y = nx, ny
            salida.append(("L", x, y))
            ultimo_control = None
        elif c == "H":
            nx = num()
            x = nx + x if rel else nx
            salida.append(("L", x, y))
            ultimo_control = None
        elif c == "V":
            ny = num()
            y = ny + y if rel else ny
            salida.append(("L", x, y))
            ultimo_control = None
        elif c == "C":
            a = [num() for _ in range(6)]
            if rel:
                a = [a[0] + x, a[1] + y, a[2] + x, a[3] + y, a[4] + x, a[5] + y]
            salida.append(("C", *a))
            ultimo_control = (a[2], a[3])
            x, y = a[4], a[5]
        elif c == "S":
            a = [num() for _ in range(4)]
            if rel:
                a = [a[0] + x, a[1] + y, a[2] + x, a[3] + y]
            c1 = (2 * x - ultimo_control[0], 2 * y - ultimo_control[1]) if ultimo_control else (x, y)
            salida.append(("C", c1[0], c1[1], a[0], a[1], a[2], a[3]))
            ultimo_control = (a[0], a[1])
            x, y = a[2], a[3]
        elif c == "Q":
            a = [num() for _ in range(4)]
            if rel:
                a = [a[0] + x, a[1] + y, a[2] + x, a[3] + y]
            q0, q1, q2 = (x, y), (a[0], a[1]), (a[2], a[3])
            c1 = (q0[0] + 2 / 3 * (q1[0] - q0[0]), q0[1] + 2 / 3 * (q1[1] - q0[1]))
            c2 = (q2[0] + 2 / 3 * (q1[0] - q2[0]), q2[1] + 2 / 3 * (q1[1] - q2[1]))
            salida.append(("C", c1[0], c1[1], c2[0], c2[1], q2[0], q2[1]))
            x, y = q2
            ultimo_control = None
        else:
            raise SystemExit(f"El glifo trae el comando «{cmd}», que este generador no convierte (arcos).")
    return salida


def _n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def a_lienzo_256(d: str) -> str:
    """Trazo de la fuente → comandos absolutos en el lienzo 256 × 256, sin segmentos degenerados."""
    def p(px: float, py: float) -> tuple[float, float]:
        return px * ESCALA, (ASCENSO - py) * ESCALA

    partes: list[str] = []
    cx = cy = None
    for s in _segmentos(d):
        if s[0] == "M":
            px, py = p(s[1], s[2])
            partes.append(f"M{_n(px)},{_n(py)}")
            cx, cy = px, py
        elif s[0] == "L":
            px, py = p(s[1], s[2])
            if cx is not None and abs(px - cx) < 0.01 and abs(py - cy) < 0.01:
                continue
            partes.append(f"L{_n(px)},{_n(py)}")
            cx, cy = px, py
        elif s[0] == "C":
            p1, p2, p3 = p(s[1], s[2]), p(s[3], s[4]), p(s[5], s[6])
            diminuta = all(abs(q[0] - cx) < 0.2 and abs(q[1] - cy) < 0.2 for q in (p1, p2, p3))
            if diminuta:
                if abs(p3[0] - cx) >= 0.01 or abs(p3[1] - cy) >= 0.01:
                    partes.append(f"L{_n(p3[0])},{_n(p3[1])}")
                    cx, cy = p3
                continue
            partes.append(f"C{_n(p1[0])},{_n(p1[1])} {_n(p2[0])},{_n(p2[1])} {_n(p3[0])},{_n(p3[1])}")
            cx, cy = p3
        else:
            partes.append("Z")
    return " ".join(partes)


# ------------------------------------------------------------------------------------------ escritura

def svg_de(capas: list[tuple[str, str, str, tuple[float, float, float]]], lado: int) -> str:
    """Una o varias capas (glifo, peso, color, (desplazamiento x, y, escala)) sobre el lienzo de 256."""
    cuerpo = []
    for nombre, peso, color, (tx, ty, esc) in capas:
        d = a_lienzo_256(glifo(nombre, peso))
        transformacion = "" if (tx, ty, esc) == (0, 0, 1) else f' transform="translate({_n(tx)} {_n(ty)}) scale({_n(esc)})"'
        cuerpo.append(f'<path fill="{color}"{transformacion} d="{d}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{lado}" height="{lado}" viewBox="0 0 256 256">'
            + "".join(cuerpo) + "</svg>\n")


def una(nombre: str, peso: str, color: str) -> list[tuple[str, str, str, tuple[float, float, float]]]:
    return [(nombre, peso, color, (0, 0, 1))]


TINTA, GRIS, ROJO = "#1D1D1F", "#6E6E73", "#C1191D"
VERDE, AZUL, AMBAR, BLANCO = "#017A48", "#02739E", "#806600", "#FFFFFF"

# archivo (sin .svg) → (capas, lado en px que se muestra). Lado 24 ≈ 24 dp: Resizetizer genera los buckets a partir de él.
ICONOS_ESTUDIO: dict[str, tuple[list, int]] = {
    "estudio_close": (una("x", "bold", TINTA), 22),
    "estudio_clock": (una("clock", "regular", GRIS), 20),
    "estudio_clock_red": (una("clock", "regular", ROJO), 20),
    "estudio_download": (una("download-simple", "bold", TINTA), 20),
    "estudio_download_blue": (una("download-simple", "bold", AZUL), 20),
    "estudio_check_green": (una("check-circle", "fill", VERDE), 20),
    "estudio_check_bold_green": (una("check", "bold", VERDE), 20),
    "estudio_pause": (una("pause", "fill", TINTA), 20),
    "estudio_play": (una("play", "fill", TINTA), 20),
    "estudio_more": (una("dots-three", "bold", GRIS), 24),
    "estudio_arrow_white": (una("arrow-right", "bold", BLANCO), 20),
    "estudio_arrow_ink": (una("arrow-right", "bold", TINTA), 20),
    "estudio_arrow_left": (una("arrow-left", "bold", TINTA), 20),
    "estudio_cloud_up_amber": (una("cloud-arrow-up", "regular", AMBAR), 22),
    "estudio_sync_blue": (una("arrows-clockwise", "bold", AZUL), 22),
    "estudio_cloud_check_green": (una("cloud-check", "regular", VERDE), 22),
    "estudio_sparkle_blue": (una("sparkle", "fill", "#01A4E1"), 22),
    "estudio_wifi_off": (una("wifi-slash", "regular", GRIS), 20),
    "estudio_info": (una("info", "regular", AZUL), 22),
    "estudio_trash": (una("trash", "regular", ROJO), 22),
    "estudio_lock": (una("lock-simple", "regular", GRIS), 20),
    "estudio_exam": (una("exam", "regular", GRIS), 22),
    "estudio_storage": (una("hard-drives", "regular", GRIS), 18),
    "estudio_eye": (una("eye", "regular", GRIS), 20),
    "estudio_clipboard": (una("clipboard-text", "regular", GRIS), 22),
    # Estado vacío: el libro abierto con la marca de «al día» en su esquina.
    "estudio_book_check": ([("book-open", "light", "#8E8E93", (0, 0, 1)),
                            ("check-circle", "fill", "#019D60", (138, 138, 0.46))], 96),
    # Dock del menú del alumno: mismo formato que los demás dock_*.svg (blanco, 26 px).
    "dock_study": (una("graduation-cap", "regular", BLANCO), 26),
}


def escribir(carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, (capas, lado) in ICONOS_ESTUDIO.items():
        (carpeta / f"{nombre}.svg").write_text(svg_de(capas, lado), encoding="utf-8")
        print(f"  {nombre}.svg")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geometria", nargs=2, metavar=("ICONO", "PESO"), help="imprime el Data de un Path (lienzo 256)")
    ap.add_argument("--salida", type=Path, default=SALIDA_ESTUDIO, help="carpeta de destino de los SVG")
    args = ap.parse_args()
    if args.geometria:
        print(a_lienzo_256(glifo(*args.geometria)))
        return
    print(f"Escribiendo iconos en {args.salida}")
    escribir(args.salida)


if __name__ == "__main__":
    sys.exit(main())
