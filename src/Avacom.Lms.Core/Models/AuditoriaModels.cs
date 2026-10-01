using System.Text.Json;
using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Models;

// MOD-019 · Audit. Lo que devuelve /api/auditoria/ y /api/logs/ (contrato en spec-driven/05-audit-logs/backend.md).

public sealed record ActorAsiento(
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("usuario_id")] string? UsuarioId,
    [property: JsonPropertyName("rotulo")] string? Rotulo)
{
    /// <summary>Lo que se muestra: el alias si el nodo lo trajo; si no, el tipo de actor en lenguaje llano.</summary>
    public string Legible => !string.IsNullOrWhiteSpace(Rotulo) ? Rotulo! : Tipo switch
    {
        "sistema" => "El nodo (automático)",
        "instalador" => "El instalador",
        "dispositivo" => "Un equipo",
        "declarado" => string.IsNullOrWhiteSpace(UsuarioId) ? "Alguien sin sesión" : UsuarioId!,
        _ => string.IsNullOrWhiteSpace(UsuarioId) ? "Desconocido" : UsuarioId!,
    };
}

public sealed record ObjetoAsiento(
    [property: JsonPropertyName("tabla")] string? Tabla,
    [property: JsonPropertyName("id")] string? Id)
{
    public string Legible => string.IsNullOrWhiteSpace(Tabla) ? "—" : string.IsNullOrWhiteSpace(Id) ? Tabla! : $"{Tabla} · {Id}";
}

/// <summary>Un asiento de la bitácora. En la lista <c>Huella</c> viene abreviada; en el detalle, completa y con <c>HuellaPrevia</c>.</summary>
public sealed record Asiento(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("secuencia")] long Secuencia,
    [property: JsonPropertyName("ocurrido_en")] long OcurridoEn,
    [property: JsonPropertyName("actor")] ActorAsiento? Actor,
    [property: JsonPropertyName("roles_activos")] IReadOnlyList<string>? RolesActivos,
    [property: JsonPropertyName("modulo")] string? Modulo,
    [property: JsonPropertyName("modulo_etiqueta")] string? ModuloEtiqueta,
    [property: JsonPropertyName("accion")] string Accion,
    [property: JsonPropertyName("etiqueta")] string? Etiqueta,
    [property: JsonPropertyName("resultado")] string Resultado,
    [property: JsonPropertyName("objeto")] ObjetoAsiento? Objeto,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("origen")] string? Origen,
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId,
    [property: JsonPropertyName("correlacion_id")] string? CorrelacionId,
    [property: JsonPropertyName("evento_id")] string? EventoId,
    [property: JsonPropertyName("tramo_id")] string? TramoId,
    [property: JsonPropertyName("sensible")] bool Sensible,
    [property: JsonPropertyName("enmascarado")] bool Enmascarado,
    [property: JsonPropertyName("huella")] string? Huella,
    [property: JsonPropertyName("huella_previa")] string? HuellaPrevia = null,
    [property: JsonPropertyName("valor_anterior")] JsonElement? ValorAnterior = null,
    [property: JsonPropertyName("valor_nuevo")] JsonElement? ValorNuevo = null)
{
    public string EtiquetaLegible => string.IsNullOrWhiteSpace(Etiqueta) ? Accion : Etiqueta!;
    public string ResultadoLegible => Resultado switch { "ok" => "Correcto", "denegado" => "Denegado", "fallido" => "Fallido", _ => Resultado };
    public DateTimeOffset Momento => DateTimeOffset.FromUnixTimeMilliseconds(OcurridoEn).ToLocalTime();
}

public sealed record PaginaAsientos(
    [property: JsonPropertyName("asientos")] IReadOnlyList<Asiento> Asientos,
    [property: JsonPropertyName("siguiente")] long? Siguiente,
    [property: JsonPropertyName("orden")] string? Orden,
    [property: JsonPropertyName("limite")] int Limite,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("enmascarado")] bool Enmascarado);

public sealed record AccionCatalogo(
    [property: JsonPropertyName("clave")] string Clave,
    [property: JsonPropertyName("modulo")] string Modulo,
    [property: JsonPropertyName("etiqueta")] string Etiqueta,
    [property: JsonPropertyName("exige_motivo")] bool ExigeMotivo,
    [property: JsonPropertyName("sensible")] bool Sensible);

public sealed record ClaveEtiqueta(
    [property: JsonPropertyName("clave")] string Clave,
    [property: JsonPropertyName("etiqueta")] string Etiqueta);

public sealed record CatalogoAuditoria(
    [property: JsonPropertyName("version")] string? Version,
    [property: JsonPropertyName("modulos")] IReadOnlyList<ClaveEtiqueta> Modulos,
    [property: JsonPropertyName("acciones")] IReadOnlyList<AccionCatalogo> Acciones,
    [property: JsonPropertyName("resultados")] IReadOnlyList<ClaveEtiqueta> Resultados,
    [property: JsonPropertyName("origenes")] IReadOnlyList<string> Origenes);

public sealed record TramoBitacora(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("desde")] long Desde,
    [property: JsonPropertyName("hasta")] long Hasta,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("abierta")] bool Abierta,
    [property: JsonPropertyName("huella_cierre")] string? HuellaCierre,
    [property: JsonPropertyName("verificado_en")] long? VerificadoEn,
    [property: JsonPropertyName("verificado_hasta")] long? VerificadoHasta,
    [property: JsonPropertyName("salto_en")] long? SaltoEn,
    [property: JsonPropertyName("salto_causa")] string? SaltoCausa,
    [property: JsonPropertyName("exportado_en")] long? ExportadoEn,
    [property: JsonPropertyName("archivo")] string? Archivo,
    [property: JsonPropertyName("rotado_en")] long? RotadoEn,
    [property: JsonPropertyName("creado_en")] long CreadoEn,
    [property: JsonPropertyName("asientos")] long Asientos)
{
    public string EstadoLegible => Estado switch
    {
        "activa" => "Activa", "verificada" => "Verificada", "con_salto" => "Salto detectado", "rotada" => "Rotada", _ => Estado,
    };
    public string Rango => Hasta < Desde ? $"desde {Desde} (vacío)" : $"{Desde} – {Hasta}";
}

public sealed record TramosBitacora([property: JsonPropertyName("tramos")] IReadOnlyList<TramoBitacora> Tramos);

public sealed record CabezaBitacora(
    [property: JsonPropertyName("secuencia")] long Secuencia,
    [property: JsonPropertyName("huella")] string? Huella);

public sealed record SaltoBitacora(
    [property: JsonPropertyName("tramo_id")] string? TramoId,
    [property: JsonPropertyName("secuencia")] long? Secuencia,
    [property: JsonPropertyName("causa")] string? Causa);

public sealed record EstadoBitacora(
    [property: JsonPropertyName("cabeza")] CabezaBitacora Cabeza,
    [property: JsonPropertyName("total_asientos")] long TotalAsientos,
    [property: JsonPropertyName("tramo_activo")] TramoBitacora? TramoActivo,
    [property: JsonPropertyName("ultimo_verificado_en")] long? UltimoVerificadoEn,
    [property: JsonPropertyName("salto_detectado")] bool SaltoDetectado,
    [property: JsonPropertyName("salto")] SaltoBitacora? Salto,
    [property: JsonPropertyName("triggers_ok")] bool TriggersOk,
    [property: JsonPropertyName("tamano_bytes")] long TamanoBytes,
    [property: JsonPropertyName("umbral_bytes")] long UmbralBytes,
    [property: JsonPropertyName("porcentaje_umbral")] double? PorcentajeUmbral,
    [property: JsonPropertyName("tramos")] int Tramos,
    [property: JsonPropertyName("version_catalogo")] string? VersionCatalogo,
    [property: JsonPropertyName("verificar_cada_s")] int VerificarCadaS)
{
    /// <summary>Lo que dice el semáforo de «Integridad» (PAN-240): verde si la cadena verificó sin salto, rojo si hay salto, ámbar si nunca se verificó.</summary>
    public string Semaforo => SaltoDetectado || !TriggersOk ? "rojo" : UltimoVerificadoEn is null ? "ambar" : "verde";
}

public sealed record VerificacionTramo(
    [property: JsonPropertyName("tramo_id")] string? TramoId,
    [property: JsonPropertyName("desde")] long Desde,
    [property: JsonPropertyName("hasta")] long Hasta,
    [property: JsonPropertyName("estado")] string? Estado,
    [property: JsonPropertyName("verificados")] long Verificados,
    [property: JsonPropertyName("salto_en")] long? SaltoEn,
    [property: JsonPropertyName("causa")] string? Causa);

public sealed record ResultadoVerificacion(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("verificados")] long Verificados,
    [property: JsonPropertyName("salto_en")] long? SaltoEn,
    [property: JsonPropertyName("causa")] string? Causa,
    [property: JsonPropertyName("tramos")] IReadOnlyList<VerificacionTramo>? Tramos);

public sealed record Exportacion(
    [property: JsonPropertyName("exportacion_id")] string ExportacionId,
    [property: JsonPropertyName("alcance")] string? Alcance,
    [property: JsonPropertyName("desde")] long? Desde,
    [property: JsonPropertyName("hasta")] long? Hasta,
    [property: JsonPropertyName("total")] long? Total,
    [property: JsonPropertyName("archivo")] string? Archivo,
    [property: JsonPropertyName("firma")] string? Firma,
    [property: JsonPropertyName("exportado_en")] long? ExportadoEn,
    [property: JsonPropertyName("exportado_por")] string? ExportadoPor,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("disponible")] bool? Disponible,
    [property: JsonPropertyName("mensaje")] string? Mensaje,
    [property: JsonPropertyName("descarga")] string? Descarga);

public sealed record MotivoExportacion(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("etiqueta")] string Etiqueta);

public sealed record ListaExportaciones(
    [property: JsonPropertyName("exportaciones")] IReadOnlyList<Exportacion> Exportaciones,
    [property: JsonPropertyName("motivos")] IReadOnlyList<MotivoExportacion> Motivos,
    [property: JsonPropertyName("autorizacion_vigente")] bool AutorizacionVigente);

public sealed record TecnicoAuditado(
    [property: JsonPropertyName("usuario_id")] string UsuarioId,
    [property: JsonPropertyName("rotulo")] string? Rotulo);

public sealed record AccesosDelTecnico(
    [property: JsonPropertyName("tecnicos")] IReadOnlyList<TecnicoAuditado> Tecnicos,
    [property: JsonPropertyName("asientos")] IReadOnlyList<Asiento> Asientos,
    [property: JsonPropertyName("siguiente")] long? Siguiente,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("denegaciones")] int Denegaciones,
    [property: JsonPropertyName("sin_acceso_a_datos_personales")] bool SinAccesoADatosPersonales,
    [property: JsonPropertyName("cadena_verificada")] bool CadenaVerificada,
    [property: JsonPropertyName("salto_detectado")] bool SaltoDetectado);

/// <summary>Una línea de los logs del nodo (<c>GET /api/logs/</c>): identificadores y cifras, nunca datos personales.</summary>
public sealed record LineaLog(
    [property: JsonPropertyName("ts")] string? Ts,
    [property: JsonPropertyName("nivel")] string? Nivel,
    [property: JsonPropertyName("canal")] string? Canal,
    [property: JsonPropertyName("app")] string? App,
    [property: JsonPropertyName("modulo")] string? Modulo,
    [property: JsonPropertyName("evento")] string? Evento,
    [property: JsonPropertyName("ruta")] string? Ruta,
    [property: JsonPropertyName("caso")] string? Caso,
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId,
    [property: JsonPropertyName("usuario_id")] string? UsuarioId,
    [property: JsonPropertyName("corr")] string? Corr,
    [property: JsonPropertyName("mensaje")] string? Mensaje,
    [property: JsonPropertyName("detalle")] JsonElement? Detalle,
    [property: JsonPropertyName("traza")] string? Traza,
    [property: JsonPropertyName("archivo")] string? Archivo);

public sealed record ResumenLogs(
    [property: JsonPropertyName("happy")] int Happy,
    [property: JsonPropertyName("sad")] int Sad,
    [property: JsonPropertyName("bad")] int Bad,
    [property: JsonPropertyName("niveles")] Dictionary<string, int>? Niveles);

public sealed record LogsDelNodo(
    [property: JsonPropertyName("lineas")] IReadOnlyList<LineaLog> Lineas,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("resumen")] ResumenLogs? Resumen,
    [property: JsonPropertyName("archivos")] IReadOnlyList<string>? Archivos);

public sealed record EntregaLogs(
    [property: JsonPropertyName("recibidos")] int Recibidos,
    [property: JsonPropertyName("escritos")] int Escritos,
    [property: JsonPropertyName("descartados")] int Descartados,
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId);

/// <summary>Filtros de la consulta de asientos (PAN-240 «Comportamiento»). Todo es opcional; se traduce a la query de <c>GET asientos/</c>.</summary>
public sealed record FiltrosBitacora(
    string? Actor = null, string? ActorTipo = null, long? Desde = null, long? Hasta = null, string? Modulo = null, string? Accion = null,
    string? Resultado = null, string? ObjetoTabla = null, string? ObjetoId = null, string? Dispositivo = null, string? Correlacion = null,
    string? Texto = null, string? Tramo = null, bool? Sensible = null, int? Limite = null, long? Antes = null, long? Despues = null)
{
    public string Query()
    {
        var partes = new List<string>();
        void Agregar(string clave, object? valor)
        {
            if (valor is null) return;
            var texto = valor is bool b ? (b ? "true" : "false") : Convert.ToString(valor, System.Globalization.CultureInfo.InvariantCulture);
            if (string.IsNullOrWhiteSpace(texto)) return;
            partes.Add($"{clave}={Uri.EscapeDataString(texto!)}");
        }
        Agregar("actor", Actor); Agregar("actor_tipo", ActorTipo); Agregar("desde", Desde); Agregar("hasta", Hasta); Agregar("modulo", Modulo);
        Agregar("accion", Accion); Agregar("resultado", Resultado); Agregar("objeto_tabla", ObjetoTabla); Agregar("objeto_id", ObjetoId);
        Agregar("dispositivo", Dispositivo); Agregar("correlacion", Correlacion); Agregar("texto", Texto); Agregar("tramo", Tramo);
        Agregar("sensible", Sensible); Agregar("limite", Limite); Agregar("antes", Antes); Agregar("despues", Despues);
        return partes.Count == 0 ? string.Empty : "?" + string.Join("&", partes);
    }
}

/// <summary>Filtros de <c>GET /api/logs/</c> (pestaña «Errores», PAN-242).</summary>
public sealed record FiltrosLogs(
    string? Canal = null, string? Nivel = null, string? App = null, string? Ruta = null, string? Desde = null, string? Corr = null,
    string? Dispositivo = null, string? Evento = null, string? Archivo = null, int? Ultimos = null)
{
    public string Query()
    {
        var partes = new List<string>();
        void Agregar(string clave, object? valor)
        {
            var texto = Convert.ToString(valor, System.Globalization.CultureInfo.InvariantCulture);
            if (!string.IsNullOrWhiteSpace(texto)) partes.Add($"{clave}={Uri.EscapeDataString(texto!)}");
        }
        Agregar("canal", Canal); Agregar("nivel", Nivel); Agregar("app", App); Agregar("ruta", Ruta); Agregar("desde", Desde); Agregar("corr", Corr);
        Agregar("dispositivo", Dispositivo); Agregar("evento", Evento); Agregar("archivo", Archivo); Agregar("ultimos", Ultimos);
        return partes.Count == 0 ? string.Empty : "?" + string.Join("&", partes);
    }
}
