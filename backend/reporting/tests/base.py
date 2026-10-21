"""
Base común de las pruebas de MOD-013: el nodo de las pruebas de la evaluación (grupo 8A con su docente y un alumno, Juan; grupo 9B sin docente todavía; el reloj del nodo que la prueba mueve
a voluntad; la biblioteca de ejemplo con el calificador de referencia) más lo propio de los reportes: un árbol académico de mentira, los demás roles (técnico, reportes, otro docente),
alumnos de sobra y atajos para sembrar UNA CLASE COMPLETA por las rutas reales del aula (así nacen sus eventos de verdad).

Nada se simula de lo que Reporting lee: las clases, los intentos y las notas son los de MOD-007/010/011 por HTTP, con sus reglas. Lo único falso es el árbol de la biblioteca (para
probar el filtro por nodo académico sin AVACOM Contenido abierta).
"""
from __future__ import annotations

from unittest import mock

from rest_framework.test import APIClient

from evaluacion.tests.base import CURSO, BaseEvaluacion, respuesta_correcta, respuesta_incorrecta

from nodo.pruebas import cola, nodo_limpio
from .. import models as m

R = "/api/reportes"
AULA = "/api/aula"
LECCION = "l1-three-states"
ACTIVIDAD = "l1-activity"
PREGUNTAS = ["l1-act-q1", "l1-act-q2", "l1-act-q3", "l1-act-q4", "l1-act-q5"]      # las cinco que se califican solas (la sexta es abierta)


class ArbolFalso:
    """El árbol de la biblioteca de mentira: `cursos_del_arbol` devuelve lo que la prueba diga (None = biblioteca cerrada)."""

    def __init__(self):
        self.disponible = True
        self.cursos: dict[tuple, set[str]] = {}

    def arbol(self):
        return (True, "", [{"kind": "country", "code": "CO", "name": "Colombia", "count": 1, "children": []}]) if self.disponible else (False, "AVACOM Biblioteca está cerrada.", [])

    def cursos_del_arbol(self, arbol: dict[str, str]):
        if not self.disponible:
            return None
        return self.cursos.get(tuple(sorted(arbol.items())), set())


class BaseReporting(BaseEvaluacion):
    sincronizar_al_consultar = True

    def setUp(self):
        super().setUp()
        self.arbol = ArbolFalso()
        nodo_limpio()                                       # MOD-015: la marca alta del reloj del nodo no viaja de una prueba a otra
        parche = mock.patch("reporting.infraestructura.unidad_trabajo.ArbolBiblioteca", side_effect=lambda: self.arbol)
        parche.start()
        self.addCleanup(parche.stop)
        # UN solo reloj del nodo: BaseEvaluacion mueve el de la evaluación (y con él el de los reportes); aquí se unen el del aula y el del modo estudio, que tienen el suyo.
        for clase_de_reloj in ("classroom_engine.infraestructura.contenedor.RelojNodo", "modo_estudio.infraestructura.contenedor.RelojNodo"):
            reloj = mock.patch(f"{clase_de_reloj}.ahora_ms", side_effect=lambda: self.t)
            reloj.start()
            self.addCleanup(reloj.stop)
        if not self.sincronizar_al_consultar:
            from django.test import override_settings
            sobre = override_settings(AVACOM_REPORTES_SINCRONIZAR=False)
            sobre.enable()
            self.addCleanup(sobre.disable)
        self._n_alumnos = 0

    # ------------------------------------------------------------------------------------------------------------------- personas
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

    def otro_docente(self) -> tuple[str, APIClient]:
        """Un segundo profesor con SU grupo (9B): no tiene nada que ver con el 8A."""
        docente_id, cliente = self.crear_usuario("TEACHER", "90.444.555", "Docente2.2026!", "Prof. Ruiz")
        r = self.admin.post(f"/api/acceso/grupos/{self.otro_grupo['id']}/miembros/", {"usuario_id": docente_id, "papel": "DOCENTE"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.otro_docente_id = docente_id
        return docente_id, cliente

    def alumno_nuevo(self, alias: str | None = None, grupo_id: str | None = None, cliente: APIClient | None = None) -> tuple[str, str]:
        """Un alumno más del grupo (por defecto, 8A, dado de alta por su profesor; con `cliente`, por quien se diga). Devuelve `(id, alias)`."""
        self._n_alumnos += 1
        alias = alias or f"Alumno {self._n_alumnos:02d}"
        r = (cliente or self.docente).post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": alias, "persona": {"nombres": alias, "apellidos": "Prueba"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": f"9{self._n_alumnos:05d}", "es_login": True}], "secreto": f"{500000 + self._n_alumnos}",
            "secreto_definitivo": True, "grupo_id": grupo_id or self.grupo["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"], alias

    def alumnos(self, n: int) -> list[tuple[str, str]]:
        return [self.alumno_nuevo() for _ in range(n)]

    # ---------------------------------------------------------------------------------------------------------------------- una clase
    def clase(self, profesor: str | None = None, grupo_id: str | None = "", **extra) -> dict:
        cuerpo = {"via": "leccion", "curso_ref": CURSO, "leccion_ref": LECCION, "fuente": "ejemplo", "profesor_id": profesor or self.docente_id, "profesor_rotulo": "Prof. Gómez",
                  "superficie": "pantalla", **extra}
        if grupo_id != "":
            cuerpo["grupo_id"] = grupo_id
        elif "grupo_id" not in extra:
            cuerpo["grupo_id"] = self.grupo["id"]
        r = self.api.post(f"{AULA}/sesiones/", cuerpo, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def unir(self, sesion: dict, persona_id: str, rotulo: str = "", dispositivo: str | None = None) -> str:
        """El alumno se une a la clase con su tableta. Devuelve el `participante_id`."""
        r = self.api.post(f"{AULA}/sesiones/unirse/", {"codigo_union": sesion["codigo_union"], "persona_id": persona_id, "persona_rotulo": rotulo or persona_id,
                                                         "dispositivo": dispositivo or f"hw-{persona_id[:8]}"}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
        return r.json()["participante"]["id"]

    def lanzar(self, sesion_id: str, **extra) -> dict:
        r = self.api.post(f"{AULA}/sesiones/{sesion_id}/distribuciones/", {"clase": "actividad", "objeto_ref": ACTIVIDAD, "intentos_permitidos": 2, **extra}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def responder(self, sesion_id: str, d: dict, participante_id: str, aciertos: int = 5, total: int = 5, esperado: int = 200) -> dict:
        """El alumno contesta `total` de las cinco preguntas que se califican solas, `aciertos` de ellas bien."""
        respuestas = [{"pregunta_ref": ref, "secuencia": 1, "respuesta": (respuesta_correcta(ref) if i < aciertos else respuesta_incorrecta(ref))} for i, ref in enumerate(PREGUNTAS[:total])]
        r = self.api.post(f"{AULA}/sesiones/{sesion_id}/distribuciones/{d['id']}/respuestas/", {"participante_id": participante_id, "respuestas": respuestas}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def entregar(self, sesion_id: str, d: dict, participante_id: str, esperado: int = 200, origen: str = "directo") -> dict:
        """Entregar el intento: en el aula es una petición de respuestas con `entregar: true` (`origen: cola` cuando sale de la cola de la tableta)."""
        r = self.api.post(f"{AULA}/sesiones/{sesion_id}/distribuciones/{d['id']}/respuestas/", {"participante_id": participante_id, "respuestas": [], "entregar": True, "origen": origen}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def cerrar_clase(self, sesion_id: str) -> dict:
        r = self.api.post(f"{AULA}/sesiones/{sesion_id}/cerrar/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def cerrar_actividad(self, sesion_id: str, d: dict) -> dict:
        r = self.api.post(f"{AULA}/sesiones/{sesion_id}/distribuciones/{d['id']}/cerrar/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def presencia(self, sesion_id: str, participante_id: str, estado: str) -> dict:
        r = self.api.post(f"{AULA}/sesiones/{sesion_id}/participantes/{participante_id}/presencia/", {"estado": estado}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def clase_cerrada(self, notas: list[tuple[int, int] | None], profesor: str | None = None, grupo_id: str | None = "", cerrar: bool = True) -> dict:
        """Una clase COMPLETA: se unen tantos alumnos como `notas` (los que haga falta se crean), se lanza una actividad de cinco preguntas y cada alumno entrega `(aciertos, total)`
        —o `None` si no contesta nada—; al final se cierra (con `cerrar=False` queda abierta). Devuelve `{sesion, distribucion, alumnos: [(id, alias, participante_id)], participantes}`."""
        existentes = list(m_alumnos_del_grupo(self))
        while len(existentes) < len(notas):
            existentes.append(self.alumno_nuevo())
        existentes.sort(key=lambda x: (x[1], x[0]))             # siempre en el mismo orden: «los n primeros» son los mismos en cada clase
        s = self.clase(profesor=profesor, grupo_id=grupo_id)
        unidos = []
        for (alumno_id, alias) in existentes[:len(notas)]:
            unidos.append((alumno_id, alias, self.unir(s, alumno_id, alias)))
        d = self.lanzar(s["id"])
        for (alumno_id, alias, pid), nota in zip(unidos, notas):
            if nota is None:
                continue
            self.responder(s["id"], d, pid, aciertos=nota[0], total=nota[1])
            self.entregar(s["id"], d, pid)
        if cerrar:
            self.avanzar(seg=30)
            self.cerrar_actividad(s["id"], d)
            self.cerrar_clase(s["id"])
        return {"sesion": s, "distribucion": d, "alumnos": unidos}

    # ------------------------------------------------------------------------------------------------------- evaluaciones y estudio reales
    def evaluacion(self, titulo: str = "Estados de la materia", grupo_id: str | None = None, actor: str | None = None, **extra) -> dict:
        """Una evaluación real (por la ruta de MOD-010): publica `evaluacion.asignada.v1`."""
        return self.crear_asignacion("supervisado", titulo=titulo, grupo_id=grupo_id or self.grupo["id"], actor=actor or self.docente_id, **extra)

    def estudio(self, leccion: str = LECCION, titulo: str | None = None, grupo_id: str | None = None, actor: str | None = None, **extra) -> dict:
        """Un estudio asignado real (por la ruta de MOD-008): publica `estudio.asignacion.creada.v1`."""
        cuerpo = {"alcance": "grupo", "grupo_id": grupo_id or self.grupo["id"], "curso_ref": CURSO, "fuente": "ejemplo", "leccion_ref": leccion,
                  "actor": actor or self.docente_id, "actor_rotulo": "Prof. Gómez", **extra}
        if titulo:
            cuerpo["titulo"] = titulo
        r = self.api.post("/api/modo-estudio/docente/asignaciones/", cuerpo, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    # --------------------------------------------------------------------------------------------------------------------- los reportes
    def rp(self, ruta: str, cliente: APIClient | None = None, esperado: int = 200, **params) -> dict:
        r = (cliente or self.docente).get(f"{R}{ruta}", params)
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json() if r.content else {}

    def rp_post(self, ruta: str, cuerpo: dict | None = None, cliente: APIClient | None = None, esperado: int = 200) -> dict:
        r = (cliente or self.docente).post(f"{R}{ruta}", cuerpo or {}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json() if r.content and r.get("Content-Type", "").startswith("application/json") else {}

    def rp_put(self, ruta: str, cuerpo: dict, cliente: APIClient | None = None, esperado: int = 200) -> dict:
        r = (cliente or self.admin).put(f"{R}{ruta}", cuerpo, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json() if r.content else {}

    def reporte_de_clase(self, sesion_id: str, cliente: APIClient | None = None, esperado: int = 200) -> dict:
        return self.rp(f"/clases/{sesion_id}/", cliente=cliente, esperado=esperado)

    def reconstruir(self, cliente: APIClient | None = None, esperado: int = 200) -> dict:
        return self.rp_post("/reconstruir/", {}, cliente=cliente or self.admin, esperado=esperado)

    def actualizar(self, cliente: APIClient | None = None, esperado: int = 200) -> dict:
        return self.rp_post("/actualizar/", {}, cliente=cliente or self.admin, esperado=esperado)

    def eventos_rp(self, *tipos: str) -> list[str]:
        filas = cola("reporting").order_by("id")
        if tipos:
            filas = filas.filter(tipo_evento__in=tipos)
        return list(filas.values_list("tipo_evento", flat=True))

    def asientos(self, accion: str):
        from audit.models import Bitacora
        return list(Bitacora.objects.filter(accion=accion).order_by("secuencia"))


def m_alumnos_del_grupo(prueba: BaseReporting):
    """Los alumnos que ya tiene el grupo 8A (Juan y los que se crearon), como `(id, alias)`, en un orden fijo."""
    from acceso.models import MiembroGrupo
    filas = MiembroGrupo.objects.filter(grupo_id=prueba.grupo["id"], papel="ESTUDIANTE", hasta__isnull=True).select_related("usuario").order_by("usuario__alias", "usuario_id")
    return [(f.usuario_id, f.usuario.alias) for f in filas]
