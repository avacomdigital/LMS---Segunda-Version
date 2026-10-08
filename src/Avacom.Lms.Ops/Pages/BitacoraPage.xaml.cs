using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// «Bitácora» (PAN-240) y «Estado del equipo» (PAN-242) de MOD-019 · Audit, ruta <c>logs-bitacora</c>. Lo que ve cada rol:
/// · Administrador: Comportamiento (la bitácora, sólo lectura, con filtros y detalle), Integridad (semáforo de la cadena, tramos, verificar
///   ahora, tamaño frente al umbral), Exportaciones (alcance declarado, motivo de lista, autorización de salida PAN-241, descarga),
///   Accesos del técnico y Errores (los logs del nodo y de los equipos).
/// · Técnico: Estado del equipo (servicios, espacio, cola pendiente, diagnóstico), Errores y Medios (la cola de medios del nodo). Nunca la bitácora (BR-097).
/// Todo exige sesión de usuario: sin ella el nodo responde 401 y aquí se ofrece ir al acceso. Nada de esta pantalla interrumpe una clase:
/// no hay ventanas emergentes, sólo tarjetas. Mientras carga, esqueleto; ante un error de red, el motivo y «Reintentar» (y la línea al log
/// local, canal comunicacion, la deja el propio cliente).
/// </summary>
public partial class BitacoraPage : ContentPage
{
    private enum Pestana { Comportamiento, Integridad, Exportaciones, Tecnico, Errores, Equipo, Medios, Rendimiento }

    private static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");
    private static readonly Color TintaExito = Color.FromArgb("#017A48");
    private static readonly Color TintaAlerta = Color.FromArgb("#7A5B00");

    private readonly Dictionary<Pestana, Button> _pestanas = new();
    private Pestana _actual;
    private int _version;
    private CatalogoAuditoria? _catalogo;

    private static bool EsTecnico => Sesion.Usuario?.Rol == "TECHNICIAN";
    private static bool HaySesion => Sesion.Usuario is not null;

    public BitacoraPage()
    {
        InitializeComponent();
        var actualizar = Ds.Boton("Actualizar", Ds.Rango.Secondary, async (_, _) => await MostrarAsync(_actual), 56);
        var volver = Ds.Boton("Menú principal", Ds.Rango.Quiet, async (_, _) => await Shell.Current.GoToAsync(".."), 56);
        actualizar.FontSize = volver.FontSize = 16;
        AccionesHost.Add(Ds.Capsula(actualizar));
        AccionesHost.Add(volver);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        ArmarPestanas();
        await MostrarAsync(_actual);
    }

    // ------------------------------------------------------------------ pestañas

    private void ArmarPestanas()
    {
        PestanasHost.Clear();
        _pestanas.Clear();
        if (EsTecnico)
        {
            EyebrowLabel.Text = "ESTADO DEL EQUIPO";
            TituloLabel.Text = "Diagnóstico del nodo y de los equipos";
            SubtituloLabel.Text = "Escritura, red y dispositivos, sin datos de alumnos. La bitácora de auditoría no se ve desde el perfil técnico.";
            Agregar(Pestana.Equipo, "Estado del equipo");
            Agregar(Pestana.Errores, "Errores");
            Agregar(Pestana.Medios, "Medios");
            Agregar(Pestana.Rendimiento, "Rendimiento");
            if (_actual is not (Pestana.Equipo or Pestana.Errores or Pestana.Medios or Pestana.Rendimiento)) _actual = Pestana.Equipo;
        }
        else
        {
            EyebrowLabel.Text = "BITÁCORA Y LOGS";
            TituloLabel.Text = "Bitácora de auditoría";
            SubtituloLabel.Text = "Quién hizo qué, cuándo, sobre qué y con qué resultado. La bitácora sólo se agrega; nadie puede editarla.";
            Agregar(Pestana.Comportamiento, "Comportamiento");
            Agregar(Pestana.Integridad, "Integridad");
            Agregar(Pestana.Exportaciones, "Exportaciones");
            Agregar(Pestana.Tecnico, "Accesos del técnico");
            Agregar(Pestana.Errores, "Errores");
            Agregar(Pestana.Medios, "Medios");
            Agregar(Pestana.Rendimiento, "Rendimiento");
            if (_actual == Pestana.Equipo) _actual = Pestana.Comportamiento;
        }
        PintarPestanas();
    }

    /// <summary>Pestañas planas (sin sombra ni degradado: un botón con sombra dentro de una pila horizontal centrada entra en ciclo de layout en WinUI).</summary>
    private void Agregar(Pestana pestana, string texto)
    {
        var boton = new Button
        {
            Text = texto, HeightRequest = 52, MinimumHeightRequest = 52, MinimumWidthRequest = 170, CornerRadius = Ds.RadioBoton, FontSize = 15,
            FontFamily = Ds.FuenteMedia, Padding = new Thickness(22, 0), BorderWidth = 1, BorderColor = Ds.Filo,
        };
        boton.Clicked += async (_, _) => await MostrarAsync(pestana);
        _pestanas[pestana] = boton;
        PestanasHost.Add(boton);
    }

    /// <summary>La pestaña activa en tinta con texto blanco; las demás, blancas con tinta: legibles sobre el lienzo claro.</summary>
    private void PintarPestanas()
    {
        foreach (var (pestana, boton) in _pestanas)
        {
            var activa = pestana == _actual;
            boton.BackgroundColor = activa ? Ds.Tinta : Colors.White;
            boton.TextColor = activa ? Colors.White : Ds.Tinta;
        }
    }

    private async Task MostrarAsync(Pestana pestana)
    {
        _actual = pestana;
        PintarPestanas();
        var version = ++_version;
        ContenidoHost.Clear();
        ContenidoHost.Add(Esqueleto());
        try
        {
            View contenido = pestana switch
            {
                Pestana.Comportamiento => await ComportamientoAsync(),
                Pestana.Integridad => await IntegridadAsync(),
                Pestana.Exportaciones => await ExportacionesAsync(),
                Pestana.Tecnico => await AccesosDelTecnicoAsync(),
                Pestana.Errores => await ErroresAsync(),
                Pestana.Medios => await MediosAsync(),
                Pestana.Rendimiento => await RendimientoAsync(),
                _ => await EstadoDelEquipoAsync(),
            };
            if (version != _version) return;
            ContenidoHost.Clear();
            ContenidoHost.Add(contenido);
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("ops", $"BitacoraPage.{pestana}", ex);
            if (version != _version) return;
            ContenidoHost.Clear();
            ContenidoHost.Add(TarjetaDeError("No se pudo mostrar esta pestaña", ex.Message, () => MostrarAsync(pestana)));
        }
    }

    // ------------------------------------------------------------------ piezas comunes

    private static View Esqueleto()
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        for (var i = 0; i < 4; i++)
            pila.Add(new Border { BackgroundColor = Color.FromArgb("#E4E4E7"), StrokeThickness = 0, HeightRequest = i == 0 ? 88 : 64, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Opacity = 0.9 - i * 0.15 });
        return pila;
    }

    /// <summary>Un error del nodo: sin sesión se ofrece ir al acceso; sin permiso, el mensaje claro (el nodo ya asentó la denegación); si no, el motivo y «Reintentar».</summary>
    private View TarjetaDeError(string titulo, string? detalle, Func<Task> reintentar, ErrorAula? error = null)
    {
        if (error is { Estado: 401 })
            return TarjetaConAccion("Esta pantalla exige identificarse", "La bitácora y los logs sólo se consultan con una sesión de usuario del nodo. Cierra esta pantalla y entra con tu documento y tu clave.",
                                    Ds.AlertaSuave, TintaAlerta, "Ir al acceso", async () => await Shell.Current.GoToAsync("//login"));
        if (error is { Estado: 403 })
            return Ds.Alerta_("Tu rol no puede ver esto", $"{error.Detalle} El intento quedó registrado en la bitácora.", Ds.PeligroSuave, TintaPeligro);
        return TarjetaConAccion(titulo, detalle, Ds.PeligroSuave, TintaPeligro, "Reintentar", reintentar);
    }

    private static View TarjetaConAccion(string titulo, string? detalle, Color fondo, Color tinta, string accion, Func<Task> alPulsar)
    {
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        fila.Add(Ds.Alerta_(titulo, detalle, fondo, tinta), 0, 0);
        var boton = Ds.Boton(accion, Ds.Rango.Secondary, async (_, _) => await alPulsar(), 56, 180);
        boton.VerticalOptions = LayoutOptions.Center;
        fila.Add(boton, 1, 0);
        return fila;
    }

    /// <summary>
    /// Una fila de lista SIN sombra. WinUI cuenta las pasadas de layout y, con decenas de tarjetas con sombra dentro de un ScrollView, lanza
    /// LayoutCycleException (pasó con 200 líneas de log): las listas largas de esta pantalla usan un borde de filo, no la tarjeta con sombra.
    /// </summary>
    private static Border FilaPlana(View contenido, Color? fondo = null) => new()
    {
        BackgroundColor = fondo ?? Colors.White, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1,
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Padding = new Thickness(18, 12), Content = contenido,
    };

    private static View Vacio(string titulo, string detalle) =>
        Ds.Tarjeta(new VerticalStackLayout { Spacing = 6, Children = { Ds.Cuerpo(titulo, 18), Ds.Secundario(detalle, 15) } }, Ds.RadioTarjeta, new Thickness(24), Colors.White);

    private static Border Chip(string texto, Color fondo, Color tinta)
    {
        var chip = Ds.Pildora(texto, fondo, tinta, 13);
        chip.VerticalOptions = LayoutOptions.Center;
        return chip;
    }

    private static Border ChipResultado(string resultado) => resultado switch
    {
        "ok" => Chip("Correcto", Ds.ExitoSuave, TintaExito),
        "denegado" => Chip("Denegado", Ds.AlertaSuave, TintaAlerta),
        _ => Chip("Fallido", Ds.PeligroSuave, TintaPeligro),
    };

    private static Border ChipRuta(string? ruta) => ruta switch
    {
        "happy" => Chip("happy", Ds.ExitoSuave, TintaExito),
        "sad" => Chip("sad", Ds.AlertaSuave, TintaAlerta),
        "bad" => Chip("bad", Ds.PeligroSuave, TintaPeligro),
        _ => Chip("—", Color.FromArgb("#EEEEF0"), Ds.TintaSuave),
    };

    private static string Hora(long ms) => DateTimeOffset.FromUnixTimeMilliseconds(ms).ToLocalTime().ToString("dd/MM HH:mm:ss");
    private static string Fecha(long? ms) => ms is null ? "—" : DateTimeOffset.FromUnixTimeMilliseconds(ms.Value).ToLocalTime().ToString("dd/MM/yyyy HH:mm");
    private static string Mb(long bytes) => $"{bytes / 1024d / 1024d:0.0} MB";
    private static string Abreviar(string? texto, int largo = 10) => string.IsNullOrEmpty(texto) ? "—" : texto.Length <= largo ? texto : texto[..largo] + "…";

    private static string Bonito(System.Text.Json.JsonElement? valor)
    {
        if (valor is null || valor.Value.ValueKind == System.Text.Json.JsonValueKind.Null) return "—";
        try { return System.Text.Json.JsonSerializer.Serialize(valor.Value, new System.Text.Json.JsonSerializerOptions { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }); }
        catch { return valor.Value.ToString(); }
    }

    /// <summary>Texto técnico (JSON, huellas, trazas). Envuelve por carácter: una huella o un JSON sin espacios no deben ensanchar la fila.</summary>
    private static Label Mono(string texto, double tamano = 13) => new()
    {
        Text = texto, FontFamily = "Consolas", FontSize = tamano, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.CharacterWrap,
    };

    private static DatePicker FechaPicker(DateTime? inicial)
    {
        var picker = new DatePicker { Format = "dd/MM/yyyy", FontSize = 15, TextColor = Ds.Tinta, MinimumDate = new DateTime(2024, 1, 1), MaximumDate = DateTime.Today.AddDays(1), HeightRequest = 48, WidthRequest = 150 };
        picker.Date = inicial ?? DateTime.Today;
        return picker;
    }

    private static long InicioDelDia(DateTime fecha) => new DateTimeOffset(fecha.Date).ToUnixTimeMilliseconds();
    private static long FinDelDia(DateTime fecha) => new DateTimeOffset(fecha.Date.AddDays(1)).ToUnixTimeMilliseconds() - 1;

    private static string CarpetaDescargas()
    {
        var perfil = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var descargas = System.IO.Path.Combine(perfil, "Downloads");
        return System.IO.Path.Combine(Directory.Exists(descargas) ? descargas : FileSystem.AppDataDirectory, "avacom-auditoria");
    }
}
