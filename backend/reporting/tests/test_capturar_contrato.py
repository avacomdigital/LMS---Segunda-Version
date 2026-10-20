"""
Captura las respuestas REALES de `/api/reportes/` como archivos JSON (y un archivo exportado de verdad) para las pruebas de los clientes de C#
(`tests/Avacom.Lms.Core.Tests/Fixtures/reportes/`). Así un campo mal escrito en un DTO de C# se descubre contra el backend de verdad y no contra lo que alguien creyó que devolvía.

No hace nada en una corrida normal. Para regenerar los archivos:

    set AVACOM_CAPTURAR_CONTRATO=C:\\projects\\prototypes\\prototype-lms-v04\\tests\\Avacom.Lms.Core.Tests\\Fixtures\\reportes
    .venv\\Scripts\\python manage.py test reporting.tests.test_capturar_contrato

Los identificadores y las horas cambian en cada corrida: las pruebas de C# comprueban la FORMA, no esos valores.
"""
from __future__ import annotations

import hashlib
import json
import os
import unittest

from .test_boletin import _ConExamenCalificado
from .test_exportacion import BaseExportacion

CARPETA = os.environ.get("AVACOM_CAPTURAR_CONTRATO", "")


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO no está definida: no se capturan archivos")
class CapturarContratoTests(BaseExportacion):
    def guardar(self, nombre: str, cuerpo) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(cuerpo, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def guardar_bytes(self, nombre: str, contenido: bytes) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, nombre), "wb") as f:
            f.write(contenido)

    def exportar_de_verdad(self, reporte: dict, formato: str, destino: str, **extra):
        r = self.docente.post("/api/reportes/exportaciones/", {"reporte": reporte, "formato": formato, "destino_tipo": destino, **extra}, format="json")
        self.assertEqual(r.status_code, 201, r.content if not getattr(r, "streaming", False) else b"")
        return r, b"".join(r.streaming_content)

    def test_capturar(self):
        # --- una semana de clases en el grupo 8A: clases con y sin entregas, una incompleta, evaluación y estudio ---
        c1 = self.clase_cerrada([(5, 5), (3, 5), None, (5, 5), (0, 5)])
        self.avanzar(minutos=40)
        a, b = self.alumno_nuevo(), self.alumno_nuevo()
        s2 = self.clase()
        pa, pb = self.unir(s2, a[0], a[1]), self.unir(s2, b[0], b[1])
        self.presencia(s2["id"], pa, "reconectando")
        d2 = self.lanzar(s2["id"])
        self.responder(s2["id"], d2, pb)
        self.entregar(s2["id"], d2, pb)
        self.cerrar_actividad(s2["id"], d2)
        self.cerrar_clase(s2["id"])
        self.evaluacion(titulo="Examen de los estados")
        self.estudio(titulo="Leer la lección")
        sid1 = c1["sesion"]["id"]
        ana = c1["alumnos"][0][0]

        # --- leer ---
        self.guardar("clases", self.rp("/clases/", grupo_id=self.grupo["id"]))
        self.guardar("clase", self.reporte_de_clase(sid1))
        self.guardar("clase_incompleta", self.reporte_de_clase(s2["id"]))
        abierta = self.clase()
        self.guardar("error_clase_en_curso", self.rp(f"/clases/{abierta['id']}/", esperado=409))
        self.guardar("grupo", self.rp(f"/grupos/{self.grupo['id']}/"))
        self.guardar("alumnos", self.rp("/alumnos/", grupo_id=self.grupo["id"]))
        self.guardar("alumno", self.rp(f"/alumnos/{ana}/"))
        self.guardar("uso", self.rp("/uso/", cliente=self.admin))
        self.guardar("error_sin_clases_finalizadas", self.rp("/uso/", cliente=self.admin, desde="2020-01-01", hasta="2020-01-02", esperado=409))
        self.guardar("filtros", self.rp("/filtros/"))
        self.guardar("recientes", self.rp("/recientes/"))
        self.guardar("estado", self.rp("/estado/", cliente=self.admin))
        self.guardar("error_reservada", self.rp("/cobertura/", esperado=501))
        _, otro = self.otro_docente()
        self.guardar("error_fuera_de_alcance", self.rp(f"/grupos/{self.grupo['id']}/", cliente=otro, esperado=403))
        self.guardar("error_sin_permiso", self.rp(f"/grupos/{self.grupo['id']}/", cliente=self.tecnico(), esperado=403))
        self.guardar("error_no_encontrado", self.rp("/grupos/no-existe/", esperado=404))

        # --- configuración y mantenimiento ---
        self.guardar("configuracion", self.rp("/configuracion/"))
        self.guardar("configuracion_cambiada", self.rp_put("/configuracion/", {"umbral_privacidad": True}))
        self.guardar("clase_privacidad", self.reporte_de_clase(s2["id"]))                      # dos participantes: menos de cinco, con el umbral activo
        for _ in range(2):                                                                      # el 9B de Prof. Ruiz tiene dos alumnos: BR-086 también recorta el reporte del grupo
            self.alumno_nuevo(grupo_id=self.otro_grupo["id"], cliente=self.admin)
        self.guardar("grupo_privacidad", self.rp(f"/grupos/{self.otro_grupo['id']}/", cliente=otro))
        self.rp_put("/configuracion/", {"umbral_privacidad": False})
        self.guardar("error_configuracion_conflicto", self.rp_put("/configuracion/", {"exigir_razon": True, "version_esperada": 99}, esperado=409))
        self.guardar("actualizar", self.actualizar())
        self.guardar("error_reconstruir_sesion_activa", self.rp_post("/reconstruir/", cliente=self.admin, esperado=409))
        self.cerrar_clase(abierta["id"])
        self.guardar("reconstruir", self.reconstruir())
        self.guardar("error_reconstruir_sin_permiso", self.rp_post("/reconstruir/", cliente=self.docente, esperado=403))

        # --- exportar, en dos tiempos ---
        reporte = {"tipo": "grupo", "grupo_id": self.grupo["id"]}
        self.guardar("exportacion_alcance", self.alcance(reporte))
        r, cuerpo = self.exportar_de_verdad(reporte, "csv", "extraible")
        self.guardar_bytes("exportacion_cuerpo.csv", cuerpo)
        self.guardar("exportacion_encabezados", {k: v for k, v in sorted(r.items()) if k.lower().startswith(("x-avacom-export", "content-"))})
        eid, huella = r["X-Avacom-Export-Id"], r["X-Avacom-Export-Huella"]
        self.assertEqual(hashlib.sha256(cuerpo).hexdigest(), huella)
        self.guardar("confirmacion_fallida", self.confirmar(eid, {"resultado": "fallido", "destino_tipo": "extraible", "motivo": "medio_retirado"}))
        self.guardar("error_huella_distinta", self.confirmar(eid, {"resultado": "guardado", "destino_tipo": "carpeta_local", "huella_verificada": "0" * 64}, esperado=409))
        self.guardar("confirmacion_guardado", self.confirmar(eid, {"resultado": "guardado", "destino_tipo": "carpeta_local", "huella_verificada": huella}))
        self.guardar("exportacion", self.rp(f"/exportaciones/{eid}/"))
        self.guardar("exportaciones", self.rp("/exportaciones/"))
        r2, _ = self.exportar_de_verdad(reporte, "xlsx", "red")
        self.avanzar(minutos=16)
        self.guardar("error_exportacion_caducada", self.confirmar(r2["X-Avacom-Export-Id"], {"resultado": "guardado", "destino_tipo": "red", "huella_verificada": r2["X-Avacom-Export-Huella"]}, esperado=409))
        self.rp_put("/configuracion/", {"extraibles_permitidos": False, "exigir_razon": True})
        self.guardar("error_razon_requerida", self.docente.post("/api/reportes/exportaciones/", {"reporte": reporte, "formato": "xlsx", "destino_tipo": "carpeta_local"}, format="json").json())
        self.guardar("error_destino_no_permitido", self.docente.post("/api/reportes/exportaciones/", {"reporte": reporte, "formato": "xlsx", "destino_tipo": "extraible",
                                                                                                    "razon_codigo": "entrega_a_familias"}, format="json").json())
        self.guardar("exportacion_alcance_con_politica", self.alcance(reporte))


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO no está definida: no se capturan archivos")
class CapturarBoletinTests(_ConExamenCalificado):
    """El boletín académico (un examen calificado con el sistema de Colombia y las recomendaciones del profesor): las respuestas que leen los clientes de C#."""

    def guardar(self, nombre: str, cuerpo) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(cuerpo, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def test_capturar(self):
        self.politica(pais="CO", institucion="IE San José")
        self.gb(f"/estudiantes/{self.estudiante_id}/observacion/", {"grupo_id": self.grupo["id"], "recomendaciones": ["practicar_ejercicios", "pedir_ayuda"], "texto": "Va mejorando."}, metodo="put")
        self.guardar("boletin", self.boletin())
        self.guardar("boletines", self.rp("/boletines/", grupo_id=self.grupo["id"]))
        self.guardar("boletin_alcance", self.alcance({"tipo": "boletin", "alumno_id": self.estudiante_id, "grupo_id": self.grupo["id"]}))
        self.guardar("boletines_alcance", self.alcance({"tipo": "boletin", "grupo_id": self.grupo["id"]}))
        self.guardar("configuracion_boletin", self.admin.put("/api/reportes/configuracion/", {"plantilla_boletin": "mx", "periodos_boletin": ["1.er periodo", "2.º periodo", "3.er periodo"]}, format="json").json())
        self.guardar("recientes_boletin", self.rp("/recientes/"))
