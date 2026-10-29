"""
Sonda del agente de IA para el equipo REAL (donde sí está Qwen): recorre la cadena OPS → nodo → AVACOM Local AI → Qwen/Piper y dice en qué eslabón falla. Sólo LEE y pregunta: no crea
personas, grupos ni clases. Sólo usa la biblioteca estándar.

    backend\\.venv\\Scripts\\python backend\\tools\\probar_agente_ia.py --documento <doc de un profesor> --clave <su contraseña>
    backend\\.venv\\Scripts\\python backend\\tools\\probar_agente_ia.py --documento ... --clave ... --preguntas   # además 5 preguntas de muestra, para LEER las respuestas
    ... --guardar C:\\Temp\\voz.wav                                                                                # guarda el audio de la voz para ESCUCHARLO

Qué comprueba, en orden (cada paso dice OK o FALLA con el motivo y qué mirar):
  1. El servicio de IA directo (http://127.0.0.1:12000/health/dependencies): Ollama, el modelo Qwen, la voz y el contexto.
  2. El nodo (por defecto http://127.0.0.1:8000): el inicio de sesión y /api/agente-ia/estado/.
  3. Una pregunta y su respuesta: tiempo, longitud, que no traiga Markdown ni «<think>», que esté en español.
  4. La voz de esa respuesta: un WAV válido (mono, 16 bits, 22 050 Hz) y cuánto dura.
  5. (con --preguntas) la memoria de la conversación y el uso del contexto de AVACOM.

Sale con 0 si todo bien y con 1 si algo falló. NUNCA lo apuntes a un nodo que no sea el tuyo con credenciales que no sean tuyas.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import time
import urllib.error
import urllib.request

AYUDA = {
    "ai_unreachable": "El servicio «AVACOM Local AI» no contesta. En PowerShell: Get-Service AVACOMLocalAI  (debe estar Running) y  Invoke-RestMethod http://127.0.0.1:12000/health",
    "llm_unavailable": "Ollama no está en marcha. En PowerShell: Get-Service AVACOMOllama  (y  ollama list  debe mostrar el modelo).",
    "llm_model_missing": "El modelo no está instalado o su nombre no coincide con AVACOM_LLM_MODEL (C:\\ProgramData\\AVACOM\\LocalAI\\config\\.env). Revisa  ollama list.",
    "context_unavailable": "El archivo avacom-context.txt falta, está vacío o pasa de 8000 caracteres (C:\\ProgramData\\AVACOM\\LocalAI\\context\\).",
    "llm_timeout": "Qwen no respondió a tiempo: el modelo es demasiado grande para este equipo. Prueba con qwen3:4b o qwen3:1.7b (AVACOM_LLM_MODEL).",
    "ai_timeout": "El servicio de IA tardó más de lo que el nodo espera (160 s). Mismo remedio que llm_timeout.",
    "busy": "Hay otra consulta en curso: espera y repite.",
    "tts_unavailable": "La voz no carga: mira  /health/dependencies  →  tts_model.error  y que existan los .onnx en C:\\ProgramData\\AVACOM\\LocalAI\\models\\piper\\.",
    "tts_busy": "La voz está ocupada: espera y repite.",
    "ai_invalid_response": "El servicio contestó algo que no es lo esperado: mira backend-errores.log (evento agente_ia.*).",
    "sin_permiso": "Este usuario no puede usar el asistente (los alumnos no). Usa un profesor.",
}
fallos: list[str] = []


def ok(paso: str, bien: bool, si_falla: str = "", si_bien: str = "") -> bool:
    detalle = si_bien if bien else si_falla
    print(("  OK     " if bien else "  FALLA  ") + paso + (f"  → {detalle}" if detalle else ""))
    if not bien:
        fallos.append(paso)
    return bien


def llamar(url: str, cuerpo: dict | None = None, token: str | None = None, espera: float = 200.0):
    datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8") if cuerpo is not None else None
    r = urllib.request.Request(url, data=datos, method="POST" if cuerpo is not None else "GET")
    r.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=espera) as resp:
            return resp.status, resp.read(), dict(resp.headers), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers), time.time() - t0
    except Exception as e:  # noqa: BLE001 — sin conexión, tiempo agotado…
        return 0, str(e).encode("utf-8"), {}, time.time() - t0


def cuerpo_json(b: bytes) -> dict:
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def explicar(e: int, b: bytes) -> str:
    j = cuerpo_json(b)
    codigo = j.get("codigo") or ("sin_conexion" if e == 0 else f"http_{e}")
    return f"{e} {codigo}: {j.get('detail') or b.decode('utf-8', 'replace')[:200]}. {AYUDA.get(codigo, '')}".strip()


def wav_info(b: bytes):
    if len(b) < 44 or b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        return None
    canales, frecuencia = struct.unpack_from("<HI", b, 22)
    bits = struct.unpack_from("<H", b, 34)[0]
    datos = struct.unpack_from("<I", b, 40)[0]
    return canales, frecuencia, bits, datos / max(1, frecuencia * canales * bits // 8)


def main() -> int:
    ap = argparse.ArgumentParser(description="Sonda del agente de IA (nodo → AVACOM Local AI → Qwen/Piper)")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="la dirección del nodo (OPS Master)")
    ap.add_argument("--ia", default="http://127.0.0.1:12000", help="la dirección del servicio de IA (sólo para el paso 1)")
    ap.add_argument("--documento", required=True, help="documento de un PROFESOR (o de administración)")
    ap.add_argument("--clave", required=True)
    ap.add_argument("--pin-maestro", default="", help="sólo si entras con la administración")
    ap.add_argument("--preguntas", action="store_true", help="además, 5 preguntas de muestra (memoria y contexto) para leer las respuestas")
    ap.add_argument("--guardar", default="", help="guarda el WAV de la voz en esta ruta")
    a = ap.parse_args()

    print("1) El servicio de IA, directo")
    e, b, _, dt = llamar(a.ia + "/health/dependencies", espera=10)
    if e != 200:
        ok("el servicio de IA contesta", False, f"{e} {b.decode('utf-8', 'replace')[:160]}. {AYUDA['ai_unreachable']}")
    else:
        d = cuerpo_json(b)
        ok("el servicio de IA contesta", True, si_bien=f"{dt:.2f}s")
        ok("Ollama en marcha", bool(d.get("ollama", {}).get("reachable")), AYUDA["llm_unavailable"])
        ok(f"modelo {d.get('llm_model', {}).get('name')} instalado", bool(d.get("llm_model", {}).get("installed")), AYUDA["llm_model_missing"])
        ok("voz cargada", bool(d.get("tts_model", {}).get("loaded") or d.get("tts_model", {}).get("file_present")), AYUDA["tts_unavailable"])
        ok("contexto de AVACOM cargado", d.get("context", {}).get("state") == "loaded", AYUDA["context_unavailable"])

    print("2) El nodo")
    e, b, _, _ = llamar(a.base + "/api/acceso/sesiones/", {"identificador": a.documento, "secreto": a.clave, "dispositivo": "", "rol": "", **({"pin_maestro": a.pin_maestro} if a.pin_maestro else {})})
    if not ok("inicio de sesión", e == 200, f"{e} {b.decode('utf-8', 'replace')[:200]}"):
        return 1
    token = cuerpo_json(b)["token"]
    e, b, _, dt = llamar(a.base + "/api/agente-ia/estado/", token=token, espera=30)
    est = cuerpo_json(b)
    if not ok("el nodo responde el estado del asistente", e == 200, explicar(e, b)):
        return 1
    ok("asistente disponible", bool(est.get("disponible")), f"{est.get('codigo')}: {est.get('motivo')}. {AYUDA.get(est.get('codigo') or '', '')}")
    ok("voz disponible", bool(est.get("voz_disponible")), est.get("motivo_voz") or "")
    if not est.get("disponible"):
        print("\nFALLAS:", fallos)
        return 1

    print("3) Pregunta y respuesta (la primera puede tardar: carga Qwen en la memoria)")
    conv = f"sonda-{int(time.time())}"
    e, b, _, dt = llamar(a.base + "/api/agente-ia/preguntar/", {"pregunta": "¿Qué es AVACOM y en qué me puedes ayudar?", "conversacion": conv}, token)
    if not ok("el modelo responde", e == 200, explicar(e, b)):
        return 1
    r = cuerpo_json(b)
    texto = r["texto"]
    print(f"        ({dt:.1f} s · {len(texto)} caracteres · modelo {r.get('modelo')})\n        «{texto}»")
    ok("sin Markdown ni emojis", not re.search(r"(\*\*|^#|^\s*[-*] |`|<think>)", texto, re.M) and not re.search("[\U0001F300-\U0001FAFF]", texto), "el modelo puso formato: revisa el contexto")
    ok("respuesta breve (< 600 caracteres)", len(texto) < 600, f"{len(texto)} caracteres: la voz tendrá que trocearla (funciona, pero tarda más)")
    ok("responde en español", bool(re.search(r"\b(el|la|de|que|y|en|para|los|las)\b", texto, re.I)), "no parece español")

    print("4) La voz")
    e, b, h, dt = llamar(a.base + "/api/agente-ia/hablar/", {"texto": texto}, token)
    if not ok("la voz responde", e == 200, explicar(e, b)):
        return 1
    info = wav_info(b)
    ok("es un WAV válido (mono, 16 bits, 22 050 Hz)", info is not None and info[:3] == (1, 22050, 16), str(info))
    if info:
        print(f"        {len(b) / 1e6:.2f} MB · {info[3]:.1f} s de audio · {h.get('X-Audio-Chunks')} trozo(s) · tardó {dt:.1f} s (factor tiempo real ≈ {dt / max(info[3], 0.1):.2f})")
    if a.guardar:
        with open(a.guardar, "wb") as f:
            f.write(b)
        print(f"        guardado en {a.guardar}: ESCÚCHALO (claridad, pronunciación mexicana, tono)")

    if a.preguntas:
        print("5) Preguntas de muestra: LÉELAS (¿correctas? ¿en español latino? ¿breves? ¿inventan datos?)")
        conv2 = f"sonda-mem-{int(time.time())}"
        for p in ("Me llamo Ana.", "¿Cómo me llamo?", "¿Qué es el LMS de AVACOM?", "Explícame las fracciones a un niño de cuarto de primaria.", "¿Cuál es el horario del curso de astrofísica cuántica de AVACOM?"):
            e, b, _, dt = llamar(a.base + "/api/agente-ia/preguntar/", {"pregunta": p, "conversacion": conv2}, token)
            t = cuerpo_json(b).get("texto") or explicar(e, b)
            print(f"        P: {p}\n        R ({dt:.1f} s): {t}\n")
            if p == "¿Cómo me llamo?":
                ok("recuerda el nombre (memoria de la conversación)", "ana" in t.lower(), t)

    print("\n" + ("TODO BIEN" if not fallos else f"FALLAS: {fallos}"))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
