"""
El formato `.avupd` (P-02, CAP-109, BR-013): lo que se acepta y, sobre todo, lo que se RECHAZA, siempre con motivo y sin escribir nada (TST-047, TST-048, TST-062). Cada rechazo de
forma se prueba con un paquete FIRMADO CORRECTAMENTE cuando lo que se quiere demostrar es que lo rechaza la regla y no la firma.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
import zipfile

from django.test import SimpleTestCase

from actualizacion.dominio import catalogos as cat
from actualizacion.dominio import contenedor, firma, manifiesto as mf, paquete, rutas
from actualizacion.dominio.errores import FirmaInvalida, PaqueteRechazado

from . import emisor
from .emisor import KID_DEV_1, KID_DEV_2, archivos_de_ejemplo, claves_publicas, emitir, emitir_crudo, empaquetar, manifiesto_de_ejemplo


def motivo(accion) -> str:
    try:
        accion()
    except PaqueteRechazado as error:
        return error.motivo
    raise AssertionError("el paquete debía rechazarse y se aceptó")


def rechazo_de(datos: bytes, claves=None) -> PaqueteRechazado:
    try:
        paquete.verificar(datos, claves if claves is not None else claves_publicas())
    except PaqueteRechazado as error:
        return error
    raise AssertionError("el paquete debía rechazarse y se aceptó")


def manifiesto_json(**cambios) -> dict:
    return {**mf.a_dict(manifiesto_de_ejemplo()), **cambios}


def crudo(datos: dict, **kw) -> bytes:
    return emitir_crudo(json.dumps(datos, sort_keys=True, separators=(",", ":")).encode("utf-8"), **kw)


class IdaYVueltaTests(SimpleTestCase):
    def test_un_paquete_firmado_se_verifica_y_entrega_sus_archivos_tal_cual(self):
        """TST-047: paquete importado con firma verificada y recursos completos."""
        archivos = archivos_de_ejemplo()
        p = paquete.verificar(emitir(), claves_publicas())
        self.assertEqual((p.kid, p.manifiesto.paquete_id, p.manifiesto.nombre, p.manifiesto.serie), (KID_DEV_1, emisor.PAQUETE_ID, "Reportes 1.4.0 · corrección del boletín", 7))
        self.assertEqual(p.manifiesto.nombres_de_modulos, ("reporting",))
        self.assertEqual(p.manifiesto.modulo("reporting").migraciones, (mf.Migracion("0004_parche_de_ejemplo", "0003_corte_cola_unica"),))
        self.assertEqual(dict(p.archivos()), archivos)
        self.assertEqual(p.sha256, hashlib.sha256(emitir()).hexdigest())
        self.assertEqual(len(p.sha256), 64)
        self.assertTrue(p.bytes > 0 and p.manifiesto.bytes_total == sum(len(c) for c in archivos.values()))

    def test_un_paquete_comprimido_se_rechaza(self):
        """D-4: el contenedor va sin comprimir (cada byte determinado por el contenido); una entrada deflate es `metodo`."""
        salida = io.BytesIO()
        m = mf.escribir(manifiesto_de_ejemplo())
        with zipfile.ZipFile(salida, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(cat.NOMBRE_MANIFIESTO, m)
            zf.writestr(cat.NOMBRE_FIRMA, firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), m))
            for ruta, contenido in archivos_de_ejemplo().items():
                zf.writestr(cat.CARPETA_ARCHIVOS + ruta, contenido)
        self.assertEqual(rechazo_de(salida.getvalue()).motivo, "metodo")

    def test_el_mismo_contenido_da_siempre_los_mismos_bytes(self):
        self.assertEqual(emitir(), emitir())                 # Ed25519 es determinista y el ZIP se escribe de una sola manera

    def test_las_dos_llaves_de_desarrollo_firman_y_una_ajena_con_el_mismo_kid_no(self):
        self.assertEqual(paquete.verificar(emitir(kid=KID_DEV_2), claves_publicas()).kid, KID_DEV_2)
        privada, _ = firma.par_nuevo()
        self.assertEqual(rechazo_de(emitir(kid=KID_DEV_1, clave=privada)).motivo, "firma_invalida")

    def test_el_manifiesto_que_vuelve_es_el_que_se_firmo(self):
        m = manifiesto_de_ejemplo()
        self.assertEqual(mf.leer(mf.escribir(m)), m)
        self.assertEqual(mf.resumen(m)["archivos"], 2)
        self.assertNotIn("ruta", json.dumps(mf.resumen(m)))      # el resumen no lleva rutas (R-13 del nodo)


class FirmaTests(SimpleTestCase):
    """TST-048 y TST-062: alterado o sin firma → rechazo con motivo, antes de interpretar el manifiesto."""

    def test_sin_firma(self):
        datos = empaquetar(mf.escribir(manifiesto_de_ejemplo()), None, archivos_de_ejemplo())
        error = rechazo_de(datos)
        self.assertIsInstance(error, FirmaInvalida)
        self.assertEqual((error.motivo, error.codigo, error.http), ("sin_firma", "firma_invalida", 422))

    def test_sin_manifiesto(self):
        m = mf.escribir(manifiesto_de_ejemplo())
        self.assertEqual(rechazo_de(empaquetar(None, firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), m), archivos_de_ejemplo())).motivo, "sin_manifiesto")

    def test_kid_desconocido(self):
        self.assertEqual(rechazo_de(emitir(kid="prod-2030-9")).motivo, "kid_desconocido")
        self.assertEqual(rechazo_de(emitir(), claves={}).motivo, "kid_desconocido")        # un nodo de producción sin llaves no acepta nada

    def test_firma_de_otra_llave(self):
        privada, _ = firma.par_nuevo()
        self.assertEqual(rechazo_de(emitir(clave=privada)).motivo, "firma_invalida")

    def test_un_manifiesto_cambiado_tras_firmar_se_rechaza_sin_interpretarlo(self):
        m = mf.escribir(manifiesto_de_ejemplo())
        sello = firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), m)
        alterado = m.replace(b'"serie":7', b'"serie":9')
        self.assertNotEqual(alterado, m)
        self.assertEqual(rechazo_de(empaquetar(alterado, sello, archivos_de_ejemplo())).motivo, "firma_invalida")
        # y uno con un manifiesto ilegible pero firmado se rechaza por el manifiesto, no por la firma: la firma SÍ se verificó primero
        self.assertEqual(rechazo_de(emitir_crudo(b"{no es json")).motivo, "manifiesto_ilegible")

    def test_la_firma_cubre_el_kid_y_la_version(self):
        """Cambiar el kid o la versión de la firma (dejando la firma) la invalida: nadie «degrada» un paquete tocando la cabecera."""
        m = mf.escribir(manifiesto_de_ejemplo())
        sello = firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), m)
        otro_kid = firma.escribir(KID_DEV_2, sello[-64:])
        self.assertEqual(rechazo_de(empaquetar(m, otro_kid, archivos_de_ejemplo())).motivo, "firma_invalida")

    def test_formato_de_la_firma(self):
        m = mf.escribir(manifiesto_de_ejemplo())
        sello = firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), m)
        casos = {
            "firma_formato": [sello[:-1], sello + b"\x00", b"", b"XXXX" + sello[4:]],
            "version_firma_desconocida": [sello[:4] + struct.pack(">H", 2) + sello[6:]],
            "kid_invalido": [sello[:6] + b"\x00" + sello[7:], firma.cabecera("Mayus") + sello[-64:], sello[:6] + bytes([40]) + b"a" * 40 + sello[-64:]],
        }
        for esperado, variantes in casos.items():
            for variante in variantes:
                self.assertEqual(rechazo_de(empaquetar(m, variante, archivos_de_ejemplo())).motivo, esperado, variante[:12])

    def test_los_motivos_de_firma_son_firma_invalida_y_el_resto_paquete_invalido(self):
        for m in cat.MOTIVOS_DE_FIRMA:
            self.assertIsInstance(PaqueteRechazado.__new__(FirmaInvalida), FirmaInvalida)
            self.assertIn(m, cat.MENSAJES_DE_MOTIVO)
        self.assertEqual(rechazo_de(emitir() + b"\x00").codigo, "paquete_invalido")
        self.assertEqual(rechazo_de(emitir(kid="x-1")).codigo, "firma_invalida")


class ContenedorTests(SimpleTestCase):
    """A1 y A3 sobre el contenedor: truncado, sobrante, duplicado, enlace, directorio, cifrado, descriptor, extras, ZIP64."""

    def test_truncado_y_bytes_sobrantes(self):
        datos = emitir()
        self.assertEqual(rechazo_de(datos[:-1]).motivo, "truncado")
        self.assertEqual(rechazo_de(datos[:-40]).motivo, "truncado")
        self.assertEqual(rechazo_de(datos[: len(datos) // 2]).motivo, "truncado")
        self.assertEqual(rechazo_de(datos + b"\x00").motivo, "bytes_sobrantes")
        self.assertEqual(rechazo_de(datos + b"relleno" * 10).motivo, "bytes_sobrantes")
        self.assertEqual(rechazo_de(b"\x00" + datos).motivo, "bytes_sobrantes")       # bytes por delante: los offsets ya no cuadran
        self.assertEqual(rechazo_de(b"").motivo, "demasiado_corto")
        self.assertEqual(rechazo_de(b"no soy un zip, soy un texto cualquiera con mas de cincuenta y dos bytes").motivo, "estructura")

    def test_demasiado_grande(self):
        datos = emitir()
        self.assertEqual(rechazo_de(datos + b"x" * 10, claves=None).motivo, "bytes_sobrantes")
        with self.assertRaises(PaqueteRechazado) as ctx:
            paquete.verificar(datos, claves_publicas(), max_bytes=len(datos) - 1)
        self.assertEqual(ctx.exception.motivo, "demasiado_grande")

    def test_nombre_duplicado(self):
        m = mf.escribir(manifiesto_de_ejemplo())
        archivos = archivos_de_ejemplo()
        datos = empaquetar(m, firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), m), archivos, duplicar=next(iter(archivos)))
        self.assertEqual(rechazo_de(datos).motivo, "nombre_duplicado")

    def test_un_zip_corriente_no_es_un_paquete(self):
        """`zipfile` escribe fechas reales y atributos: no es el contenedor canónico, así que un `.avupd` hecho a mano con cualquier herramienta se rechaza (la forma la fija el emisor)."""
        salida = io.BytesIO()
        m = mf.escribir(manifiesto_de_ejemplo())
        with zipfile.ZipFile(salida, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr(cat.NOMBRE_MANIFIESTO, m)
            zf.writestr(cat.NOMBRE_FIRMA, firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), m))
            for ruta, contenido in archivos_de_ejemplo().items():
                zf.writestr(cat.CARPETA_ARCHIVOS + ruta, contenido)
        self.assertEqual(rechazo_de(salida.getvalue()).motivo, "estructura")
        # pero el contenedor canónico lo lee cualquier `zipfile` (el técnico puede abrirlo con 7-Zip para mirarlo)
        with zipfile.ZipFile(io.BytesIO(emitir())) as zf:
            self.assertEqual(sorted(zf.namelist()), sorted([cat.NOMBRE_MANIFIESTO, cat.NOMBRE_FIRMA, *(cat.CARPETA_ARCHIVOS + r for r in archivos_de_ejemplo())]))
            self.assertIsNone(zf.testzip())
            self.assertEqual(zf.read(cat.NOMBRE_MANIFIESTO), m)

    def test_enlace_simbolico_y_directorio(self):
        archivos = archivos_de_ejemplo()
        ruta = next(iter(archivos))
        m = mf.escribir(manifiesto_de_ejemplo(archivos))
        sello = firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), m)
        enlace = empaquetar(m, sello, archivos, atributos={ruta: 0o120777 << 16})
        self.assertEqual(rechazo_de(enlace).motivo, "enlace")
        directorio = empaquetar(m, sello, archivos, extra={"archivos/reporting/carpeta/": b""})
        self.assertEqual(rechazo_de(directorio).motivo, "directorio")
        directorio_por_atributo = empaquetar(m, sello, archivos, extra={"archivos/reporting/x.py": b""}, atributos={"archivos/reporting/x.py": 0o040755 << 16})
        self.assertEqual(rechazo_de(directorio_por_atributo).motivo, "directorio")
        # cualquier otro atributo (permisos, «archivo» de DOS) tampoco es canónico
        self.assertEqual(rechazo_de(empaquetar(m, sello, archivos, atributos={ruta: 0o100644 << 16})).motivo, "estructura")
        self.assertEqual(rechazo_de(empaquetar(m, sello, archivos, atributos={ruta: 0x20})).motivo, "estructura")

    def test_la_fecha_y_la_version_son_fijas(self):
        """Canónico: cambiar la fecha, la hora o la versión de una cabecera (lo que un ZIP corriente deja libre) se rechaza."""
        datos = emitir()
        pos = datos.find(b"PK\x01\x02")
        for desplazamiento in (4, 6, 12, 14, 30, 32, 36, 38):        # hecho por, necesita, hora, fecha, extra, comentario, attr internos, attr externos
            m = bytearray(datos)
            m[pos + desplazamiento] ^= 0x01
            self.assertEqual(rechazo_de(bytes(m)).motivo, "estructura", desplazamiento)
        for desplazamiento in (4, 10, 12):                           # cabecera local: versión, hora, fecha
            m = bytearray(datos)
            m[desplazamiento] ^= 0x01
            self.assertEqual(rechazo_de(bytes(m)).motivo, "estructura", desplazamiento)

    def test_cifrado_descriptor_de_datos_campo_extra_y_zip64_se_rechazan(self):
        datos = bytearray(emitir())
        # el primer header local está en 0: los flags en los bytes 6-7; también hay que tocar el del directorio central, si no es «estructura» igual
        def con_flags(flags: int) -> bytes:
            m = bytearray(datos)
            struct.pack_into("<H", m, 6, flags)
            pos = m.rfind(b"PK\x01\x02")
            pos = m.find(b"PK\x01\x02")
            struct.pack_into("<H", m, pos + 8, flags)
            return bytes(m)
        self.assertEqual(rechazo_de(con_flags(0x0001)).motivo, "cifrado")
        self.assertEqual(rechazo_de(con_flags(0x0008)).motivo, "estructura")
        self.assertEqual(rechazo_de(con_flags(0x0800)).motivo, "estructura")
        # ZIP64: un tamaño 0xFFFFFFFF en el directorio
        m = bytearray(datos)
        pos = m.find(b"PK\x01\x02")
        struct.pack_into("<I", m, pos + 20, 0xFFFFFFFF)
        self.assertEqual(rechazo_de(bytes(m)).motivo, "zip64")
        # campo extra en el directorio (sin mover el resto: la estructura ya no cuadra)
        m = bytearray(datos)
        struct.pack_into("<H", m, pos + 30, 4)
        self.assertEqual(rechazo_de(bytes(m)).motivo, "estructura")

    def test_un_metodo_de_compresion_que_no_es_deflate_ni_almacenado(self):
        datos = bytearray(emitir())
        pos = datos.find(b"PK\x01\x02")
        struct.pack_into("<H", datos, pos + 10, 12)          # bzip2
        struct.pack_into("<H", datos, 8, 12)
        self.assertEqual(rechazo_de(bytes(datos)).motivo, "metodo")

    def test_una_entrada_cuyo_contenido_no_cuadra_con_su_crc(self):
        datos = bytearray(emitir())
        pos = datos.find(b"archivos/reporting/dominio/parche_de_ejemplo.py")
        inicio = pos + len("archivos/reporting/dominio/parche_de_ejemplo.py")
        datos[inicio] ^= 0xFF
        self.assertIn(rechazo_de(bytes(datos)).motivo, ("estructura", "sha_distinto"))

    def test_sin_descompresion_no_hay_bomba(self):
        """A3: nada se descomprime (D-4), así que un archivo mide lo que ocupa; dos megas de ceros son dos megas de ceros, y un tamaño mentido en la cabecera es `tamano_distinto`."""
        grande = b"\x00" * (2 * cat.MIB)
        archivos = {"reporting/dominio/relleno.py": grande}
        m = manifiesto_de_ejemplo(archivos)
        datos = emitir(m, archivos=archivos)
        self.assertGreater(len(datos), 2 * cat.MIB)
        self.assertEqual(dict(paquete.verificar(datos, claves_publicas()).archivos()), archivos)
        datos = bytearray(emitir(manifiesto_de_ejemplo({"reporting/dominio/a.py": b"ab" * 50}), archivos={"reporting/dominio/a.py": b"ab" * 50}))
        pos = datos.find(b"PK\x01\x02")
        for _ in range(2):
            pos = datos.find(b"PK\x01\x02", pos + 1)
        nombre_len = struct.unpack_from("<H", datos, pos + 28)[0]
        self.assertEqual(datos[pos + 46:pos + 46 + nombre_len], b"archivos/reporting/dominio/a.py")
        struct.pack_into("<I", datos, pos + 24, 10)          # «mide 10» (el manifiesto dice 100): tamaño distinto antes de descomprimir
        self.assertIn(rechazo_de(bytes(datos)).motivo, ("tamano_distinto", "estructura"))


class ManifiestoTests(SimpleTestCase):
    """Cada rechazo con un manifiesto FIRMADO: lo rechaza la regla de forma."""

    def test_version_de_formato_desconocida(self):
        self.assertEqual(rechazo_de(crudo(manifiesto_json(formato=2))).motivo, "version_formato_desconocida")
        self.assertEqual(rechazo_de(crudo(manifiesto_json(formato="1"))).motivo, "version_formato_desconocida")

    def test_etiqueta_critica_desconocida(self):
        self.assertEqual(rechazo_de(crudo(manifiesto_json(criticas=["cifrado_v2"]))).motivo, "etiqueta_critica_desconocida")

    def test_producto_distinto(self):
        self.assertEqual(rechazo_de(crudo(manifiesto_json(producto="AVACOM Contenido"))).motivo, "producto_distinto")

    def test_campos_faltantes_e_invalidos(self):
        for campo in ("paquete_id", "nombre", "version_producto", "emitido_en", "modulos", "archivos", "producto"):
            d = manifiesto_json()
            del d[campo]
            self.assertEqual(rechazo_de(crudo(d)).motivo, "campo_faltante", campo)
        for cambios in (dict(paquete_id="no-es-uuid"), dict(paquete_id="ABCDEF12-0001-4000-8000-000000000001"), dict(version_producto="2.12"), dict(version_minima="x"), dict(emitido_en=0),
                        dict(emitido_en="ayer"), dict(nombre=""), dict(nombre="x" * 200), dict(modulos=[]), dict(archivos=[]), dict(nota="n" * 3000), dict(requisitos=[])):
            self.assertEqual(rechazo_de(crudo(manifiesto_json(**cambios))).motivo, "campo_invalido", cambios)
        self.assertEqual(rechazo_de(crudo([1, 2])).motivo, "manifiesto_ilegible")
        self.assertEqual(rechazo_de(emitir_crudo(b"\xff\xfe")).motivo, "manifiesto_ilegible")

    def test_modulos_invalidos(self):
        base = manifiesto_json()["modulos"][0]
        for cambios in (dict(nombre="Reporting"), dict(nombre="../x"), dict(version="1"), dict(version_datos=-1), dict(version_contrato=0), dict(serie=0), dict(serie="7"),
                        dict(cambia_contrato="si"), dict(requiere={"nodo": 0}), dict(requiere={"No": 1}),
                        dict(migraciones=[{"nombre": "x", "reverso": "0003_y"}]), dict(migraciones=[{"nombre": "0004_x", "reverso": "../0003"}])):
            self.assertEqual(rechazo_de(crudo(manifiesto_json(modulos=[{**base, **cambios}]))).motivo, "campo_invalido", cambios)
        # BR-015: toda migración declara su reverso
        self.assertEqual(rechazo_de(crudo(manifiesto_json(modulos=[{**base, "migraciones": [{"nombre": "0004_x"}]}]))).motivo, "campo_faltante")
        self.assertEqual(rechazo_de(crudo(manifiesto_json(modulos=[base, base]))).motivo, "campo_invalido")           # dos veces el mismo módulo
        self.assertEqual(rechazo_de(crudo(manifiesto_json(modulos=[{**base, "nombre": "biblioteca"}]))).motivo, "ruta_intocable")

    def test_rutas_absolutas_con_retroceso_fuera_del_modulo_o_prohibidas(self):
        base = manifiesto_json()
        archivo = dict(base["archivos"][0])
        casos = {
            "ruta_absoluta": ["/etc/passwd", "C:/Windows/x.py", "c:reporting/x.py", "/reporting/x.py"],
            "ruta_con_retroceso": ["../avacom_lms/settings.py", "reporting/../acceso/x.py", "reporting/dominio/../../x.py"],
            "ruta_invalida": ["reporting\\dominio\\x.py", "reporting//x.py", "reporting/./x.py", "reporting/dominio/", "reporting/con.py", "reporting/__pycache__/x.py",
                              "reporting/x y.py", "reporting/x.py ", "reporting/ñ.py", "", "reporting/" + "a" * 90 + ".py", "reporting/x..py" if False else "reporting/x./y.py"],
            "extension_prohibida": ["reporting/x.exe", "reporting/x.dll", "reporting/x.pyd", "reporting/x.bat", "reporting/x.ps1", "reporting/x", "reporting/x.PY.so"],
            "ruta_fuera_del_modulo": ["acceso/dominio/x.py", "manage.py", "avacom_lms/settings.py", "avacom_lms/asgi.py", "nodo/x.py"],
            "ruta_intocable": ["biblioteca/cliente.py"],
        }
        for esperado, variantes in casos.items():
            for ruta in variantes:
                d = dict(base)
                d["archivos"] = [{**archivo, "ruta": ruta}]
                self.assertEqual(rechazo_de(crudo(d)).motivo, esperado, ruta)
        # el registro de módulos SÍ puede viajar (D-2)
        self.assertEqual(rutas.validar("avacom_lms/modulos.json"), "avacom_lms/modulos.json")
        rutas.exigir_dentro_de("avacom_lms/modulos.json", ("reporting",))

    def test_ruta_duplicada_y_sha_invalido(self):
        base = manifiesto_json()
        self.assertEqual(rechazo_de(crudo({**base, "archivos": base["archivos"] + [base["archivos"][0]]})).motivo, "ruta_duplicada")
        self.assertEqual(rechazo_de(crudo({**base, "archivos": [{**base["archivos"][0], "sha256": "abc"}]})).motivo, "campo_invalido")
        self.assertEqual(rechazo_de(crudo({**base, "archivos": [{**base["archivos"][0], "bytes": -1}]})).motivo, "campo_invalido")

    def test_archivo_no_declarado_faltante_tamano_y_sha_distintos(self):
        archivos = archivos_de_ejemplo()
        m = mf.escribir(manifiesto_de_ejemplo(archivos))
        sello = firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), m)
        self.assertEqual(rechazo_de(empaquetar(m, sello, archivos, extra={"archivos/reporting/colado.py": b"x"})).motivo, "archivo_no_declarado")
        self.assertEqual(rechazo_de(empaquetar(m, sello, archivos, extra={"colado.txt": b"x"})).motivo, "archivo_no_declarado")
        menos = dict(list(archivos.items())[:1])
        self.assertEqual(rechazo_de(empaquetar(m, sello, menos)).motivo, "archivo_faltante")
        ruta = next(iter(archivos))
        cambiado = {**archivos, ruta: archivos[ruta] + b"#"}
        self.assertEqual(rechazo_de(empaquetar(m, sello, cambiado)).motivo, "tamano_distinto")
        mismo_tamano = {**archivos, ruta: bytes(reversed(archivos[ruta]))}
        self.assertEqual(rechazo_de(empaquetar(m, sello, mismo_tamano)).motivo, "sha_distinto")

    def test_demasiados_archivos(self):
        base = manifiesto_json()
        archivo = base["archivos"][0]
        base["archivos"] = [{**archivo, "ruta": f"reporting/dominio/a{i}.py"} for i in range(cat.MAX_ARCHIVOS + 1)]
        self.assertEqual(rechazo_de(crudo(base)).motivo, "campo_invalido")


class RutasTests(SimpleTestCase):
    def test_validar_devuelve_la_ruta_tal_cual(self):
        for ruta in ("reporting/dominio/boletin.py", "reporting/migrations/0004_x.py", "gradebook/datos/escalas.json", "search/README.md", "acceso/__init__.py"):
            self.assertEqual(rutas.validar(ruta), ruta)

    def test_nombres_reservados_de_windows(self):
        for nombre in ("con", "CON.py", "prn.txt", "aux.py", "nul.json", "com1.py", "lpt9.py"):
            self.assertEqual(motivo(lambda n=nombre: rutas.validar(f"reporting/{n}")), "ruta_invalida", nombre)
