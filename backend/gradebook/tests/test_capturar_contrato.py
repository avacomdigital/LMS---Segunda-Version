"""
Captura las respuestas REALES de `/api/gradebook/` como archivos JSON para las pruebas de los clientes de C# (`tests/Avacom.Lms.Core.Tests/Fixtures/gradebook/`). Así un campo
mal escrito en un DTO de C# se descubre contra el backend de verdad y no contra lo que alguien creyó que devolvía.

No hace nada en una corrida normal. Para regenerar los archivos:

    set AVACOM_CAPTURAR_CONTRATO=C:\\projects\\prototypes\\prototype-lms-v04\\tests\\Avacom.Lms.Core.Tests\\Fixtures\\gradebook
    .venv\\Scripts\\python manage.py test gradebook.tests.test_capturar_contrato

Los identificadores y las horas cambian en cada corrida: las pruebas de C# comprueban la FORMA, no esos valores.
"""
from __future__ import annotations

import json
import os
import unittest

from .base import BaseGradebook

CARPETA = os.environ.get("AVACOM_CAPTURAR_CONTRATO", "")


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO no está definida: no se capturan archivos")
class CapturarContratoTests(BaseGradebook):
    activar_modo = False

    def guardar(self, nombre: str, cuerpo) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(cuerpo, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def test_capturar(self):
        # ---- la administración: plantillas, adopción, modo por nivel y política
        self.guardar("plantillas", self.leer("/escalas/plantillas/", cliente=self.admin))
        self.guardar("configuracion_inicial", self.leer("/configuracion/", cliente=self.admin))
        co = self.gb("/escalas/adoptar/", {"plantilla": "co-1-5", "jurisdiccion": "Antioquia"}, cliente=self.admin, esperado=201)
        self.guardar("escala", co)
        self.guardar("escalas", self.leer("/escalas/", cliente=self.admin))
        self.guardar("vista_previa", self.gb("/escalas/vista-previa/", {"escala_version_id": co["versiones"][0]["id"], "valores": [0, 49.99, 50, 75, 90, 100]}))
        self.guardar("escala_invalida", self.gb("/escalas/vista-previa/", {"definicion": {"tipo": "alfabetica", "conversion": "tramos", "decimales": 0, "redondeo": "mitad_arriba",
                     "tramos": [{"orden": 1, "clave": "F", "etiqueta": "F", "desde": "0", "hasta": "60"}, {"orden": 2, "clave": "A", "etiqueta": "A", "desde": "65", "hasta": "100"}]}},
                     esperado=400))
        self.guardar("nivel_validado", self.gb("/niveles/secundaria/", {"modo": "calificaciones", "escala_id": co["id"], "validar": True}, metodo="put", cliente=self.admin))
        self.guardar("nivel_cambiado", self.gb("/niveles/secundaria/", {"modo": "calificaciones", "escala_id": co["id"]}, metodo="put", cliente=self.admin))
        self.guardar("politica", self.gb("/politica/", {"pais": "CO", "jurisdiccion": "Antioquia", "institucion": "IE San José", "politica_intentos": "ultimo"}, metodo="put", cliente=self.admin))
        self.guardar("configuracion", self.leer("/configuracion/", cliente=self.admin))
        self.guardar("politica_mejor", self.gb("/politica/", {"politica_intentos": "mejor"}, metodo="put", cliente=self.admin))
        self.guardar("politica_repetida", self.gb("/politica/", {"politica_intentos": "mejor"}, metodo="put", cliente=self.admin))
        self.gb("/politica/", {"politica_intentos": "ultimo"}, metodo="put", cliente=self.admin)         # vuelve a la de antes: el resto de la captura cuenta con ella

        # ---- un examen con revisión pendiente: la bandeja, el detalle, la rúbrica y la confirmación
        a, i, refs, tipos = self.examen_entregado(abiertas=True)
        abiertas = self.pendientes(i)
        puntos = self.puntos_de(i)
        self.guardar("libro_con_revision", self.libro())
        self.guardar("libro_por_materia", self.libro(subject="science"))                                     # segmentado por materia (lo aplica el nodo)
        self.guardar("libro_sin_materia", self.libro(subject="math"))
        self.guardar("registrar_con_pendientes", self.gb(f"/asignaciones/{a['id']}/registrar/", {}))        # en revisión docente: no se puede registrar todavía, y se dice por qué
        self.guardar("bandeja", self.leer("/revisiones/", grupo_id=self.grupo["id"]))
        detalle = self.leer(f"/revisiones/{i}/")
        self.guardar("revision", detalle)
        criterios = [{"criterio_id": c["id"], "puntos": c["puntos_max"]} for c in next(f for f in detalle["filas"] if f["pregunta_ref"] == abiertas[1])["rubrica"]["criterios"]]
        self.guardar("revision_manual", self.gb(f"/revisiones/{i}/respuestas/{abiertas[0]}/", {"puntaje": puntos[abiertas[0]] - 1, "comentario": "Explica el cambio de estado.", "solicitud_id": "cap-1"}))
        self.guardar("revision_rubrica", self.gb(f"/revisiones/{i}/respuestas/{abiertas[1]}/", {"criterios": criterios, "comentario": "Cumple todos los criterios."}))
        self.guardar("revision_conflicto", self.gb(f"/revisiones/{i}/respuestas/{abiertas[0]}/", {"criterios": criterios}, esperado=400))
        confirmada = self.gb(f"/revisiones/{i}/confirmar/", {})
        self.guardar("revision_confirmada", confirmada)
        cal = confirmada["calificacion"]

        # ---- el libro, el detalle, el ajuste, el historial y la concurrencia
        self.guardar("libro", self.libro())
        self.guardar("calificacion", self.leer(f"/calificaciones/{cal['id']}/"))
        ajuste = self.ajustar(cal, 85, motivo="Se reconoció una respuesta correcta que la rúbrica inicial no contemplaba", solicitud_id="cap-aj-1")
        self.guardar("ajuste", ajuste)
        self.guardar("ajuste_conflicto", self.ajustar(cal, 60, esperado=409))
        self.guardar("ajuste_invalido", self.ajustar(ajuste["calificacion"], 150, esperado=400))
        cal = ajuste["calificacion"]
        self.guardar("valoracion", self.gb(f"/calificaciones/{cal['id']}/valoracion/", {"tramo": "alto", "motivo": "Su proceso fue superior al de la prueba", "version_esperada": cal["version"]}))
        cal = self.leer(f"/calificaciones/{cal['id']}/")["calificacion"]
        self.guardar("retroalimentacion", self.gb(f"/calificaciones/{cal['id']}/retroalimentacion/", {
            "fortalezas": "Razona bien los cambios de estado.", "dificultades": "Se confunde al ordenar procesos.", "oportunidades": "Practicar con diagramas.",
            "adaptacion": "Tiempo adicional del 25 %", "version_esperada": cal["version"]}))
        cal = self.leer(f"/calificaciones/{cal['id']}/")["calificacion"]

        # ---- el alumno antes y después de publicar
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.guardar("mias_sin_publicar", self.leer("/mias/", cliente=alumno))
        self.guardar("publicada", self.gb(f"/calificaciones/{cal['id']}/publicar/", {"version_esperada": cal["version"]}))
        self.guardar("mias_publicada", self.leer("/mias/", cliente=alumno))
        self.guardar("publicar_sin_permiso", self.gb(f"/calificaciones/{cal['id']}/publicar/", {}, cliente=alumno, esperado=403))
        pub = self.leer(f"/calificaciones/{cal['id']}/")["calificacion"]
        self.guardar("retirada", self.gb(f"/calificaciones/{cal['id']}/retirar-publicacion/", {"motivo": "Se publicó antes de revisar el acta", "version_esperada": pub["version"]}))
        pub = self.leer(f"/calificaciones/{cal['id']}/")["calificacion"]
        self.guardar("reabierta", self.gb(f"/calificaciones/{cal['id']}/reabrir/", {"motivo": "El estudiante pidió revisar su argumento", "version_esperada": pub["version"]}))
        self.guardar("bandeja_reabierta", self.leer("/revisiones/", grupo_id=self.grupo["id"]))

        # ---- un segundo examen automático: publicación por asignación, resumen, historial e intentos
        a2, i2, _, _ = self.examen_entregado(abiertas=False, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        self.sincronizar()
        self.guardar("publicar_asignacion", self.gb(f"/asignaciones/{a2['id']}/publicar/", {}))
        self.guardar("registrar_ya_registrada", self.gb(f"/asignaciones/{a2['id']}/registrar/", {}))
        self.guardar("asignacion", self.leer(f"/asignaciones/{a2['id']}/"))
        self.guardar("clasificacion", self.gb(f"/asignaciones/{a2['id']}/clasificacion/", {"tipo_evaluacion": "formativa", "objetivos": ["obj-1"]}, metodo="put"))
        self.guardar("resumen", self.leer("/resumen/", grupo_id=self.grupo["id"]))
        self.guardar("estudiante", self.leer(f"/estudiantes/{self.estudiante_id}/"))
        # las recomendaciones del profesor (la cuarta pregunta del boletín): crear, repetir sin cambios y lo que no vale
        self.guardar("observacion", self.gb(f"/estudiantes/{self.estudiante_id}/observacion/", {"grupo_id": self.grupo["id"], "recomendaciones": ["practicar_ejercicios", "pedir_ayuda"], "texto": "Va mejorando."}, metodo="put"))
        self.guardar("observacion_repetida", self.gb(f"/estudiantes/{self.estudiante_id}/observacion/", {"grupo_id": self.grupo["id"], "recomendaciones": ["practicar_ejercicios", "pedir_ayuda"], "texto": "Va mejorando."}, metodo="put"))
        self.guardar("observacion_invalida", self.gb(f"/estudiantes/{self.estudiante_id}/observacion/", {"grupo_id": self.grupo["id"], "recomendaciones": ["inventada"]}, metodo="put", esperado=400))
        self.guardar("boletin", self.leer(f"/estudiantes/{self.estudiante_id}/boletin/", grupo_id=self.grupo["id"]))
        self.guardar("boletin_por_materia", self.leer(f"/estudiantes/{self.estudiante_id}/boletin/", grupo_id=self.grupo["id"], subject="science"))
        self.guardar("boletin_pagina", self.leer(f"/estudiantes/{self.estudiante_id}/boletin/", grupo_id=self.grupo["id"], limite=1, desde=1))
        self.guardar("libro_resumen", self.libro(vista="resumen"))
        self.guardar("sincronizar", self.sincronizar())
        self.guardar("sin_permiso", self.gb("/escalas/adoptar/", {"plantilla": "gen-0-5"}, cliente=self.docente, esperado=403))
        self.guardar("reconstruir", self.gb("/derivados/reconstruir/", {"reproducir": True}, cliente=self.admin))

        # ---- preescolar en modo simple: estados y símbolos, ningún número
        r = self.admin.post("/api/acceso/grupos/", {"codigo": "P1", "nombre": "Párvulos", "periodo": "2026", "nivel_clave": "preescolar"}, format="json")
        grupo_pre = r.json()
        self.admin.post(f"/api/acceso/grupos/{grupo_pre['id']}/miembros/", {"usuario_id": self.docente_id, "papel": "DOCENTE"}, format="json")
        ana_id, hw = self.alumno_con_tableta("Ana", "300001", capacidad="supervisado", grupo_id=grupo_pre["id"])
        a3 = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, grupo_id=grupo_pre["id"])
        self.guardar("mias_simple_sin_empezar", self.leer("/mias/", cliente=self.api, alumno_id=ana_id))
        _, i3, _, _ = self.examen_entregado(abiertas=False, asignacion=a3, hw=hw, alumno_id=ana_id)
        self.accion(f"/intentos/{i3}/liberar-resultado/", {})
        self.guardar("mias_simple", self.leer("/mias/", cliente=self.api, alumno_id=ana_id))
        self.guardar("registrar_modo_simple", self.gb(f"/asignaciones/{a3['id']}/registrar/", {}))          # en modo simple no se registra nada y se dice
        self.guardar("boletin_simple", self.leer(f"/estudiantes/{ana_id}/boletin/", grupo_id=grupo_pre["id"]))
        self.guardar("libro_simple", self.libro(grupo_id=grupo_pre["id"]))
