"""Transactional Outbox y Unit of Work: el evento nace en la misma transacción que el cambio."""
from __future__ import annotations

from acceso import models as m
from acceso.dominio.entidades import EventoSalida
from acceso.infraestructura.contenedor import servicios
from expediente.models import Auditoria

from .base import BaseAcceso


class OutboxTests(BaseAcceso):
    def test_crear_usuario_deja_evento_y_auditoria(self):
        eventos = m.EventoSalida.objects.filter(tipo_evento="identidad.usuario.creado.v1", agregado_id=self.estudiante_id)
        self.assertEqual(eventos.count(), 1)
        self.assertEqual(eventos.first().carga["rol"], "STUDENT")
        self.assertIsNone(eventos.first().publicado_en)
        self.assertTrue(Auditoria.objects.filter(accion="identidad.usuario.creado", objeto_id=self.estudiante_id).exists())
        # todos los eventos del módulo siguen la nomenclatura del Documento Maestro
        for ev in m.EventoSalida.objects.all():
            self.assertRegex(ev.tipo_evento, r"^identidad\.[a-z_]+(\.[a-z_]+)?\.v1$")
        # la carga del outbox nunca lleva PII ni secretos
        for ev in m.EventoSalida.objects.all():
            texto = str(ev.carga)
            self.assertNotIn("Juan", texto)
            self.assertNotIn(self.ESTUDIANTE_PIN, texto)
            self.assertNotIn(self.ADMIN_PASS, texto)

    def test_un_fallo_deshace_el_cambio_y_el_evento(self):
        antes = m.EventoSalida.objects.count()
        fabrica = servicios().uow
        with self.assertRaises(RuntimeError):
            with fabrica() as uow:
                uow.outbox.publicar(EventoSalida("prueba", "x", "acceso.prueba", {}, 1))
                uow.auditoria.registrar("x", "prueba.transaccion")
                raise RuntimeError("algo falló después de escribir")
        self.assertEqual(m.EventoSalida.objects.count(), antes)
        self.assertFalse(Auditoria.objects.filter(accion="prueba.transaccion").exists())

    def test_una_creacion_rechazada_no_deja_rastro(self):
        antes = (m.Usuario.objects.count(), m.EventoSalida.objects.count(), m.Credencial.objects.count())
        r = self.docente.post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": "Fallido", "persona": {"nombres": "F"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": "150001"}],
            "secreto": "111111", "grupo_id": self.grupo["id"]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual((m.Usuario.objects.count(), m.EventoSalida.objects.count(), m.Credencial.objects.count()), antes)
