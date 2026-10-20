using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Reportes (MOD-013), el inicio: tres tarjetas grandes —Una clase, Un alumno, Un grupo— y, si el rol puede, «Uso de equipos»; debajo, los reportes recientes de quien entró, para volver a
/// abrirlos (y exportarlos) sin repetir los filtros. Es una pantalla de tarjetas, así que sigue la composición de tercios: Grid de columnas <c>*,*,*</c> y de filas <c>*,4*,*</c>, con las
/// tarjetas en la fila central (de 1/6 a 5/6 del alto) y la del medio en el tercio central. Lo que se ofrece sale de lo que el nodo dice que esta persona puede (<c>filtros.puede</c>); si
/// el rol no accede a datos académicos, la pantalla lo dice sin llamar al nodo (TST-069).
/// </summary>
public sealed class ReportesPage : ContentPage
{
    private const double Aire = 10;       // lo que separa cada tarjeta de las líneas de tercios: así quedan DENTRO de su tercio y separadas entre sí

    private readonly Grid _raiz;
    private readonly VerticalStackLayout _tarjetasHost = new();
    private readonly VerticalStackLayout _avisosHost = new() { Spacing = 8 };
    private readonly VerticalStackLayout _recientesHost = new() { Spacing = 8 };
    private readonly Grid _tarjetas;
    private readonly ContentView _usoHost = new();
    private readonly HorizontalStackLayout _acciones = new() { Spacing = 12, VerticalOptions = LayoutOptions.Center };
    private bool _visible, _cargando, _estadoAgregado;

    public ReportesPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        BackgroundColor = Color.FromArgb("#F1F1F1");

        var textos = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = "REPORTES", FontFamily = "InterRegular", FontSize = 12, TextColor = Color.FromArgb("#52525B"), CharacterSpacing = 2.5 });
        textos.Add(new Label { Text = "Reportes", FontFamily = "InterMedium", FontSize = 30, TextColor = Color.FromArgb("#18181B"), AutomationId = "reportes-titulo" });
        textos.Add(new Label { Text = "Elige qué quieres ver. Todos los reportes dicen hasta qué momento llegan sus datos.", FontFamily = "InterLight", FontSize = 15, TextColor = Color.FromArgb("#52525B"), LineBreakMode = LineBreakMode.WordWrap });

        // La demo «Monitor de actividad» (con la lista de visitantes y «Vincular a un alumno», RF-09c) abría desde este hexágono antes de MOD-013: sigue a un toque de aquí.
        _acciones.Add(ExamenUi.Accion("Visitantes y actividad", Ds.Rango.Quiet, () => Shell.Current.GoToAsync("activity-monitor"), 250, "reportes-visitantes").Vista);
        _acciones.Add(ExamenUi.Accion("Actualizar", Ds.Rango.Secondary, ReportesUi.Seguro(nameof(ReportesPage), "Actualizar", () => CargarAsync(forzar: true)), 170, "reportes-actualizar").Vista);
        _acciones.Add(ExamenUi.Accion("‹  Menú principal", Ds.Rango.Quiet, () => Shell.Current.GoToAsync(".."), 220, "reportes-volver").Vista);

        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 24, Padding = new Thickness(44, 24, 48, 0), VerticalOptions = LayoutOptions.Start };
        cabecera.Add(textos, 0, 0);
        cabecera.Add(_acciones, 1, 0);

        // Las tres tarjetas, cada una en su tercio; el aviso (sin conexión, sin acceso) ocupa el tercio central.
        _tarjetas = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)] };

        var pie = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], Padding = new Thickness(0, 10, 0, 12), VerticalOptions = LayoutOptions.Start };
        var recientes = new VerticalStackLayout { Spacing = 6, Margin = new Thickness(44, 0, 20, 0) };
        recientes.Add(_avisosHost);
        recientes.Add(_recientesHost);
        pie.Add(recientes, 0, 0);
        Grid.SetColumnSpan(recientes, 2);
        pie.Add(_usoHost, 2, 0);

        _raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(new GridLength(4, GridUnitType.Star)), new RowDefinition(GridLength.Star)] };
        _raiz.Add(cabecera, 0, 0);
        _raiz.Add(_tarjetas, 0, 1);
        _raiz.Add(pie, 0, 2);
        Content = _raiz;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!ReportesUi.PuedeLeer)
            {
                PonerSoloCentral(ReportesUi.SinAcceso(ReportesUi.Rol));
                return;
            }
            ReportesUi.LimpiarTemporalesViejos();
            await CargarAsync(forzar: true);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ReportesPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
    }

    // =============================================================================================================== leer

    private async Task CargarAsync(bool forzar)
    {
        if (_cargando || !_visible || !ReportesUi.PuedeLeer) return;
        _cargando = true;
        try
        {
            var api = ReportesUi.Api;
            var filtros = await ReportesUi.FiltrosAsync(forzar);
            if (!_visible) return;
            if (filtros is null)
            {
                // MOD-018 · H-01: Reportes en pausa por la licencia (402 no_disponible_por_licencia). «Visitantes y actividad» (con «Vincular a un alumno», RF-09c) es núcleo y sólo se
                // alcanza desde aquí: el botón de la cabecera se queda y el aviso lo repite. El texto es el común de la licencia; quien la administra tiene a mano «Ver la licencia».
                if (api.UltimoError is { EsModuloNoDisponible: true } porLicencia)
                {
                    // 64 px, como todo lo de la licencia (NFR-044: la pantalla táctil de 86").
                    const double alto = Avacom.Lms.Ops.Licencia.Ui.LicenciaUi.AltoTactil;
                    var botones = new List<View>
                    {
                        ExamenUi.Accion("Visitantes y actividad", Ds.Rango.Secondary, ReportesUi.Seguro(nameof(ReportesPage), "VisitantesConLicencia", () => Shell.Current.GoToAsync("activity-monitor")),
                            250, "reportes-licencia-visitantes", alto, margen: false).Vista,
                    };
                    if (ReglasDeLicencia.VeLaLicencia(Sesion.Usuario))
                        botones.Add(ExamenUi.Accion("Ver la licencia", Ds.Rango.Quiet, ReportesUi.Seguro(nameof(ReportesPage), "VerLicencia", () => Shell.Current.GoToAsync("licencia")), 200,
                            "reportes-licencia-ver", alto, margen: false).Vista);
                    PonerSoloCentral(ReportesUi.Estado("No disponible con la licencia de este equipo", LicenciaTexto.ParaError(porLicencia) ?? ReportesUi.Error(api), [.. botones]));
                    _recientesHost.Clear();
                    _usoHost.Content = null;
                    return;
                }
                var sinConexion = ReportesUi.SinConexion(api);
                PonerSoloCentral(ReportesUi.Estado(sinConexion ? "Sin conexión con el aula" : "No se pudieron leer los reportes", ReportesUi.Error(api),
                    ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, ReportesUi.Seguro(nameof(ReportesPage), "Reintentar", () => CargarAsync(forzar: true)), 170, "reportes-reintentar", margen: false).Vista));
                _recientesHost.Clear();
                _usoHost.Content = null;
                return;
            }
            var recientes = filtros.Puede.PuedeVerAlgo ? await api.RecientesAsync(ReportesUi.Actor) : null;
            var ultima = filtros.Puede.Clase ? await api.ClasesAsync(ReportesUi.Actor, new FiltroDeClases(Limite: 1)) : null;
            if (!_visible) return;
            PintarTarjetas(filtros, ultima);
            PintarRecientes(recientes, filtros);
            PintarAcciones(filtros);
        }
        finally { _cargando = false; }
    }

    // =============================================================================================================== pintar

    /// <summary>Un solo mensaje en el tercio central (sin conexión, sin acceso): las tarjetas no se pintan.</summary>
    private void PonerSoloCentral(View vista)
    {
        _tarjetas.Clear();
        _tarjetas.Add(vista, 1, 0);
        vista.VerticalOptions = LayoutOptions.Start;
    }

    private void PintarTarjetas(FiltrosDeReportes filtros, ListaDeClases? ultima)
    {
        _tarjetas.Clear();
        var p = filtros.Puede;
        if (!p.PuedeVerAlgo)
        {
            PonerSoloCentral(ReportesUi.Estado("No tienes reportes para ver", "Tu rol no ve reportes de clases, estudiantes ni grupos. Si lo necesitas, pídelo a la administración."));
            return;
        }
        var grupos = filtros.Grupos;
        string? datoClase = ultima?.Clases.FirstOrDefault() is { } c ? $"Última: {(c.Grupo?.Rotulo ?? "sin grupo")} · {FormatoDeReportes.FechaCorta(c.FinalizadaEn)}" : p.Clase && ultima is not null ? "Todavía no hay clases cerradas" : null;
        var alumnos = grupos.Sum(g => g.Alumnos ?? 0);
        var atencion = grupos.Sum(g => g.EnAtencion ?? 0);

        Agregar(0, "reportes_clase.png", "Una clase", "Lo que hizo cada estudiante en una clase ya cerrada: participación y aciertos.", datoClase, p.Clase, RutasDeReportes.DeElegir(RutasDeReportes.ElegirClase), "reportes-tarjeta-clase",
            "La participación y los aciertos de cada estudiante", "Cómo quedó la tableta de cada uno al cerrar", "El promedio de la clase, abajo");
        Agregar(1, "reportes_alumno.png", "Un estudiante", "Cómo va un estudiante: asistencia, participación, evaluaciones y estudio.", alumnos > 0 ? $"{FormatoDeReportes.Plural(alumnos, "estudiante", "estudiantes")} en {FormatoDeReportes.Plural(grupos.Count, "grupo", "grupos")}" : grupos.Count == 0 ? EstadosVaciosDeReportes.SinGrupos : null,
            p.Alumno, RutasDeReportes.DeElegir(RutasDeReportes.ElegirAlumno), "reportes-tarjeta-alumno",
            "Su asistencia y su participación", "Sus evaluaciones, con la nota de su nivel", "Sus tareas de estudio y sus clases");
        Agregar(2, "reportes_grupo.png", "Un grupo", "Quién necesita atención y cómo va todo el grupo.", atencion > 0 ? (atencion == 1 ? "1 estudiante necesita atención" : $"{atencion} estudiantes necesitan atención") : grupos.Count > 0 ? "Nadie necesita atención ahora" : EstadosVaciosDeReportes.SinGrupos,
            p.Grupo, RutasDeReportes.DeElegir(RutasDeReportes.ElegirGrupo), "reportes-tarjeta-grupo",
            "Quién necesita atención, primero y con su motivo", "Todos los estudiantes del grupo", "Sus clases cerradas y sus evaluaciones");
    }

    private void Agregar(int columna, string icono, string titulo, string descripcion, string? dato, bool activa, string ruta, string id, params string[] veras)
    {
        // El icono arriba, el texto debajo y «Elegir ›» siempre al pie: así las tres tarjetas alinean aunque una descripción ocupe una línea más que otra.
        var texto = new VerticalStackLayout { Spacing = 12, Margin = new Thickness(0, 22, 0, 0), VerticalOptions = LayoutOptions.Start };
        texto.Add(new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 30, TextColor = Ds.Tinta });
        texto.Add(Ds.Secundario(descripcion, 17));
        if (!string.IsNullOrWhiteSpace(dato)) texto.Add(new Label { Text = dato, FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap, Margin = new Thickness(0, 6, 0, 0) });
        if (veras.Length > 0)
        {
            var lista = new VerticalStackLayout { Spacing = 6, Margin = new Thickness(0, 18, 0, 0) };
            lista.Add(EstudioUi.Eyebrow("QUÉ VERÁS"));
            foreach (var linea in veras) lista.Add(Ds.Secundario($"•  {linea}", 16));
            texto.Add(lista);
        }

        var cuerpo = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star), new RowDefinition(GridLength.Auto)] };
        cuerpo.Add(new Image { Source = icono, WidthRequest = 64, HeightRequest = 64, HorizontalOptions = LayoutOptions.Start }, 0, 0);
        cuerpo.Add(texto, 0, 1);
        cuerpo.Add(new Label { Text = activa ? "Elegir  ›" : "Tu rol no puede ver este reporte", FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = activa ? Ds.Rojo : Ds.TintaSuave }, 0, 2);

        var tarjeta = ReportesUi.Tocable(cuerpo, activa ? ReportesUi.Seguro(nameof(ReportesPage), id, () => Shell.Current.GoToAsync(ruta)) : () => Task.CompletedTask, $"{titulo}. {descripcion}", id,
            Colors.White, new Thickness(32, 30));
        tarjeta.StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioGrande };
        tarjeta.Shadow = Ds.SombraTarjeta();
        tarjeta.Margin = new Thickness(Aire, 0);
        tarjeta.Opacity = activa ? 1 : 0.6;
        _tarjetas.Add(tarjeta, columna, 0);
    }

    private void PintarRecientes(RecientesDeReportes? recientes, FiltrosDeReportes filtros)
    {
        _recientesHost.Clear();
        _usoHost.Content = null;
        // En el tercio derecho del pie: el boletín académico (un archivo por estudiante, con la plantilla del país) y el uso de equipos, según lo que el nodo deja a esta persona.
        var secundarias = new VerticalStackLayout { Spacing = 8 };
        if (filtros.Puede.Alumno)
            secundarias.Add(TarjetaPequena("reportes_alumno.png", "Boletín académico", "Un boletín por estudiante: puntos, calificación, competencias, progreso y recomendaciones.",
                RutasDeReportes.DeElegir(RutasDeReportes.ElegirBoletin), "reportes-tarjeta-boletin", "Boletin"));
        if (filtros.Puede.Uso)
            secundarias.Add(TarjetaPequena("reportes_uso.png", "Uso de equipos", "Qué tabletas se usaron y cuánto.", RutasDeReportes.DeUso(), "reportes-tarjeta-uso", "Uso"));
        if (secundarias.Children.Count > 0) _usoHost.Content = secundarias;

        var lista = recientes?.Recientes.Where(r => RutasDeReportes.DeReciente(r) is not null).Take(6).ToList() ?? [];
        _recientesHost.Add(EstudioUi.Eyebrow("RECIENTES"));
        if (lista.Count == 0)
        {
            _recientesHost.Add(Ds.Secundario(EstadosVaciosDeReportes.SinRecientes, 15));
            return;
        }
        var fila = EstudioUi.Envolver();
        for (var i = 0; i < lista.Count; i++)
        {
            var r = lista[i];
            var ruta = RutasDeReportes.DeReciente(r)!;
            fila.Add(EstudioUi.Chip(Recortar(r.Titulo, 34), false, ReportesUi.Seguro(nameof(ReportesPage), "Reciente", () => Shell.Current.GoToAsync(ruta)), $"reportes-reciente-{i}"));
        }
        _recientesHost.Add(fila);
    }

    private static string Recortar(string texto, int maximo) => texto.Length <= maximo ? texto : texto[..(maximo - 1)].TrimEnd() + "…";

    private static Border TarjetaPequena(string icono, string titulo, string descripcion, string ruta, string id, string donde)
    {
        var tarjeta = ReportesUi.Tocable(new HorizontalStackLayout
        {
            Spacing = 14, Children =
            {
                new Image { Source = icono, WidthRequest = 40, HeightRequest = 40, VerticalOptions = LayoutOptions.Center },
                new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center, Children =
                {
                    new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta },
                    Ds.Secundario(descripcion, 14),
                } },
            },
        }, ReportesUi.Seguro(nameof(ReportesPage), donde, () => Shell.Current.GoToAsync(ruta)), $"{titulo}. {descripcion}", id, Colors.White, new Thickness(18, 12));
        tarjeta.StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioTarjeta };
        tarjeta.Shadow = Ds.SombraTarjeta();
        tarjeta.Margin = new Thickness(Aire, 0);
        return tarjeta;
    }

    private void PintarAcciones(FiltrosDeReportes filtros)
    {
        // «Estado y ajustes» sólo para quien puede reconstruir o configurar los reportes (lo dice el nodo).
        if (!(filtros.Puede.Reconstruir || filtros.Puede.Configurar) || _estadoAgregado) return;
        _estadoAgregado = true;
        var (_, vista) = ExamenUi.Accion("Estado y ajustes", Ds.Rango.Secondary, ReportesUi.Seguro(nameof(ReportesPage), "Estado", () => Shell.Current.GoToAsync(RutasDeReportes.Estado)), 210, "reportes-estado");
        _acciones.Insert(1, vista);
    }
}
