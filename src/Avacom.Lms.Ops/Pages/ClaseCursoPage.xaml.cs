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
        var vista = await aula.CursoAsync(CursoRef, docente: true);
        if (vista is null)
        {
            var error = aula.UltimoError;
            AvisoHost.Add(Ds.Alerta_("No se pudo leer el curso", string.Join(" ", new[] { error?.Detalle, error?.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x))), Ds.PeligroSuave, Color.FromArgb("#8A1C1F")));
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
        if (v.Clasificacion?.Asignatura?.Nombre is { } asig) chips.Add(Ds.Pildora(asig, Ds.CatClaseEnVivo));
        if (v.Clasificacion?.Grado?.Nombre is { } grado) chips.Add(Ds.Pildora(grado, Ds.Lienzo, Ds.Tinta));
        if (v.Clasificacion?.Nivel?.Nombre is { } nivel) chips.Add(Ds.Pildora(nivel, Ds.Lienzo, Ds.Tinta));
        if (v.DuracionEstimadaMin is > 0) chips.Add(Ds.Pildora($"{v.DuracionEstimadaMin} min en total", Ds.Lienzo, Ds.Tinta));
        textos.Add(chips);
        textos.Add(Ds.Titulo(v.Titulo, 30));
        if (!string.IsNullOrWhiteSpace(v.Subtitulo)) textos.Add(Ds.Cuerpo(v.Subtitulo!, 18, Ds.TintaSuave));
        if (!string.IsNullOrWhiteSpace(v.Descripcion)) textos.Add(Ds.Secundario(v.Descripcion!, 15));
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
        var grid = new Grid
        {
            ColumnDefinitions = [new ColumnDefinition(56), new ColumnDefinition(GridLength.Star)],
            ColumnSpacing = 18,
        };
        var soloExamen = leccion.SoloExamen;
        var numeroChip = new Border
        {
            BackgroundColor = Ds.Rojo, StrokeThickness = 0, WidthRequest = 56, HeightRequest = 56,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, VerticalOptions = LayoutOptions.Start,
            Content = new Label { Text = numero.ToString(), FontSize = 24, FontAttributes = FontAttributes.Bold, TextColor = Colors.White, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        };
        grid.Add(numeroChip, 0, 0);
        var textos = new VerticalStackLayout { Spacing = 8 };
        textos.Add(Ds.Titulo(leccion.Titulo, 22));
        if (!string.IsNullOrWhiteSpace(leccion.Resumen)) textos.Add(Ds.Secundario(leccion.Resumen!, 16));
        var chips = new FlexLayout { Wrap = FlexWrap.Wrap, Direction = FlexDirection.Row, JustifyContent = FlexJustify.Start, AlignItems = FlexAlignItems.Center };
        foreach (var objeto in leccion.Objetos ?? [])
        {
            var color = Ds.Categoria(objeto.Componente);
            // El examen ya se puede aplicar (MOD-010): su chip es de categoría como los demás. Sólo lo que de verdad no se ejecuta sigue atenuado.
            var noSeEjecuta = objeto.FueraDeAlcance && objeto.Componente != "examen" && objeto.Tipo != "exam";
            var chip = Ds.Pildora($"{Ds.Icono(objeto.Componente)}  {objeto.ComponenteLegible} · {objeto.Titulo}", noSeEjecuta ? Ds.Lienzo : color, noSeEjecuta ? Ds.TintaSuave : null, 14);
            chip.Margin = new Thickness(0, 0, 8, 8);
            if (noSeEjecuta) chip.Opacity = 0.7;
            chips.Add(chip);
        }
        textos.Add(chips);
        var pie = string.Join(" · ", new[]
        {
            leccion.DuracionEstimadaMin is > 0 ? $"{leccion.DuracionEstimadaMin} min" : null,
            $"{leccion.ObjetosDelAula.Count} objeto(s) para el aula",
            soloExamen ? "Sólo examen: se aplica durante la clase" : null,
        }.Where(x => x is not null));
        textos.Add(Ds.Secundario(pie, 14));
        grid.Add(textos, 1, 0);
        var tarjeta = Ds.Tarjeta(grid, Ds.RadioTarjeta, new Thickness(22, 20));
        // Una lección que sólo tiene examen también se puede dar: el examen se aplica desde la clase.
        Ds.Tocable(tarjeta, () => { Seleccionar(leccion); return Task.CompletedTask; });
        return tarjeta;
    }

    private void Seleccionar(LeccionAula leccion)
    {
        _seleccionada = leccion;
        foreach (var (ref_, tarjeta) in _tarjetas)
        {
            var activa = ref_ == leccion.LeccionRef;
            tarjeta.Stroke = new SolidColorBrush(activa ? Ds.Rojo : Ds.Filo);
            tarjeta.StrokeThickness = activa ? 3 : 1;
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
                var continuar = await DisplayAlertAsync("Ya tienes una clase abierta", "Puedes continuarla con el mismo código o cerrarla y empezar esta.", "Continuar esa clase", "Cerrarla y empezar");
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
            AvisoHost.Add(Ds.Alerta_("No se pudo iniciar la clase", string.Join(" ", new[] { error?.Detalle, error?.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x))), Ds.PeligroSuave, Color.FromArgb("#8A1C1F")));
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
