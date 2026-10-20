using System.Text;
using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Licencia;

// Contratos de /api/licencia/ (MOD-018 · Licensing) tal como los entrega el nodo (backend/licenciamiento/interfaces/views.py y aplicacion/acciones.py). Los nombres JSON son los del
// backend (snake_case). El cliente NO decide nada de la licencia (SEC-001): lo que llega es lo que el nodo calculó y aquí sólo se lee para pintarlo. Las horas son instantes del nodo
// en milisegundos. Un límite, un porcentaje o un día que llega null significa «sin tope» o «no aplica», nunca un cero.

// ------------------------------------------------------------------------------------------------ catálogos (los códigos del contrato; el texto lo pone LicenciaTexto)

/// <summary>Los estados de la licencia (P-05). El estado SALE del tiempo y de los hechos: el nodo lo calcula y el cliente sólo lo nombra.</summary>
public static class EstadosDeLicencia
{
    public const string SinLicencia = "sin_licencia";
    public const string Activa = "activa";
    public const string Reactivada = "reactivada";
    public const string EnGracia = "en_gracia";
    public const string LiberacionPendiente = "liberacion_pendiente";
    public const string Degradada = "degradada";

    public static readonly IReadOnlyList<string> Todos = [SinLicencia, Activa, Reactivada, EnGracia, LiberacionPendiente, Degradada];
}

/// <summary>El «por qué» de un estado (<c>motivo</c> de <c>estado/</c>).</summary>
public static class MotivosDeEstado
{
    public const string Evaluacion = "evaluacion";
    public const string EvaluacionVencida = "evaluacion_vencida";
    public const string Vigente = "vigente";
    public const string Vencida = "vencida";
    public const string HuellaDistinta = "huella_distinta";
    public const string LiberacionPendiente = "liberacion_pendiente";
    public const string LiberacionNoConfirmada = "liberacion_no_confirmada";
    public const string AunNoVigente = "aun_no_vigente";
    public const string Reactivada = "reactivada";
    public const string LicenciaIlimitada = "licencia_ilimitada";

    public static readonly IReadOnlyList<string> Todos =
        [Evaluacion, EvaluacionVencida, Vigente, Vencida, HuellaDistinta, LiberacionPendiente, LiberacionNoConfirmada, AunNoVigente, Reactivada, LicenciaIlimitada];
}

/// <summary>Banderas ortogonales al estado: se suman a él, no lo reemplazan.</summary>
public static class BanderasDeLicencia
{
    /// <summary>El reloj de este equipo está ATRASADO respecto de lo que el aula ya vio.</summary>
    public const string RelojSospechoso = "reloj_sospechoso";
    /// <summary>La fecha de este equipo está ADELANTADA y el nodo no la acepta (Q-L13): un error hasta que la fecha concuerde o la administración la confirme.</summary>
    public const string RelojAdelantado = "reloj_adelantado";
    public const string HuellaParcial = "huella_parcial";
    public const string IntegridadAlterada = "integridad_alterada";

    public static readonly IReadOnlyList<string> Todas = [RelojSospechoso, RelojAdelantado, HuellaParcial, IntegridadAlterada];
}

/// <summary>Los módulos que una licencia puede apagar (P-07). Todo lo demás —la clase, la evaluación, el modo de estudio, la lectura de datos— es núcleo y no se apaga nunca.</summary>
public static class CapacidadesLicenciables
{
    public const string Reportes = "reportes";
    public const string Busqueda = "busqueda";
    public const string Importacion = "importacion";
    public const string AdministracionAvanzada = "administracion_avanzada";

    public static readonly IReadOnlyList<string> Todas = [Reportes, Busqueda, Importacion, AdministracionAvanzada];
}

/// <summary>Los códigos de <c>avisos[]</c>: el nodo los da con sus cifras y en orden de importancia; el texto lo pone el cliente (<see cref="LicenciaTexto.Aviso"/>).</summary>
public static class AvisosDeLicencia
{
    public const string Degradada = "degradada";
    public const string Gracia = "gracia";
    public const string LiberacionPendiente = "liberacion_pendiente";
    public const string Evaluacion = "evaluacion";
    public const string PorVencer = "por_vencer";
    public const string Cupo = "cupo";
    public const string RelojSospechoso = BanderasDeLicencia.RelojSospechoso;
    public const string RelojAdelantado = BanderasDeLicencia.RelojAdelantado;
    public const string HuellaParcial = BanderasDeLicencia.HuellaParcial;
    public const string IntegridadAlterada = BanderasDeLicencia.IntegridadAlterada;

    public static readonly IReadOnlyList<string> Todos = [Degradada, Gracia, LiberacionPendiente, Evaluacion, PorVencer, Cupo, RelojSospechoso, RelojAdelantado, HuellaParcial, IntegridadAlterada];
}

/// <summary>Los <c>motivo</c> de un 400 <c>licencia_invalida</c> (backend/licenciamiento/dominio/errores.py: «son parte del contrato, no se renombran»).</summary>
public static class MotivosDeRechazo
{
    public const string DemasiadoGrande = "demasiado_grande";
    public const string DemasiadoCorta = "demasiado_corta";
    public const string Formato = "formato";
    public const string Texto = "texto";
    public const string VersionNoSoportada = "version_no_soportada";
    public const string KidDesconocido = "kid_desconocido";
    public const string FirmaInvalida = "firma_invalida";
    public const string EtiquetaCriticaDesconocida = "etiqueta_critica_desconocida";
    public const string CampoFaltante = "campo_faltante";
    public const string CampoInvalido = "campo_invalido";
    public const string SolicitudAjena = "solicitud_ajena";
    public const string SerieNoPosterior = "serie_no_posterior";
    public const string OtraLicencia = "otra_licencia";
    public const string SinLicenciaInstalada = "sin_licencia_instalada";
    public const string TipoNoAdmitido = "tipo_no_admitido";
    public const string AunNoVigente = "aun_no_vigente";

    public static readonly IReadOnlyList<string> Todos =
    [
        DemasiadoGrande, DemasiadoCorta, Formato, Texto, VersionNoSoportada, KidDesconocido, FirmaInvalida, EtiquetaCriticaDesconocida, CampoFaltante, CampoInvalido,
        SolicitudAjena, SerieNoPosterior, OtraLicencia, SinLicenciaInstalada, TipoNoAdmitido, AunNoVigente,
    ];
}

/// <summary>Los <c>codigo</c> de error de <c>/api/licencia/</c> (y los dos 402 que cualquier módulo puede devolver).</summary>
public static class CodigosDeLicencia
{
    public const string LicenciaInvalida = "licencia_invalida";
    public const string HuellaNoCoincide = "huella_no_coincide";
    public const string Conflicto = "conflicto";
    public const string SinPermiso = "sin_permiso";
    public const string NoEncontrado = "no_encontrado";
    public const string DatosInvalidos = "datos_invalidos";
    public const string NoDisponiblePorLicencia = "no_disponible_por_licencia";
    public const string CupoAgotado = "cupo_agotado";

    public static readonly IReadOnlyList<string> Todos = [LicenciaInvalida, HuellaNoCoincide, Conflicto, SinPermiso, NoEncontrado, DatosInvalidos, NoDisponiblePorLicencia, CupoAgotado];
}

public static class ModosDeLicencia
{
    /// <summary>El nodo verifica licencias firmadas (producción, o desarrollo con <c>AVACOM_LICENCIA_MODO=firmada</c>).</summary>
    public const string Firmada = "firmada";
    /// <summary>Desarrollo y pruebas: nada se restringe y no hay nada que activar.</summary>
    public const string Ilimitada = "ilimitada";
}

/// <summary>Lo que el nodo hizo al instalar un archivo (<c>accion</c> de <c>activar/</c> y <c>renovar/</c>).</summary>
public static class AccionesDeInstalacion
{
    public const string Activada = "activada";
    public const string Renovada = "renovada";
    public const string Reactivada = "reactivada";

    public static readonly IReadOnlyList<string> Todas = [Activada, Renovada, Reactivada];
}

/// <summary>A qué está sellada la licencia: al hardware del equipo o, si el equipo no tiene datos de hardware fiables, a una huella de instalación (más débil).</summary>
public static class NivelesDeHuella
{
    public const string Hardware = "hardware";
    public const string Instalacion = "instalacion";
}

public static class TiposDeLicencia
{
    public const string Produccion = "produccion";
    public const string Evaluacion = "evaluacion";
    public const string Desarrollo = "desarrollo";
}

/// <summary>Los permisos de MOD-018 (P-15): leer y activar los tienen la administración y el soporte técnico; renovar, sólo la administración.</summary>
public static class PermisosDeLicencia
{
    public const string Leer = "license.read";
    public const string Activar = "license.activate";
    public const string Renovar = "license.renew";
}

/// <summary>Por qué ruta se instala un archivo: <c>activar/</c> o <c>renovar/</c>.</summary>
public static class ViasDeInstalacion
{
    public const string Activar = "activar";
    public const string Renovar = "renovar";
}

// ------------------------------------------------------------------------------------------------ estado/ (y el mismo cuerpo tras activar, renovar, liberar o confirmar la fecha)

/// <summary>Lo que permite la licencia. null = sin tope.</summary>
public sealed record LimitesDeLicencia(
    [property: JsonPropertyName("equipos")] int? Equipos,
    [property: JsonPropertyName("usuarios")] int? Usuarios,
    [property: JsonPropertyName("concurrentes_normal")] int? ConcurrentesNormal,
    [property: JsonPropertyName("concurrentes_pico")] int? ConcurrentesPico);

/// <summary>La licencia instalada tal como la ve el administrador: sin la firma, sin los hashes de la huella. <see cref="Archivo"/> son los 12 primeros caracteres del SHA-256 del archivo.</summary>
public sealed record ResumenDeLicencia(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("serie")] int Serie,
    [property: JsonPropertyName("aula")] string? Aula,
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("emitida")] long Emitida,
    [property: JsonPropertyName("desde")] long Desde,
    [property: JsonPropertyName("vence")] long Vence,
    [property: JsonPropertyName("gracia_dias")] int GraciaDias,
    [property: JsonPropertyName("limites")] LimitesDeLicencia? Limites,
    [property: JsonPropertyName("capacidades")] IReadOnlyList<string>? Capacidades,
    [property: JsonPropertyName("liberacion_pendiente")] bool LiberacionPendiente,
    [property: JsonPropertyName("liberacion_dias")] int LiberacionDias,
    [property: JsonPropertyName("kid")] string? Kid,
    [property: JsonPropertyName("archivo")] string? Archivo)
{
    /// <summary>La licencia habilita todos los módulos licenciables (<c>*</c>).</summary>
    public bool Todas => Capacidades?.Contains("*") == true;
}

/// <summary>
/// Las fechas que importan: <see cref="Desde"/> y <see cref="Vence"/> de la licencia (null sin licencia), los días de gracia y el PRÓXIMO hito para quien lee (<see cref="Hasta"/>: fin de
/// la vigencia, de la gracia, de la liberación o de la evaluación) con los días completos que faltan.
/// </summary>
public sealed record VigenciaDeLicencia(
    [property: JsonPropertyName("desde")] long? Desde,
    [property: JsonPropertyName("vence")] long? Vence,
    [property: JsonPropertyName("gracia_dias")] int? GraciaDias,
    [property: JsonPropertyName("hasta")] long? Hasta,
    [property: JsonPropertyName("dias_restantes")] int? DiasRestantes);

/// <summary>La huella del equipo frente a la de la licencia: sólo el nivel y cifras, ningún identificador. Sin licencia, <see cref="Coincide"/> y las cifras son null.</summary>
public sealed record HuellaDelEquipo(
    [property: JsonPropertyName("nivel")] string? Nivel,
    [property: JsonPropertyName("coincide")] bool? Coincide,
    [property: JsonPropertyName("parcial")] bool Parcial,
    [property: JsonPropertyName("k")] int? K,
    [property: JsonPropertyName("factores")] int? Factores,
    [property: JsonPropertyName("coinciden")] int? Coinciden);

/// <summary>Qué módulos licenciables están encendidos y cuáles en pausa AHORA.</summary>
public sealed record CapacidadesDeLicencia(
    [property: JsonPropertyName("habilitadas")] IReadOnlyList<string>? Habilitadas,
    [property: JsonPropertyName("no_disponibles")] IReadOnlyList<string>? NoDisponibles);

/// <summary>
/// Un aviso con sus cifras (los campos que no aplican a su código llegan ausentes y quedan null). La fecha adelantada (<c>reloj_adelantado</c>, Q-L13) trae cuántos días lo está
/// (<see cref="AdelantoDias"/>), la fecha que tiene el equipo (<see cref="FechaEquipo"/>) y la que el aula lleva (<see cref="FechaEsperada"/>, la hora confiable), en milisegundos del nodo.
/// </summary>
public sealed record AvisoDeLicencia(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("motivo")] string? Motivo = null,
    [property: JsonPropertyName("dias")] int? Dias = null,
    [property: JsonPropertyName("urgente")] bool? Urgente = null,
    [property: JsonPropertyName("umbral")] int? Umbral = null,
    [property: JsonPropertyName("tipo")] string? Tipo = null,
    [property: JsonPropertyName("en_uso")] int? EnUso = null,
    [property: JsonPropertyName("limite")] int? Limite = null,
    [property: JsonPropertyName("porcentaje")] int? Porcentaje = null,
    [property: JsonPropertyName("adelanto_dias")] int? AdelantoDias = null,
    [property: JsonPropertyName("fecha_equipo")] long? FechaEquipo = null,
    [property: JsonPropertyName("fecha_esperada")] long? FechaEsperada = null);

/// <summary>Lo que se usa del cupo según la última instantánea del nodo (el conteo fino y en el momento está en <c>consumo/</c>).</summary>
public sealed record ConsumoActual(
    [property: JsonPropertyName("equipos")] int? Equipos,
    [property: JsonPropertyName("usuarios")] int? Usuarios);

/// <summary>
/// El estado de la licencia de este nodo (<c>GET estado/</c>). Es también el cuerpo que devuelven <c>activar/</c>, <c>renovar/</c> (con <see cref="Accion"/>), <c>liberar/</c> y
/// <c>reloj/confirmar/</c>: después de cualquier acción la pantalla pinta el estado nuevo sin volver a preguntar.
/// </summary>
public sealed record EstadoLicencia(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("modo")] string? Modo,
    [property: JsonPropertyName("entorno")] string? Entorno,
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("restringe")] bool Restringe,
    [property: JsonPropertyName("banderas")] IReadOnlyList<string>? Banderas,
    [property: JsonPropertyName("licencia")] ResumenDeLicencia? Licencia,
    [property: JsonPropertyName("vigencia")] VigenciaDeLicencia? Vigencia,
    [property: JsonPropertyName("huella")] HuellaDelEquipo? Huella,
    [property: JsonPropertyName("limites")] LimitesDeLicencia? Limites,
    [property: JsonPropertyName("capacidades")] CapacidadesDeLicencia? Capacidades,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoDeLicencia>? Avisos,
    [property: JsonPropertyName("consumo")] ConsumoActual? Consumo,
    [property: JsonPropertyName("calculada_en")] long CalculadaEn,
    [property: JsonPropertyName("ahora")] long Ahora,
    [property: JsonPropertyName("accion")] string? Accion = null)
{
    /// <summary>Desarrollo y pruebas: nada se verifica ni se restringe, y no hay nada que activar.</summary>
    public bool Ilimitada => Modo == ModosDeLicencia.Ilimitada || Motivo == MotivosDeEstado.LicenciaIlimitada;

    /// <summary>Hay una licencia instalada (aunque esté vencida, sea de otro equipo o todavía no empiece).</summary>
    public bool TieneLicencia => Licencia is not null;

    public IReadOnlyList<string> BanderasActivas => Banderas ?? [];
    public IReadOnlyList<AvisoDeLicencia> AvisosActivos => Avisos ?? [];
    public IReadOnlyList<string> Habilitadas => Capacidades?.Habilitadas ?? [];
    public IReadOnlyList<string> NoDisponibles => Capacidades?.NoDisponibles ?? [];

    public bool Tiene(string bandera) => Banderas?.Contains(bandera) == true;

    /// <summary>
    /// El aviso de fecha adelantada (Q-L13), si lo hay: lo que el nodo no aceptó. Con él, <see cref="Ahora"/> es la hora que el aula lleva y la fecha del equipo es
    /// <see cref="AvisoDeLicencia.FechaEquipo"/>.
    /// </summary>
    public AvisoDeLicencia? FechaAdelantada => AvisosActivos.FirstOrDefault(a => a.Codigo == AvisosDeLicencia.RelojAdelantado);

    /// <summary>La fecha que tiene el equipo del aula: la adelantada que el nodo no aceptó, o, si no hay ninguna, la del nodo (<see cref="Ahora"/>). Es la que se confirma.</summary>
    public long FechaDelEquipo => FechaAdelantada?.FechaEquipo ?? Ahora;
}

// ------------------------------------------------------------------------------------------------ consumo/ y capacidades/

/// <summary>Una fila del consumo: cuánto se usa frente al límite. Sin tope, <see cref="Limite"/> y <see cref="Porcentaje"/> son null.</summary>
public sealed record UsoDelCupo(
    [property: JsonPropertyName("en_uso")] int? EnUso,
    [property: JsonPropertyName("limite")] int? Limite,
    [property: JsonPropertyName("porcentaje")] int? Porcentaje)
{
    public bool SinTope => Limite is null;
}

/// <summary>Los topes de conexiones simultáneas del aula (BR-063): en operación normal y en pico.</summary>
public sealed record ConcurrenciaDeLicencia(
    [property: JsonPropertyName("normal")] int? Normal,
    [property: JsonPropertyName("pico")] int? Pico);

/// <summary>Equipos y usuarios frente a lo contratado, contados en el momento (<c>GET consumo/</c>).</summary>
public sealed record ConsumoDeLicencia(
    [property: JsonPropertyName("equipos")] UsoDelCupo? Equipos,
    [property: JsonPropertyName("usuarios")] UsoDelCupo? Usuarios,
    [property: JsonPropertyName("concurrentes")] ConcurrenciaDeLicencia? Concurrentes,
    [property: JsonPropertyName("calculado_en")] long CalculadoEn);

/// <summary>Lo que cualquier sesión puede saber (<c>GET capacidades/</c>): qué módulos están encendidos, SIN ningún detalle de la licencia.</summary>
public sealed record CapacidadesDelNodo(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("restringe")] bool Restringe,
    [property: JsonPropertyName("habilitadas")] IReadOnlyList<string>? Habilitadas,
    [property: JsonPropertyName("no_disponibles")] IReadOnlyList<string>? NoDisponibles);

// ------------------------------------------------------------------------------------------------ los archivos que entrega el nodo

/// <summary>Un archivo que el nodo entrega para que OPS lo guarde: los bytes (base64), su nombre propuesto y su SHA-256, con el que se verifica lo que quedó escrito.</summary>
public interface IArchivoDelNodo
{
    string ArchivoB64 { get; }
    string? Texto { get; }
    string Nombre { get; }
    string Sha256 { get; }
}

/// <summary>La solicitud de licencia de este equipo (<c>POST solicitud/</c>): la huella hasheada, un nonce, la versión y el nivel, firmados con la llave del nodo.</summary>
public sealed record SolicitudDeLicencia(
    [property: JsonPropertyName("archivo_b64")] string ArchivoB64,
    [property: JsonPropertyName("texto")] string? Texto,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("nivel")] string? Nivel,
    [property: JsonPropertyName("k")] int? K,
    [property: JsonPropertyName("factores")] int? Factores,
    [property: JsonPropertyName("sha256")] string Sha256) : IArchivoDelNodo;

/// <summary>El <c>.avlic</c> vigente, para guardarlo bajo custodia de la institución (<c>GET copia/</c>, CAP-111).</summary>
public sealed record CopiaDeLicencia(
    [property: JsonPropertyName("archivo_b64")] string ArchivoB64,
    [property: JsonPropertyName("texto")] string? Texto,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonPropertyName("licencia")] ResumenDeLicencia? Licencia) : IArchivoDelNodo;

/// <summary>La prueba de liberación (<c>.avrel</c>) que el nodo firma al dejar de usar la licencia (<c>POST liberar/</c>, JRN-020).</summary>
public sealed record LiberacionDeLicencia(
    [property: JsonPropertyName("archivo_b64")] string ArchivoB64,
    [property: JsonPropertyName("texto")] string? Texto,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonPropertyName("licencia_id")] string? LicenciaId,
    [property: JsonPropertyName("serie")] int? Serie) : IArchivoDelNodo;

/// <summary><c>liberar/</c> devuelve en el mismo cuerpo el archivo de liberación y el estado nuevo del nodo: aquí van separados.</summary>
public sealed record ResultadoDeLiberacion(LiberacionDeLicencia Archivo, EstadoLicencia Estado);

/// <summary>Los bytes de un archivo del nodo (vacíos si el base64 viniera dañado: quien escribe lo verifica contra el SHA-256 y lo rechaza).</summary>
public static class ArchivosDelNodo
{
    public static byte[] Bytes(this IArchivoDelNodo archivo)
    {
        try { return Convert.FromBase64String(archivo.ArchivoB64 ?? string.Empty); }
        catch (FormatException) { return []; }
    }
}

// ------------------------------------------------------------------------------------------------ cómo se reconoce un archivo de licencia en una memoria

/// <summary>Las dos formas en que llega un <c>.avlic</c>: binario (empieza por la marca <c>AVLC</c>) o como texto (<c>AVL1.</c> + base64url, para copiar como texto).</summary>
public enum FormaDeLicencia { Desconocida, Binaria, Texto }

/// <summary>
/// La marca con la que OPS reconoce un archivo de licencia SIN interpretarlo: sólo sirve para no listar basura en las tarjetas del paso 3. OPS no verifica la firma ni lee los campos
/// (SEC-001): eso lo hace el nodo al instalarlo. Un archivo de texto puede traer la marca de orden de bytes de UTF-8 delante (lo pone el Bloc de notas): se acepta y se quita.
/// </summary>
public static class MarcaDeLicencia
{
    /// <summary>Lo que mide como mucho un archivo de licencia (el nodo rechaza más de 16 KiB: una licencia real mide menos de 1 KiB).</summary>
    public const int TamanoMaximo = 16 * 1024;

    /// <summary>Los bytes que hacen falta para reconocer la marca (con la marca UTF-8 y algún espacio o salto de línea delante del texto).</summary>
    public const int BytesParaReconocer = 32;

    /// <summary>Cuántos espacios o saltos de línea se toleran delante de la forma de texto (un copiar-pegar los trae).</summary>
    private const int EspaciosTolerados = 16;

    public static ReadOnlySpan<byte> Binaria => "AVLC"u8;
    public static ReadOnlySpan<byte> Texto => "AVL1."u8;
    private static ReadOnlySpan<byte> MarcaUtf8 => [0xEF, 0xBB, 0xBF];
    public const string PrefijoDeTexto = "AVL1.";

    /// <summary>Qué forma tiene un archivo por sus primeros bytes.</summary>
    public static FormaDeLicencia Reconocer(ReadOnlySpan<byte> inicio)
    {
        if (inicio.StartsWith(Binaria)) return FormaDeLicencia.Binaria;
        var resto = inicio.StartsWith(MarcaUtf8) ? inicio[MarcaUtf8.Length..] : inicio;
        var i = 0;
        while (i < resto.Length && i < EspaciosTolerados && resto[i] is (byte)' ' or (byte)'\t' or (byte)'\r' or (byte)'\n') i++;
        return resto[i..].StartsWith(Texto) ? FormaDeLicencia.Texto : FormaDeLicencia.Desconocida;
    }

    /// <summary>
    /// El texto <c>AVL1.…</c> de un archivo en forma de texto: sin la marca UTF-8 y sin espacios ni saltos de línea en los extremos (un copiar-pegar los trae; el nodo lee el texto en sí
    /// de forma estricta). Null si no es texto ASCII que empiece por la marca.
    /// </summary>
    public static string? TextoDe(ReadOnlySpan<byte> archivo)
    {
        if (Reconocer(archivo) != FormaDeLicencia.Texto) return null;
        var cuerpo = archivo.StartsWith(MarcaUtf8) ? archivo[MarcaUtf8.Length..] : archivo;
        foreach (var b in cuerpo)
            if (b > 0x7E || (b < 0x20 && b is not (byte)'\r' and not (byte)'\n' and not (byte)'\t')) return null;
        var texto = Encoding.ASCII.GetString(cuerpo).Trim();
        return texto.StartsWith(PrefijoDeTexto, StringComparison.Ordinal) ? texto : null;
    }
}
