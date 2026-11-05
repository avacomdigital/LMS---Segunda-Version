"""
Los adaptadores de MOD-016 contra el sistema de archivos y SQLite de verdad (sin nodo instalado): la instantánea consistente, la clave del equipo, la carpeta de respaldos, las unidades
y lo que se rehace tras restaurar.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from respaldo.dominio import catalogos as cat
from respaldo.dominio import cripto
from respaldo.dominio.errores import EspacioInsuficiente
from respaldo.infraestructura import origen as mod_origen
from respaldo.infraestructura.adaptadores import TrasRestaurarDelNodo
from respaldo.infraestructura.almacen import AlmacenEnCarpeta
from respaldo.infraestructura.clavero import ClaveroDelNodo
from respaldo.infraestructura.origen import OrigenDelNodo, analizar_carpetas, copiar_base
from respaldo.infraestructura.unidades import UnidadesDelNodo


class Temporal(SimpleTestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="avacom-resp-infra-"))
        self.addCleanup(shutil.rmtree, self.t, True)


class InstantaneaDeLaBase(Temporal):
    """La API de respaldo de SQLite: una copia CONSISTENTE de una base en uso, sin detener a quien escribe (la promesa del respaldo en caliente)."""

    def base(self) -> Path:
        ruta = self.t / "viva.sqlite3"
        with closing(sqlite3.connect(ruta)) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("CREATE TABLE respuesta (id INTEGER PRIMARY KEY, intento INTEGER, valor TEXT)")
            c.execute("CREATE TABLE intento (id INTEGER PRIMARY KEY, respuestas INTEGER)")
            c.commit()
        return ruta

    def test_la_copia_es_consistente_aunque_alguien_escriba_mientras_se_copia(self):
        viva = self.base()
        parar = threading.Event()

        def escribir():
            with closing(sqlite3.connect(viva, timeout=20)) as c:
                n = 0
                while not parar.is_set():
                    n += 1
                    c.execute("BEGIN IMMEDIATE")
                    c.execute("INSERT INTO respuesta (intento, valor) VALUES (?, ?)", (n, "x" * 200))
                    c.execute("INSERT INTO intento (id, respuestas) VALUES (?, 1)", (n,))             # la pareja SIEMPRE va junta en una transacción
                    c.commit()

        hilo = threading.Thread(target=escribir)
        hilo.start()
        try:
            time.sleep(0.2)
            for i in range(5):
                copia = self.t / f"copia{i}.sqlite3"
                with closing(sqlite3.connect(viva)) as origen, closing(sqlite3.connect(copia)) as destino:
                    copiar_base(origen, destino)
                with closing(sqlite3.connect(copia)) as c:
                    self.assertEqual(c.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
                    a, b = c.execute("SELECT (SELECT COUNT(*) FROM respuesta), (SELECT COUNT(*) FROM intento)").fetchone()
                    self.assertEqual(a, b, "una copia a medias de una transacción (una respuesta sin su intento)")
        finally:
            parar.set()
            hilo.join()

    def test_si_la_base_esta_ocupada_por_la_propia_conexion_falla_en_vez_de_esperar_para_siempre(self):
        viva = self.base()
        with closing(sqlite3.connect(viva, isolation_level=None)) as origen, closing(sqlite3.connect(self.t / "c.sqlite3")) as destino:
            origen.execute("BEGIN IMMEDIATE")
            origen.execute("INSERT INTO intento (id, respuestas) VALUES (1, 1)")
            with mock.patch.object(mod_origen, "ESPERA_MAXIMA_S", 1):
                t0 = time.monotonic()
                with self.assertRaises(sqlite3.OperationalError):
                    copiar_base(origen, destino)
                self.assertLess(time.monotonic() - t0, 10)


class ArchivosDeLaInstitucion(Temporal):
    def test_las_carpetas_se_declaran_con_nombre_y_clase_y_lo_invalido_se_ignora(self):
        crudo = f"evidencias={self.t / 'a'};medios:reinstalable={self.t / 'b'};../mal={self.t};con espacio={self.t};x:rara={self.t};sinigual;vacia="
        self.assertEqual([(c.nombre, c.clase) for c in analizar_carpetas(crudo)], [("evidencias", "primario"), ("medios", "reinstalable")])
        self.assertEqual(analizar_carpetas(""), [])

    def test_lo_reinstalable_no_entra_salvo_que_se_pida_y_los_enlaces_y_nombres_inseguros_se_omiten(self):
        (self.t / "ev").mkdir()
        (self.t / "med").mkdir()
        (self.t / "ev" / "Mª Ángeles (copia).docx").write_bytes(b"1")
        (self.t / "ev" / "sub").mkdir()
        (self.t / "ev" / "sub" / "b.txt").write_bytes(b"22")
        (self.t / "ev" / "con.txt").write_bytes(b"x")                      # nombre reservado de Windows: no se extrae seguro
        (self.t / "med" / "video.mp4").write_bytes(b"3" * 10)
        o = OrigenDelNodo(f"ev={self.t / 'ev'};med:reinstalable={self.t / 'med'}")
        archivos, omitidos = o.archivos(False, None)
        self.assertEqual(sorted(a.nombre for a in archivos), ["ev/Mª Ángeles (copia).docx", "ev/sub/b.txt"])
        self.assertEqual(omitidos, ["ev/con.txt"])
        todos, _ = o.archivos(True, None)
        self.assertIn("med/video.mp4", [a.nombre for a in todos])
        self.assertEqual(todos[0].abrir().read(), b"1") if todos[0].nombre.endswith(".docx") else None

    def test_un_incremental_solo_lleva_lo_modificado_desde_el_respaldo_anterior(self):
        (self.t / "ev").mkdir()
        viejo, nuevo = self.t / "ev" / "viejo.txt", self.t / "ev" / "nuevo.txt"
        viejo.write_bytes(b"v")
        nuevo.write_bytes(b"n")
        ahora = time.time()
        os.utime(viejo, (ahora - 86400, ahora - 86400))
        archivos, _ = OrigenDelNodo(f"ev={self.t / 'ev'}").archivos(False, int((ahora - 3600) * 1000))
        self.assertEqual([a.nombre for a in archivos], ["ev/nuevo.txt"])


class ClaveDelEquipo(Temporal):
    def test_la_clave_y_la_identidad_persisten_y_la_clave_no_se_guarda_en_claro_en_windows(self):
        c = ClaveroDelNodo(self.t)
        clave, nodo = c.clave_del_nodo(), c.nodo_id()
        self.assertEqual(len(clave), 32)
        otra = ClaveroDelNodo(self.t)
        self.assertEqual((otra.clave_del_nodo(), otra.nodo_id()), (clave, nodo))
        if os.name == "nt":
            self.assertNotIn(clave, (self.t / "estado" / "nodo.key").read_bytes(), "DPAPI: el archivo copiado a otro equipo no sirve")

    def test_la_custodia_se_guarda_envuelta_con_la_clave_del_nodo_y_el_codigo_no_se_guarda(self):
        c = ClaveroDelNodo(self.t, usar_dpapi=False)
        self.assertIsNone(c.custodia())
        codigo = cripto.generar_codigo_de_custodia()
        sal = cripto.generar_sal()
        kek = cripto.clave_de_custodia(cripto.secreto_de_custodia(codigo), sal)
        c.guardar_custodia(123, sal, kek)
        self.assertEqual(c.custodia(), {"emitida_en": 123, "sal": sal, "clave": kek})
        crudo = (self.t / "estado" / "nodo.json").read_bytes()
        self.assertNotIn(kek.hex().encode(), crudo)
        self.assertNotIn(codigo.replace("-", "").encode(), crudo)
        (self.t / "estado" / "nodo.key").unlink()                           # un equipo sin la clave no puede abrir la custodia guardada
        self.assertIsNone(ClaveroDelNodo(self.t, usar_dpapi=False).custodia())

    def test_una_clave_dañada_no_se_sustituye_en_silencio(self):
        c = ClaveroDelNodo(self.t, usar_dpapi=False)
        c.clave_del_nodo()
        (self.t / "estado" / "nodo.key").write_bytes(b"AVK0corta")
        with self.assertRaises(OSError):
            c.clave_del_nodo()


class CarpetaDeRespaldos(Temporal):
    def test_nombres_validos_informes_atomicos_y_trabajo_confinado(self):
        a = AlmacenEnCarpeta(self.t / "R")
        a.guardar_informe("resumen-de-respaldos.csv", "á;b\r\n", con_bom=True)
        self.assertEqual((self.t / "R" / "Informes" / "resumen-de-respaldos.csv").read_bytes()[:3], b"\xef\xbb\xbf")
        self.assertEqual(a.leer_informe("resumen-de-respaldos.csv"), "á;b\r\n")
        for malo in ("../x.txt", "a/b.txt", "", "con espacio.txt", ".oculto"):
            with self.assertRaises(ValueError):
                a.guardar_informe(malo, "x")
            self.assertIsNone(a.leer_informe(malo))
        self.assertEqual(a.listar_informes(), ["resumen-de-respaldos.csv"])
        fuera = self.t / "no-tocar"
        fuera.mkdir()
        a.limpiar_trabajo(fuera)
        self.assertTrue(fuera.exists(), "limpiar_trabajo no borra nada fuera de la carpeta de trabajo")
        w = a.carpeta_de_trabajo("restauracion-abc")
        self.assertTrue(w.is_dir())
        a.limpiar_trabajo(w)
        self.assertFalse(w.exists())

    def test_un_respaldo_se_escribe_como_parcial_y_solo_al_terminar_aparece_con_su_nombre(self):
        a = AlmacenEnCarpeta(self.t / "R")
        f, manija = a.abrir_para_escribir("aaaaaaaa-bbbb")
        f.write(b"datos")
        self.assertEqual(a.listar(), [], "un parcial no es un respaldo")
        nombre = a.terminar(manija, "aaaaaaaa-bbbb", 1_790_000_000_000, "completo")
        self.assertEqual(a.listar(), [nombre])
        self.assertTrue(nombre.startswith("respaldo-") and nombre.endswith(".avbak"))
        self.assertEqual(a.tamano(nombre), 5)
        self.assertIsNone(a.abrir("../../etc/passwd"))
        self.assertIsNone(a.ruta_de("x.txt"))
        f2, m2 = a.abrir_para_escribir("cccc")
        a.descartar(m2)
        self.assertEqual([p.name for p in (self.t / "R").iterdir() if p.suffix == ".parcial"], [])


class Unidades(Temporal):
    def test_se_copia_con_su_constancia_y_sin_espacio_se_dice_antes_de_empezar(self):
        usb = self.t / "usb"
        usb.mkdir()
        origen = self.t / "r.avbak"
        origen.write_bytes(b"x" * 1000)
        u = UnidadesDelNodo(self.t / "entrada", [usb], usar_unidades_reales=False)
        (uid,) = [x.id for x in u.listar()]
        self.assertEqual(u.copiar(uid, origen, "r.avbak", {"constancia.txt": "hola"}), "usb")
        self.assertEqual((usb / "AVACOM" / "Respaldos" / "r.avbak").read_bytes(), b"x" * 1000)
        self.assertEqual((usb / "AVACOM" / "Respaldos" / "constancia.txt").read_text(encoding="utf-8"), "hola")
        with mock.patch("shutil.disk_usage", return_value=mock.Mock(free=10)):
            with self.assertRaises(EspacioInsuficiente):
                u.copiar(uid, origen, "otro.avbak")
        self.assertFalse((usb / "AVACOM" / "Respaldos" / "otro.avbak").exists())

    def test_los_candidatos_se_encuentran_en_la_unidad_y_en_la_entrada_con_ids_opacos(self):
        usb = self.t / "usb"
        (usb / "AVACOM" / "Respaldos").mkdir(parents=True)
        (self.t / "entrada").mkdir()
        (usb / "AVACOM" / "Respaldos" / "a.avbak").write_bytes(b"1")
        (self.t / "entrada" / "b.avbak").write_bytes(b"22")
        (usb / "AVACOM" / "Respaldos" / "no.txt").write_bytes(b"3")
        u = UnidadesDelNodo(self.t / "entrada", [usb], usar_unidades_reales=False)
        c = {x.nombre: x for x in u.candidatos()}
        self.assertEqual(sorted(c), ["a.avbak", "b.avbak"])
        self.assertNotIn(str(self.t), c["a.avbak"].id)
        trabajo = self.t / "trabajo"
        self.assertEqual(u.traer(c["a.avbak"].id, trabajo).nombre, "a.avbak")
        self.assertEqual((trabajo / "a.avbak").read_bytes(), b"1")
        self.assertIsNone(u.traer("no-existe", trabajo))


class TrasRestaurar(SimpleTestCase):
    def test_cada_paso_en_lo_suyo_y_uno_que_falla_no_detiene_a_los_demas(self):
        llamados = []

        def comando(nombre, **kw):
            llamados.append(nombre)
            if nombre == "reporting_reconstruir":
                raise RuntimeError("una clase está abierta")

        with mock.patch("django.core.management.call_command", side_effect=comando), \
                mock.patch("nodo.servicios.arrancar", return_value={"arranque_id": 1}) as nodo, \
                mock.patch("acceso.servicios.revocar_sesiones_por_restauracion", return_value=4) as sesiones, \
                mock.patch("licenciamiento.servicios.evaluar_ahora") as licencia:
            r = TrasRestaurarDelNodo().ejecutar(False)
        self.assertEqual(llamados, ["migrate", "search_reconstruir", "reporting_reconstruir", "gradebook_reconstruir"])
        nodo.assert_called_once()
        sesiones.assert_called_once()
        licencia.assert_called_once_with("restauracion")
        self.assertEqual((r["sesiones"], r["nodo"], r["reconstruidos"]), (4, "arranque registrado", ["search", "gradebook"]))
        self.assertEqual(len(r["fallos"]), 1)
        self.assertIn("reporting_reconstruir", r["fallos"][0])

    def test_nunca_lanza(self):
        with mock.patch("django.core.management.call_command", side_effect=RuntimeError("x")), mock.patch("nodo.servicios.arrancar", side_effect=RuntimeError("y")), \
                mock.patch("acceso.servicios.revocar_sesiones_por_restauracion", side_effect=RuntimeError("z")), mock.patch("licenciamiento.servicios.evaluar_ahora", side_effect=RuntimeError("w")):
            r = TrasRestaurarDelNodo().ejecutar(True)
        self.assertEqual(len(r["fallos"]), 7)
        self.assertEqual(cat.MODULO, "respaldo")
