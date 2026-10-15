"""
El documento del índice (la PROYECCIÓN de una entidad del LMS) y la visibilidad de quien consulta. Puro.

El documento nunca es la fuente de verdad: copia lo mínimo para encontrar la entidad (un título, una descripción, unas palabras clave) y NO para decidir nada. Quién
puede leerla se decide en cada consulta con el padrón y los permisos VIGENTES (`Visibilidad`), no con lo que valían cuando se indexó.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from . import catalogos as cat


@dataclass(frozen=True)
class Documento:
    tipo: str
    entidad_id: str
    titulo: str
    descripcion: str = ""
    palabras: str = ""             # curso, lección, materia, unidad… separados por espacios
    contexto: str = ""             # grupo, profesor…
    etiquetas: str = ""            # palabras del TIPO («examen», «evaluación»): sólo se indexan, para que quien escribe «examen» encuentre la evaluación; nunca se muestran
    subtipo: str = ""              # examen | actividad (evaluación)
    grupo_id: str = ""
    profesor_id: str = ""
    curso_ref: str = ""
    estado: str = ""
    referencia: dict = field(default_factory=dict)   # lo que el cliente necesita para abrirlo: {leccion_ref, objeto_ref, fuente, …}
    origen_actualizado_en: int | None = None

    def huella(self) -> str:
        """SHA-1 de lo indexable: si no cambió, indexar de nuevo no hace nada (idempotencia) y no se emite ningún evento."""
        datos = asdict(self)
        datos.pop("origen_actualizado_en", None)
        return hashlib.sha1(json.dumps(datos, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Visibilidad:
    """Lo que UNA persona puede leer, calculado con los datos vigentes en el momento de la consulta (BR-088)."""

    persona_id: str
    por_tipo: dict = field(default_factory=dict)            # tipo → ORGANIZACION | GRUPOS; un tipo ausente no se puede leer
    grupos: frozenset = frozenset()                         # los grupos de los que es docente (vigentes)
    contenido: bool = False                                 # puede leer el catálogo de la biblioteca

    @property
    def tipos_locales(self) -> tuple[str, ...]:
        return tuple(t for t in cat.TIPOS_LOCALES if t in self.por_tipo)

    @property
    def tipos(self) -> tuple[str, ...]:
        return tuple(t for t in cat.TIPOS if t in self.por_tipo)

    def alcance_de(self, tipo: str) -> str | None:
        return self.por_tipo.get(tipo)

    def puede_leer(self, tipo: str, grupo_id: str = "", profesor_id: str = "") -> bool:
        alcance = self.por_tipo.get(tipo)
        if alcance is None:
            return False
        if alcance == cat.ORGANIZACION:
            return True
        if grupo_id:
            return grupo_id in self.grupos
        return bool(profesor_id) and profesor_id == self.persona_id     # sin grupo: sólo lo que esa persona creó
