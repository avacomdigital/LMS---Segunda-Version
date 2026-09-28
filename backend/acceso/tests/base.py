"""
Base de las pruebas de API del módulo de acceso: instala el nodo, crea un grupo,
un docente y un estudiante, y deja tokens listos. Argon2 con coste bajo para
que la suite sea rápida (la política de producción está en settings).
"""
from __future__ import annotations

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

ARGON2_RAPIDO = {"time_cost": 1, "memory_cost": 8192, "parallelism": 1}


@override_settings(AVACOM_LMS_ARGON2=ARGON2_RAPIDO)
class BaseAcceso(TestCase):
    ADMIN_DNI = "1042888795"
    ADMIN_PASS = "Rectoria.2026!"
    DOCENTE_DNI = "80.123.456"
    DOCENTE_PASS = "Docente.2026!"
    ESTUDIANTE_CODIGO = "122499"
    ESTUDIANTE_PIN = "691302"
    TABLETA = "tableta-07-hw-id"

    def setUp(self):
        self.api = APIClient()
        r = self.api.post("/api/acceso/instalacion/", {
            "organizacion": {"codigo": "IE-SANJOSE", "nombre": "IE San José", "pais": "CO", "idioma": "es", "locale": "es-CO"},
            "administrador": {"alias": "Rectoría", "nombres": "Ana", "apellidos": "Pérez", "dni": self.ADMIN_DNI,
                              "password": self.ADMIN_PASS},
        }, format="json")
        assert r.status_code == 201, r.content
        self.admin_id = r.json()["administrador"]["id"]
        self.admin = self.sesion(self.ADMIN_DNI, self.ADMIN_PASS)

        self.grupo = self.admin.post("/api/acceso/grupos/", {"codigo": "8A", "nombre": "Octavo A", "periodo": "2026"},
                                     format="json").json()
        self.otro_grupo = self.admin.post("/api/acceso/grupos/", {"codigo": "9B", "nombre": "Noveno B", "periodo": "2026"},
                                          format="json").json()

        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "TEACHER", "alias": "Prof. Gómez",
            "persona": {"nombres": "Luis", "apellidos": "Gómez"},
            "identificadores": [{"tipo": "DNI", "valor": self.DOCENTE_DNI, "es_login": True}],
            "secreto": self.DOCENTE_PASS, "secreto_definitivo": True,
        }, format="json")
        assert r.status_code == 201, r.content
        self.docente_id = r.json()["id"]
        r = self.admin.post(f"/api/acceso/grupos/{self.grupo['id']}/miembros/",
                            {"usuario_id": self.docente_id, "papel": "DOCENTE"}, format="json")
        assert r.status_code == 201, r.content
        self.docente = self.sesion(self.DOCENTE_DNI, self.DOCENTE_PASS)

        r = self.docente.post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": "Juan P.",
            "persona": {"nombres": "Juan", "apellidos": "Pérez", "fecha_nacimiento": "2012-04-09"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": self.ESTUDIANTE_CODIGO, "es_login": True},
                                {"tipo": "DNI", "valor": "1.020.334.556", "es_login": False}],
            "secreto": self.ESTUDIANTE_PIN, "secreto_definitivo": True, "grupo_id": self.grupo["id"],
        }, format="json")
        assert r.status_code == 201, r.content
        self.estudiante_id = r.json()["id"]

        r = self.api.post("/api/dispositivos/", {"identificador": self.TABLETA, "nombre": "tableta-07"}, format="json")
        assert r.status_code == 201, r.content
        self.tableta = r.json()

    # ------------------------------------------------------------- utilidades
    def login(self, identificador: str, secreto: str, dispositivo: str | None = None, rol: str | None = None):
        return self.api.post("/api/acceso/sesiones/", {"identificador": identificador, "secreto": secreto,
                                                        "dispositivo": dispositivo or "", "rol": rol or ""}, format="json")

    def sesion(self, identificador: str, secreto: str, dispositivo: str | None = None) -> APIClient:
        r = self.login(identificador, secreto, dispositivo)
        assert r.status_code == 200, r.content
        return self.con_token(r.json()["token"])

    @staticmethod
    def con_token(token: str) -> APIClient:
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        cliente.token = token
        return cliente
