"""
Niveles de control, capacidad del dispositivo y plan de bloqueo (DEC-009, CAP-063, CAP-064, BR-075, BR-076, D-11, D-12).

Tres ideas, todas puras:

  1. Un NIVEL es lo que el examen exige (`controlado` > `supervisado` > `abierto`). Una CAPACIDAD es lo que la tableta DECLARA poder
     garantizar. La tableta ALCANZA el nivel si el rango de su capacidad no es menor. `controlado` significa «la capa del sistema
     operativo está aprovisionada» (Device Owner en Android; Assigned Access o Shell Launcher en Windows): la app mide e informa, no presume.
  2. El PLAN DE BLOQUEO es la ÚNICA fuente de verdad de qué se bloquea en cada nivel. Lo decide el nodo y viaja con el intento; la tableta lo
     EJECUTA con su servicio de kiosco y INFORMA lo que logró. El cliente no tiene una tabla propia de «qué se bloquea».
  3. Lo que la plataforma no garantiza se dice: un plan `controlado` con capacidad menor es `parcial`, nunca se presenta como completo.

Ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

from . import catalogos as cat
from .errores import DatosInvalidos


def validar_nivel(valor, nombre: str = "nivel_examen") -> str:
    texto = str(valor or "").strip().lower()
    if texto not in cat.NIVELES:
        raise DatosInvalidos(f"{nombre} debe ser uno de: {', '.join(cat.NIVELES)}.", **{nombre: valor})
    return texto


def normalizar_capacidad(valor) -> str:
    """La capacidad que declara una tableta. Lo que no declara (o declara mal) cuenta como `abierto`: el nodo no presume lo que no sabe."""
    texto = str(valor or "").strip().lower()
    return texto if texto in cat.NIVELES else cat.ABIERTO


def validar_capacidad(valor) -> str:
    """La capacidad en una entrada HTTP: vacío es «no declarada» (`abierto`); un valor desconocido es un error de datos."""
    texto = str(valor or "").strip().lower()
    if not texto:
        return cat.ABIERTO
    if texto not in cat.NIVELES:
        raise DatosInvalidos(f"capacidad_control debe ser uno de: {', '.join(cat.NIVELES)}.", capacidad_control=valor)
    return texto


def rango(nivel: str) -> int:
    return cat.RANGO_NIVEL[nivel]


def alcanza(capacidad: str, nivel: str) -> bool:
    """BR-075: ¿la capacidad declarada por la tableta cumple el nivel que exige el examen?"""
    return rango(normalizar_capacidad(capacidad)) >= rango(nivel)


def es_menor(nivel: str, que: str) -> bool:
    return rango(nivel) < rango(que)


def validar_degradacion(vigente: str, nuevo: str) -> None:
    """FUN-118: el nivel sólo baja. Subirlo durante el examen cambiaría las reglas a quien ya empezó."""
    if not es_menor(nuevo, vigente):
        raise DatosInvalidos(f"Degradar baja el nivel: de «{vigente}» sólo se puede pasar a uno menor.", vigente=vigente, nuevo=nuevo)


def validar_admision(exigido: str, admitido: str) -> None:
    """FUN-116: se admite POR DEBAJO del nivel exigido, nunca en uno igual o mayor."""
    if not es_menor(admitido, exigido):
        raise DatosInvalidos(f"Admitir una tableta es aceptarla en un nivel menor al exigido («{exigido}»).",
                             nivel_exigido=exigido, nivel_admitido=admitido)


def condiciones(nivel: str) -> dict:
    """El texto OBLIGATORIO de la antesala (el alumno sabe siempre bajo qué condiciones presenta) y lo que se registra."""
    base = cat.CONDICIONES[nivel]
    return {"nivel": nivel, "titulo": base["titulo"], "texto": base["texto"], "registra": list(base["registra"])}


def plan_de_bloqueo(nivel_efectivo: str, capacidad: str, nivel_exigido: str | None = None) -> dict:
    """Qué capas debe aplicar la tableta, con la capacidad que declaró (§6.4 del modelo).

    `capa_sistema`: Lock Task (Android) o Assigned Access/Shell Launcher (Windows); sólo si el nivel es `controlado` Y la tableta declaró
    poder garantizarla. `capa_app`: pantalla completa, Atrás/cierre/teclas descartados; en `controlado`. `parcial` avisa de que se pide
    `controlado` y la capa del sistema no está: la tableta debe informarlo como incidente en vez de callarlo."""
    nivel = validar_nivel(nivel_efectivo)
    capacidad = normalizar_capacidad(capacidad)
    controlado = nivel == cat.CONTROLADO
    sistema = controlado and rango(capacidad) >= rango(cat.CONTROLADO)
    return {
        "nivel": nivel,
        "nivel_exigido": nivel_exigido or nivel,
        "capacidad": capacidad,
        "capa_sistema": sistema,
        "capa_app": controlado,
        "registrar_salidas": nivel in (cat.CONTROLADO, cat.SUPERVISADO),
        "registrar_consultas": nivel == cat.SUPERVISADO,
        "bloquear_capturas": controlado,
        "cubrir_pantallas_extra": controlado,
        "latido_seg": 10 if nivel == cat.ABIERTO else 5,
        "parcial": controlado and not sistema,
    }


def valida_informe_de_bloqueo(resultado, capas) -> tuple[str, dict]:
    """El informe que la tableta manda tras aplicar el plan: `resultado` y las `capas` que logró (`sistema`, `app`, `capturas`, `pantallas`)."""
    resultado = str(resultado or "").strip().lower()
    if resultado not in cat.RESULTADOS_BLOQUEO:
        raise DatosInvalidos(f"resultado debe ser uno de: {', '.join(cat.RESULTADOS_BLOQUEO)}.", resultado=resultado)
    if capas is None:
        capas = {}
    if not isinstance(capas, dict):
        raise DatosInvalidos("`capas` debe ser un objeto {sistema, app, capturas, pantallas}.")
    return resultado, {c: bool(capas.get(c)) for c in cat.CAPAS_BLOQUEO}
