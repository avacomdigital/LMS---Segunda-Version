"""
Base común de las pruebas de MOD-021: el nodo de las pruebas de la evaluación (grupo 8A con su docente, un alumno y el reloj del nodo; grupo 9B sin docente todavía) más
lo propio de la búsqueda: un catálogo de biblioteca de mentira, atajos para sembrar evaluaciones, estudios y clases POR LAS RUTAS REALES (así nacen sus eventos de verdad),
un segundo docente con SU grupo y los demás roles (técnico y reportes).

Nada se simula del índice: se llena con los eventos reales de los módulos propietarios y con su propia reconstrucción.
"""
from __future__ import annotations

from unittest import mock

from rest_framework.test import APIClient

from evaluacion.tests.base import CURSO, BaseEvaluacion

from nodo.pruebas import cola, nodo_limpio
from .. import models as m
from ..infraestructura.contenedor import servicios
from .falsos import CatalogoFalso

SEARCH = "/api/search"
ESTUDIO = "/api/modo-estudio"


class BaseSearch(BaseEvaluacion):
    sincronizar_al_consultar = True

    def setUp(self):
        super().setUp()
        self.catalogo = CatalogoFalso()
        nodo_limpio()                                       # MOD-015: la marca alta del reloj del nodo no viaja de una prueba a otra
        parche = mock.patch("search.infraestructura.contenedor.CatalogoBiblioteca", side_effect=lambda: self.catalogo)
        parche.start()
        self.addCleanup(parche.stop)
        if not self.sincronizar_al_consultar:
            from django.test import override_settings
            sobre = override_settings(AVACOM_SEARCH_SINCRONIZAR=False)
            sobre.enable()
            self.addCleanup(sobre.disable)

    # ------------------------------------------------------------------------------------------- personas
    def crear_usuario(self, rol: str, dni: str, secreto: str, alias: str) -> tuple[str, APIClient]:
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": rol, "alias": alias, "persona": {"nombres": alias, "apellidos": "Prueba"},
            "identificadores": [{"tipo": "DNI", "valor": dni, "es_login": True}], "secreto": secreto, "secreto_definitivo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"], self.sesion(dni, secreto)

    def otro_docente(self) -> tuple[str, APIClient]:
        """Un segundo profesor con SU grupo (9B): no tiene nada que ver con el 8A."""
        docente_id, cliente = self.crear_usuario("TEACHER", "90.444.555", "Docente2.2026!", "Prof. Ruiz")
        r = self.admin.post(f"/api/acceso/grupos/{self.otro_grupo['id']}/miembros/", {"usuario_id": docente_id, "papel": "DOCENTE"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.otro_docente_id = docente_id
        return docente_id, cliente

    def tecnico(self) -> APIClient:
        return self.crear_usuario("TECHNICIAN", "70.111.222", "Tecnico.2026!Aula", "Técnico AVACOM")[1]

    def reportes(self) -> APIClient:
        return self.crear_usuario("REPORTS", "60.222.333", "Reportes.2026!Aula", "Reportes")[1]

    def alumno_con_sesion(self) -> APIClient:
        return self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)

    # ------------------------------------------------------------------------------------------- sembrar
    def evaluacion(self, titulo: str = "Estados de la materia", grupo_id: str | None = None, actor: str | None = None, **extra) -> dict:
        """Una evaluación real (por la ruta de MOD-010): publica `evaluacion.asignada.v1`. El título se puede cambiar para buscarla."""
        return self.crear_asignacion("supervisado", titulo=titulo, grupo_id=grupo_id or self.grupo["id"], actor=actor or self.docente_id, **extra)

    def estudio(self, leccion: str = "l1-three-states", titulo: str | None = None, grupo_id: str | None = None, actor: str | None = None, **extra) -> dict:
        cuerpo = {"alcance": "grupo", "grupo_id": grupo_id or self.grupo["id"], "curso_ref": CURSO, "fuente": "ejemplo", "leccion_ref": leccion,
                  "actor": actor or self.docente_id, "actor_rotulo": "Prof. Gómez", **extra}
        if titulo:
            cuerpo["titulo"] = titulo
        r = self.api.post(f"{ESTUDIO}/docente/asignaciones/", cuerpo, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def clase(self, profesor: str | None = None, leccion: str = "l1-three-states", **extra) -> dict:
        cuerpo = {"via": "leccion", "curso_ref": CURSO, "leccion_ref": leccion, "fuente": "ejemplo", "profesor_id": profesor or self.docente_id,
                  "profesor_rotulo": "Prof. Gómez", "superficie": "pantalla", "grupo_id": self.grupo["id"], **extra}
        r = self.api.post("/api/aula/sesiones/", cuerpo, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def cerrar_clase(self, sesion_id: str) -> dict:
        r = self.api.post(f"/api/aula/sesiones/{sesion_id}/cerrar/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    # ------------------------------------------------------------------------------------------- consultar
    def buscar(self, q: str, cliente: APIClient | None = None, esperado: int = 200, **params) -> dict:
        r = (cliente or self.docente).get(f"{SEARCH}/", {"q": q, **params})
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json() if r.content else {}

    def ids(self, respuesta: dict, tipo: str | None = None) -> list[str]:
        return [r["entity_id"] for r in respuesta["results"] if tipo is None or r["entity_type"] == tipo]

    def titulos(self, respuesta: dict) -> list[str]:
        return [r["title"] for r in respuesta["results"]]

    def sincronizar(self, cliente: APIClient | None = None) -> dict:
        r = (cliente or self.admin).post(f"{SEARCH}/sync/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def reconstruir(self, cliente: APIClient | None = None, esperado: int = 200) -> dict:
        r = (cliente or self.admin).post(f"{SEARCH}/reindex/", {}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def estado(self, cliente: APIClient | None = None, esperado: int = 200) -> dict:
        r = (cliente or self.docente).get(f"{SEARCH}/status/")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def eventos_search(self, *tipos: str) -> list[str]:
        filas = cola("search").order_by("id")
        if tipos:
            filas = filas.filter(tipo_evento__in=tipos)
        return list(filas.values_list("tipo_evento", flat=True))

    def documentos(self, tipo: str | None = None) -> list[m.Documento]:
        filas = m.Documento.objects.order_by("id")
        return list(filas.filter(tipo=tipo) if tipo else filas)

    @staticmethod
    def servicios():
        return servicios()
