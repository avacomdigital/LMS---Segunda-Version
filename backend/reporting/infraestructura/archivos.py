"""
Los archivos de una exportación: el documento (cabecera BR-083, resumen y tablas) escrito como XLSX o CSV. Todo con la biblioteca estándar de Python (`zipfile`, `csv`, `hashlib`): nada
que descargar ni instalar (BR-084) y nada que pueda faltar en el instalador.

  XLSX  (por defecto) un libro de Office Open XML escrito a mano: una hoja «Resumen» (la cabecera y los totales) y una hoja por tabla, con encabezado fijo, filtro, anchos de
        columna y números como números (no como texto). Los textos van como cadenas en línea: un texto que empieza por «=» sigue siendo texto, nunca una fórmula.
  CSV   UTF-8 con BOM (para que Excel en español respete tildes y la ñ), separador «;» y coma decimal (lo que espera Excel con la configuración regional de España y de Sudamérica;
        en México el separador de listas es «,»: es una pregunta abierta). Un texto que empezaría una fórmula (`=`, `+`, `-`, `@`) se escribe con una comilla delante: la «inyección de
        fórmulas» de los CSV no aplica.

El archivo se escribe en un temporal que pasa a disco si crece (8 MB) y se entrega con su SHA-256 calculado releyéndolo por bloques: nunca queda entero en memoria dos veces. Misma
entrada → mismos bytes (las fechas internas del zip son fijas): la huella identifica el contenido.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import tempfile
import zipfile
from xml.sax.saxutils import escape

from ..aplicacion.puertos import ArchivoGenerado
from ..dominio import archivo as arch
from ..dominio import catalogos as cat
from ..dominio import documento as doc

_ILEGALES = re.compile("[^\u0009\u000A\u000D -퟿-�\U00010000-\U0010FFFF]")
MAX_TEXTO = 32_767                                 # el tope de una celda de Excel
FECHA_FIJA = (1980, 1, 1, 0, 0, 0)
UMBRAL_EN_MEMORIA = 8 * 1024 * 1024
PREFIJOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")
NOMBRES_PROHIBIDOS_DE_HOJA = re.compile(r"[\[\]:*?/\\]")

ESTILO_NORMAL, ESTILO_ENCABEZADO, ESTILO_DECIMAL, ESTILO_ENTERO, ESTILO_TITULO, ESTILO_ETIQUETA, ESTILO_AJUSTADO = 0, 1, 2, 3, 4, 5, 6


def _texto(valor) -> str:
    return _ILEGALES.sub("", str(valor if valor is not None else ""))[:MAX_TEXTO]


def _columna(n: int) -> str:
    """1 → A, 27 → AA."""
    letras = ""
    while n:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _numero(valor):
    """`int`/`float`/`Decimal` → número, o None si no lo es (un booleano no es un número)."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return valor
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


# ===================================================================================================================== XLSX

_TIPOS_NUMERICOS = (doc.ENTERO, doc.DECIMAL, doc.PORCENTAJE, doc.MINUTOS)


def _celda(ref: str, valor, tipo: str, estilo: int | None = None) -> str:
    if valor is None or valor == "":
        return ""
    if tipo in _TIPOS_NUMERICOS:
        n = _numero(valor)
        if n is not None:
            s = ESTILO_ENTERO if tipo == doc.ENTERO else ESTILO_DECIMAL
            return f'<c r="{ref}" s="{s}"><v>{n!r}</v></c>' if isinstance(n, float) else f'<c r="{ref}" s="{s}"><v>{n}</v></c>'
    s = estilo if estilo is not None else ESTILO_NORMAL
    return f'<c r="{ref}" t="inlineStr" s="{s}"><is><t xml:space="preserve">{escape(_texto(valor))}</t></is></c>'


def _nombre_de_hoja(nombre: str, usadas: list[str]) -> str:
    base = NOMBRES_PROHIBIDOS_DE_HOJA.sub("-", _texto(nombre)).strip("' ")[:31] or "Hoja"
    candidato, n = base, 2
    while candidato.casefold() in (u.casefold() for u in usadas):
        sufijo = f" ({n})"
        candidato, n = base[:31 - len(sufijo)] + sufijo, n + 1
    return candidato


def _ancho(valores) -> float:
    mayor = max((len(_texto(v)) for v in valores), default=8)
    return float(min(60, max(10, round(mayor * 1.1 + 2))))


def _hoja_de_resumen(documento: doc.Documento, destino) -> None:
    filas: list[str] = []
    n = 1
    filas.append(f'<row r="{n}">{_celda(f"A{n}", documento.titulo, doc.TEXTO, ESTILO_TITULO)}</row>')
    n += 2
    for etiqueta, valor in documento.cabecera:
        filas.append(f'<row r="{n}">{_celda(f"A{n}", etiqueta, doc.TEXTO, ESTILO_ETIQUETA)}{_celda(f"B{n}", valor, doc.TEXTO, ESTILO_AJUSTADO)}</row>')
        n += 1
    if documento.resumen:
        n += 1
        filas.append(f'<row r="{n}">{_celda(f"A{n}", "Resumen", doc.TEXTO, ESTILO_ETIQUETA)}</row>')
        n += 1
        for etiqueta, valor, tipo in documento.resumen:
            filas.append(f'<row r="{n}">{_celda(f"A{n}", etiqueta, doc.TEXTO, ESTILO_ETIQUETA)}{_celda(f"B{n}", valor, tipo, ESTILO_AJUSTADO)}</row>')
            n += 1
    if documento.notas:
        n += 1
        for nota in documento.notas:
            filas.append(f'<row r="{n}">{_celda(f"A{n}", "Nota", doc.TEXTO, ESTILO_ETIQUETA)}{_celda(f"B{n}", nota, doc.TEXTO, ESTILO_AJUSTADO)}</row>')
            n += 1
    ancho_a = _ancho([e for e, *_ in documento.cabecera] + [e for e, *_ in documento.resumen] + ["Nota"])
    destino.write(('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews><sheetFormatPr defaultRowHeight="15"/>'
                   f'<cols><col min="1" max="1" width="{ancho_a}" customWidth="1"/><col min="2" max="2" width="90" customWidth="1"/></cols><sheetData>').encode("utf-8"))
    for f in filas:
        destino.write(f.encode("utf-8"))
    destino.write(b'</sheetData><pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/></worksheet>')


def _hoja_de_tabla(tabla: doc.Tabla, destino) -> None:
    columnas = tabla.columnas
    anchos = [_ancho([c.titulo] + [f[i] for f in tabla.filas[:500]]) for i, c in enumerate(columnas)]
    destino.write(('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft"/></sheetView></sheetViews>'
                   '<sheetFormatPr defaultRowHeight="15"/><cols>' +
                   "".join(f'<col min="{i + 1}" max="{i + 1}" width="{a}" customWidth="1"/>' for i, a in enumerate(anchos)) + "</cols><sheetData>").encode("utf-8"))
    destino.write((f'<row r="1">' + "".join(_celda(f"{_columna(i + 1)}1", c.titulo, doc.TEXTO, ESTILO_ENCABEZADO) for i, c in enumerate(columnas)) + "</row>").encode("utf-8"))
    for r, fila in enumerate(tabla.filas, start=2):
        destino.write((f'<row r="{r}">' + "".join(_celda(f"{_columna(i + 1)}{r}", valor, columnas[i].tipo) for i, valor in enumerate(fila)) + "</row>").encode("utf-8"))
    ultima = max(1, len(tabla.filas) + 1)
    destino.write((f'</sheetData><autoFilter ref="A1:{_columna(len(columnas))}{ultima}"/>'
                   '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/></worksheet>').encode("utf-8"))


_ESTILOS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="14"/><name val="Calibri"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFEAEAEA"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="7">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
            '<xf numFmtId="2" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '<xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1" horizontal="left"/></xf>'
            '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def escribir_xlsx(documento: doc.Documento, destino) -> None:
    """Escribe el libro en `destino` (un archivo binario). Una hoja «Resumen» y una por tabla."""
    hojas: list[tuple[str, object]] = [("Resumen", None)] + [(t.nombre, t) for t in documento.tablas]
    nombres: list[str] = []
    for nombre, _ in hojas:
        nombres.append(_nombre_de_hoja(nombre, nombres))
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        def parte(ruta: str, contenido: str) -> None:
            z.writestr(zipfile.ZipInfo(ruta, FECHA_FIJA), contenido.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)

        tipos = "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(hojas)))
        parte("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + tipos +
              '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
              '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>')
        parte("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
              '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
              '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')
        parte("docProps/core.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
              'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
              f'<dc:title>{escape(_texto(documento.titulo))}</dc:title><dc:creator>AVACOM LMS</dc:creator></cp:coreProperties>')
        parte("docProps/app.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
              '<Application>AVACOM LMS</Application></Properties>')
        hojas_xml = "".join(f'<sheet name="{escape(n, {chr(34): "&quot;"})}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(nombres))
        parte("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>' + hojas_xml + '</sheets></workbook>')
        relaciones = "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                             for i in range(len(hojas)))
        parte("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + relaciones +
              f'<Relationship Id="rId{len(hojas) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        parte("xl/styles.xml", _ESTILOS)
        for i, (_, tabla) in enumerate(hojas, start=1):
            informacion = zipfile.ZipInfo(f"xl/worksheets/sheet{i}.xml", FECHA_FIJA)
            informacion.compress_type = zipfile.ZIP_DEFLATED
            with z.open(informacion, "w") as f:
                (_hoja_de_resumen(documento, f) if tabla is None else _hoja_de_tabla(tabla, f))


# ===================================================================================================================== CSV

def _csv_texto(valor) -> str:
    t = _texto(valor)
    return "'" + t if t.startswith(PREFIJOS_DE_FORMULA) else t


def _csv_valor(valor, tipo: str) -> str:
    if valor is None:
        return ""
    if tipo in _TIPOS_NUMERICOS:
        n = _numero(valor)
        if n is not None:
            return (str(n) if isinstance(n, int) else f"{n:.2f}".rstrip("0").rstrip(".") if tipo != doc.MINUTOS else f"{n:.1f}").replace(".", ",")
    return _csv_texto(valor)


def escribir_csv(documento: doc.Documento, destino) -> None:
    """UTF-8 con BOM, `;` y coma decimal. Primero la cabecera (BR-083) y el resumen; después cada tabla con su nombre."""
    texto = io.TextIOWrapper(destino, encoding="utf-8-sig", newline="", write_through=True)
    w = csv.writer(texto, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow([_csv_texto(documento.titulo)])
    w.writerow([])
    for etiqueta, valor in documento.cabecera:
        w.writerow([_csv_texto(etiqueta), _csv_texto(valor)])
    if documento.resumen:
        w.writerow([])
        w.writerow(["Resumen"])
        for etiqueta, valor, tipo in documento.resumen:
            w.writerow([_csv_texto(etiqueta), _csv_valor(valor, tipo)])
    for nota in documento.notas:
        w.writerow(["Nota", _csv_texto(nota)])
    for tabla in documento.tablas:
        w.writerow([])
        w.writerow([_csv_texto(tabla.nombre)])
        w.writerow([_csv_texto(c.titulo) for c in tabla.columnas])
        for fila in tabla.filas:
            w.writerow([_csv_valor(v, tabla.columnas[i].tipo) for i, v in enumerate(fila)])
    texto.flush()
    texto.detach()                       # no cerrar el archivo de abajo: es de quien lo recibe


# ===================================================================================================================== el escritor

class EscritorDeArchivos:
    def escribir(self, documento: doc.Documento, formato: str) -> ArchivoGenerado:
        if formato not in cat.FORMATOS:
            raise ValueError(f"Formato fuera del catálogo de MOD-013: {formato}")
        spool = tempfile.SpooledTemporaryFile(max_size=UMBRAL_EN_MEMORIA, mode="w+b")
        try:
            (escribir_xlsx if formato == cat.XLSX else escribir_csv)(documento, spool)
            return self._entregar(spool)
        except Exception:
            spool.close()
            raise

    def escribir_varios(self, documentos: list[doc.Documento], formato: str, nombres: list[str]) -> ArchivoGenerado:
        """VARIOS documentos (uno por estudiante) en UN `zip`: cada uno en el formato pedido, con su nombre ya saneado (sin repetir), fechas fijas en las partes del zip (misma
        entrada → mismos bytes). Lo que el profesor lleva a la memoria USB es un solo archivo; dentro, uno por familia."""
        if formato not in cat.FORMATOS:
            raise ValueError(f"Formato fuera del catálogo de MOD-013: {formato}")
        if len(documentos) != len(nombres):
            raise ValueError("Cada documento necesita su nombre")
        spool = tempfile.SpooledTemporaryFile(max_size=UMBRAL_EN_MEMORIA, mode="w+b")
        try:
            usados: set[str] = set()
            with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as z:
                for documento, propuesto in zip(documentos, nombres):
                    nombre = arch.sanear(propuesto, cat.EXTENSION_DE[formato])
                    base, n = nombre, 2
                    while nombre.casefold() in usados:
                        raiz, punto, ext = base.rpartition(".")
                        nombre, n = f"{raiz or ext} ({n}).{ext}" if punto else f"{base} ({n})", n + 1
                    usados.add(nombre.casefold())
                    parte = io.BytesIO()
                    (escribir_xlsx if formato == cat.XLSX else escribir_csv)(documento, parte)
                    informacion = zipfile.ZipInfo(nombre, FECHA_FIJA)
                    informacion.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(informacion, parte.getvalue())
            return self._entregar(spool)
        except Exception:
            spool.close()
            raise

    @staticmethod
    def _entregar(spool) -> ArchivoGenerado:
        total = spool.tell()
        spool.seek(0)
        h = hashlib.sha256()
        for bloque in iter(lambda: spool.read(1024 * 1024), b""):
            h.update(bloque)
        spool.seek(0)
        return ArchivoGenerado(contenido=spool, bytes_total=total, huella=h.hexdigest())
