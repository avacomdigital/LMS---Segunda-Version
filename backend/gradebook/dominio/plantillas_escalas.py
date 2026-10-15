"""
Plantillas de escalas de calificación (§4.3 y «Sistema de calificaciones internacionales configurables»): España, Estados Unidos, México, Colombia,
Chile, Perú y Ecuador, más las genéricas (0–5, 0–10, 0–20, 0–100, letras y conceptual). Añadir otro país es añadir otra entrada aquí: la lógica central
(`escala.py`) no cambia.

LO QUE ESTO ES Y LO QUE NO ES. Una plantilla es un PUNTO DE PARTIDA orientativo. No es una equivalencia oficial, no es válida para toda una nación (las
normas varían por nivel, por jurisdicción y, en varios países, por institución) y no se usa para presentar una calificación hasta que la institución la
revisa, la ajusta si hace falta y la ADOPTA (`m11_escala` + `m11_escala_version`, versionada). Las cifras de cada plantilla son las prácticas habituales
que conocía el autor y NO se han contrastado con la normativa vigente de cada país: hay que verificarlas antes de adoptarlas. Un país o un nivel sin
plantilla no recibe una conversión inventada: se configura una escala propia.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from . import catalogos as cat
from .escala import DefinicionEscala, Tramo, a_dict, describir, lineal, validar

ADVERTENCIA = ("Plantilla orientativa: no es una equivalencia oficial ni válida para todo un país. La institución debe revisarla con su normativa y su "
               "sistema de evaluación, ajustarla y adoptarla (queda versionada) antes de presentar calificaciones con ella.")

TODOS = ("primaria", "secundaria", "bachillerato", "preuniversitario")


@dataclass(frozen=True)
class Plantilla:
    codigo: str
    nombre: str
    pais: str                          # ISO 3166-1 alfa-2; '' = genérica
    jurisdiccion: str
    niveles: tuple[str, ...]           # los niveles a los que suele aplicar (sugerencia; la institución decide)
    definicion: DefinicionEscala
    referencia: str                    # de dónde sale la práctica que recoge (a verificar)
    advertencia: str = ADVERTENCIA


def _d(valor) -> Decimal:
    return Decimal(str(valor))


def _numerica(minimo, maximo, *, decimales: int, aprobacion=None, puntos=None, tramos=(), redondeo: str = cat.MITAD_ARRIBA) -> DefinicionEscala:
    minimo, maximo = _d(minimo), _d(maximo)
    return DefinicionEscala(
        tipo=cat.NUMERICA, conversion=cat.INTERPOLADA, decimales=decimales, redondeo=redondeo, valor_min=minimo, valor_max=maximo,
        puntos=tuple((_d(x), _d(y)) for x, y in puntos) if puntos else lineal(minimo, maximo),
        aprobacion_minima=None if aprobacion is None else _d(aprobacion), tramos=tuple(tramos))


def _tramos(filas) -> tuple[Tramo, ...]:
    """`(clave, etiqueta, desde, hasta, aprueba[, desempeño])` de menor a mayor resultado interno. Sin desempeño explícito, el descriptor es la etiqueta."""
    return tuple(Tramo(orden=i, clave=f[0], etiqueta=f[1], desde=_d(f[2]), hasta=_d(f[3]), aprueba=f[4], nivel_desempeno=f[5] if len(f) > 5 else f[1])
                 for i, f in enumerate(filas, start=1))


def _por_tramos(tipo: str, filas) -> DefinicionEscala:
    return DefinicionEscala(tipo=tipo, conversion=cat.TRAMOS, decimales=0, redondeo=cat.MITAD_ARRIBA, tramos=_tramos(filas))


_LETRAS = (("F", "F", 0, 60, False, "No alcanza"), ("D", "D", 60, 70, True, "Suficiente"), ("C", "C", 70, 80, True, "Satisfactorio"),
           ("B", "B", 80, 90, True, "Notable"), ("A", "A", 90, 100, True, "Sobresaliente"))
_CONCEPTUAL = (("bajo", "Bajo", 0, 60, False), ("basico", "Básico", 60, 75, True), ("alto", "Alto", 75, 90, True), ("superior", "Superior", 90, 100, True))

PLANTILLAS: tuple[Plantilla, ...] = (
    # ---------------------------------------------------------------------------------------------- genéricas (§4.3)
    Plantilla("gen-0-5", "Numérica de 0 a 5", "", "", TODOS, _numerica(0, 5, decimales=1), "Conversión lineal de 0–100 a 0–5."),
    Plantilla("gen-0-10", "Numérica de 0 a 10", "", "", TODOS, _numerica(0, 10, decimales=1), "Conversión lineal de 0–100 a 0–10."),
    Plantilla("gen-0-20", "Numérica de 0 a 20", "", "", TODOS, _numerica(0, 20, decimales=0), "Conversión lineal de 0–100 a 0–20."),
    Plantilla("gen-0-100", "Numérica de 0 a 100", "", "", TODOS, _numerica(0, 100, decimales=0), "La escala interna tal cual."),
    Plantilla("gen-letras", "Letras A, B, C, D, F", "", "", TODOS, _por_tramos(cat.ALFABETICA, _LETRAS),
              "Tramos de diez puntos (90/80/70/60), práctica habitual de la escala alfabética."),
    Plantilla("gen-conceptual", "Conceptual: Superior, Alto, Básico, Bajo", "", "", TODOS, _por_tramos(cat.CUALITATIVA, _CONCEPTUAL),
              "Cuatro conceptos; las denominaciones y los cortes se configuran."),
    # -------------------------------------------------------------------------------------------------------- España
    Plantilla("es-terminos", "España · Primaria y ESO · IN, SU, BI, NT, SB", "ES", "", ("primaria", "secundaria"),
              _por_tramos(cat.CUALITATIVA, (("IN", "Insuficiente", 0, 50, False), ("SU", "Suficiente", 50, 60, True), ("BI", "Bien", 60, 70, True),
                                            ("NT", "Notable", 70, 90, True), ("SB", "Sobresaliente", 90, 100, True))),
              "En Primaria y ESO se califica con los términos Insuficiente (IN), Suficiente (SU), Bien (BI), Notable (NT) y Sobresaliente (SB); se aprueba desde "
              "Suficiente. La normativa estatal la concretan las comunidades autónomas. Educación Infantil no se califica con notas: use el modo simple."),
    Plantilla("es-0-10", "España · Bachillerato · 0 a 10 (Insuficiente a Sobresaliente)", "ES", "", ("secundaria", "bachillerato"),
              _numerica(0, 10, decimales=1, aprobacion=5, redondeo=cat.ABAJO, tramos=_tramos((
                  ("IN", "Insuficiente", 0, 50, False), ("SU", "Suficiente", 50, 60, True), ("BI", "Bien", 60, 70, True),
                  ("NT", "Notable", 70, 90, True), ("SB", "Sobresaliente", 90, 100, True)))),
              "Calificaciones numéricas de 0 a 10 (se aprueba con 5) acompañadas de los términos IN, SU, BI, NT y SB; es la escala de Bachillerato y la que "
              "acompaña a los términos en el expediente de ESO. Las comunidades autónomas la concretan."),
    # ------------------------------------------------------------------------------------------------ Estados Unidos
    Plantilla("us-letras", "Estados Unidos · letras A–F", "US", "", TODOS, _por_tramos(cat.ALFABETICA, _LETRAS),
              "Escala de letras con tramos de diez puntos. Distritos y estados cambian los cortes, admiten más/menos (A−, B+) y definen el mínimo aprobatorio."),
    Plantilla("us-gpa", "Estados Unidos · GPA 0,0 a 4,0 (A = 4,0)", "US", "", ("secundaria", "bachillerato", "preuniversitario"),
              _numerica(0, 4, decimales=2, aprobacion=1, redondeo=cat.ABAJO, puntos=((0, 0), (60, 1), (70, 2), (80, 3), (90, 4), (100, 4)), tramos=_tramos((
                  ("F", "F", 0, 60, False, "No alcanza"), ("D", "D", 60, 70, True, "Suficiente"), ("C", "C", 70, 80, True, "Satisfactorio"),
                  ("B", "B", 80, 90, True, "Notable"), ("A", "A", 90, 100, True, "Sobresaliente")))),
              "Promedio de puntos de 0,0 a 4,0 con A = 4,0, B = 3,0, C = 2,0, D = 1,0 y F = 0,0; entre una letra y otra se interpola. Cada distrito o universidad cambia "
              "los cortes, admite más y menos (A−, B+) y pondera los cursos avanzados; el mínimo aprobatorio (aquí D, 1,0) lo fija cada institución."),
    Plantilla("us-porcentaje", "Estados Unidos · porcentaje 0–100", "US", "", TODOS, _numerica(0, 100, decimales=0, aprobacion=60),
              "Porcentaje de 0 a 100; el mínimo aprobatorio (60) lo fija cada distrito."),
    # ---------------------------------------------------------------------------------------------------------- México
    Plantilla("mx-0-10", "México · 0 a 10 (se aprueba con 6)", "MX", "", ("primaria", "secundaria", "bachillerato"),
              _numerica(0, 10, decimales=1, aprobacion=6),
              "Escala de 0 a 10 con 6 como mínimo aprobatorio. La educación básica oficial no asienta calificaciones menores a 5 y la Nueva Escuela Mexicana "
              "usa en algunos grados valoraciones descriptivas: para la escala que empieza en 5 use «México · 5 a 10»."),
    Plantilla("mx-5-10", "México · 5 a 10 (se aprueba con 6)", "MX", "", ("primaria", "secundaria"),
              _numerica(5, 10, decimales=1, aprobacion=6, redondeo=cat.ABAJO, puntos=((0, 5), (60, 6), (100, 10))),
              "Escala de 5 a 10, donde 5 es «no aprobado» y 6 el mínimo aprobatorio (aquí el 60 % del resultado interno): la que se usa en Secundaria y en varios grados "
              "de Primaria. En otros grados la escala empieza en 6: su institución debe confirmar cuál aplica a cada grado."),
    # ------------------------------------------------------------------------------------------------------- Colombia
    Plantilla("co-1-5", "Colombia · 1,0 a 5,0 (Bajo a Superior)", "CO", "", ("primaria", "secundaria", "bachillerato"),
              _numerica(1, 5, decimales=1, aprobacion=3, redondeo=cat.ABAJO, tramos=_tramos((
                  ("bajo", "Bajo", 0, 50, False), ("basico", "Básico", 50, 75, True), ("alto", "Alto", 75, 90, True), ("superior", "Superior", 90, 100, True)))),
              "Escala nacional de desempeño Superior, Alto, Básico y Bajo; la escala numérica y sus equivalencias las define cada institución en su sistema "
              "institucional de evaluación (Decreto 1290 de 2009). Se trunca (no se redondea hacia arriba) para que el redondeo no lleve un resultado por encima del "
              "corte de aprobación."),
    # --------------------------------------------------------------------------------------------------------- Chile
    Plantilla("cl-1-7", "Chile · 1,0 a 7,0 (se aprueba con 4,0 al 60 %)", "CL", "", ("primaria", "secundaria"),
              _numerica(1, 7, decimales=1, aprobacion=4, puntos=((0, 1), (60, 4), (100, 7))),
              "Notas de 1,0 a 7,0 con 4,0 como mínimo aprobatorio; el 4,0 corresponde habitualmente al 60 % de exigencia, que cada establecimiento puede cambiar. "
              "Educación Parvularia no califica con notas: use el modo simple."),
    # ---------------------------------------------------------------------------------------------------------- Perú
    Plantilla("pe-0-20", "Perú · vigesimal 0 a 20 (se aprueba con 11)", "PE", "", ("secundaria", "bachillerato"),
              _numerica(0, 20, decimales=0, aprobacion=11),
              "Escala vigesimal con 11 como mínimo aprobatorio, usada en secundaria y en educación superior."),
    Plantilla("pe-literal", "Perú · literal AD, A, B, C (competencias)", "PE", "", ("preescolar", "primaria", "secundaria"),
              _por_tramos(cat.COMPETENCIAS, (("C", "C", 0, 55, None, "En inicio"), ("B", "B", 55, 70, None, "En proceso"),
                                             ("A", "A", 70, 90, None, "Logro esperado"), ("AD", "AD", 90, 100, None, "Logro destacado"))),
              "Escala literal por competencias del Currículo Nacional. Los cortes sobre 0–100 son una equivalencia aproximada con la escala vigesimal: la "
              "evaluación por competencias es una valoración docente, no sólo un cálculo (use la valoración docente para fijar el nivel)."),
    # ------------------------------------------------------------------------------------------------------- Ecuador
    Plantilla("ec-0-10", "Ecuador · 0 a 10 (DAR, AAR, PAAR, NAAR)", "EC", "", ("primaria", "secundaria", "bachillerato"),
              _numerica(0, 10, decimales=2, aprobacion=7, redondeo=cat.ABAJO, tramos=_tramos((
                  ("NAAR", "No alcanza los aprendizajes requeridos", 0, "40.1", False), ("PAAR", "Próximo a alcanzar los aprendizajes requeridos", "40.1", 70, False),
                  ("AAR", "Alcanza los aprendizajes requeridos", 70, 90, True), ("DAR", "Domina los aprendizajes requeridos", 90, 100, True)))),
              "Escala cualitativa y cuantitativa del Ministerio de Educación: 9–10 DAR, 7–8,99 AAR, 4,01–6,99 PAAR, ≤ 4 NAAR; se aprueba con 7. Educación Inicial "
              "usa una valoración descriptiva: use el modo simple."),
)

POR_CODIGO: dict[str, Plantilla] = {p.codigo: p for p in PLANTILLAS}


def plantilla(codigo: str) -> Plantilla | None:
    return POR_CODIGO.get(codigo)


def como_dict(p: Plantilla) -> dict:
    return {"codigo": p.codigo, "nombre": p.nombre, "pais": p.pais, "jurisdiccion": p.jurisdiccion, "niveles": list(p.niveles), "referencia": p.referencia,
            "advertencia": p.advertencia, "tipo": p.definicion.tipo, "definicion": a_dict(p.definicion), "problemas": validar(p.definicion),
            "sistema": describir(p.definicion)}


def listar(pais: str | None = None) -> list[dict]:
    """El catálogo de plantillas (con las genéricas siempre), filtrado por país ISO si se pide."""
    pais = (pais or "").strip().upper()
    return [como_dict(p) for p in PLANTILLAS if not pais or p.pais in (pais, "")]
