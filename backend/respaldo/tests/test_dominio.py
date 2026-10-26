"""
El dominio puro de MOD-016: el pase de soporte de AVACOM (D-2), el calendario y la retención, el estado derivado del historial y los informes para el personal administrativo.
"""
from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import SimpleTestCase

from respaldo.dominio import catalogos as cat
from respaldo.dominio import estados, informes, pase, programacion
from respaldo.dominio.errores import DatosInvalidos, PaseInvalido

from . import emisor

AHORA = 1_790_000_000_000
PUBLICAS = {"sop-dev-1": bytes.fromhex(emisor.publica_hex(1))}


class Pase(SimpleTestCase):
    def abrir(self, datos: bytes, ahora: int = AHORA, permiso: str = cat.P_RESTAURAR, nodo: str = "nodo-a"):
        return pase.abrir(datos, PUBLICAS, ahora, permiso, nodo)

    def motivo(self, datos: bytes, **kw) -> str:
        with self.assertRaises(PaseInvalido) as r:
            self.abrir(datos, **kw)
        return r.exception.motivo

    def test_un_pase_valido_dice_quien_para_que_y_hasta_cuando(self):
        p = self.abrir(emisor.emitir([cat.P_RESTAURAR], AHORA, tecnico="Ana de AVACOM", horas=2))
        self.assertEqual((p.tecnico, p.acciones, p.nodo, p.vence_en - p.emitido_en), ("Ana de AVACOM", (cat.P_RESTAURAR,), "*", 2 * cat.HORA_MS))

    def test_vencido_y_aun_no_vigente(self):
        datos = emisor.emitir([cat.P_RESTAURAR], AHORA, horas=1)
        self.assertEqual(self.motivo(datos, ahora=AHORA + 2 * cat.HORA_MS), "vencido")
        self.assertEqual(self.motivo(datos, ahora=AHORA - cat.HORA_MS), "aun_no_vigente")
        self.abrir(datos, ahora=AHORA - cat.TOLERANCIA_PASE_MS + 1000)           # el reloj de quien emite y el del nodo no coinciden al milisegundo

    def test_una_vigencia_de_mas_de_un_dia_se_rechaza(self):
        self.assertEqual(self.motivo(emisor.emitir([cat.P_RESTAURAR], AHORA, horas=25)), "vigencia_excesiva")
        self.assertEqual(self.motivo(emisor.emitir([cat.P_RESTAURAR], AHORA, emitido_en=AHORA, vence_en=AHORA)), "vigencia_excesiva")

    def test_solo_vale_para_lo_que_dice(self):
        datos = emisor.emitir([cat.P_EXPORTAR], AHORA)
        self.assertEqual(self.motivo(datos, permiso=cat.P_RESTAURAR), "accion_no_incluida")

    def test_un_pase_para_un_equipo_no_vale_en_otro_y_el_comodin_vale_en_cualquiera(self):
        self.assertEqual(self.motivo(emisor.emitir([cat.P_RESTAURAR], AHORA, nodo="nodo-b")), "otro_equipo")
        self.abrir(emisor.emitir([cat.P_RESTAURAR], AHORA, nodo="nodo-a"))
        self.abrir(emisor.emitir([cat.P_RESTAURAR], AHORA, nodo="*"), nodo="cualquiera")

    def test_firmado_con_otra_llave_o_con_un_kid_que_no_se_conoce(self):
        ajena = Ed25519PrivateKey.generate()
        payload = {"pase_id": str(uuid.uuid4()), "tecnico": "x", "emitido_en": AHORA, "vence_en": AHORA + cat.HORA_MS, "acciones": [cat.P_RESTAURAR], "nodo": "*"}
        self.assertEqual(self.motivo(pase.firmar(payload, "sop-dev-1", ajena)), "firma_invalida")
        self.assertEqual(self.motivo(pase.firmar(payload, "sop-2026-1", ajena)), "kid_desconocido")

    def test_cambiar_cualquier_byte_invalida_el_pase(self):
        datos = emisor.emitir([cat.P_RESTAURAR], AHORA)
        for i in range(len(datos)):
            mal = bytearray(datos)
            mal[i] ^= 0x01
            with self.assertRaises(PaseInvalido, msg=f"byte {i}"):
                self.abrir(bytes(mal))

    def test_el_kid_cambiado_no_se_acepta_con_la_misma_firma(self):
        datos = emisor.emitir([cat.P_RESTAURAR], AHORA)
        mal = datos[:4] + bytes([9]) + b"sop-dev-X" + datos[5 + datos[4]:]
        self.assertIn(self.motivo(mal), ("kid_desconocido", "firma_invalida", "formato"))

    def test_basura(self):
        for datos in (b"", b"AVSP", b"x" * 200, base64.b64decode(b"AAAA") * 40):
            self.assertIn(self.motivo(datos), ("formato", "kid_desconocido"))

    def test_una_firma_universal_con_un_punto_de_orden_pequeno_no_se_acepta(self):
        cuerpo = json.dumps({"formato": 1, "pase_id": "x", "tecnico": "t", "emitido_en": AHORA, "vence_en": AHORA + cat.HORA_MS, "acciones": [cat.P_RESTAURAR], "nodo": "*"},
                            sort_keys=True, separators=(",", ":")).encode()
        universal = b"AVSP" + bytes([2]) + b"zz" + bytes([1]) + bytes(31) + bytes(32) + cuerpo       # R = identidad, S = 0
        llaves = {"zz": bytes([1]) + bytes(31)}                                                       # A = identidad
        with self.assertRaises(PaseInvalido) as r:
            pase.abrir(universal, llaves, AHORA, cat.P_RESTAURAR, "n")
        self.assertEqual(r.exception.motivo, "firma_invalida")

    def test_un_pase_no_puede_autorizar_lo_que_no_es_suyo(self):
        for permiso in (cat.P_LEER, cat.P_EJECUTAR, "identity.escalation.grant", "otra.cosa"):
            self.assertEqual(self.motivo(emisor.emitir([permiso], AHORA)), "contenido")


class Calendario(SimpleTestCase):
    # 2026-10-26 es lunes. 1_790_000_000_000 ms = 2026-09-21 ... se calculan los instantes a partir de la fecha para no depender de la aritmética a mano.
    @staticmethod
    def ms(anio, mes, dia, hora=0, minuto=0) -> int:
        from datetime import datetime, timezone
        return int(datetime(anio, mes, dia, hora, minuto, tzinfo=timezone.utc).timestamp() * 1000)

    def test_el_horario_pasado_mas_reciente_respeta_la_hora_los_dias_y_la_zona(self):
        p = programacion.Programa(hora_min=2 * 60, dias=(0, 2))                               # lunes y miércoles a las 02:00
        lunes_03 = self.ms(2026, 10, 26, 3)
        self.assertEqual(programacion.ultimo_horario(p, lunes_03, 0), self.ms(2026, 10, 26, 2))
        martes = self.ms(2026, 10, 27, 12)
        self.assertEqual(programacion.ultimo_horario(p, martes, 0), self.ms(2026, 10, 26, 2))
        lunes_01 = self.ms(2026, 10, 26, 1)                                                    # todavía no son las 02:00 del lunes: el último fue el miércoles anterior
        self.assertEqual(programacion.ultimo_horario(p, lunes_01, 0), self.ms(2026, 10, 21, 2))
        bogota = -300                                                                            # UTC-5: las 02:00 locales son las 07:00 UTC
        self.assertEqual(programacion.ultimo_horario(p, self.ms(2026, 10, 26, 8), bogota), self.ms(2026, 10, 26, 7))

    def test_toca_si_ningun_automatico_cubrio_el_horario_y_se_pone_al_dia_una_vez(self):
        p = programacion.Programa(hora_min=120, dias=programacion.Programa().dias)
        ahora = self.ms(2026, 10, 26, 9)                                                       # el equipo estuvo apagado a las 02:00
        self.assertEqual(programacion.corresponde(p, ahora, None, 0), self.ms(2026, 10, 26, 2))
        self.assertEqual(programacion.corresponde(p, ahora, self.ms(2026, 10, 25, 2), 0), self.ms(2026, 10, 26, 2))
        self.assertIsNone(programacion.corresponde(p, ahora, self.ms(2026, 10, 26, 2, 5), 0))
        self.assertIsNone(programacion.corresponde(p, ahora, self.ms(2026, 10, 26, 8), 0), "un respaldo hecho a las 08:00 ya cubre el horario de las 02:00")
        self.assertIsNone(programacion.corresponde(programacion.Programa(activo=False), ahora, None, 0))

    def test_siguiente_horario(self):
        p = programacion.Programa(hora_min=120, dias=(1,))                                     # los martes a las 02:00
        self.assertEqual(programacion.siguiente_horario(p, self.ms(2026, 10, 26, 12), 0), self.ms(2026, 10, 27, 2))
        self.assertEqual(programacion.siguiente_horario(p, self.ms(2026, 10, 27, 1), 0), self.ms(2026, 10, 27, 2))
        self.assertEqual(programacion.siguiente_horario(p, self.ms(2026, 10, 27, 3), 0), self.ms(2026, 11, 3, 2))

    def test_completo_cada_siete_dias_y_entre_medias_incremental(self):
        p = programacion.Programa()
        self.assertEqual(programacion.tipo_que_toca(p, None, AHORA), cat.T_COMPLETO)
        self.assertEqual(programacion.tipo_que_toca(p, AHORA - 2 * cat.DIA_MS, AHORA), cat.T_INCREMENTAL)
        self.assertEqual(programacion.tipo_que_toca(p, AHORA - 7 * cat.DIA_MS + cat.HORA_MS, AHORA), cat.T_COMPLETO, "con medio día de holgura")

    def test_validar_rechaza_lo_absurdo_y_conserva_lo_que_no_se_toca(self):
        actual = programacion.Programa(hora_min=300, retencion=20)
        nuevo = programacion.validar({"hora_min": 60}, actual)
        self.assertEqual((nuevo.hora_min, nuevo.retencion), (60, 20))
        for malo in ({"hora_min": 1440}, {"hora_min": -1}, {"hora_min": "2"}, {"dias": []}, {"dias": [7]}, {"retencion": 2}, {"retencion": True}, {"destino": "nube"}, {"activo": "si"},
                     {"completo_cada_dias": 0}):
            with self.assertRaises(DatosInvalidos, msg=str(malo)):
                programacion.validar(malo, actual)


@dataclass
class C:
    id: str
    t: int
    tipo: str = "completo"
    base: str | None = None
    restaurable: bool = True
    existe: bool = True

    def a(self):
        return programacion.Candidato(self.id, self.t, self.tipo, self.base, self.restaurable, self.existe)


class Retencion(SimpleTestCase):
    def test_conserva_los_n_mas_recientes_y_deja_caducar_el_resto(self):
        lista = [C(f"r{i}", i).a() for i in range(1, 11)]
        self.assertEqual(sorted(programacion.caducables(lista, 4)), [f"r{i}" for i in range(1, 7)])

    def test_nunca_deja_sin_base_a_un_incremental_que_se_conserva(self):
        lista = [C("c1", 1).a(), C("i2", 2, "incremental", "c1").a(), C("i3", 3, "incremental", "i2").a(), C("c4", 4).a(), C("i5", 5, "incremental", "c4").a()]
        self.assertEqual(sorted(programacion.caducables(lista, 1)), ["c1", "i2", "i3"], "i5 se conserva con su base c4; la cadena vieja sobra entera")
        self.assertEqual(programacion.caducables([C("c1", 1).a(), C("i2", 2, "incremental", "c1").a(), C("i3", 3, "incremental", "i2").a()], 1), [])

    def test_nunca_caduca_el_ultimo_restaurable(self):
        lista = [C("bueno", 1).a(), C("m2", 2, restaurable=False).a(), C("m3", 3, restaurable=False).a()]
        self.assertEqual(programacion.caducables(lista, 2), [], "el único restaurable se queda aunque los dos más recientes no lo sean")

    def test_lo_que_ya_no_existe_ni_cuenta_ni_se_vuelve_a_caducar(self):
        lista = [C("a", 1).a(), C("b", 2).a(), C("fantasma", 3, existe=False, restaurable=False).a()]
        self.assertEqual(programacion.caducables(lista, 2), [])


class Fila:
    def __init__(self, tipo, en, detalle=None):
        self.tipo, self.en, self.detalle = tipo, en, detalle or {}


class Estados(SimpleTestCase):
    def d(self, *filas, vivo=False):
        return estados.derivar([Fila(t, i + 1, *([x] if x else [])) for i, (t, x) in enumerate((f if isinstance(f, tuple) else (f, None)) for f in filas)], vivo)

    def test_el_camino_feliz(self):
        self.assertEqual(self.d("iniciado", vivo=True).estado, cat.E_EN_CURSO)
        self.assertEqual(self.d("iniciado", "completo_ejecutado").estado, cat.E_NO_VERIFICADO)
        v = self.d("iniciado", "completo_ejecutado", "verificado")
        self.assertEqual(v.estado, cat.E_VERIFICADO)
        self.assertTrue(v.restaurable)
        self.assertEqual(self.d("iniciado", "completo_ejecutado", "verificado", "exportado").estado, cat.E_EXPORTADO)
        self.assertEqual(self.d("iniciado", "completo_ejecutado", "verificado", "caducado").estado, cat.E_CADUCADO)

    def test_un_respaldo_que_falla_la_verificacion_no_se_descarta_se_marca_no_verificado_y_no_es_restaurable(self):
        d = self.d("iniciado", "incremental_ejecutado", "no_verificado")
        self.assertEqual(d.estado, cat.E_NO_VERIFICADO)
        self.assertFalse(d.restaurable)
        self.assertTrue(d.existe)

    def test_la_ultima_verificacion_manda(self):
        self.assertEqual(self.d("iniciado", "completo_ejecutado", "verificado", "no_verificado").estado, cat.E_NO_VERIFICADO)
        self.assertEqual(self.d("iniciado", "completo_ejecutado", "no_verificado", "verificado").estado, cat.E_VERIFICADO)

    def test_un_iniciado_que_nadie_atiende_es_incompleto_y_se_puede_reanudar(self):
        self.assertEqual(self.d("iniciado").estado, cat.E_INCOMPLETO)
        self.assertEqual(self.d("iniciado", "interrumpido").estado, cat.E_INCOMPLETO)
        self.assertEqual(self.d("iniciado", "interrumpido", "reanudado", vivo=True).estado, cat.E_EN_CURSO)
        self.assertEqual(self.d("iniciado", "interrumpido", "reanudado", "completo_ejecutado", "verificado").estado, cat.E_VERIFICADO)

    def test_fallido(self):
        d = self.d("iniciado", ("fallido", {"motivo": "espacio_insuficiente"}))
        self.assertEqual((d.estado, d.error, d.existe), (cat.E_FALLIDO, "espacio_insuficiente", False))


class Informes(SimpleTestCase):
    FICHA = {"respaldo_id": "abcdef12-0000-4000-8000-000000000000", "tipo": "completo", "disparo": "programado", "estado": "completo_verificado", "creado_en": 1_790_000_000_000,
             "verificado_en": 1_790_000_100_000, "exportado": False, "exportado_en": None, "bytes": 52_428_800, "archivos": 3, "version_producto": "2.14.0", "sha256": "0123456789abcdef" * 4,
             "error": ""}

    def test_la_constancia_se_lee_en_castellano_y_dice_lo_que_el_personal_administrativo_necesita(self):
        t = informes.constancia(self.FICHA, "IE San José", -300)
        for esperado in ("CONSTANCIA DE RESPALDO", "IE San José", "ABCDEF12", "Terminado y verificado", "50.0 MB", "cifrado", "AVACOM WORLD", "no contiene datos de personas"):
            self.assertIn(esperado, t)

    def test_la_constancia_de_un_fallo_dice_que_paso_sin_jerga(self):
        t = informes.constancia({**self.FICHA, "estado": "fallido", "error": "espacio_insuficiente", "verificado_en": None}, "", 0)
        self.assertIn("No terminó", t)
        self.assertIn("espacio suficiente", t)

    def test_el_resumen_csv_abre_en_excel_ordenado_de_lo_nuevo_a_lo_viejo(self):
        csv = informes.resumen_csv([self.FICHA, {**self.FICHA, "respaldo_id": "11111111-0", "creado_en": 1_780_000_000_000}], 0)
        lineas = csv.strip().split("\r\n")
        self.assertEqual(len(lineas), 3)
        self.assertTrue(lineas[0].startswith("fecha;tipo;estado"))
        self.assertIn("ABCDEF12", lineas[1])
        self.assertIn("50,0", lineas[1], "el decimal con coma, como lo espera un Excel en español")

    def test_la_hoja_de_custodia_lleva_el_codigo_una_vez_y_dice_como_guardarlo(self):
        t = informes.hoja_de_custodia("AAAAA-BBBBB", "nodo-1234-xxxx", 1_790_000_000_000, "IE San José", 0)
        self.assertEqual(t.count("AAAAA-BBBBB"), 1)
        for esperado in ("HOJA DE CUSTODIA", "bajo llave", "UNA sola vez", "no conserva el código"):
            self.assertIn(esperado, t)

    def test_el_informe_de_restauracion_dice_que_se_recupera_y_que_se_pierde(self):
        t = informes.informe_de_restauracion(self.FICHA, {"ok": True, "en": 1_790_100_000_000, "archivos": 4, "perdidas": {"horas": 30.5, "eventos": 120}, "punto_de_retorno": "99999999-x"}, "IE", 0)
        for esperado in ("QUÉ SE RECUPERÓ", "QUÉ SE PIERDE", "30.5 horas", "120", "99999999".upper(), "sesiones abiertas"):
            self.assertIn(esperado, t)

    def test_ningun_informe_trae_datos_de_personas_ni_rutas(self):
        textos = [informes.constancia(self.FICHA, "IE", 0), informes.resumen_csv([self.FICHA], 0), informes.hoja_de_custodia("X-Y", "n", 1, "IE", 0)]
        for t in textos:
            for prohibido in ("C:\\", "ProgramData", "/home/", "password", "pin ", "DNI"):
                self.assertNotIn(prohibido, t)
