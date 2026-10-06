"""
Unit of Work sobre Django: una transacción por caso de uso. Todo lo que se escribe
dentro (incluido el outbox) se confirma o se deshace junto.
"""
from __future__ import annotations

from django.db import transaction

from ..aplicacion.puertos import Cifrador
from . import repositorios as r


class UnidadDeTrabajoDjango:
    """La versión de verdad de la «carpeta de trabajo» descrita en `puertos.py`.

    Aquí es donde se decide QUIÉN hace el trabajo: SQLite a través de Django. Si
    mañana el backend pasa a FastAPI con SQLAlchemy, se reescribe este archivo y el
    resto del módulo (dominio y casos de uso) no se entera.
    """

    def __init__(self, cifrador: Cifrador):
        # El cifrador viaja hasta aquí porque el cajón de usuarios necesita cifrar
        # nombres y documentos justo al escribirlos, y descifrarlos al leerlos.
        self._cifrador = cifrador
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoDjango":
        # Abrir la carpeta = abrir una transacción de base de datos. A partir de
        # este momento nada de lo que se escriba es definitivo todavía.
        self._atomic = transaction.atomic()
        self._atomic.__enter__()
        # Y se preparan los cajones: cada uno sabe leer y escribir una cosa.
        self.organizaciones = r.OrganizacionesDjango()
        self.politicas = r.PoliticasDjango()
        self.permisos = r.PermisosDjango()
        self.roles = r.RolesDjango()
        self.usuarios = r.UsuariosDjango(self._cifrador)
        self.credenciales = r.CredencialesDjango()
        self.pines_maestros = r.PinesMaestrosDjango()
        self.grupos = r.GruposDjango()
        self.dispositivos = r.DispositivosDjango()
        self.sesiones = r.SesionesDjango()
        self.intentos = r.IntentosDjango()
        self.autorizaciones = r.AutorizacionesDjango()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaExpediente()
        return self

    def __exit__(self, tipo, valor, traza) -> None:
        # Cerrar la carpeta. `transaction.atomic` mira si la gestión terminó bien:
        #   - sin error  -> commit:   todo lo escrito queda guardado de golpe.
        #   - con error  -> rollback: la base vuelve a como estaba al abrir, como
        #                             si la gestión nunca hubiera empezado.
        # Por eso una matrícula a medias es imposible: no hay un punto intermedio.
        self._atomic.__exit__(tipo, valor, traza)
        self._atomic = None


class FabricaUoWDjango:
    """Reparte carpetas nuevas: cada gestión (cada caso de uso) estrena la suya.

    Es lo que los casos de uso llaman con `self.s.uow()`. No se reutiliza una
    carpeta entre dos gestiones distintas, porque entonces un fallo en la segunda
    borraría el trabajo de la primera.
    """

    def __init__(self, cifrador: Cifrador):
        self._cifrador = cifrador

    def __call__(self) -> UnidadDeTrabajoDjango:
        return UnidadDeTrabajoDjango(self._cifrador)
