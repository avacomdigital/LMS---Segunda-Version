"""
Los archivos que MOD-016 deja para el personal administrativo de la institución: texto llano y CSV que se abren con el Bloc de notas y con Excel, en español y SIN datos de personas
(INV-021: ni nombres, ni notas, ni evidencias; sólo fechas, tamaños, estados y huellas cortas).

  · constancia de un respaldo          cada vez que un respaldo termina: qué se guardó, cuándo, si se comprobó que se puede restaurar y dónde está
  · resumen de respaldos (CSV)         el historial completo, para Excel
  · hoja de custodia                   el código que la institución guarda para restaurar en OTRO equipo (BR-102). Se imprime una vez y NO se guarda en el equipo
  · informe de restauración            qué se recuperó y qué se pierde (JRN-019: «ve qué se recupera y qué se pierde»)

Quien los ve: la administración los LEE (`backup.read`); no puede respaldar ni restaurar (D-1). Puro: no importa Django.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from . import catalogos as cat

_TIPO = {cat.T_COMPLETO: "Completo", cat.T_INCREMENTAL: "Incremental (sólo lo que cambió desde el anterior)"}
_ESTADO = {cat.E_EN_CURSO: "En curso", cat.E_NO_VERIFICADO: "Terminado, pendiente de verificar", cat.E_VERIFICADO: "Terminado y verificado",
           cat.E_EXPORTADO: "Terminado, verificado y copiado a una memoria externa", cat.E_CADUCADO: "Retirado por la política de retención",
           cat.E_INCOMPLETO: "Quedó a medias (el equipo se apagó)", cat.E_FALLIDO: "No terminó (falló)"}
_DISPARO = {cat.D_PROGRAMADO: "Automático, según el calendario", cat.D_MANUAL: "Manual, pedido por el personal técnico de AVACOM",
            cat.D_PREVIO_ACTUALIZACION: "Previo a una actualización", cat.D_PREVIO_RESTAURACION: "Previo a una restauración (punto de retorno)"}
_MOTIVO_FALLO = {"espacio_insuficiente": "No había espacio suficiente en el destino.", "archivo_cambio": "Un archivo cambió mientras se copiaba; se reintenta en el siguiente ciclo.",
                 "sin_origen": "No se pudo leer la base de datos del aula."}


def _fecha(ms: int | None, desfase_min: int = 0) -> str:
    if ms is None:
        return "—"
    zona = timezone(timedelta(minutes=int(desfase_min)))
    return datetime.fromtimestamp(int(ms) / 1000, tz=zona).strftime("%d/%m/%Y %H:%M")


def _tamano(n: int | None) -> str:
    n = int(n or 0)
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{max(1, n // 1024) if n else 0} KB"


def _raya(ancho: int = 64) -> str:
    return "-" * ancho


def constancia(r: dict, institucion: str = "", desfase_min: int = 0) -> str:
    """La constancia de un respaldo. `r` es la ficha que arma `aplicacion.base.respaldo_a_dict`."""
    d = r.get("derivado") or {}
    estado = r.get("estado") or d.get("estado") or ""
    lineas = [
        "AVACOM · CONSTANCIA DE RESPALDO", _raya(),
        f"Institución:        {institucion or '—'}",
        f"Respaldo:           {str(r.get('respaldo_id') or '')[:8].upper()}  ({_TIPO.get(r.get('tipo'), r.get('tipo'))})",
        f"Hecho el:           {_fecha(r.get('creado_en'), desfase_min)}",
        f"Cómo se pidió:      {_DISPARO.get(r.get('disparo'), r.get('disparo') or '—')}",
        f"Estado:             {_ESTADO.get(estado, estado)}",
    ]
    if estado == cat.E_FALLIDO:
        lineas.append(f"Qué pasó:           {_MOTIVO_FALLO.get(r.get('error'), r.get('error') or 'Falló; el detalle está en el registro técnico.')}")
    lineas += [
        f"Verificado el:      {_fecha(r.get('verificado_en'), desfase_min) if r.get('verificado_en') else 'Todavía no (se verifica sola poco después)'}",
        f"Copiado a memoria:  {_fecha(r.get('exportado_en'), desfase_min) if r.get('exportado') else 'No'}",
        f"Tamaño del archivo: {_tamano(r.get('bytes'))}", "",
        "QUÉ CONTIENE",
        "  · La base de datos del aula completa: usuarios, grupos, clases, evaluaciones, calificaciones, asistencia y bitácora de auditoría.",
        f"  · Archivos de la institución: {int(r.get('archivos') or 0)}.",
    ]
    if r.get("tipo") == cat.T_INCREMENTAL:
        lineas.append("  · Es incremental: para restaurar hace falta también el respaldo completo anterior.")
    lineas += ["  · NO incluye el contenido reinstalable (cursos de la biblioteca y medios en caché) salvo que el personal técnico lo haya pedido: se vuelve a descargar.", "",
               "PROTECCIÓN",
               "  · El archivo está cifrado (AES-256). Ni el personal técnico puede leer los datos de los alumnos.",
               "  · Sólo se restaura en este mismo equipo o en otro con el CÓDIGO DE CUSTODIA de la institución (hoja de custodia).",
               "  · Restaurar o sacar una copia del equipo sólo lo hace el personal técnico de AVACOM WORLD, con una autorización firmada por AVACOM.", "",
               "DATOS DE CONTROL",
               f"  Versión del producto:  {r.get('version_producto') or '—'}",
               f"  Huella del archivo:    {str(r.get('sha256') or '')[:16] or '—'}",
               f"  Copia local hasta:     {r.get('conservar_hasta') or 'según la política de retención'}", "",
               "Esta constancia no contiene datos de personas.", _raya()]
    return "\n".join(lineas) + "\n"


def resumen_csv(respaldos: list[dict], desfase_min: int = 0) -> str:
    """El historial de respaldos para abrir en Excel (separador `;`, como en las exportaciones del resto del producto; el llamador lo guarda en UTF-8 con BOM)."""
    s = io.StringIO()
    w = csv.writer(s, delimiter=";", lineterminator="\r\n")
    w.writerow(["fecha", "tipo", "estado", "como_se_pidio", "verificado", "copiado_a_memoria", "tamano_mb", "version_producto", "huella", "respaldo"])
    for r in sorted(respaldos, key=lambda x: int(x.get("creado_en") or 0), reverse=True):
        w.writerow([_fecha(r.get("creado_en"), desfase_min), r.get("tipo"), _ESTADO.get(r.get("estado"), r.get("estado")), _DISPARO.get(r.get("disparo"), r.get("disparo")),
                    _fecha(r.get("verificado_en"), desfase_min) if r.get("verificado_en") else "", _fecha(r.get("exportado_en"), desfase_min) if r.get("exportado") else "",
                    f"{int(r.get('bytes') or 0) / 1024 ** 2:.1f}".replace(".", ","), r.get("version_producto") or "", str(r.get("sha256") or "")[:16], str(r.get("respaldo_id") or "")[:8].upper()])
    return s.getvalue()


def hoja_de_custodia(codigo: str, nodo_id: str, emitida_en: int, institucion: str = "", desfase_min: int = 0) -> str:
    """El código de custodia para imprimir (BR-102). Contiene el SECRETO: se entrega una vez al representante de la institución y no se guarda en el equipo."""
    return "\n".join([
        "AVACOM · HOJA DE CUSTODIA DE LOS RESPALDOS", _raya(),
        f"Institución:  {institucion or '—'}",
        f"Equipo:       {str(nodo_id)[:8].upper()}",
        f"Emitida el:   {_fecha(emitida_en, desfase_min)}", "",
        "CÓDIGO DE CUSTODIA", "",
        f"    {codigo}", "",
        "PARA QUÉ SIRVE",
        "  Los respaldos están cifrados. En el mismo equipo se abren solos; en un equipo NUEVO o reemplazado, el personal técnico de AVACOM necesitará este código para restaurar",
        "  la información de la institución. Sin él, un respaldo hecho en otro equipo no se puede abrir (BR-102).", "",
        "CÓMO GUARDARLO",
        "  1. Imprima esta hoja y guárdela bajo llave (caja fuerte o archivo de la rectoría), separada del equipo y de las memorias con los respaldos.",
        "  2. No lo fotografíe ni lo envíe por correo o mensajería.",
        "  3. Anote quién lo custodia y la fecha. Si se pierde, avise al personal técnico de AVACOM: se emite uno nuevo (los respaldos anteriores siguen abriéndose en este equipo).", "",
        "Esta hoja se muestra UNA sola vez. El equipo no conserva el código.", _raya()]) + "\n"


def informe_de_restauracion(r: dict, resultado: dict, institucion: str = "", desfase_min: int = 0) -> str:
    """Qué se recuperó y qué se pierde (JRN-019). `resultado`: lo que devuelve el motor al restaurar."""
    perdidas = resultado.get("perdidas") or {}
    lineas = [
        "AVACOM · INFORME DE RESTAURACIÓN", _raya(),
        f"Institución:            {institucion or '—'}",
        f"Restaurado el:          {_fecha(resultado.get('en'), desfase_min)}",
        f"Respaldo usado:         {str(r.get('respaldo_id') or '')[:8].upper()}  ({_TIPO.get(r.get('tipo'), r.get('tipo'))}, del {_fecha(r.get('creado_en'), desfase_min)})",
        f"Resultado:              {'Restauración completa' if resultado.get('ok', True) else 'No se restauró'}", "",
        "QUÉ SE RECUPERÓ",
        "  · La base de datos del aula tal como estaba al hacerse el respaldo.",
        f"  · Archivos de la institución: {int(resultado.get('archivos') or 0)}.", "",
        "QUÉ SE PIERDE",
        f"  · Todo lo registrado entre el respaldo y la restauración: unas {perdidas.get('horas', '—')} horas de actividad.",
        f"  · Eventos de la cola posteriores al respaldo: {perdidas.get('eventos', '—')} (la secuencia del equipo NO retrocede: ninguna secuencia se repite).", "",
        "QUÉ PASÓ ADEMÁS",
        f"  · Se tomó un respaldo de seguridad ANTES de restaurar (punto de retorno {str(resultado.get('punto_de_retorno') or '—')[:8].upper()}).",
        "  · Se cerraron todas las sesiones abiertas: cada persona entra de nuevo.",
        f"  · Licencia: {resultado.get('licencia') or 'se vuelve a validar contra la huella del equipo'}.",
        f"  · Índices y reportes: {resultado.get('reconstruidos') or 'se reconstruyen a partir de los datos restaurados'}.", "",
        "QUÉ HACER AHORA",
        "  1. Pida a los profesores y a los alumnos que vuelvan a entrar.",
        "  2. Reinicie el servicio del aula si el personal técnico lo indica.",
        "  3. Guarde este informe junto con la constancia del respaldo usado.", "",
        "Este informe no contiene datos de personas.", _raya()]
    return "\n".join(lineas) + "\n"
