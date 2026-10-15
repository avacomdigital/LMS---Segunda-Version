"""
El catálogo de la biblioteca de mentira para las pruebas de Search: cumple el puerto `Catalogo` con cursos, lecciones y recursos que la prueba declara, un árbol
académico y una clasificación por curso. Registra cada consulta que recibe (para comprobar qué se le pidió) y se puede «cerrar» como una biblioteca apagada.
"""
from __future__ import annotations

from search.aplicacion.puertos import Impacto, ResultadoDelCatalogo
from search.dominio import catalogos as cat
from search.dominio import texto


class CatalogoFalso:
    def __init__(self):
        self.disponible = True
        self.motivo = "AVACOM Biblioteca no está encendida en este equipo (prueba)."
        self.hallazgos: list[dict] = []          # [{tipo, curso_ref, titulo, texto, leccion_ref, objeto_ref, ruta}]
        self.clasificacion: dict[str, dict] = {}  # curso_ref → {country, level, grade, subject, topic}
        self.existentes: set[tuple] = set()      # (curso_ref, leccion_ref, objeto_ref) que `existe` da por buenos
        self.consultas: list[dict] = []
        self.nodos: list[dict] = []

    # ------------------------------------------------------------------------------------------------ declarar
    def curso(self, curso_ref: str, titulo: str, texto_: str = "", **clasificacion) -> "CatalogoFalso":
        self.clasificacion[curso_ref] = clasificacion
        self.hallazgos.append({"tipo": cat.CURSO, "curso_ref": curso_ref, "titulo": titulo, "texto": texto_, "leccion_ref": "", "objeto_ref": "",
                               "ruta": [clasificacion.get("country", ""), titulo]})
        self.existentes.add((curso_ref, "", ""))
        return self

    def leccion(self, curso_ref: str, leccion_ref: str, titulo: str, texto_: str = "") -> "CatalogoFalso":
        self.hallazgos.append({"tipo": cat.LECCION, "curso_ref": curso_ref, "titulo": titulo, "texto": texto_, "leccion_ref": leccion_ref, "objeto_ref": "", "ruta": []})
        self.existentes.add((curso_ref, leccion_ref, ""))
        return self

    def retirar(self, curso_ref: str) -> None:
        """La biblioteca retira el curso (o la política del nodo lo desactiva): deja de salir en la búsqueda y de existir."""
        self.hallazgos = [h for h in self.hallazgos if h["curso_ref"] != curso_ref]
        self.existentes = {e for e in self.existentes if e[0] != curso_ref}
        self.clasificacion.pop(curso_ref, None)

    # ------------------------------------------------------------------------------------------------ puerto
    def buscar(self, consulta: str, arbol: dict[str, str], tipos: tuple[str, ...], limite: int) -> ResultadoDelCatalogo:
        self.consultas.append({"q": consulta, "arbol": dict(arbol), "tipos": tuple(tipos)})
        if not self.disponible:
            return ResultadoDelCatalogo(disponible=False, motivo=self.motivo, sugerencia="Abre la aplicación de contenido.")
        buscadas = texto.significativas(consulta)
        impactos = []
        for h in self.hallazgos:
            if h["tipo"] not in tipos:
                continue
            clasif = self.clasificacion.get(h["curso_ref"], {})
            if any(clasif.get(k) != v for k, v in arbol.items()):
                continue
            pajar = set(texto.raices(f"{h['titulo']} {h['texto']}"))
            if not buscadas or not all(b in pajar or any(p.startswith(b) for p in pajar) for b in buscadas):
                continue
            impactos.append(Impacto(tipo=h["tipo"], curso_ref=h["curso_ref"], titulo=h["titulo"], leccion_ref=h["leccion_ref"], objeto_ref=h["objeto_ref"],
                                    fragmento=h["texto"], ruta_arbol=tuple(h["ruta"]), posicion=len(impactos)))
        return ResultadoDelCatalogo(disponible=True, impactos=tuple(impactos[:limite]), total=len(impactos))

    def arbol(self) -> tuple[bool, str, list[dict]]:
        if not self.disponible:
            return False, self.motivo, []
        return True, "", self.nodos

    def cursos_del_arbol(self, arbol: dict[str, str]) -> set[str] | None:
        if not self.disponible:
            return None
        return {ref for ref, clasif in self.clasificacion.items() if all(clasif.get(k) == v for k, v in arbol.items())}

    def existe(self, curso_ref: str, leccion_ref: str = "", objeto_ref: str = "") -> bool | None:
        if not self.disponible:
            return None
        return (curso_ref, leccion_ref, objeto_ref) in self.existentes
