"""
El identificador de conversación que ve el servicio de IA.

La memoria de una conversación vive en el servicio local (30 min de inactividad, 6 intercambios, se pierde al reiniciarlo) y se llama por `conversation_id`. Aquí se arma ese id para que:

  · sea OPACO: `lms-<huella de quien pregunta>-<id que eligió la pantalla>`; ningún dato personal llega al servicio ni a sus logs;
  · una persona no pueda leer ni continuar la conversación de otra aunque adivine el id de la pantalla (la huella de quien pregunta va dentro);
  · cumpla el patrón del servicio (`^[A-Za-z0-9_.:-]{1,64}$`).

Sin id de pantalla no hay conversación: cada pregunta se responde sin memoria.
"""
from __future__ import annotations

import hashlib
import re

_NO_PERMITIDO = re.compile(r"[^A-Za-z0-9_.:-]")
LARGO_PANTALLA = 40


def huella_de(usuario_id: str | None) -> str:
    return hashlib.sha256(f"avacom-agente-ia|{usuario_id or 'anonimo'}".encode("utf-8")).hexdigest()[:10]


def conversacion_de(usuario_id: str | None, id_de_pantalla: str | None) -> str | None:
    limpio = _NO_PERMITIDO.sub("", str(id_de_pantalla or ""))[:LARGO_PANTALLA]
    if not limpio:
        return None
    return f"lms-{huella_de(usuario_id)}-{limpio}"
