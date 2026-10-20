"""
La identidad propia del nodo (el secreto de instalación y su llave Ed25519) cuando el archivo en que viven NO se puede abrir en esta máquina: Windows reinstalado, el disco clonado a otro
equipo, un blob dañado. Revisión independiente, BUG-2: el nodo devolvía un valor en memoria y no guardaba nada, así que cada arranque tenía una identidad distinta (una licencia de nivel
«instalación» no volvía a coincidir ni pidiendo una solicitud nueva, las anclas del reloj fallaban su verificación en cada arranque y una liberación legítima no podía cotejarse con la llave).

Lo correcto: el archivo se aparta SIN borrarse, se guarda uno nuevo, la identidad es estable desde ese arranque y queda UN asiento de integridad; y dos casos que NO se tratan así porque el
archivo puede estar bien (DPAPI sin responder; un disco que no dejó leer ahora).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from audit.models import Bitacora
from licenciamiento import models as m
from licenciamiento.dominio import catalogos as cat
from licenciamiento.dominio.politica import HORA_MS
from licenciamiento.infraestructura import contenedor
from licenciamiento.infraestructura.almacen import CUARENTENA_MAXIMA, AlmacenEnCarpeta, AlmacenEnMemoria
from licenciamiento.infraestructura.nodo import NodoDeLicencia
from licenciamiento.infraestructura.proteccion import MARCA_DPAPI, ProtectorAutomatico, ProteccionFallida, ProteccionNoDisponible

from .base import BaseLicencia


class ProtectorDeUnaMaquina:
    """Sólo abre lo que él mismo protegió: lo que dejó OTRA máquina (otra marca) no se puede abrir."""

    def __init__(self, marca: bytes):
        self.marca = marca

    def proteger(self, datos: bytes) -> bytes:
        return self.marca + bytes(datos)

    def desproteger(self, blob: bytes) -> bytes:
        if blob[:len(self.marca)] != self.marca:
            raise ProteccionFallida("otra máquina")
        return bytes(blob[len(self.marca):])


class ProtectorSinDpapi(ProtectorDeUnaMaquina):
    def desproteger(self, blob: bytes) -> bytes:
        raise ProteccionNoDisponible("DPAPI no responde")


def apartados(almacen: AlmacenEnMemoria, nombre: str) -> list[str]:
    return sorted(n for n in almacen.archivos if n.startswith(f"{nombre}.ilegible-"))


class SecretoIlegibleTests(SimpleTestCase):
    def test_un_secreto_que_esta_maquina_no_abre_se_aparta_y_el_nodo_conserva_su_nueva_identidad(self):
        almacen = AlmacenEnMemoria()
        secreto_viejo = NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M1:")).secreto_de_instalacion()
        nuevo = NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M2:"))                            # otra máquina, o Windows reinstalado: el archivo está pero no se abre
        secreto_nuevo = nuevo.secreto_de_instalacion()
        self.assertNotEqual(secreto_nuevo, secreto_viejo)
        self.assertEqual(len(apartados(almacen, "instalacion.bin")), 1)
        self.assertEqual(almacen.archivos[apartados(almacen, "instalacion.bin")[0]], b"M1:" + secreto_viejo)       # nada se borró
        siguiente = NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M2:"))                         # el SIGUIENTE arranque: el mismo secreto, no uno nuevo
        self.assertEqual(siguiente.secreto_de_instalacion(), secreto_nuevo)
        self.assertEqual(len(apartados(almacen, "instalacion.bin")), 1)
        self.assertEqual(nuevo.tomar_novedades(), ["instalacion.bin"])
        self.assertEqual(nuevo.tomar_novedades(), [])                                              # una sola entrega
        self.assertEqual(siguiente.tomar_novedades(), [])

    def test_la_llave_del_nodo_tambien_y_ya_no_cambia_en_cada_arranque(self):
        almacen = AlmacenEnMemoria()
        publica_vieja = NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M1:")).clave_publica()
        nuevo = NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M2:"))
        publica_nueva = nuevo.clave_publica()
        self.assertNotEqual(publica_nueva, publica_vieja)
        self.assertEqual(NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M2:")).clave_publica(), publica_nueva)       # firma solicitudes y liberaciones con una llave que se recuerda
        self.assertEqual(len(apartados(almacen, "nodo.key")), 1)
        self.assertEqual(nuevo.tomar_novedades(), ["nodo.key"])

    def test_lo_entregado_que_no_llego_a_asentarse_vuelve_a_la_cola(self):
        almacen = AlmacenEnMemoria()
        NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M1:")).secreto_de_instalacion()
        nodo = NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M2:"))
        nodo.secreto_de_instalacion()
        entregadas = nodo.tomar_novedades()
        nodo.devolver_novedades(entregadas)
        self.assertEqual(nodo.tomar_novedades(), ["instalacion.bin"])

    def test_si_dpapi_no_responde_ahora_el_archivo_no_se_toca(self):
        """El archivo puede estar perfectamente bien: concluir que está perdido por un fallo del momento cambiaría la identidad del nodo para siempre."""
        almacen = AlmacenEnMemoria()
        NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M1:")).secreto_de_instalacion()
        antes = dict(almacen.archivos)
        nodo = NodoDeLicencia(almacen, ProtectorSinDpapi(b"M1:"))
        self.assertEqual(len(nodo.secreto_de_instalacion()), 32)                                   # un valor desechable de esta corrida
        self.assertEqual(almacen.archivos, antes)                                                  # ni apartado, ni reemplazado
        self.assertEqual(nodo.tomar_novedades(), [])

    def test_un_archivo_que_el_disco_no_dejo_leer_ahora_no_se_pisa(self):
        class AlmacenQueNoLee(AlmacenEnMemoria):
            def leer(self, nombre):
                return None                                                                        # (un bloqueo del disco, un permiso)

        almacen = AlmacenQueNoLee()
        almacen.archivos["instalacion.bin"] = b"M1:" + b"x" * 32
        nodo = NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M1:"))
        nodo.secreto_de_instalacion()
        self.assertEqual(almacen.archivos, {"instalacion.bin": b"M1:" + b"x" * 32})
        self.assertEqual(nodo.tomar_novedades(), [])

    def test_si_no_se_puede_apartar_no_se_pisa(self):
        class AlmacenQueNoAparta(AlmacenEnMemoria):
            def poner_en_cuarentena(self, nombre):
                raise OSError("sin permiso")

        almacen = AlmacenQueNoAparta()
        almacen.archivos["instalacion.bin"] = b"M1:" + b"x" * 32
        nodo = NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M2:"))
        nodo.secreto_de_instalacion()
        self.assertEqual(almacen.archivos, {"instalacion.bin": b"M1:" + b"x" * 32})
        self.assertEqual(nodo.tomar_novedades(), [])

    def test_un_archivo_que_no_existe_se_crea_sin_novedad(self):
        almacen = AlmacenEnMemoria()
        nodo = NodoDeLicencia(almacen, ProtectorDeUnaMaquina(b"M1:"))
        nodo.secreto_de_instalacion()
        self.assertIn("instalacion.bin", almacen.archivos)
        self.assertEqual((apartados(almacen, "instalacion.bin"), nodo.tomar_novedades()), ([], []))

    def test_el_protector_distingue_un_archivo_malo_de_un_dpapi_que_no_responde(self):
        protector = ProtectorAutomatico()
        with self.assertRaises(ProteccionFallida) as sin_formato:
            protector.desproteger(b"esto no es un blob de nadie")
        self.assertNotIsInstance(sin_formato.exception, ProteccionNoDisponible)                     # el archivo es el malo: se aparta
        protector._dpapi = None                                                                    # DPAPI no responde ahora
        with self.assertRaises(ProteccionNoDisponible):
            protector.desproteger(MARCA_DPAPI + b"cualquier cosa")                                 # el archivo puede ser bueno: no se toca


class CuarentenaEnDiscoTests(SimpleTestCase):
    def setUp(self):
        self.carpeta = Path(tempfile.mkdtemp(prefix="avacom-cuarentena-"))
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        self.almacen = AlmacenEnCarpeta(self.carpeta)

    def test_apartar_es_renombrar_no_borrar(self):
        self.almacen.escribir("instalacion.bin", b"contenido")
        nombre = self.almacen.poner_en_cuarentena("instalacion.bin")
        self.assertTrue(nombre.startswith("instalacion.bin.ilegible-"))
        self.assertFalse(self.almacen.existe("instalacion.bin"))
        self.assertEqual(self.almacen.leer(nombre), b"contenido")

    def test_apartar_lo_que_no_existe_devuelve_none(self):
        self.assertIsNone(self.almacen.poner_en_cuarentena("instalacion.bin"))

    def test_sólo_se_conservan_los_ultimos_apartados(self):
        for n in range(CUARENTENA_MAXIMA + 3):
            self.almacen.escribir("instalacion.bin", f"v{n}".encode())
            self.almacen.poner_en_cuarentena("instalacion.bin")
        guardados = sorted(p.name for p in self.carpeta.glob("instalacion.bin.ilegible-*"))
        self.assertEqual(len(guardados), CUARENTENA_MAXIMA)
        contenidos = {p.read_bytes() for p in self.carpeta.glob("instalacion.bin.ilegible-*")}
        self.assertIn(f"v{CUARENTENA_MAXIMA + 2}".encode(), contenidos)                            # lo más reciente se conserva
        self.assertNotIn(b"v0", contenidos)                                                        # lo más viejo cede su lugar

    def test_un_nombre_de_archivo_no_valido_no_sale_de_la_carpeta(self):
        with self.assertRaises(ValueError):
            self.almacen.poner_en_cuarentena("../fuera.bin")


class IdentidadDelNodoTests(BaseLicencia):
    """F-08 de «impacto de funciones»: reinstalar Windows en un panel cuyo SMBIOS es de relleno. Con un nodo real: base, bitácora, anclas, API y permisos."""

    POBRE = {1: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", 2: "03000200-0400-0500-0006-000700080009", 3: "Default string", 4: "To be filled by O.E.M."}

    def reiniciar_el_nodo(self):
        """Un arranque nuevo: servicios nuevos sobre la MISMA carpeta de estado y la MISMA base; el reloj y el hardware siguen siendo los de la prueba."""
        contenedor.reiniciar()
        self.s = contenedor.servicios()
        self.s.reloj, self.s.huella = self.reloj, self.huella

    def corromper(self, nombre: str):
        self.s.almacen.escribir(nombre, b"un archivo que esta maquina ya no puede abrir")

    def test_un_secreto_ilegible_se_asienta_una_sola_vez_y_el_nodo_conserva_la_identidad_nueva(self):
        self.evaluar("arranque")
        secreto_original = self.s.nodo.secreto_de_instalacion()
        self.corromper(cat.ARCHIVO_SECRETO)
        self.reiniciar_el_nodo()
        e = self.evaluar("arranque")
        self.assertIn(cat.B_INTEGRIDAD_ALTERADA, e.estado.banderas)
        nuevo = self.s.nodo.secreto_de_instalacion()
        self.assertNotEqual(nuevo, secreto_original)
        # queda asentado UNA vez, con el nombre lógico del secreto y sin contenido
        asientos = list(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD))
        self.assertEqual(len(asientos), 1)
        self.assertEqual(asientos[0].valor_nuevo["secretos"], ["secreto_de_instalacion"])
        self.assertNotIn("instalacion.bin", str(asientos[0].valor_nuevo))
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento=cat.EV_INTEGRIDAD).count(), 1)
        self.assertEqual(m.Observacion.objects.filter(tipo=cat.O_INTEGRIDAD).count(), 1)
        self.assertEqual(len(list(Path(self.carpeta).glob("instalacion.bin.ilegible-*"))), 1)             # el archivo viejo quedó apartado en la carpeta de estado, no borrado
        # las anclas del reloj, que ya no verificaban con la identidad vieja, se rehacen con la nueva
        self.assertEqual(self.s.anclas.leer().alteradas, ())
        # el siguiente arranque: la misma identidad y NADA nuevo que asentar
        self.reiniciar_el_nodo()
        self.evaluar("arranque")
        self.assertEqual(self.s.nodo.secreto_de_instalacion(), nuevo)
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD).count(), 1)
        self.assertEqual(len(list(Path(self.carpeta).glob("instalacion.bin.ilegible-*"))), 1)

    def test_lo_asentado_no_se_vuelve_a_asentar_en_los_ciclos_siguientes_del_mismo_proceso(self):
        """Lo entregado se asienta UNA vez: sólo lo que la base no aceptó vuelve a la cola."""
        self.evaluar("arranque")
        self.corromper(cat.ARCHIVO_SECRETO)
        self.reiniciar_el_nodo()
        self.evaluar("arranque")
        for _ in range(3):
            self.reloj.avanzar(11 * 60_000)
            self.evaluar("tick")
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD).count(), 1)
        self.assertEqual(m.Observacion.objects.filter(tipo=cat.O_INTEGRIDAD).count(), 1)
        self.assertEqual(self.s.nodo.tomar_novedades(), [])

    def test_si_la_base_no_acepta_el_asiento_la_novedad_se_reintenta_en_el_siguiente_ciclo(self):
        from unittest import mock
        self.evaluar("arranque")
        self.corromper(cat.ARCHIVO_SECRETO)
        self.reiniciar_el_nodo()
        with mock.patch("licenciamiento.aplicacion.evaluar.Evaluar._una", side_effect=RuntimeError("base ocupada")):
            self.evaluar("arranque")
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD).count(), 0)
        self.reloj.avanzar(10 * 60_000)
        e = self.evaluar("tick")
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD).count(), 1)             # la novedad no se perdió
        self.assertIn(cat.B_INTEGRIDAD_ALTERADA, e.estado.banderas)

    def test_f_08_reinstalar_windows_en_un_panel_con_smbios_de_relleno_tiene_salida(self):
        self.huella.valores = dict(self.POBRE)
        primera = self.solicitud_del_nodo()                                                        # nivel «instalación»: la huella es el secreto de ESTE Windows
        self.assertEqual(primera.nivel, "instalacion")
        self.activar_ok(huella=primera.huella)
        self.assertEqual(self.estado()["estado"], "activa")
        # Windows se reinstala: el MachineGuid cambia y lo protegido con DPAPI ya no se abre
        self.huella.valores = {**self.POBRE, 1: "0a0b0c0d-2222-4c3c-9d4e-bbbbbbbbbb02"}
        self.corromper(cat.ARCHIVO_SECRETO)
        self.corromper(cat.ARCHIVO_LLAVE_NODO)
        self.reiniciar_el_nodo()
        e = self.evaluar("arranque")
        self.assertEqual((e.estado.estado, e.estado.motivo), (cat.EN_GRACIA, cat.M_HUELLA_DISTINTA))       # la clase sigue; empieza la gracia
        # una solicitud NUEVA se firma con la llave nueva… que el siguiente arranque recuerda (antes cambiaba en cada arranque)
        segunda = self.solicitud_del_nodo()
        self.assertNotEqual(segunda.huella, primera.huella)
        self.assertNotEqual(segunda.clave_nodo, primera.clave_nodo)
        self.reiniciar_el_nodo()
        self.assertEqual(self.s.nodo.clave_publica(), segunda.clave_nodo)
        self.assertEqual(self.solicitud_del_nodo().huella, segunda.huella)                         # y la huella de instalación tampoco cambia
        # el emisor entrega la serie 2 de la MISMA licencia para la huella nueva y el TÉCNICO la activa (traslado, D-10)
        r = self.activar(cliente=self.tecnico(), serie=2, emitida=self.reloj.t - HORA_MS, huella=segunda.huella)
        self.assertEqual((r.status_code, r.json()["accion"], r.json()["estado"]), (200, "activada", "activa"), r.content)
