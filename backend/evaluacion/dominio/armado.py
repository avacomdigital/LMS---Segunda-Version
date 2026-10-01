"""
El examen de cada alumno (D-5, §7 del modelo). Función pura y DETERMINISTA: la misma `semilla` produce siempre el mismo examen, así una
auditoría puede reproducirlo y un reinicio del nodo no cambia las preguntas de nadie. No importa Django ni sabe de la biblioteca: recibe el
`pool` (los metadatos de cada pregunta que publica la biblioteca) y devuelve las REFERENCIAS elegidas, nunca su texto (artículo 14).

  fixed            todas las preguntas del banco, en el orden del banco
  random_balanced  `cantidad` preguntas con dificultad y tiempo totales parecidos a los del promedio del banco (dentro de las tolerancias del
                   examen) y, si el examen lo pide, con los mismos temas cubiertos

`random_balanced` busca hasta `intentos` combinaciones y se queda con la mejor; si ninguna cae dentro de las tolerancias entrega la mejor
con `dentro_de_tolerancia = False` (nunca se bloquea a un alumno por una configuración estrecha: el profesor lo ve al asignar).
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

from . import catalogos as cat
from .errores import DatosInvalidos

FIXED, RANDOM_BALANCED = "fixed", "random_balanced"
ESTRATEGIAS = (FIXED, RANDOM_BALANCED)
INTENTOS_POR_DEFECTO = 200


@dataclass
class Armado:
    refs: list[str]                       # el examen de este alumno, en orden
    estrategia: str
    dentro_de_tolerancia: bool = True
    dificultad_total: float = 0.0
    tiempo_total_seg: int = 0
    puntos_total: float = 0.0
    desvio_dificultad_pct: float = 0.0
    desvio_tiempo_pct: float = 0.0
    avisos: list[str] = field(default_factory=list)
    tipos: dict[str, str] = field(default_factory=dict)
    puntos: dict[str, float] = field(default_factory=dict)

    def meta(self) -> dict:
        """Lo que se guarda en `m10_intento.armado_meta`."""
        return {"estrategia": self.estrategia, "tipos": dict(self.tipos), "puntos": dict(self.puntos), "puntos_totales": round(self.puntos_total, 4),
                "estimado_seg": self.tiempo_total_seg, "dentro_de_tolerancia": self.dentro_de_tolerancia, "avisos": list(self.avisos)}


def normalizar_pool(pool: dict) -> list[dict]:
    """El `ExamPool` de la biblioteca (`questions[]` con `questionId`, `type`, `topicRef`, `difficulty`, `estimatedSec`, `points`) a una lista
    plana. Tolera la forma ya traducida (`pregunta_ref`, `tema_ref`…). Una pregunta sin identificador no existe."""
    salida = []
    for p in pool.get("questions") or pool.get("preguntas") or []:
        if not isinstance(p, dict):
            continue
        ref = str(p.get("questionId") or p.get("pregunta_ref") or p.get("id") or "").strip()
        if not ref:
            continue
        salida.append({
            "pregunta_ref": ref,
            "tipo": str(p.get("type") or p.get("tipo") or ""),
            "tema_ref": str(p.get("topicRef") or p.get("tema_ref") or ""),
            "dificultad": _num(p.get("difficulty", p.get("dificultad")), 1.0),
            "estimado_seg": int(_num(p.get("estimatedSec", p.get("estimado_seg")), 60)),
            "puntos": _num(p.get("points", p.get("puntos")), 1.0),
        })
    return salida


def ajustes_de_biblioteca(settings: dict) -> dict:
    """Los `settings` de un `ExamObject` (esquema de curso 1.0) normalizados. Acepta las dos formas que existen: la del esquema entregado
    (`difficultyTolerancePct`, `timeLimit.policy` + `extraPct`) y la de AVACOM Contenido 2.1.7 (`…Percent`, sin `policy`: `fixedSec` o `extraPercent`,
    uno solo). `mostrar_resultados` se traduce a la enumeración del LMS."""
    seleccion = settings.get("selection") or {}
    tiempo = settings.get("timeLimit") or {}
    extra = tiempo.get("extraPercent", tiempo.get("extraPct"))
    politica = tiempo.get("policy") or ("fixed" if tiempo.get("fixedSec") is not None else "sum_of_estimates" if extra is not None else "none")
    return {
        "estrategia": seleccion.get("strategy") or FIXED,
        "cantidad_preguntas": seleccion.get("questionCount"),
        "tolerancia_dificultad_pct": seleccion.get("difficultyTolerancePercent", seleccion.get("difficultyTolerancePct")),
        "tolerancia_tiempo_pct": seleccion.get("timeTolerancePercent", seleccion.get("timeTolerancePct")),
        "cubrir_todos_los_temas": bool(seleccion.get("coverAllTopics")),
        "tiempo": {"politica": politica, "fijo_seg": tiempo.get("fixedSec"), "extra_pct": extra},
        "aprobacion_pct": settings.get("passingScorePct"),
        "mostrar_resultados": cat.RESULTADOS_DE_LA_BIBLIOTECA.get(settings.get("showResults"), cat.TRAS_LIBERAR),
        "navegacion_atras": bool(settings.get("allowBackNavigation", True)),
        "barajar_opciones": bool(settings.get("shuffleOptions", True)),
    }


def semilla_del_intento(asignacion_id: str, alumno_id: str, numero: int) -> str:
    """D-5: el examen de un alumno depende sólo de la asignación, el alumno y el número de intento."""
    return f"{asignacion_id}|{alumno_id}|{int(numero)}"


def _rng(semilla: str) -> random.Random:
    return random.Random(int(hashlib.sha256(str(semilla).encode("utf-8")).hexdigest(), 16))


def armar(pool: list[dict], *, estrategia: str, cantidad: int | None, tolerancia_dificultad_pct: float | None,
          tolerancia_tiempo_pct: float | None, cubrir_temas: bool, semilla: str, intentos: int = INTENTOS_POR_DEFECTO) -> Armado:
    if estrategia not in ESTRATEGIAS:
        raise DatosInvalidos(f"La estrategia de selección «{estrategia}» no existe. Estrategias: {', '.join(ESTRATEGIAS)}.", estrategia=estrategia)
    if not pool:
        raise DatosInvalidos("El banco de preguntas del examen está vacío.")
    por_ref = {p["pregunta_ref"]: p for p in pool}
    if estrategia == FIXED:
        return _resultado([p["pregunta_ref"] for p in pool], por_ref, FIXED, True, 0.0, 0.0, [])

    total = len(pool)
    cantidad = max(1, min(int(cantidad or total), total))
    tol_d = 100.0 if tolerancia_dificultad_pct is None else float(tolerancia_dificultad_pct)
    tol_t = 100.0 if tolerancia_tiempo_pct is None else float(tolerancia_tiempo_pct)
    rng = _rng(semilla)
    media_d = sum(p["dificultad"] for p in pool) / total
    media_t = sum(p["estimado_seg"] for p in pool) / total
    objetivo_d, objetivo_t = cantidad * media_d, cantidad * media_t

    por_tema: dict[str, list[dict]] = {}
    for p in pool:
        por_tema.setdefault(p["tema_ref"], []).append(p)
    temas = list(por_tema)                # orden de aparición: estable
    avisos: list[str] = []
    if cubrir_temas and cantidad < len(temas):
        avisos.append("W-EXAM-TOPICS")    # no caben todos los temas: se cubren los que alcancen

    def desvios(elegidas: list[dict]) -> tuple[float, float]:
        dd = abs(sum(p["dificultad"] for p in elegidas) - objetivo_d) / objetivo_d * 100 if objetivo_d else 0.0
        dt = abs(sum(p["estimado_seg"] for p in elegidas) - objetivo_t) / objetivo_t * 100 if objetivo_t else 0.0
        return dd, dt

    mejor: tuple[float, list[dict], float, float] | None = None
    for _ in range(max(1, int(intentos))):
        elegidas: list[dict] = []
        if cubrir_temas:
            for tema in rng.sample(temas, len(temas)):
                if len(elegidas) < cantidad:
                    elegidas.append(rng.choice(por_tema[tema]))
        restantes = [p for p in pool if p not in elegidas]
        rng.shuffle(restantes)
        elegidas += restantes[: cantidad - len(elegidas)]
        dd, dt = desvios(elegidas)
        peor = max(dd / tol_d if tol_d else dd, dt / tol_t if tol_t else dt)       # 1.0 = justo en el límite de ambas tolerancias
        if mejor is None or peor < mejor[0]:
            mejor = (peor, elegidas, dd, dt)
        if peor <= 1.0:
            break
    peor, elegidas, dd, dt = mejor
    rng.shuffle(elegidas)                  # el orden también es del alumno
    dentro = peor <= 1.0
    if not dentro:
        avisos.append("W-EXAM-TOLERANCE")
    return _resultado([p["pregunta_ref"] for p in elegidas], por_ref, RANDOM_BALANCED, dentro, dd, dt, avisos)


def _resultado(refs: list[str], por_ref: dict[str, dict], estrategia: str, dentro: bool, dd: float, dt: float, avisos: list[str]) -> Armado:
    elegidas = [por_ref[r] for r in refs]
    return Armado(
        refs=list(refs), estrategia=estrategia, dentro_de_tolerancia=dentro,
        dificultad_total=round(sum(p["dificultad"] for p in elegidas), 4),
        tiempo_total_seg=int(sum(p["estimado_seg"] for p in elegidas)),
        puntos_total=round(sum(p["puntos"] for p in elegidas), 4),
        desvio_dificultad_pct=round(dd, 2), desvio_tiempo_pct=round(dt, 2), avisos=list(avisos),
        tipos={p["pregunta_ref"]: p["tipo"] for p in elegidas}, puntos={p["pregunta_ref"]: p["puntos"] for p in elegidas})


def limite_en_segundos(politica: str | None, *, estimado_seg: int, fijo_seg: int | None = None, extra_pct: float | None = None) -> int | None:
    """El tiempo de un examen según la política de la biblioteca (§7.2): `sum_of_estimates` suma lo estimado de SUS preguntas con un margen;
    `fixed` es `fixedSec`; `none` (o sin política) no tiene cronómetro."""
    if politica == "fixed" and fijo_seg:
        return int(fijo_seg)
    if politica == "sum_of_estimates" and estimado_seg > 0:
        return int(math.ceil(estimado_seg * (1 + float(extra_pct or 0) / 100.0)))
    return None


def _num(valor, por_defecto: float) -> float:
    if valor is None or isinstance(valor, bool):
        return por_defecto
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto
