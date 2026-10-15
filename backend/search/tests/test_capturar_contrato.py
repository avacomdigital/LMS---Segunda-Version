"""
Captura las respuestas REALES de `/api/search/` como archivos JSON para las pruebas de los clientes de C# (`tests/Avacom.Lms.Core.Tests/Fixtures/search/`). Así un campo mal escrito
en un DTO de C# se descubre contra el backend de verdad y no contra lo que alguien creyó que devolvía.

No hace nada en una corrida normal. Para regenerar los archivos:

    set AVACOM_CAPTURAR_CONTRATO=C:\\projects\\prototypes\\prototype-lms-v04\\tests\\Avacom.Lms.Core.Tests\\Fixtures\\search
    .venv\\Scripts\\python manage.py test search.tests.test_capturar_contrato

Los identificadores y las horas cambian en cada corrida: las pruebas de C# comprueban la FORMA, no esos valores.
"""
from __future__ import annotations

import json
import os
import unittest

from .base import SEARCH, BaseSearch

CARPETA = os.environ.get("AVACOM_CAPTURAR_CONTRATO", "")
CURSO = "avacom.co.primary.4.math.fractions"


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO no está definida: no se capturan archivos")
class CapturarContratoTests(BaseSearch):
    def guardar(self, nombre: str, cuerpo) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(cuerpo, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def test_capturar(self):
        self.catalogo.curso(CURSO, "Estados de la materia", "Curso para entender los estados de la materia", country="CO", level="primary", grade="4", subject="math")
        self.catalogo.leccion(CURSO, "l1", "Los estados de la materia en la cocina", "Ejemplos cotidianos de estados")
        self.catalogo.nodos = [{"kind": "country", "code": "CO", "name": "Colombia", "count": 1, "children": [
            {"kind": "level", "code": "primary", "name": "Primaria", "count": 1, "children": [
                {"kind": "grade", "code": "4", "name": "Cuarto", "count": 1, "children": [
                    {"kind": "subject", "code": "math", "name": "Matemáticas", "count": 1, "children": []}]}]}]}]
        self.evaluacion("Estados de la materia", descripcion="Examen de los estados de la materia")
        self.estudio("l1-three-states", titulo="Estados de la materia en casa")
        self.clase()

        self.guardar("busqueda", self.buscar("estados"))
        self.guardar("busqueda_pagina_2", self.buscar("estados", limit=2, page=2))
        self.guardar("busqueda_filtrada", self.buscar("estados", type="assessment,class", period="2026", group=self.grupo["id"]))
        self.guardar("busqueda_sin_coincidencias", self.buscar("trigonometria"))
        self.guardar("busqueda_relajada", self.buscar("estados trigonometria"))
        self.guardar("error_consulta_vacia", self.buscar("", esperado=400))
        self.guardar("error_consulta_invalida", self.buscar("x", esperado=400))
        self.guardar("error_tipo_invalido", self.buscar("estados", esperado=400, type="alumno"))
        self.catalogo.disponible = False
        self.guardar("busqueda_catalogo_cerrado", self.buscar("estados"))
        self.catalogo.disponible = True
        self.guardar("filtros", self.docente.get(f"{SEARCH}/filters/").json())
        self.guardar("estado", self.estado())
        self.guardar("estado_detalle", self.estado(self.admin))
        evaluacion = self.buscar("estados", type="assessment")["results"][0]
        self.guardar("abrir", self.docente.post(f"{SEARCH}/open/", {"entity_type": "assessment", "entity_id": evaluacion["entity_id"]}, format="json").json())
        r = self.docente.post(f"{SEARCH}/open/", {"entity_type": "assessment", "entity_id": "no-existe"}, format="json")
        self.assertEqual(r.status_code, 404)
        self.guardar("abrir_no_disponible", r.json())
        r = self.alumno_con_sesion().get(f"{SEARCH}/", {"q": "estados"})
        self.assertEqual(r.status_code, 403)
        self.guardar("error_sin_permiso", r.json())
