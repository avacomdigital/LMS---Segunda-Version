"""
Base común de las pruebas de MOD-011: el nodo de las pruebas de la evaluación (grupo 8A con un docente y un alumno, Juan; el examen de ejemplo de banco fijo
—las doce preguntas, de los seis tipos, dos de ellas abiertas—; el reloj del nodo que la prueba mueve a voluntad) más lo propio del libro: el nivel del grupo, un
administrador que adopta una escala y activa el modo calificaciones, y atajos para llevar un examen real hasta `calificado` o `en_revision_docente`.

Nada se simula del libro: los intentos son los de MOD-010 (por HTTP, con sus reglas) y las calificaciones nacen del consumidor de sus eventos. La fuente
«ejemplo» sirve el examen y la rúbrica; la calificación de las cerradas la hace el calificador de referencia de la biblioteca (`FuenteQueCalifica`).
"""
from __future__ import annotations

from rest_framework.test import APIClient

from evaluacion.tests.base import BaseEvaluacion, respuesta_correcta, respuesta_incorrecta

from nodo.pruebas import cola, nodo_limpio
from .. import models as m

GB = "/api/gradebook"


class BaseGradebook(BaseEvaluacion):
    nivel = "secundaria"
    plantilla = "gen-0-100"
    activar_modo = True               # las pruebas del modo simple lo apagan

    def setUp(self):
        super().setUp()
        contexto = self.examen_de_banco_fijo()
        nodo_limpio()                                       # MOD-015: la marca alta del reloj del nodo no viaja de una prueba a otra
        contexto.__enter__()
        self.addCleanup(contexto.__exit__, None, None, None)
        self.poner_nivel(self.grupo["id"], self.nivel)
        if self.activar_modo:
            self.escala = self.activar_calificaciones(self.nivel, self.plantilla)

    # ------------------------------------------------------------------------------------------- configuración
    def poner_nivel(self, grupo_id: str, nivel: str) -> None:
        r = self.admin.patch(f"/api/acceso/grupos/{grupo_id}/", {"nivel_clave": nivel}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def adoptar(self, plantilla: str, esperado: int = 201, **extra) -> dict:
        r = self.admin.post(f"{GB}/escalas/adoptar/", {"plantilla": plantilla, **extra}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def activar_calificaciones(self, nivel: str = "secundaria", plantilla: str = "gen-0-100", **extra) -> dict:
        """El administrador adopta la plantilla y activa el modo calificaciones del nivel con ella. Devuelve la escala."""
        escala = self.adoptar(plantilla, **extra)
        r = self.admin.put(f"{GB}/niveles/{nivel}/", {"modo": "calificaciones", "escala_id": escala["id"]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        return escala

    # ----------------------------------------------------------------------------------------------- personas
    def crear_usuario(self, rol: str, dni: str, secreto: str, alias: str) -> tuple[str, APIClient]:
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": rol, "alias": alias, "persona": {"nombres": alias, "apellidos": "Prueba"},
            "identificadores": [{"tipo": "DNI", "valor": dni, "es_login": True}], "secreto": secreto, "secreto_definitivo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"], self.sesion(dni, secreto)

    def tecnico(self) -> APIClient:
        self.tecnico_id, cliente = self.crear_usuario("TECHNICIAN", "70.111.222", "Tecnico.2026!Aula", "Técnico AVACOM")
        return cliente

    def reportes(self) -> APIClient:
        self.reportes_id, cliente = self.crear_usuario("REPORTS", "60.222.333", "Reportes.2026!Aula", "Reportes")
        return cliente

    def segundo_docente(self) -> APIClient:
        """Otro profesor del MISMO grupo 8A (dos personas pueden editar a la vez la misma calificación)."""
        docente_id, cliente = self.crear_usuario("TEACHER", "91.555.666", "Docente3.2026!", "Prof. Mora")
        r = self.admin.post(f"/api/acceso/grupos/{self.grupo['id']}/miembros/", {"usuario_id": docente_id, "papel": "DOCENTE"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return cliente

    def otro_docente(self) -> tuple[str, APIClient, dict]:
        """Un segundo profesor con SU grupo (9B de nivel secundaria): no tiene nada que ver con el 8A."""
        docente_id, cliente = self.crear_usuario("TEACHER", "90.444.555", "Docente2.2026!", "Prof. Ruiz")
        r = self.admin.post(f"/api/acceso/grupos/{self.otro_grupo['id']}/miembros/", {"usuario_id": docente_id, "papel": "DOCENTE"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.poner_nivel(self.otro_grupo["id"], self.nivel)
        return docente_id, cliente, self.otro_grupo

    # ------------------------------------------------------------------------------------------- un examen real
    def examen_entregado(self, *, bien: bool = True, abiertas: bool = True, hw: str | None = None, alumno_id: str | None = None, asignacion: dict | None = None,
                         **extra) -> tuple[dict, str, list[str], dict]:
        """Juan (o el alumno que se diga) presenta el examen completo y lo entrega. Con `abiertas` las dos preguntas abiertas quedan respondidas y el intento pasa
        a `en_revision_docente`; sin ellas, el intento queda `calificado` solo. Devuelve (asignación, intento_id, referencias, tipos)."""
        a = asignacion or self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, **extra)
        apertura = self.abrir(a["id"], hw=hw, alumno_id=alumno_id)
        intento_id = apertura["intento"]["id"]
        tipos = self.fila(intento_id).armado_meta["tipos"]
        f = respuesta_correcta if bien else respuesta_incorrecta
        refs = [r for r in tipos if abiertas or tipos[r] != "open"]
        self.responder(intento_id, [self.r(ref, n + 1, f(ref)) for n, ref in enumerate(refs)], hw=hw, alumno_id=alumno_id)
        self.entregar(intento_id, hw=hw, alumno_id=alumno_id, confirmar=True)
        return a, intento_id, refs, tipos

    def puntos_de(self, intento_id: str) -> dict:
        return self.fila(intento_id).armado_meta["puntos"]

    def revisar_todo(self, intento_id: str, cliente: APIClient | None = None, fraccion: float = 1.0) -> dict:
        """Puntúa a mano las preguntas abiertas pendientes (la `fraccion` de su valor) y confirma la revisión. Devuelve lo que responde la confirmación."""
        cliente = cliente or self.docente
        pendientes = self.pendientes(intento_id)
        puntos = self.puntos_de(intento_id)
        for ref in pendientes:
            r = cliente.post(f"{GB}/revisiones/{intento_id}/respuestas/{ref}/", {"puntaje": puntos[ref] * fraccion, "comentario": "Bien argumentado"}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        return self.gb(f"/revisiones/{intento_id}/confirmar/", {}, cliente=cliente)

    def pendientes(self, intento_id: str) -> list[str]:
        tipos = self.fila(intento_id).armado_meta["tipos"]
        return [ref for ref in self.fila(intento_id).armado if tipos[ref] == "open"]

    # ---------------------------------------------------------------------------------------------- el libro
    def gb(self, ruta: str, cuerpo: dict | None = None, esperado: int = 200, cliente: APIClient | None = None, metodo: str = "post", **params) -> dict:
        cliente = cliente or self.docente
        if metodo == "get":
            r = cliente.get(f"{GB}{ruta}", params)
        else:
            r = getattr(cliente, metodo)(f"{GB}{ruta}", cuerpo or {}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json() if r.content else {}

    def leer(self, ruta: str, esperado: int = 200, cliente: APIClient | None = None, **params) -> dict:
        return self.gb(ruta, esperado=esperado, cliente=cliente, metodo="get", **params)

    def libro(self, cliente: APIClient | None = None, **params) -> dict:
        return self.leer("/libro/", cliente=cliente, grupo_id=params.pop("grupo_id", self.grupo["id"]), **params)

    def sincronizar(self) -> dict:
        return self.gb("/sincronizar/", {})

    def calificacion(self, intento_id: str) -> dict:
        """La calificación de ese intento (poniendo el libro al día antes)."""
        self.sincronizar()
        fila = m.Calificacion.objects.filter(intento_id=intento_id).first()
        self.assertIsNotNone(fila, "el libro no registró la calificación de ese intento")
        return self.leer(f"/calificaciones/{fila.id}/")["calificacion"]

    def fila_cal(self, intento_id: str) -> m.Calificacion:
        return m.Calificacion.objects.get(intento_id=intento_id)

    def ajustar(self, cal: dict, nuevo, motivo: str = "Se reconoció una respuesta correcta que la rúbrica inicial no contemplaba", esperado: int = 200, **extra) -> dict:
        cliente = extra.pop("cliente", None)
        return self.gb(f"/calificaciones/{cal['id']}/ajustar/", {"puntaje_nuevo": nuevo, "motivo": motivo, "version_esperada": cal["version"], **extra}, esperado=esperado,
                       cliente=cliente)

    def eventos_gb(self, *tipos: str) -> list[str]:
        filas = cola("gradebook").order_by("id")
        if tipos:
            filas = filas.filter(tipo_evento__in=tipos)
        return list(filas.values_list("tipo_evento", flat=True))
