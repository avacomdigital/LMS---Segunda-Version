"""
La línea de comandos de punta a punta, tal como la usa la guía interna (LIC-E-02, 03, 05…09, 14, 15): se crean llaves, se emiten licencias de verdad y se leen con el lector del nodo.
"""
from __future__ import annotations

import contextlib
import io
import json
import random
import socket
import unittest
from unittest import mock

from avacom_licencias import cli
from avacom_licencias.dominio_nodo import huella, licencia, tlv
from avacom_licencias.registro import Registro

from licenciamiento.dominio import estado  # noqa: E402

from .apoyo import AHORA, DIA_MS, FRASE, BaseConCarpeta, NodoDePrueba, correr

OTROS_VALORES = {
    huella.F_MACHINE_GUID: "11111111-2222-4333-8444-555555555555", huella.F_SMBIOS_UUID: "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
    huella.F_PLACA: "NUEVA-PLACA-0042-XX", huella.F_CHASIS: "CHASIS-NUEVO-7788", huella.F_PROCESADOR: "BFEBFBFF000A0671",
}
OK = huella.Coincidencia(k=3, en_licencia=5, coinciden=5, ok=True, parcial=False, nivel=huella.NIVEL_HARDWARE)


class LicenciaNuevaTests(BaseConCarpeta):
    def test_de_punta_a_punta(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        r = self.emitir(sol)
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("RESUMEN DE LA LICENCIA", r.salida)
        archivos = self.licencias()
        self.assertEqual(len(archivos), 1)
        lic = self.leer(archivos[0])
        self.assertEqual((lic.serie, lic.aula, lic.tipo), (1, "Colegio San Martín", "produccion"))
        self.assertEqual(lic.limites, licencia.Limites(60, 1200, 50, 100))                     # el tamaño máximo de un aula que fijó el CTO (Q-L1)
        self.assertEqual(lic.capacidades, frozenset({"*"}))
        self.assertEqual((lic.gracia_dias, lic.liberacion_pendiente), (30, False))
        hoja = archivos[0].with_suffix(".txt").read_text(encoding="utf-8-sig")
        self.assertIn(licencia.a_texto(archivos[0].read_bytes()), hoja)
        self.assertIn(lic.sha256, hoja)
        self.assertIn(lic.sha256, r.salida)
        registro = Registro(self.registro)
        self.assertEqual(registro.verificar()[2], 1)
        self.assertEqual(registro.renglones()[0]["sha256_licencia"], lic.sha256)

    def test_sin_la_palabra_de_confirmacion_no_se_crea_nada(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        for respuesta in ("no", "", "emitir ", "Emitir"):
            r = self.emitir(sol, entradas=[respuesta])
            self.assertEqual(r.codigo, 2, respuesta)
            self.assertIn("Cancelado", r.salida)
        self.assertEqual(self.licencias(), [])
        self.assertEqual(Registro(self.registro).verificar()[2], 0)

    def test_con_la_palabra_se_firma(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        r = self.emitir(sol, entradas=["EMITIR"])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertEqual(len(self.licencias()), 1)

    def test_un_plan_sin_tope_pide_una_segunda_confirmacion_si_las_reglas_del_cto_lo_permiten(self):
        """El plan «sin tope» ya no se entrega (el CTO fijó el tamaño máximo, Q-L1), pero el mecanismo de la segunda confirmación sigue ahí para una carpeta de planes sin esa regla."""
        planes = self.dir / "planes-sin-reglas"
        planes.mkdir()
        (planes / "sin-tope.json").write_text(json.dumps({
            "nombre": "sin-tope", "tipo": "produccion", "meses": 12, "gracia_dias": 30, "capacidades": ["*"], "confirmacion_extra": True,
            "limites": {"equipos": "sin_tope", "usuarios": "sin_tope", "concurrentes_normal": 50, "concurrentes_pico": 100}}), encoding="utf-8")
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        self.assertEqual(self.emitir(sol, "--planes", str(planes), "--plan", "sin-tope", entradas=["EMITIR"]).codigo, 2)
        self.assertEqual(self.licencias(), [])
        r = self.emitir(sol, "--planes", str(planes), "--plan", "sin-tope", entradas=["SIN TOPE", "EMITIR"])
        self.assertEqual(r.codigo, 0, r.error)
        lic = self.leer(self.licencias()[0])
        self.assertEqual((lic.limites.equipos, lic.limites.usuarios), (licencia.ILIMITADO, licencia.ILIMITADO))
        self.assertIn("NO tiene tope", r.salida)

    def test_limites_modulos_y_gracia_a_mano(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        r = self.emitir(sol, "--equipos", "10", "--usuarios", "99", "--normal", "5", "--pico", "8", "--capacidades", "reportes,busqueda", "--gracia", "30", "--tipo", "evaluacion")
        self.assertEqual(r.codigo, 0, r.error)
        lic = self.leer(self.licencias()[0])
        self.assertEqual(lic.limites, licencia.Limites(10, 99, 5, 8))
        self.assertEqual(lic.capacidades, frozenset({"reportes", "busqueda"}))
        self.assertEqual((lic.gracia_dias, lic.tipo), (30, "evaluacion"))
        self.assertIn("EVALUACIÓN", r.salida)

    def test_las_reglas_del_cto_no_se_contradicen_ni_con_una_opcion(self):
        """Q-L16 · la gracia son 30 días corridos EXACTOS y Q-L1 · un aula no pasa de 60 equipos y 1200 usuarios, ni con «sin_tope»: nada se firma ni se registra."""
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        for opciones, texto in ((("--gracia", "15"), "30 días corridos exactos"), (("--gracia", "45"), "30 días corridos exactos"), (("--gracia", "0"), "30 días corridos exactos"),
                                (("--equipos", "61"), "tamaño máximo"), (("--usuarios", "1201"), "tamaño máximo"),
                                (("--equipos", "sin_tope"), "tamaño máximo"), (("--usuarios", "sin_tope"), "tamaño máximo")):
            r = self.emitir(sol, *opciones)
            self.assertEqual(r.codigo, 1, opciones)
            self.assertIn(texto, r.error + r.salida, opciones)
        self.assertEqual(self.licencias(), [])
        self.assertEqual(Registro(self.registro).verificar()[2], 0)
        r = self.emitir(sol, "--equipos", "60", "--usuarios", "1200", "--gracia", "30")           # justo el máximo y la gracia exacta
        self.assertEqual(r.codigo, 0, r.error)

    def test_un_plan_que_contradice_las_reglas_no_se_carga(self):
        """Las reglas valen también para los planes: un plan con 45 días de gracia o 80 equipos no se puede ni elegir."""
        planes = self.dir / "planes-malos"
        planes.mkdir()
        (planes / "reglas.json").write_text(json.dumps({"version": 1, "gracia_dias": 30, "tamano_maximo": {"equipos": 60, "usuarios": 1200}}), encoding="utf-8")
        (planes / "grande.json").write_text(json.dumps({
            "nombre": "grande", "tipo": "produccion", "meses": 12, "gracia_dias": 30, "capacidades": ["*"],
            "limites": {"equipos": 80, "usuarios": 1200, "concurrentes_normal": 50, "concurrentes_pico": 100}}), encoding="utf-8")
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        r = self.emitir(sol, "--planes", str(planes), "--plan", "grande")
        self.assertEqual(r.codigo, 1)
        self.assertIn("grande.json", r.error + r.salida)
        self.assertIn("tamaño máximo", r.error + r.salida)
        self.assertEqual(self.licencias(), [])

    def test_opciones_que_no_valen(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        self.assertEqual(self.emitir(sol, "--capacidades", "magia").codigo, 1)
        self.assertEqual(self.emitir(sol, "--normal", "9", "--pico", "8").codigo, 1)
        self.assertEqual(self.emitir(sol, "--equipos", "0").codigo, 1)
        self.assertEqual(self.emitir(sol, "--meses", "3").codigo, 1)                      # con --hasta puesto por el apoyo: las dos a la vez
        self.assertEqual(self.emitir(sol, "--plan", "no-existe").codigo, 1)
        self.assertEqual(self.emitir(sol, hasta="2026-10-19").codigo, 1)                  # una vigencia que ya terminó
        self.assertEqual(self.emitir(sol, hasta="31/10/2027").codigo, 1)
        self.assertEqual(self.licencias(), [])
        self.assertEqual(self.emitir(sol, "--tipo", "desarrollo").codigo, 2)             # argparse: ni siquiera es una opción
        self.assertEqual(self.licencias(), [])

    def test_por_meses_en_vez_de_fecha(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        r = self.emitir(sol, "--meses", "6", hasta=None)
        self.assertEqual(r.codigo, 0, r.error)
        lic = self.leer(self.licencias()[0])
        self.assertIn("2027-04-20", r.salida)
        self.assertGreater(lic.vence, AHORA + 180 * DIA_MS)

    def test_la_solicitud_puede_ir_como_texto(self):
        texto = licencia.a_texto(self.nodo.solicitud(), tlv.MAGIC_SOLICITUD)
        r = correr(["emitir", "--solicitud", texto, "--privada", str(self.privada), "--registro", str(self.registro), "--salida", str(self.salida), "--hasta", "2027-10-31",
                    "--yo-confirmo"])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertEqual(len(self.licencias()), 1)

    def test_solicitud_alterada_no_se_emite(self):
        datos = bytearray(self.nodo.solicitud())
        datos[len(datos) // 2] ^= 0x01
        sol = self.guardar("mala.avreq", bytes(datos))
        r = self.emitir(sol)
        self.assertEqual(r.codigo, 1)
        self.assertIn("no es válida", r.error)
        self.assertEqual(self.licencias(), [])

    def test_solicitud_que_no_es_una_solicitud(self):
        for contenido in (b"hola", b"", b"AVRQ" + b"\x00" * 200):
            r = self.emitir(self.guardar("x.avreq", contenido))
            self.assertEqual(r.codigo, 1, contenido)
        self.assertEqual(self.emitir(self.dir / "no-existe.avreq").codigo, 1)

    def test_la_misma_solicitud_dos_veces(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        self.assertEqual(self.emitir(sol).codigo, 0)
        r = self.emitir(sol)
        self.assertEqual(r.codigo, 1)
        self.assertIn("ya se atendió", r.error)
        r = self.emitir(sol, "--reemitir", "--salida", str(self.dir / "otra"))
        self.assertEqual(r.codigo, 0, r.error)
        series = sorted(x["serie"] for x in Registro(self.registro).renglones())
        self.assertEqual(series, [1, 2])
        self.assertEqual(len({x["licencia_id"] for x in Registro(self.registro).renglones()}), 1)

    def test_frase_equivocada_no_deja_rastro(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        r = self.emitir(sol, frase="otra frase distinta y bien larga")
        self.assertEqual(r.codigo, 1)
        self.assertIn("frase de paso", r.error)
        self.assertEqual(self.licencias(), [])
        self.assertEqual(Registro(self.registro).verificar()[2], 0)

    def test_registro_alterado_impide_emitir(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        self.assertEqual(self.emitir(sol).codigo, 0)
        renglon = json.loads(self.registro.read_text(encoding="utf-8").splitlines()[0])
        renglon["aula"] = "Otra"
        self.registro.write_text(json.dumps(renglon) + "\n", encoding="utf-8")
        r = self.emitir(self.guardar("sol2.avreq", NodoDePrueba().solicitud()))
        self.assertEqual(r.codigo, 1)
        self.assertIn("alterado", r.error)
        self.assertEqual(len(self.licencias()), 1)

    def test_no_se_pisa_un_archivo_existente(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        self.assertEqual(self.emitir(sol).codigo, 0)
        # mismo día, mismo aula y misma serie 1 (otra solicitud de un equipo distinto del mismo aula) → el mismo nombre de archivo
        r = self.emitir(self.guardar("sol2.avreq", NodoDePrueba().solicitud()))
        self.assertEqual(r.codigo, 1)
        self.assertIn("Ya existe", r.error)
        self.assertIn("No se firmó ni se registró nada", r.error)
        self.assertEqual(len(self.licencias()), 1)
        self.assertEqual(Registro(self.registro).verificar()[2], 1)

    def test_sin_red(self):
        def sin_red(*args, **kwargs):
            raise AssertionError("el emisor intentó abrir una conexión de red")
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        with mock.patch.object(socket, "socket", sin_red), mock.patch.object(socket, "create_connection", sin_red), mock.patch.object(socket, "getaddrinfo", sin_red):
            r = self.emitir(sol)
            self.assertEqual(r.codigo, 0, r.error)
            self.assertEqual(self.verificar(self.licencias()[0]).codigo, 0)

    def verificar(self, ruta, *extra):
        return correr(["verificar", str(ruta), "--publica", str(self.publica), *extra])

    def test_ni_la_privada_ni_la_frase_quedan_en_ningun_archivo(self):
        from avacom_licencias import llaves
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        self.assertEqual(self.emitir(sol).codigo, 0)
        privada = llaves.abrir(self.privada.read_bytes(), FRASE).privada
        for ruta in self.dir.rglob("*"):
            if ruta.is_file() and ruta != self.privada:
                contenido = ruta.read_bytes()
                self.assertNotIn(privada, contenido, ruta.name)
                self.assertNotIn(privada.hex().encode(), contenido, ruta.name)
                self.assertNotIn(FRASE.encode(), contenido, ruta.name)


class RenovacionTests(BaseConCarpeta):
    def test_renovar_usa_la_misma_licencia_y_la_serie_siguiente(self):
        self.assertEqual(self.emitir(self.guardar("s1.avreq", self.nodo.solicitud())).codigo, 0)
        primera = self.leer(self.licencias()[0])
        r = self.emitir(self.guardar("s2.avreq", self.nodo.solicitud(licencia_vigente=primera.id)), "--salida", str(self.salida / "r"))
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("renovación", r.salida)
        segunda = self.leer(next((self.salida / "r").glob("*.avlic")))
        self.assertEqual((segunda.id, segunda.serie), (primera.id, 2))
        self.assertEqual(segunda.huella, primera.huella)

    def test_una_licencia_que_el_registro_no_conoce_pide_la_serie(self):
        r = self.emitir(self.guardar("s.avreq", self.nodo.solicitud(licencia_vigente="a7a7a7a7-0001-4000-8000-000000000001")))
        self.assertEqual(r.codigo, 1)
        self.assertIn("--serie", r.error)
        r = self.emitir(self.guardar("s.avreq", self.nodo.solicitud(licencia_vigente="a7a7a7a7-0001-4000-8000-000000000001")), "--serie", "7")
        self.assertEqual(r.codigo, 0, r.error)
        self.assertEqual(self.leer(self.licencias()[0]).serie, 7)

    def test_la_serie_a_mano_no_puede_ser_anterior(self):
        self.assertEqual(self.emitir(self.guardar("s1.avreq", self.nodo.solicitud())).codigo, 0)
        primera = self.leer(self.licencias()[0])
        r = self.emitir(self.guardar("s2.avreq", self.nodo.solicitud(licencia_vigente=primera.id)), "--serie", "1")
        self.assertEqual(r.codigo, 1)
        self.assertIn("mayor", r.error)


class CambioDeEquipoTests(BaseConCarpeta):
    def setUp(self):
        super().setUp()
        self.viejo = self.nodo
        self.nuevo = NodoDePrueba(valores=OTROS_VALORES)
        self.assertEqual(self.emitir(self.guardar("viejo.avreq", self.viejo.solicitud())).codigo, 0)
        self.primera = self.leer(self.licencias()[0])

    def test_con_la_liberacion_del_equipo_viejo_sale_la_definitiva(self):
        liberacion = self.guardar("viejo.avrel", self.viejo.liberacion(self.primera.id, 1))
        r = self.emitir(self.guardar("nuevo.avreq", self.nuevo.solicitud()), "--reemplaza", str(liberacion), "--salida", str(self.salida / "n"))
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("cambio de equipo", r.salida)
        nueva = self.leer(next((self.salida / "n").glob("*.avlic")))
        self.assertEqual((nueva.id, nueva.serie, nueva.liberacion_pendiente), (self.primera.id, 2, False))
        self.assertNotEqual(nueva.huella, self.primera.huella)
        self.assertIsNotNone(Registro(self.registro).renglones()[-1]["reemplaza_sha256"])

    def test_la_liberacion_debe_ser_de_otro_equipo(self):
        liberacion = self.guardar("viejo.avrel", self.viejo.liberacion(self.primera.id, 1))
        r = self.emitir(self.guardar("otra.avreq", self.viejo.solicitud()), "--reemplaza", str(liberacion))
        self.assertEqual(r.codigo, 1)
        self.assertIn("MISMO equipo", r.error)

    def test_la_liberacion_debe_ser_del_equipo_al_que_se_emitio(self):
        ajeno = NodoDePrueba()
        liberacion = self.guardar("ajeno.avrel", ajeno.liberacion(self.primera.id, 1))
        r = self.emitir(self.guardar("nuevo.avreq", self.nuevo.solicitud()), "--reemplaza", str(liberacion))
        self.assertEqual(r.codigo, 1)
        self.assertIn("no es del equipo", r.error)

    def test_una_serie_que_el_registro_no_emitio(self):
        liberacion = self.guardar("v.avrel", self.viejo.liberacion(self.primera.id, 5))
        r = self.emitir(self.guardar("nuevo.avreq", self.nuevo.solicitud()), "--reemplaza", str(liberacion))
        self.assertEqual(r.codigo, 1)
        self.assertIn("no emitió", r.error)

    def test_una_liberacion_alterada(self):
        datos = bytearray(self.viejo.liberacion(self.primera.id, 1))
        datos[10] ^= 0x01
        r = self.emitir(self.guardar("nuevo.avreq", self.nuevo.solicitud()), "--reemplaza", str(self.guardar("m.avrel", bytes(datos))))
        self.assertEqual(r.codigo, 1)
        self.assertIn("no es válida", r.error)

    def test_si_el_equipo_viejo_no_enciende_sale_con_liberacion_pendiente(self):
        r = self.emitir(self.guardar("nuevo.avreq", self.nuevo.solicitud()), "--licencia", self.primera.id, "--liberacion-pendiente", "45", "--salida", str(self.salida / "p"))
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("PENDIENTE", r.salida)
        pendiente = self.leer(next((self.salida / "p").glob("*.avlic")))
        self.assertEqual((pendiente.id, pendiente.serie, pendiente.liberacion_pendiente, pendiente.liberacion_dias), (self.primera.id, 2, True, 45))
        e = estado.calcular(estado.Contexto(licencia=pendiente, ahora=AHORA, instalada_en=AHORA - 100 * DIA_MS, coincidencia=OK, licencia_instalada_en=AHORA))
        self.assertEqual((e.estado, e.dias_restantes), ("liberacion_pendiente", 45))

    def test_las_dos_vias_a_la_vez_no_se_aceptan(self):
        liberacion = self.guardar("v.avrel", self.viejo.liberacion(self.primera.id, 1))
        r = self.emitir(self.guardar("nuevo.avreq", self.nuevo.solicitud()), "--reemplaza", str(liberacion), "--liberacion-pendiente", "45")
        self.assertEqual(r.codigo, 1)


class VerificarTests(BaseConCarpeta):
    def setUp(self):
        super().setUp()
        self.sol = self.guardar("sol.avreq", self.nodo.solicitud())
        self.assertEqual(self.emitir(self.sol).codigo, 0)
        self.archivo = self.licencias()[0]

    def test_verifica_con_la_publica(self):
        r = correr(["verificar", str(self.archivo), "--publica", str(self.publica)])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("La firma es válida", r.salida)
        self.assertIn("Colegio San Martín", r.salida)

    def test_con_la_solicitud_comprueba_la_huella(self):
        bien = correr(["verificar", str(self.archivo), "--publica", str(self.publica), "--solicitud", str(self.sol)])
        self.assertEqual(bien.codigo, 0, bien.error)
        self.assertIn("corresponde a la solicitud", bien.salida)
        otra = self.guardar("otra.avreq", NodoDePrueba(valores=OTROS_VALORES).solicitud())
        mal = correr(["verificar", str(self.archivo), "--publica", str(self.publica), "--solicitud", str(otra)])
        self.assertEqual(mal.codigo, 1)
        self.assertIn("NO corresponde", mal.salida)

    def test_con_otra_llave_no_verifica(self):
        otra = self.dir / "otra"
        self.assertEqual(correr(["claves", "generar", "--kid", self.kid, "--salida", str(otra)]).codigo, 0)
        r = correr(["verificar", str(self.archivo), "--publica", str(otra / f"{self.kid}.pub")])
        self.assertEqual(r.codigo, 1)
        self.assertIn("NO es válida", r.error)
        sin_llave = correr(["verificar", str(self.archivo)])
        self.assertEqual(sin_llave.codigo, 1)

    def test_un_archivo_alterado_no_verifica(self):
        datos = bytearray(self.archivo.read_bytes())
        datos[40] ^= 0x01
        r = correr(["verificar", str(self.guardar("m.avlic", bytes(datos))), "--publica", str(self.publica)])
        self.assertEqual(r.codigo, 1)

    def test_el_texto_de_la_licencia_tambien_verifica(self):
        texto = licencia.a_texto(self.archivo.read_bytes())
        r = correr(["verificar", texto, "--publica", str(self.publica)])
        self.assertEqual(r.codigo, 0, r.error)
        r = correr(["verificar", texto + "x", "--publica", str(self.publica)])
        self.assertEqual(r.codigo, 1)

    def test_una_carpeta_de_publicas(self):
        r = correr(["verificar", str(self.archivo), "--publicas", str(self.llaves_dir)])
        self.assertEqual(r.codigo, 0, r.error)

    def test_verifica_con_el_archivo_en_el_formato_del_nodo(self):
        """La ceremonia deja también `<kid>.produccion.json`, el formato de `backend/licenciamiento/claves/produccion.json`: sirve para verificar."""
        entrada = self.llaves_dir / f"{self.kid}.produccion.json"
        self.assertTrue(entrada.is_file())
        r = correr(["verificar", str(self.archivo), "--publica", str(entrada)])
        self.assertEqual(r.codigo, 0, r.error)

    def test_las_llaves_de_desarrollo_del_nodo_nunca_se_toman_por_buenas(self):
        """Una carpeta con un desarrollo.json (como la del nodo) se ignora: aunque ahí estuviera la llave que firmó, no verificaría."""
        carpeta = self.dir / "claves-del-nodo"
        carpeta.mkdir()
        (carpeta / "desarrollo.json").write_text((self.llaves_dir / f"{self.kid}.produccion.json").read_text(encoding="utf-8"), encoding="utf-8")
        r = correr(["verificar", str(self.archivo), "--publicas", str(carpeta)])
        self.assertEqual(r.codigo, 1)
        self.assertIn("Indica la llave pública", r.error)
        (carpeta / "produccion.json").write_text((self.llaves_dir / f"{self.kid}.produccion.json").read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(correr(["verificar", str(self.archivo), "--publicas", str(carpeta)]).codigo, 0)

    def test_ninguna_mutacion_de_una_licencia_emitida_por_la_herramienta_se_acepta(self):
        datos = self.archivo.read_bytes()
        azar = random.Random(99)
        claves = {self.kid: self.publica_bytes}
        for _ in range(1500):
            malo = bytearray(datos)
            malo[azar.randrange(len(malo))] ^= 1 << azar.randrange(8)
            with self.assertRaises(Exception):
                licencia.leer(bytes(malo), claves)


class SolicitudYLiberacionTests(BaseConCarpeta):
    def test_ver_una_solicitud_de_hardware(self):
        r = correr(["solicitud", "ver", str(self.guardar("s.avreq", self.nodo.solicitud()))])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("hardware", r.salida)
        self.assertIn("licencia nueva", r.salida)
        self.assertNotIn("AVISOS", r.salida)

    def test_ver_una_solicitud_de_instalacion_avisa(self):
        nodo = NodoDePrueba(valores={huella.F_MACHINE_GUID: "To be filled by O.E.M.", huella.F_SMBIOS_UUID: "00000000-0000-0000-0000-000000000000"})
        r = correr(["solicitud", "ver", str(self.guardar("s.avreq", nodo.solicitud()))])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("instalación", r.salida)
        self.assertIn("AVISOS", r.salida)
        emitida = self.emitir(self.guardar("s2.avreq", nodo.solicitud()))
        self.assertEqual(emitida.codigo, 0, emitida.error)
        self.assertIn("más débil", emitida.salida)

    def test_la_solicitud_no_muestra_hashes_ni_identificadores_crudos(self):
        r = correr(["solicitud", "ver", str(self.guardar("s.avreq", self.nodo.solicitud()))])
        for valor in ("9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", "BRD-7781-ZX-2209", "CH-55-0192-77", "4C4C4544"):
            self.assertNotIn(valor, r.salida)

    def test_una_solicitud_con_el_reloj_atrasado_avisa(self):
        r = correr(["solicitud", "ver", str(self.guardar("s.avreq", self.nodo.solicitud(creada=AHORA - 400 * DIA_MS)))])
        self.assertIn("atrasado", r.salida)

    def test_ver_una_liberacion(self):
        r = correr(["liberacion", "ver", str(self.guardar("v.avrel", self.nodo.liberacion("a7a7a7a7-0001-4000-8000-000000000001", 3)))])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("serie 3", r.salida)
        malo = correr(["liberacion", "ver", str(self.guardar("m.avrel", b"nada"))])
        self.assertEqual(malo.codigo, 1)


class RegistroYPlanesTests(BaseConCarpeta):
    def test_ver_el_registro(self):
        vacio = correr(["registro", "ver", "--registro", str(self.registro)])
        self.assertEqual(vacio.codigo, 0)
        self.assertIn("todavía no hay emisiones", vacio.salida)
        self.assertEqual(self.emitir(self.guardar("s1.avreq", self.nodo.solicitud())).codigo, 0)
        self.assertEqual(self.emitir(self.guardar("s2.avreq", NodoDePrueba().solicitud()), "--salida", str(self.dir / "o2")).codigo, 0)
        r = correr(["registro", "ver", "--registro", str(self.registro)])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("Colegio San Martín", r.salida)
        self.assertIn("íntegra", r.salida)
        como_json = correr(["registro", "ver", "--registro", str(self.registro), "--json"])
        self.assertEqual(len(json.loads(como_json.salida.split("La cadena")[0])), 2)

    def test_un_registro_alterado_se_dice(self):
        self.assertEqual(self.emitir(self.guardar("s1.avreq", self.nodo.solicitud())).codigo, 0)
        texto = self.registro.read_text(encoding="utf-8").replace("Colegio San", "Colegio Sin")
        self.registro.write_text(texto, encoding="utf-8")
        r = correr(["registro", "ver", "--registro", str(self.registro)])
        self.assertEqual(r.codigo, 1)
        self.assertIn("ATENCIÓN", r.salida)

    def test_planes(self):
        r = correr(["planes"])
        self.assertEqual(r.codigo, 0, r.error)
        for nombre in ("anual-aula", "evaluacion"):
            self.assertIn(nombre, r.salida)
        self.assertNotIn("anual-sin-tope", r.salida)                                           # contradice el tamaño máximo que fijó el CTO
        self.assertIn("gracia de 30 días corridos exactos", r.salida)
        self.assertIn("tamaño máximo de un aula: 60 equipos y 1200 usuarios", r.salida)
        self.assertIn("60 equipos", r.salida)
        self.assertIn("provisional", r.salida)                                                 # lo demás (concurrentes, módulos, meses) todavía lo es

    def test_la_herramienta_sin_comando_muestra_ayuda(self):
        self.assertEqual(correr(["--version"]).codigo, 0)


class LlavesDeLaLineaDeComandosTests(BaseConCarpeta):
    def test_una_llave_no_se_sobrescribe(self):
        r = correr(["claves", "generar", "--kid", self.kid, "--salida", str(self.llaves_dir)])
        self.assertEqual(r.codigo, 1)
        self.assertIn("no se sobrescribe", r.error)

    def test_frase_corta_o_distinta(self):
        r = correr(["claves", "generar", "--kid", "otra", "--salida", str(self.dir / "x")], frase="corta")
        self.assertEqual(r.codigo, 1)
        frases = iter(["una frase larga y distinta A", "una frase larga y distinta B"])
        with mock.patch.object(cli, "_leer_frase", lambda pregunta="": next(frases)), contextlib.redirect_stderr(io.StringIO()) as error:
            codigo = cli.main(["claves", "generar", "--kid", "otra", "--salida", str(self.dir / "y")])
        self.assertEqual(codigo, 1)
        self.assertIn("no coinciden", error.getvalue())
        self.assertFalse((self.dir / "y" / "otra.avkey").exists())

    def test_claves_ver(self):
        r = correr(["claves", "ver", "--privada", str(self.privada)])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("abre con la frase de paso", r.salida)
        mala = correr(["claves", "ver", "--privada", str(self.privada)], frase="no es esta frase de paso")
        self.assertEqual(mala.codigo, 1)

    def test_kid_invalido(self):
        self.assertEqual(correr(["claves", "generar", "--kid", "Con Espacios", "--salida", str(self.dir / "z")]).codigo, 1)

    def test_rotacion_las_dos_llaves_firman_licencias_que_el_nodo_lee(self):
        """LIC-E-14: una licencia con la llave vieja y otra con la nueva verifican con las dos públicas."""
        nueva_dir = self.dir / "nuevas"
        self.assertEqual(correr(["claves", "generar", "--kid", "prueba-2027-1", "--salida", str(nueva_dir)]).codigo, 0)
        self.assertEqual(self.emitir(self.guardar("s1.avreq", self.nodo.solicitud())).codigo, 0)
        vieja = self.licencias()[0]
        r = correr(["emitir", "--solicitud", str(self.guardar("s2.avreq", NodoDePrueba().solicitud())), "--privada", str(nueva_dir / "prueba-2027-1.avkey"), "--registro", str(self.registro),
                    "--salida", str(self.dir / "o2"), "--hasta", "2027-10-31", "--yo-confirmo"])
        self.assertEqual(r.codigo, 0, r.error)
        nueva = next((self.dir / "o2").glob("*.avlic"))
        claves = {"prueba-2026-1": self.publica_bytes}
        from avacom_licencias import llaves
        kid2, pub2 = llaves.leer_publica((nueva_dir / "prueba-2027-1.pub").read_text(encoding="utf-8"))
        claves[kid2] = pub2
        self.assertEqual(licencia.leer(vieja.read_bytes(), claves).kid, "prueba-2026-1")
        self.assertEqual(licencia.leer(nueva.read_bytes(), claves).kid, "prueba-2027-1")
        with self.assertRaises(Exception):
            licencia.leer(nueva.read_bytes(), {"prueba-2026-1": self.publica_bytes})


if __name__ == "__main__":
    unittest.main()
