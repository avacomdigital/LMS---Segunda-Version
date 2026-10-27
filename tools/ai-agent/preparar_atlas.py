"""Genera el atlas optimizado de AI Agent a partir del spritesheet original.

El original (assets/sprite-ai-agent.png) mide 8688 x 2896 px (24 fotogramas, 8 columnas x 3 filas, sin canal alfa):
supera el MAX_TEXTURE_SIZE de muchas GPU moviles (4096-8192) y pesa 15 MB. El atlas que carga WebGL se reduce a
4096 px de ancho (512 px por fotograma) y conserva la misma cuadricula, de modo que config/face-animations.json
sirve para ambos. El original no se toca.

Uso: python tools/ai-agent/preparar_atlas.py   (necesita Pillow)
"""
from pathlib import Path
from PIL import Image

RAIZ = Path(__file__).resolve().parents[2]
ORIGEN = RAIZ / "assets" / "sprite-ai-agent.png"
DESTINO = RAIZ / "src" / "Avacom.Lms.Ops" / "Resources" / "Raw" / "wwwroot" / "ai-agent" / "assets" / "sprite-ai-agent.png"
ANCHO = 4096

with Image.open(ORIGEN) as im:
    im = im.convert("RGB")
    alto = round(im.height * ANCHO / im.width)
    reducida = im.resize((ANCHO, alto), Image.LANCZOS)
DESTINO.parent.mkdir(parents=True, exist_ok=True)
reducida.save(DESTINO, optimize=True)
print(f"{ORIGEN.name} {im.size} -> {DESTINO} {reducida.size} {DESTINO.stat().st_size / 1e6:.2f} MB")
