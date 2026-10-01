"""
El host de pruebas de la API de Contenido v2 (`tools.host_contenido_v2_pruebas`, que no se toca) con las dos rutas de examen del contrato 2 que sólo usa
MOD-010:

  GET /v2/courses/{id}/exams/{oid}/pool                  → ExamPool: los ajustes del examen y, por pregunta, sus METADATOS
  GET /v2/courses/{id}/exams/{oid}/questions?ids&seed    → ExamQuestions: las preguntas pedidas, sin claves, en el orden pedido y barajadas por `seed`

Todo lo demás —token, 401 con reintento, índice reconstruyéndose, política, paquetes inválidos, la lista de peticiones— lo hace el host de la biblioteca
tal cual; esta clase sólo intercepta esas dos rutas, con las mismas comprobaciones previas que el host aplica a cualquier ruta de un curso.
"""
from __future__ import annotations

from urllib.parse import unquote, urlparse

from tools.host_contenido_v2_pruebas import HostContenidoV2Pruebas, barajar_preguntas, objeto_visible


class HostConExamenes(HostContenidoV2Pruebas):
    def _manejador_api(self):
        host = self
        base = super()._manejador_api()

        class ConExamenes(base):
            def do_GET(self):
                partes = [p for p in unquote(urlparse(self.path).path).split("/") if p]
                if not (len(partes) == 6 and partes[0] == "v2" and partes[1] == "courses" and partes[3] == "exams" and partes[5] in ("pool", "questions")):
                    return super().do_GET()
                camino, consulta, partes = self._entrada()
                if not self._autorizado():
                    return None
                if host.reconstruyendo:
                    return self._error(503, "index_rebuilding", "Index is rebuilding")
                ref = partes[2]
                curso = host.manifiestos.get(ref)
                if ref in host.invalidos:
                    return self._error(500, "package_invalid", "Installed package failed verification: E-PKG-COURSE")
                if curso is None:
                    return self._error(404, "course_not_found", "Course not installed")
                if ref in host.desactivados:
                    return self._error(403, "policy_disabled", "Disabled by school policy")
                hallado = host._objeto(curso, partes[4])
                if hallado is None or hallado[1].get("type") != "exam":
                    return self._error(404, "object_not_found", "Exam not found")
                examen = hallado[1]
                if partes[5] == "pool":
                    return self._json(200, {
                        "courseId": ref, "version": curso.get("version"), "objectId": examen.get("id"), "settings": examen.get("settings") or {},
                        "questions": [{"questionId": q.get("id"), "type": q.get("type"), "topicRef": q.get("topicRef"),
                                       "difficulty": q.get("difficulty"), "estimatedSec": q.get("estimatedSec"), "points": q.get("points")}
                                      for q in examen.get("questions") or []]})
                ids = [i for i in str(consulta.get("ids") or "").split(",") if i]
                if not ids:
                    return self._error(400, "invalid_parameter", "ids is required")
                por_id = {str(q.get("id")): q for q in examen.get("questions") or []}
                if any(i not in por_id for i in ids):
                    return self._error(404, "question_not_found", "Question not found")
                visibles = objeto_visible({**examen, "questions": [por_id[i] for i in ids]}, perfil="student")["questions"]
                barajar_preguntas(visibles, consulta.get("seed"))
                return self._json(200, {"courseId": ref, "version": curso.get("version"), "objectId": examen.get("id"),
                                        "title": examen.get("title"), "instructions": examen.get("instructions"), "questions": visibles})

        return ConExamenes
