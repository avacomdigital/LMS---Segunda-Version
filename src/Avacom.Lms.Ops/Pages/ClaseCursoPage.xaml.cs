using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Core.Actualizacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;
using Microsoft.Maui.Layouts;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// P2 · Curso y lecciones. Una tarjeta por lección con sus objetos como chips de categoría;
/// el examen es un objeto más de la lección (se aplica durante la clase, MOD-010). Se toca una lección para seleccionarla y
/// un único botón Primary inicia la clase (BR-044, vía «leccion»); «Clase libre» es la vía
/// alternativa. Nada exige teclado.
/// </summary>
[QueryProperty(nameof(CursoRef), "curso")]
[QueryProperty(nameof(Titulo), "titulo")]
public partial class ClaseCursoPage : ContentPage
{
    private VistaCurso? _vista;
    private LeccionAula? _seleccionada;
    private readonly Dictionary<string, Border> _tarjetas = new();
    private bool _iniciando;

    public string CursoRef { get; set; } = string.Empty;
    public string Titulo { get; set; } = string.Empty;

    public ClaseCursoPage() => InitializeComponent();

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        TituloLabel.Text = string.IsNullOrWhiteSpace(Titulo) ? CursoRef : Titulo;
        Ds.Hundir(DarClaseBtn);
        await CargarAsync();
    }

    private async Task CargarAsync()
    {
        var aula = Sesion.Aula;
        AvisoHost.Clear();
        CabeceraHost.Clear();
        LeccionesHost.Clear();
        _tarjetas.Clear();
        _marcas.Clear();
        _tiras.Clear();
        _detalles.Clear();
        var vista = await aula.CursoAsync(CursoRef, docente: true);
        if (vista is null)
        {
            var error = aula.UltimoError;
            AvisoHost.Add(Ds.Alerta_("No se pudo leer el curso", string.Join(" ", new[] { error?.Detalle, error?.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x))), Ds.PeligroSuave, Color.FromArgb("#A51C20")));
            AvisoHost.Add(Ds.Boton("Reintentar", Ds.Rango.Secondary, async (_, _) => await CargarAsync(), 64, 220));
            return;
        }
        _vista = vista;
        TituloLabel.Text = vista.Titulo;
        SubtituloLabel.Text = vista.Clasificacion?.Resumen ?? string.Empty;
        CabeceraHost.Add(Cabecera(vista));
        NotasBtn.IsVisible = vista.NotasDocente is not null;
        NotasHost.Clear();
        if (vista.NotasDocente is not null)
        {
            var pila = new VerticalStackLayout { Spacing = 6 };
            foreach (var linea in vista.NotasDocente.Lineas()) pila.Add(Ds.Cuerpo(linea, 16));
            NotasHost.Add(Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(20, 16), Ds.AlertaSuave));
        }
        var numero = 0;
        foreach (var leccion in vista.Lecciones)
        {
            numero++;
            var tarjeta = TarjetaLeccion(leccion, numero);
            _tarjetas[leccion.LeccionRef] = tarjeta;
            LeccionesHost.Add(tarjeta);
        }
    }

    private View Cabecera(VistaCurso v)
    {
        var grid = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 18 };
        var textos = new VerticalStackLayout { Spacing = 6 };
        var chips = new HorizontalStackLayout { Spacing = 8 };
        if (v.Clasificacion?.Asignatura?.Nombre is { } asig) chips.Add(Ds.Pildora(asig, Glass.AcentoMateria(asig, 0)));   // color de materia del DS
        if (v.Clasificacion?.Grado?.Nombre is { } grado) chips.Add(Ds.Pildora(grado, Ds.Lienzo, Ds.Tinta));
        if (v.Clasificacion?.Nivel?.Nombre is { } nivel) chips.Add(Ds.Pildora(nivel, Ds.Lienzo, Ds.Tinta));
        if (v.DuracionEstimadaMin is > 0) chips.Add(Ds.Pildora($"{v.DuracionEstimadaMin} min en total", Ds.Lienzo, Ds.Tinta));
        textos.Add(chips);
        textos.Add(Ds.Titulo(v.Titulo, 30));
        if (!string.IsNullOrWhiteSpace(v.Subtitulo)) textos.Add(Ds.Cuerpo(v.Subtitulo!, 18, Ds.TintaSuave));
        // La descripción del curso puede ser larga: dos renglones bastan para elegir la lección; lo demás estorba la lista.
        if (!string.IsNullOrWhiteSpace(v.Descripcion))
        {
            var descripcion = Ds.Secundario(v.Descripcion!, 15);
            descripcion.MaxLines = 2;
            descripcion.LineBreakMode = LineBreakMode.TailTruncation;
            textos.Add(descripcion);
        }
        grid.Add(textos, 0, 0);
        if (!string.IsNullOrWhiteSpace(v.PortadaUrl))
        {
            var portada = new Border
            {
                WidthRequest = 240, HeightRequest = 135, StrokeThickness = 0, BackgroundColor = Ds.Lienzo,
                StrokeShape = new RoundRectangle { CornerRadius = 18 }, VerticalOptions = LayoutOptions.Center,
                Content = new Image { Aspect = Aspect.AspectFill, Source = new UriImageSource { Uri = Sesion.Aula.Absoluta(v.PortadaUrl!), CachingEnabled = false } },
            };
            grid.Add(portada, 1, 0);
        }
        return Ds.Tarjeta(grid, Ds.RadioGrande, new Thickness(24, 20));
    }

    private Border TarjetaLeccion(LeccionAula leccion, int numero)
    {
        // Cabecera: número, título con «N momentos · X min» debajo y, a la derecha, la marca de selección (círculo vacío o verde con ✓).
        var cabecera = new Grid
        {
            ColumnDefinitions = [new ColumnDefinition(48), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)],
            ColumnSpacing = 16,
        };
        var numeroChip = new Border
        {
            BackgroundColor = Ds.Contenido, StrokeThickness = 0, WidthRequest = 48, HeightRequest = 48,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, VerticalOptions = LayoutOptions.Center,
            Content = new Label { Text = numero.ToString(), FontSize = 22, FontFamily = Ds.FuenteSemi, TextColor = Colors.White, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        };
        cabecera.Add(numeroChip, 0, 0);
        var titulos = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        titulos.Add(Ds.Titulo(leccion.Titulo, 22));
        var objetos = leccion.Objetos ?? [];
        var datos = string.Join(" · ", new[]
        {
            objetos.Count > 0 ? (objetos.Count == 1 ? "1 momento" : $"{objetos.Count} momentos") : null,
            leccion.DuracionEstimadaMin is > 0 ? $"{leccion.DuracionEstimadaMin} min" : null,
            leccion.SoloExamen ? "Sólo examen" : null,
        }.Where(x => x is not null));
        if (datos.Length > 0) titulos.Add(Ds.Cuerpo(datos, 15, Ds.TintaMedia));
        cabecera.Add(titulos, 1, 0);
        var marca = new Border
        {
            WidthRequest = 36, HeightRequest = 36, BackgroundColor = Colors.White, Stroke = new SolidColorBrush(Ds.Linea), StrokeThickness = 2,
            StrokeShape = new RoundRectangle { CornerRadius = 18 }, VerticalOptions = LayoutOptions.Center,
            Content = new Label { Text = "", FontSize = 20, FontFamily = Ds.FuenteSemi, TextColor = Colors.White, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        };
        cabecera.Add(marca, 2, 0);
        _marcas[leccion.LeccionRef] = marca;

        var pila = new VerticalStackLayout { Spacing = objetos.Count > 0 ? 14 : 0 };
        pila.Add(cabecera);
        if (objetos.Count > 0)
        {
            // Cerrada: los momentos como un camino de iconos en orden, sin texto (el nombre queda para el lector de pantalla).
            var tira = new HorizontalStackLayout { Spacing = 0, Margin = new Thickness(64, 0, 0, 0) };
            for (var i = 0; i < objetos.Count; i++)
            {
                if (i > 0) tira.Add(new BoxView { WidthRequest = 16, HeightRequest = 2, Color = Ds.Linea, VerticalOptions = LayoutOptions.Center });
                var icono = Ds.IconoCategoria(objetos[i].Componente, 34);
                if (NoSeEjecuta(objetos[i])) icono.Opacity = 0.5;
                SemanticProperties.SetDescription(icono, $"{i + 1}. {objetos[i].Titulo}");
                tira.Add(icono);
            }
            pila.Add(tira);
            _tiras[leccion.LeccionRef] = tira;

            // Elegida: los momentos en una sola columna numerada, para leerlos en orden.
            var detalle = new VerticalStackLayout { Spacing = 8, Margin = new Thickness(64, 0, 0, 0), IsVisible = false };
            for (var i = 0; i < objetos.Count; i++)
            {
                var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(22), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
                fila.Add(new Label { Text = (i + 1).ToString(), FontSize = 15, FontFamily = Ds.FuenteMedia, TextColor = Ds.TintaSuave, VerticalOptions = LayoutOptions.Center, HorizontalTextAlignment = TextAlignment.End }, 0, 0);
                fila.Add(Ds.IconoCategoria(objetos[i].Componente, 30), 1, 0);
                fila.Add(new Label { Text = objetos[i].Titulo, FontSize = 16, FontFamily = Ds.FuenteRegular, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, VerticalOptions = LayoutOptions.Center }, 2, 0);
                if (NoSeEjecuta(objetos[i])) fila.Opacity = 0.6;
                detalle.Add(fila);
            }
            pila.Add(detalle);
            _detalles[leccion.LeccionRef] = detalle;
        }
        var tarjeta = Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(20, 18));
        tarjeta.Stroke = new SolidColorBrush(Ds.Filo);
        tarjeta.StrokeThickness = 2;
        // Una lección que sólo tiene examen también se puede dar: el examen se aplica desde la clase.
        Ds.Tocable(tarjeta, () => { Seleccionar(leccion); return Task.CompletedTask; });
        return tarjeta;
    }

    // El examen ya se puede aplicar (MOD-010). Sólo lo que de verdad no se ejecuta sigue atenuado.
    private static bool NoSeEjecuta(ObjetoAula objeto) => objeto.FueraDeAlcance && objeto.Componente != "examen" && objeto.Tipo != "exam";

    private readonly Dictionary<string, View> _tiras = new();
    private readonly Dictionary<string, View> _detalles = new();

    private readonly Dictionary<string, Border> _marcas = new();

    private void Seleccionar(LeccionAula leccion)
    {
        _seleccionada = leccion;
        foreach (var (ref_, tarjeta) in _tarjetas)
        {
            var activa = ref_ == leccion.LeccionRef;
            tarjeta.Stroke = new SolidColorBrush(activa ? Ds.Principal : Ds.Filo);
            tarjeta.StrokeThickness = activa ? 3 : 2;
            tarjeta.BackgroundColor = activa ? Ds.Verde50 : Ds.Superficie;
            if (_tiras.TryGetValue(ref_, out var tira)) tira.IsVisible = !activa;
            if (_detalles.TryGetValue(ref_, out var detalle)) detalle.IsVisible = activa;
            if (_marcas.TryGetValue(ref_, out var marca))
            {
                marca.BackgroundColor = activa ? Ds.Principal : Colors.White;
                marca.Stroke = new SolidColorBrush(activa ? Ds.Principal : Ds.Linea);
                if (marca.Content is Label check) check.Text = activa ? "✓" : "";
            }
        }
        SeleccionLabel.Text = $"Lección seleccionada: {leccion.Titulo}";
        DarClaseBtn.IsEnabled = true;
        DarClaseBtn.Opacity = 1;
    }

    private async void OnDarClase(object? sender, EventArgs e)
    {
        if (_seleccionada is null || _vista is null) return;
        await IniciarAsync(new IniciarSesionSolicitud("leccion", _vista.CursoRef, _seleccionada.LeccionRef, null, Sesion.FuenteAula, Sesion.ProfesorId, Sesion.ProfesorRotulo, "pantalla"));
    }

    private async void OnClaseLibre(object? sender, EventArgs e) =>
        await IniciarAsync(new IniciarSesionSolicitud("libre", _vista?.CursoRef, null, null, Sesion.FuenteAula, Sesion.ProfesorId, Sesion.ProfesorRotulo, "pantalla"));

    private async Task IniciarAsync(IniciarSesionSolicitud solicitud)
    {
        if (_iniciando) return;
        _iniciando = true;
        DarClaseBtn.IsEnabled = false;
        LibreBtn.IsEnabled = false;
        try
        {
            var aula = Sesion.Aula;
            var sesion = await aula.IniciarAsync(solicitud);
            if (sesion is not null)
            {
                Sesion.ClaseAbiertaId = sesion.Id;
                await Shell.Current.GoToAsync($"clase-sesion?sesion={Uri.EscapeDataString(sesion.Id)}");
                return;
            }
            var error = aula.UltimoError;
            if (error?.Codigo == "sesion_activa_existente" && error.Texto("sesion_id") is { } existente)
            {
                var continuar = await this.AlertaAsync("Ya tienes una clase abierta", "Puedes continuarla con el mismo código o cerrarla y empezar esta.", "Continuar esa clase", "Cerrarla y empezar");
                if (continuar)
                {
                    Sesion.ClaseAbiertaId = existente;
                    await Shell.Current.GoToAsync($"clase-sesion?sesion={Uri.EscapeDataString(existente)}");
                    return;
                }
                await aula.CerrarAsync(existente, Sesion.ProfesorId, forzar: true);
                Sesion.ClaseAbiertaId = null;
                _iniciando = false;
                await IniciarAsync(solicitud);
                return;
            }
            AvisoHost.Clear();
            // MOD-017 (R-01 · R-02): con el aula actualizándose no es un fallo ni una alarma: el nodo no inicia clases unos minutos y las abiertas siguen. Se dice en calma y con las palabras de siempre.
            if (ActualizacionTexto.SiEstaActualizando(error) is { } actualizando)
            {
                AvisoHost.Add(Ds.Alerta_(actualizando.Titulo, actualizando.Completo, Ds.AlertaSuave, Color.FromArgb("#9A3412")));
                return;
            }
            AvisoHost.Add(Ds.Alerta_("No se pudo iniciar la clase", string.Join(" ", new[] { error?.Detalle, error?.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x))), Ds.PeligroSuave, Color.FromArgb("#A51C20")));
        }
        finally
        {
            _iniciando = false;
            DarClaseBtn.IsEnabled = _seleccionada is not null;
            LibreBtn.IsEnabled = true;
        }
    }

    private void OnNotas(object? sender, EventArgs e) => NotasHost.IsVisible = !NotasHost.IsVisible;
    private async void OnVolver(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");
}
