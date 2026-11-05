"""
Qué dirección y qué tiempos usa el LMS para hablar con AVACOM Local AI (el servicio de IA que corre en el MISMO equipo, topología A de `contrato-api-ai-lms.md`).

La dirección se decide EN CADA PETICIÓN, no al arrancar (como la nota de enlace de la biblioteca): si el técnico cambia el puerto del servicio, el aula lo sigue sin reiniciar el nodo.
Orden de decisión:

  1. `AVACOM_IA_URL` (backend.env), si está.
  2. El `.env` del propio servicio de IA (`%ProgramData%\\AVACOM\\LocalAI\\config\\.env`: `AVACOM_HOST`, `AVACOM_PORT`), que es donde el instalador de la IA fija el puerto.
  3. `http://127.0.0.1:12000`, el valor por defecto del servicio.

En pruebas el paso 2 está apagado (jamás se lee el equipo real).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

URL_POR_OMISION = "http://127.0.0.1:12000"


@dataclass(frozen=True)
class Configuracion:
    habilitada: bool
    url: str
    tiempo_llm_s: float          # tope de la consulta al modelo (el servicio espera hasta 30 s de turno + 120 s de inferencia: ≈150 s)
    tiempo_voz_s: float          # tope de la síntesis de UN trozo (el servicio corta a los 60 s)
    tiempo_voz_total_s: float    # tope de TODA la voz de un texto (todos sus trozos): la app no espera más que esto
    tiempo_salud_s: float
    trozo_max: int
    pregunta_max: int
    voz_texto_max: int
    max_tokens: int
    voz_turno_s: float           # cuánto espera su turno una síntesis (de a una por equipo) antes de decir «voz ocupada»


def _leer_env(ruta: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    try:
        for renglon in ruta.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            renglon = renglon.strip()
            if not renglon or renglon.startswith("#") or "=" not in renglon:
                continue
            clave, _, valor = renglon.partition("=")
            valores[clave.strip()] = valor.strip().strip('"').strip("'")
    except OSError:
        pass
    return valores


def url_del_servicio() -> str:
    explicita = str(getattr(settings, "AVACOM_IA_URL", "") or "").strip()
    if explicita:
        return explicita.rstrip("/")
    archivo = str(getattr(settings, "AVACOM_IA_ENV_ARCHIVO", "") or "").strip()
    if archivo:
        valores = _leer_env(Path(archivo))
        puerto = valores.get("AVACOM_PORT", "")
        if puerto.isdigit() and 0 < int(puerto) < 65536:
            host = valores.get("AVACOM_HOST", "") or "127.0.0.1"
            if host in ("0.0.0.0", "::", "[::]", "*"):
                host = "127.0.0.1"          # escucha en todas las interfaces: desde aquí se llega por el bucle local
            return f"http://{host}:{puerto}"
    return URL_POR_OMISION


def actual() -> Configuracion:
    g = lambda nombre, defecto: getattr(settings, nombre, defecto)  # noqa: E731
    return Configuracion(
        habilitada=bool(g("AVACOM_IA_HABILITADA", True)), url=url_del_servicio(),
        tiempo_llm_s=float(g("AVACOM_IA_TIEMPO_LLM_S", 160)), tiempo_voz_s=float(g("AVACOM_IA_TIEMPO_VOZ_S", 75)), tiempo_voz_total_s=float(g("AVACOM_IA_TIEMPO_VOZ_TOTAL_S", 120)), tiempo_salud_s=float(g("AVACOM_IA_TIEMPO_SALUD_S", 5)),
        trozo_max=int(g("AVACOM_IA_TROZO_MAX", 450)), pregunta_max=int(g("AVACOM_IA_PREGUNTA_MAX", 2000)), voz_texto_max=int(g("AVACOM_IA_VOZ_TEXTO_MAX", 3000)),
        max_tokens=int(g("AVACOM_IA_MAX_TOKENS", 256)), voz_turno_s=float(g("AVACOM_IA_VOZ_TURNO_S", 45)),
    )
