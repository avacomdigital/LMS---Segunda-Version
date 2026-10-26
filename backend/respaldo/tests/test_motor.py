"""
El motor de MOD-016 contra un nodo REAL: respaldar (completo e incremental), verificar, retención, exportar y RESTAURAR (TST-058, TST-059, TST-060, TST-063). Lo que se comprueba
es lo que el Maestro promete: consistente, cifrado, verificado, abortado ANTES de tocar lo vivo si algo no cuadra, con punto de retorno y con informe de qué se recupera y qué se pierde.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing

from respaldo.dominio import catalogos as cat

from .base import BaseRespaldo, R


def contar(ruta, tabla: str) -> int:
    with closing(sqlite3.connect(str(ruta))) as con:
        return con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


class Respaldar(BaseRespaldo):
    def test_un_respaldo_completo_queda_cifrado_verificado_catalogado_y_con_su_constancia(self):
        self.dejar_archivo("2026/entrega-de-matematicas.txt", b"mi entrega")
        f = self.respaldar()
        self.assertEqual((f["tipo"], f["estado"], f["restaurable"], f["disparo"]), ("completo", "completo_verificado", True, "manual"))
        self.assertEqual(f["archivos"], 1)
        escritos = self.archivos_escritos()
        avbak = [e for e in escritos if e.endswith(".avbak")]
        self.assertEqual(len(avbak), 1, escritos)
        self.assertTrue(any(e.startswith("Informes/constancia-") for e in escritos))
        self.assertIn("Informes/resumen-de-respaldos.csv", escritos)
        self.assertFalse([e for e in escritos if e.endswith(".parcial") or e.startswith("trabajo/")], "no debe quedar trabajo a medias")
        crudo = (self.carpeta / avbak[0]).read_bytes()
        for en_claro in (b"SQLite format", b"entrega-de-matematicas", b"Rectoria", b"IE San"):
            self.assertNotIn(en_claro, crudo, f"{en_claro!r} se lee en claro dentro del respaldo")

    def test_deja_su_rastro_en_el_historial_la_bitacora_y_la_cola_unica(self):
        f = self.respaldar()
        h = [x["tipo"] for x in self.admin.get(f"{R}/respaldos/{f['respaldo_id']}/").json()["historial"]]
        self.assertEqual(h, ["iniciado", "completo_ejecutado", "verificado"])
        self.assertEqual(self.acciones_asentadas(), ["respaldo.completo_ejecutado", "respaldo.verificado"])
        self.assertEqual(self.tipos_de_eventos(), [cat.EV_COMPLETO, cat.EV_VERIFICADO])

    def test_la_constancia_la_lee_la_administracion_y_no_trae_datos_de_personas(self):
        f = self.respaldar()
        r = self.admin.get(f"{R}/respaldos/{f['respaldo_id']}/constancia/")
        self.assertEqual(r.status_code, 200, r.content)
        texto = r.json()["texto"]
        for esperado in ("CONSTANCIA DE RESPALDO", "IE San José", "Terminado y verificado"):
            self.assertIn(esperado, texto)
        for prohibido in (self.ADMIN_DNI, self.DOCENTE_DNI, self.ESTUDIANTE_CODIGO, "Pérez", "Gómez", str(self.carpeta)):
            self.assertNotIn(prohibido, texto)
        d = self.admin.get(f"{R}/respaldos/{f['respaldo_id']}/constancia/?formato=txt")
        self.assertIn("attachment", d["Content-Disposition"])
        self.assertEqual(d["Content-Type"], "text/plain; charset=utf-8")
        csv = self.admin.get(f"{R}/resumen/?formato=csv")
        self.assertEqual(csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertTrue(csv.content.startswith(b"\xef\xbb\xbf"), "CSV con BOM para que Excel lea los acentos")

    def test_el_estado_para_la_administracion(self):
        sin = self.admin.get(f"{R}/estado/").json()
        self.assertTrue(sin["aviso_sin_respaldo"])
        self.assertIsNone(sin["ultimo_restaurable"])
        f = self.respaldar()
        e = self.admin.get(f"{R}/estado/").json()
        self.assertEqual((e["dias_sin_respaldo"], e["aviso_sin_respaldo"], e["ultimo_restaurable"]["respaldo_id"]), (0, False, f["respaldo_id"]))
        self.assertFalse(e["custodia"]["emitida"])
        self.reloj.avanzar(8 * cat.DIA_MS)
        self.assertTrue(self.admin.get(f"{R}/estado/").json()["aviso_sin_respaldo"], "MSG-066: sin respaldo en siete días")
        self.assertNotIn(str(self.carpeta), str(e), "el estado no revela rutas")

    def test_la_base_respaldada_es_una_copia_consistente_con_los_datos_del_nodo(self):
        f = self.respaldar()
        trabajo = self.s.almacen.carpeta_de_trabajo("lectura")
        from respaldo.dominio import formato
        with self.s.almacen.abrir(f["archivo"]) as a:
            m, cab = formato.leer_manifiesto(a)
            dek = formato.abrir_dek(m, self.s.clavero.clave_del_nodo(), None)
            for nombre, _i, bl in formato.recorrer(a, m, cab, dek):
                if nombre == formato.BASE_DE_DATOS:
                    (trabajo / "b.sqlite3").write_bytes(b"".join(bl))
                else:
                    list(bl)
        self.assertEqual(self.s.aplicador.comprobar_base(trabajo / "b.sqlite3")["integra"], True)
        self.assertEqual(contar(trabajo / "b.sqlite3", "m01_organizacion"), 1)
        self.assertGreaterEqual(contar(trabajo / "b.sqlite3", "m01_usuario"), 3)

    def test_el_incremental_necesita_un_completo_y_solo_lleva_lo_que_cambio(self):
        r = self.tecnico().post(f"{R}/respaldos/ahora/", {"tipo": "incremental"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "sin_respaldo_previo"))
        self.dejar_archivo("viejo.txt", b"viejo", mtime_ms=self.t0 - 5 * cat.DIA_MS)
        completo = self.respaldar()
        self.assertEqual(completo["archivos"], 1)
        self.reloj.avanzar(cat.DIA_MS)
        self.dejar_archivo("nuevo.txt", b"nuevo", mtime_ms=self.reloj.t)
        inc = self.respaldar("incremental")
        self.assertEqual((inc["tipo"], inc["base_id"], inc["archivos"], inc["estado"]), ("incremental", completo["respaldo_id"], 1, "completo_verificado"))

    def test_sin_espacio_no_se_empieza_y_se_dice_con_claridad_sin_dejar_basura(self):
        self.s.almacen.espacio_libre = lambda: 1024
        r = self.tecnico().post(f"{R}/respaldos/ahora/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "espacio_insuficiente"))
        self.assertFalse([e for e in self.archivos_escritos() if e.endswith((".avbak", ".parcial")) or e.startswith("trabajo/")])
        lista = self.admin.get(f"{R}/respaldos/").json()["respaldos"]
        self.assertEqual([x["estado"] for x in lista], ["fallido"])
        self.assertEqual(lista[0]["error"], "espacio_insuficiente")
        self.assertIn("respaldo.fallido", self.acciones_asentadas())

    def test_un_archivo_que_cambia_mientras_se_copia_hace_fallar_el_respaldo_y_lo_anterior_sigue_ahi(self):
        bueno = self.respaldar()
        ruta = self.dejar_archivo("vivo.log", b"a" * 5000)
        original = self.s.origen.archivos

        def archivos(incluir, desde):
            encontrados, omitidos = original(incluir, desde)
            ruta.write_bytes(b"a" * 9000)                    # crece DESPUÉS de medirlo
            return encontrados, omitidos

        self.s.origen.archivos = archivos
        r = self.tecnico().post(f"{R}/respaldos/ahora/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (409, "respaldo_fallido", "archivo_cambio"))
        self.assertEqual(self.ficha(bueno["respaldo_id"])["estado"], "completo_verificado")

    def test_un_respaldo_en_marcha_no_admite_otro(self):
        self.s.en_operacion.acquire()
        try:
            r = self.tecnico().post(f"{R}/respaldos/ahora/", {}, format="json")
        finally:
            self.s.en_operacion.release()
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "respaldo_en_curso"))


class Verificar(BaseRespaldo):
    def test_un_byte_cambiado_en_el_archivo_lo_marca_no_verificado_sin_descartarlo(self):
        f = self.respaldar()
        ruta = self.carpeta / f["archivo"]
        crudo = bytearray(ruta.read_bytes())
        crudo[len(crudo) // 2] ^= 0xFF
        ruta.write_bytes(bytes(crudo))
        r = self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/verificar/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["verificado"], r.json()["motivo"]), (False, "huella_distinta"))
        g = self.ficha(f["respaldo_id"])
        self.assertEqual((g["estado"], g["restaurable"], g["existe"]), ("completo_no_verificado", False, True))
        self.assertTrue(ruta.exists(), "un respaldo que falla la verificación no se descarta")
        self.assertEqual(self.admin.get(f"{R}/estado/").json()["ultimo_restaurable"], None)

    def test_verificar_de_nuevo_un_respaldo_sano_lo_deja_verificado_y_publica_el_evento(self):
        f = self.respaldar()
        r = self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/verificar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["verificado"]), (200, True))
        self.assertEqual(self.tipos_de_eventos().count(cat.EV_VERIFICADO), 2)

    def test_el_incremental_no_se_verifica_si_falta_su_base(self):
        completo = self.respaldar()
        self.reloj.avanzar(cat.DIA_MS)
        inc = self.respaldar("incremental")
        (self.carpeta / completo["archivo"]).unlink()
        r = self.tecnico().post(f"{R}/respaldos/{inc['respaldo_id']}/verificar/", {}, format="json")
        self.assertEqual((r.json()["verificado"], r.json()["motivo"]), (False, "cadena_incompleta"))


class Retencion(BaseRespaldo):
    def test_los_que_sobran_caducan_y_su_archivo_se_borra_pero_nunca_el_ultimo_restaurable(self):
        r = self.tecnico().post(f"{R}/programacion/", {"retencion": 3}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        ids = []
        for _ in range(5):
            self.reloj.avanzar(cat.HORA_MS)
            ids.append(self.respaldar()["respaldo_id"])
        estados = {i: self.ficha(i)["estado"] for i in ids}
        self.assertEqual([estados[i] for i in ids], ["caducado", "caducado", "completo_verificado", "completo_verificado", "completo_verificado"])
        self.assertEqual(len([e for e in self.archivos_escritos() if e.endswith(".avbak")]), 3)
        self.assertEqual(self.acciones_asentadas().count("respaldo.caducado"), 2)


class Exportar(BaseRespaldo):
    def unidad(self) -> str:
        u = self.tecnico().get(f"{R}/destinos/").json()["unidades"]
        self.assertEqual(len(u), 1)
        return u[0]["id"]

    def test_exportar_copia_el_respaldo_y_su_constancia_a_la_unidad_con_un_pase_y_el_pase_vale_una_vez(self):
        f = self.respaldar()
        pase = self.pase(cat.P_EXPORTAR)
        r = self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/exportar/", {"unidad": self.unidad(), "pase": pase}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        destino = self.usb / "AVACOM" / "Respaldos"
        self.assertTrue((destino / f["archivo"]).exists())
        self.assertTrue(any(p.name.startswith("constancia-") for p in destino.iterdir()))
        self.assertEqual((destino / f["archivo"]).read_bytes(), (self.carpeta / f["archivo"]).read_bytes())
        self.assertEqual(self.ficha(f["respaldo_id"])["estado"], "exportado")
        otra = self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/exportar/", {"unidad": self.unidad(), "pase": pase}, format="json")
        self.assertEqual((otra.status_code, otra.json()["motivo"]), (403, "ya_usado"))

    def test_sin_pase_o_con_un_pase_de_otra_operacion_no_sale_nada_del_equipo(self):
        f = self.respaldar()
        r = self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/exportar/", {"unidad": self.unidad()}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "pase_requerido"))
        r = self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/exportar/", {"unidad": self.unidad(), "pase": self.pase(cat.P_RESTAURAR)}, format="json")
        self.assertEqual((r.status_code, r.json()["motivo"]), (403, "accion_no_incluida"))
        self.assertFalse((self.usb / "AVACOM").exists())
        self.assertIn("respaldo.pase_rechazado", self.acciones_asentadas())

    def test_la_unidad_se_identifica_por_un_id_opaco_nunca_por_una_ruta(self):
        f = self.respaldar()
        r = self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/exportar/", {"unidad": str(self.usb), "pase": self.pase(cat.P_EXPORTAR)}, format="json")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn(str(self.usb), str(self.tecnico().get(f"{R}/destinos/").json()))


class Restaurar(BaseRespaldo):
    def restaurar(self, cuerpo: dict, cliente=None):
        return (cliente or self.tecnico()).post(f"{R}/restaurar/", {"motivo": "equipo_danado", **cuerpo}, format="json")

    def test_restaurar_devuelve_la_base_y_los_archivos_deja_punto_de_retorno_informe_y_cierra_el_pase(self):
        evidencia = self.dejar_archivo("2026/trabajo.txt", b"version original")
        f = self.respaldar()
        evidencia.write_bytes(b"version alterada despues")                  # lo que se pierde al restaurar
        (self.archivos / "2026" / "otro.txt").write_bytes(b"sobra")
        self.reloj.avanzar(3 * cat.HORA_MS)
        pase = self.pase(cat.P_RESTAURAR)
        r = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": pase, "nota": "se dañó el disco"})
        self.assertEqual(r.status_code, 200, r.content)
        res = r.json()
        self.assertTrue(res["ok"])
        self.assertEqual(contar(self.base_viva, "m01_organizacion"), 1, "la base viva recibió la del respaldo")
        self.assertEqual(evidencia.read_bytes(), b"version original")
        self.assertEqual((self.archivos / "2026" / "otro.txt").read_bytes(), b"sobra", "no se borra lo que sobra")
        self.assertEqual(self.tras.llamadas, [False], "se rehizo lo derivado (esquema, nodo, sesiones, licencia, índices) en el mismo equipo")
        self.assertEqual(res["perdidas"]["horas"], 3.0)
        self.assertIn("QUÉ SE PIERDE", res["informe_texto"])
        self.assertIn(res["informe"], self.admin.get(f"{R}/informes/").json()["informes"], "la administración puede leer el informe")
        retorno = self.ficha(res["punto_de_retorno"])
        self.assertEqual((retorno["disparo"], retorno["estado"]), ("previo_a_restauracion", "completo_verificado"))
        self.assertIn("respaldo.restauracion_completada", self.acciones_asentadas())
        self.assertIn(cat.EV_RESTAURADO, self.tipos_de_eventos())
        otra = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": pase})
        self.assertEqual((otra.status_code, otra.json()["motivo"]), (403, "ya_usado"))

    def test_TST_059_un_respaldo_truncado_aborta_antes_de_tocar_nada_y_no_gasta_el_pase(self):
        f = self.respaldar()
        ruta = self.carpeta / f["archivo"]
        ruta.write_bytes(ruta.read_bytes()[:-5000])
        pase = self.pase(cat.P_RESTAURAR)
        antes = len([e for e in self.archivos_escritos() if e.endswith(".avbak")])
        r = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": pase})
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "restauracion_abortada"))
        self.assertEqual(contar(self.base_viva, "sqlite_master"), 0, "la base viva no se tocó")
        self.assertEqual(self.tras.llamadas, [])
        self.assertEqual(len([e for e in self.archivos_escritos() if e.endswith(".avbak")]), antes, "ni siquiera se tomó un punto de retorno")
        self.assertIn("respaldo.restauracion_abortada", self.acciones_asentadas())
        from respaldo.models import PaseUsado
        self.assertFalse(PaseUsado.objects.exists(), "un pase que no se llegó a usar sigue valiendo")

    def test_con_una_clase_abierta_no_se_restaura_y_no_se_gasta_el_pase(self):
        f = self.respaldar()
        self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": self.docente_id}, format="json")
        r = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR)})
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "sesion_activa"))
        self.assertEqual(contar(self.base_viva, "sqlite_master"), 0)
        from respaldo.models import PaseUsado
        self.assertFalse(PaseUsado.objects.exists())

    def test_BR_102_en_un_equipo_nuevo_hace_falta_el_codigo_de_custodia_y_con_el_se_restaura_y_se_reancla(self):
        codigo = self.emitir_custodia()
        self.dejar_archivo("2026/a.txt", b"contenido")
        f = self.respaldar()
        self.assertTrue(f["con_custodia"])
        # el «equipo nuevo»: otra clave y otra identidad
        (self.carpeta / "estado" / "nodo.key").unlink()
        (self.carpeta / "estado" / "nodo.json").unlink()
        from respaldo.infraestructura.clavero import ClaveroDelNodo
        self.s.clavero = ClaveroDelNodo(self.carpeta)
        viejo = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR)})
        self.assertEqual((viejo.status_code, viejo.json()["codigo"], viejo.json()["motivo"]), (409, "restauracion_abortada", "clave_no_disponible"))
        otro = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR), "custodia": "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAA"})
        self.assertEqual(otro.status_code, 400, "un código mal formado ni se intenta")
        mal = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR), "custodia": codigo.replace(codigo[0], "A" if codigo[0] != "A" else "B", 1)})
        self.assertEqual(mal.status_code, 400)
        r = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR), "custodia": codigo.lower()})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["nueva_huella"])
        self.assertEqual(self.tras.llamadas, [True])
        nuevo = self.respaldar()                                                  # el equipo nuevo conserva la custodia: sus respaldos siguen abriéndose con el mismo código
        self.assertTrue(nuevo["con_custodia"])

    def test_restaurar_un_incremental_aplica_su_cadena_completa(self):
        self.dejar_archivo("a.txt", b"de la base", mtime_ms=self.t0 - 3 * cat.DIA_MS)
        completo = self.respaldar()
        self.reloj.avanzar(cat.DIA_MS)
        self.dejar_archivo("b.txt", b"del incremental", mtime_ms=self.reloj.t)
        inc = self.respaldar("incremental")
        for n in ("a.txt", "b.txt"):
            (self.archivos / n).unlink()
        r = self.restaurar({"respaldo_id": inc["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR)})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((self.archivos / "a.txt").read_bytes(), b"de la base")
        self.assertEqual((self.archivos / "b.txt").read_bytes(), b"del incremental")
        self.assertEqual(completo["tipo"], "completo")

    def test_restaurar_desde_una_unidad_externa_en_un_equipo_sin_ese_respaldo(self):
        f = self.respaldar()
        self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/exportar/", {"unidad": self.tecnico().get(f"{R}/destinos/").json()["unidades"][0]["id"], "pase": self.pase(cat.P_EXPORTAR)},
                            format="json")
        (self.carpeta / f["archivo"]).unlink()                                    # el equipo ya no tiene el archivo: sólo la memoria USB
        candidatos = self.tecnico().get(f"{R}/destinos/").json()["candidatos"]
        self.assertEqual([c["nombre"] for c in candidatos], [f["archivo"]])
        r = self.restaurar({"candidato": candidatos[0]["id"], "pase": self.pase(cat.P_RESTAURAR)})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(contar(self.base_viva, "m01_organizacion"), 1)

    def test_los_datos_de_la_peticion_se_validan(self):
        f = self.respaldar()
        pase = self.pase(cat.P_RESTAURAR)
        casos = [({"pase": pase}, "respaldo_id"), ({"respaldo_id": f["respaldo_id"], "candidato": "x", "pase": pase}, "respaldo_id"), ({"respaldo_id": f["respaldo_id"], "pase": pase, "motivo": "porque si"}, "motivo"),
                 ({"respaldo_id": f["respaldo_id"], "pase": pase, "nota": "x" * 400}, "nota")]
        for cuerpo, campo in casos:
            r = self.tecnico().post(f"{R}/restaurar/", {"motivo": "otro", **cuerpo}, format="json")
            self.assertEqual((r.status_code, r.json().get("campo")), (400, campo), cuerpo)
        r = self.restaurar({"respaldo_id": "no-existe", "pase": pase})
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))
        self.assertEqual(self.restaurar({"respaldo_id": f["respaldo_id"], "pase": "no es base64!!"}).status_code, 400)

    def test_restaurar_un_modulo_dice_con_claridad_que_hoy_ninguno_lo_declara(self):
        r = self.tecnico().post(f"{R}/restaurar/modulo/", {"modulo": "gradebook", "pase": self.pase(cat.P_RESTAURAR_MODULO)}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "modulo_sin_restauracion_aislada"))


class Catalogo(BaseRespaldo):
    def test_un_respaldo_que_la_base_no_conoce_se_cataloga_desde_la_carpeta_y_uno_que_ya_no_esta_se_marca(self):
        a = self.respaldar()
        self.reloj.avanzar(cat.HORA_MS)
        b = self.respaldar()
        from respaldo.models import Historial, Respaldo
        Historial.objects.filter(respaldo_id=a["respaldo_id"]).delete()          # una restauración devolvió la base a antes de que existiera «a»
        Respaldo.objects.filter(respaldo_id=a["respaldo_id"]).delete()
        (self.carpeta / b["archivo"]).unlink()
        from respaldo.aplicacion.puertos import Actor
        from respaldo.aplicacion.motor import Motor
        r = Motor(self.s).reconciliar(Actor(id="sistema"))
        self.assertEqual((r["catalogados"], r["ausentes"]), ([a["respaldo_id"]], [b["respaldo_id"]]))
        self.assertEqual(self.ficha(a["respaldo_id"])["estado"], "completo_no_verificado", "catalogado pero sin verificar: el vigilante lo verificará")
        self.assertEqual(self.ficha(b["respaldo_id"])["estado"], "caducado")


class Endurecimiento(BaseRespaldo):
    """Lo que encontró la revisión independiente (2026-10-26) y quedó corregido."""

    def restaurar(self, cuerpo: dict):
        return self.tecnico().post(f"{R}/restaurar/", {"motivo": "otro", **cuerpo}, format="json")

    def test_la_custodia_se_reemplaza_solo_con_pase_y_el_pase_no_se_reusa(self):
        self.emitir_custodia()
        r = self.tecnico().post(f"{R}/custodia/emitir/", {"reemplazar": True}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "pase_requerido"))
        pase = self.pase(cat.P_PROGRAMAR)
        self.assertEqual(self.tecnico().post(f"{R}/custodia/emitir/", {"reemplazar": True, "pase": pase}, format="json").status_code, 201)
        r = self.tecnico().post(f"{R}/custodia/emitir/", {"reemplazar": True, "pase": pase}, format="json")
        self.assertEqual((r.status_code, r.json()["motivo"]), (403, "ya_usado"))

    def test_si_fallan_los_archivos_tras_aplicar_la_base_se_rehace_lo_derivado_y_se_dice_parcial(self):
        self.dejar_archivo("a.txt", b"1")
        f = self.respaldar()

        def falla(*a, **k):
            raise OSError("archivo bloqueado")

        self.s.aplicador.aplicar_archivos = falla
        r = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR)})
        self.assertEqual(r.status_code, 200, r.content)
        j = r.json()
        self.assertEqual((j["ok"], j["parcial"], j["fallos_archivos"]), (False, True, ["evidencias"]))
        self.assertEqual(self.tras.llamadas, [False], "aun así se revocaron sesiones, se saltó la secuencia y se rehicieron los índices")
        self.assertIn("PARCIAL", j["informe_texto"])
        self.assertIn("evidencias", j["informe_texto"])
        self.assertIn(cat.EV_RESTAURADO, self.tipos_de_eventos())

    def test_los_pases_gastados_antes_de_restaurar_siguen_anotados_despues(self):
        from respaldo.models import PaseUsado
        f = self.respaldar()
        u = self.tecnico().get(f"{R}/destinos/").json()["unidades"][0]["id"]
        self.assertEqual(self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/exportar/", {"unidad": u, "pase": self.pase(cat.P_EXPORTAR)}, format="json").status_code, 200)
        gastado = PaseUsado.objects.get(permiso="backup.export").pase_id
        guardado = {}

        # lo que haría la base restaurada: no conocer el pase gastado después del respaldo
        original = self.s.aplicador.aplicar_base

        def aplicar_y_olvidar(ruta):
            r = original(ruta)
            PaseUsado.objects.all().delete()
            guardado["borrado"] = True
            return r

        self.s.aplicador.aplicar_base = aplicar_y_olvidar
        self.assertEqual(self.restaurar({"respaldo_id": f["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR)}).status_code, 200)
        self.assertTrue(guardado["borrado"])
        self.assertTrue(PaseUsado.objects.filter(pase_id=gastado).exists(), "el pase gastado antes de restaurar se vuelve a anotar: no revive")
        self.assertEqual(PaseUsado.objects.filter(permiso="backup.restore").count(), 1)

    def test_un_respaldo_sin_verificar_no_sirve_de_base_para_un_incremental(self):
        self.s.config = type(self.s.config)(**{**self.s.config.__dict__, "verificar_al_terminar": False})
        self.respaldar()                                                          # completo_no_verificado
        r = self.tecnico().post(f"{R}/respaldos/ahora/", {"tipo": "incremental"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "sin_respaldo_previo"))

    def test_el_calendario_hace_otro_completo_si_el_ultimo_completo_no_es_restaurable(self):
        from datetime import datetime, timezone
        self.s.config = type(self.s.config)(**{**self.s.config.__dict__, "verificar_al_terminar": False})
        self.assertEqual(self.tecnico().post(f"{R}/programacion/", {"hora_min": 120}, format="json").status_code, 200)
        from unittest import mock
        from respaldo.aplicacion.vigilante import Tick
        self.reloj.t = int(datetime(2026, 10, 26, 3, tzinfo=timezone.utc).timestamp() * 1000)
        with mock.patch.object(Tick, "_verificar", lambda *a, **k: None):             # que el vigilante no lo verifique en el mismo ciclo
            self.assertEqual(self.tick()["pasos"]["programado"], "completo")
            self.reloj.t += cat.DIA_MS
            self.assertEqual(self.tick()["pasos"]["programado"], "completo", "el de ayer nunca se verificó: no cuenta como el completo de la semana")

    def test_un_manifiesto_ajeno_no_creible_no_entra_al_catalogo_ni_lo_rompe(self):
        import io
        from respaldo.dominio import cripto, formato
        dek, nodo = cripto.generar_clave(), cripto.generar_clave()
        for nombre, base in (("ajeno-futuro.avbak", {"respaldo_id": "11111111-1111-4111-8111-111111111111", "tipo": "completo", "creado_en": self.reloj.t + 5 * cat.DIA_MS,
                                                     "disparo": "de_otro_producto"}),
                             ("ajeno-disparo.avbak", {"respaldo_id": "22222222-2222-4222-8222-222222222222", "tipo": "completo", "creado_en": self.reloj.t - cat.HORA_MS,
                                                      "disparo": "de_otro_producto"})):
            salida = io.BytesIO()
            formato.escribir(salida, base, [formato.Entrada("base.sqlite3", "primario", 3, lambda: io.BytesIO(b"abc"))], dek, formato.envolver_dek(base["respaldo_id"], dek, nodo, None))
            (self.carpeta / nombre).write_bytes(salida.getvalue())
        (self.carpeta / "roto.avbak").write_bytes(b"AVBK" + b"\x00" * 30)
        from respaldo.aplicacion.motor import Motor
        from respaldo.aplicacion.puertos import Actor
        r = Motor(self.s).reconciliar(Actor(id="sistema"))
        self.assertEqual(r["catalogados"], ["22222222-2222-4222-8222-222222222222"], "el del futuro no entra; el de un disparo desconocido entra como manual")
        self.assertEqual(self.ficha("22222222-2222-4222-8222-222222222222")["disparo"], "manual")

    def test_un_manifiesto_con_ids_que_no_son_uuid_se_rechaza(self):
        import io
        from respaldo.dominio import cripto, formato
        from respaldo.dominio.errores import RespaldoRechazado
        dek, nodo = cripto.generar_clave(), cripto.generar_clave()
        for mal in ({"respaldo_id": "no-es-uuid"}, {"respaldo_id": "11111111-1111-4111-8111-111111111111", "base_id": "x" * 40}):
            salida = io.BytesIO()
            formato.escribir(salida, {"tipo": "completo", "creado_en": 1, **mal}, [formato.Entrada("a.txt", "primario", 1, lambda: io.BytesIO(b"a"))], dek,
                             formato.envolver_dek(mal["respaldo_id"], dek, nodo, None))
            with self.assertRaises(RespaldoRechazado):
                formato.leer_manifiesto(io.BytesIO(salida.getvalue()))

    def test_los_parametros_de_scrypt_del_manifiesto_no_se_obedecen(self):
        from respaldo.dominio import cripto, formato
        from respaldo.dominio.errores import ClaveNoDisponible
        codigo = cripto.generar_codigo_de_custodia()
        sal = cripto.generar_sal()
        kek = cripto.clave_de_custodia(cripto.secreto_de_custodia(codigo), sal)
        dek = cripto.generar_clave()
        rid = "33333333-3333-4333-8333-333333333333"
        claves = formato.envolver_dek(rid, dek, cripto.generar_clave(), (kek, sal))
        for n, r, p in ((2 ** 15, 8, 4000), (2 ** 15, "ocho", 1), (2 ** 20, 8, 1)):
            claves["custodia"].update({"n": n, "r": r, "p": p})
            with self.assertRaises(ClaveNoDisponible):
                formato.abrir_dek({"respaldo_id": rid, "claves": claves}, None, codigo)

    def test_los_archivos_restaurados_llevan_la_fecha_de_la_restauracion(self):
        import time
        ruta = self.dejar_archivo("a.txt", b"original", mtime_ms=self.t0 - 10 * cat.DIA_MS)
        f = self.respaldar()
        ruta.write_bytes(b"cambiado")
        self.assertEqual(self.restaurar({"respaldo_id": f["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR)}).status_code, 200)
        self.assertEqual(ruta.read_bytes(), b"original")
        self.assertGreater(ruta.stat().st_mtime, time.time() - 120, "la fecha de modificación es la de AHORA: el siguiente incremental lo lleva")

    def test_la_nota_libre_del_tecnico_no_llega_al_historial_que_lee_la_administracion(self):
        f = self.respaldar()
        r = self.restaurar({"respaldo_id": f["respaldo_id"], "pase": self.pase(cat.P_RESTAURAR), "nota": "El hijo de la señora Martha borró las notas"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertNotIn("Martha", self.admin.get(f"{R}/respaldos/{f['respaldo_id']}/").content.decode())
        self.assertNotIn("Martha", r.content.decode())

    def test_al_restaurar_desde_una_unidad_solo_se_trae_lo_necesario(self):
        a = self.respaldar()
        self.reloj.avanzar(cat.HORA_MS)
        b = self.respaldar()
        u = self.tecnico().get(f"{R}/destinos/").json()["unidades"][0]["id"]
        for x in (a, b):
            self.assertEqual(self.tecnico().post(f"{R}/respaldos/{x['respaldo_id']}/exportar/", {"unidad": u, "pase": self.pase(cat.P_EXPORTAR)}, format="json").status_code, 200)
        traidos = []
        original = self.s.unidades.traer
        self.s.unidades.traer = lambda cid, destino: (traidos.append(cid), original(cid, destino))[1]
        candidatos = {c["nombre"]: c["id"] for c in self.tecnico().get(f"{R}/destinos/").json()["candidatos"]}
        r = self.restaurar({"candidato": candidatos[b["archivo"]], "pase": self.pase(cat.P_RESTAURAR)})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(traidos, [candidatos[b["archivo"]]], "un completo no tiene bases: no se copia nada más de la unidad")
