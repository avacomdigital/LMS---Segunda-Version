using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Sección «Asignaturas» del docente: los cursos que AVACOM Biblioteca ofrece en
/// este equipo, como hexágonos y como lista completa. No hay botón de crear: los
/// cursos se administran en la biblioteca (artículo 14).
/// </summary>
public partial class AsignaturasPage : ContentPage
{
    private bool _cargando;

    public AsignaturasPage() => InitializeComponent();

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        Sesion.Biblioteca.OlvidarHuella();
        await CargarAsync();
    }

    private async Task CargarAsync()
    {
        if (_cargando) return;
        _cargando = true;
        try
        {
            var biblioteca = Sesion.Biblioteca;
            var estado = await biblioteca.EstadoAsync();
            PintarEstado(estado);

            var respuesta = await biblioteca.CursosAsync(personaId: null);
            HexHost.Children.Clear();
            ListaHost.Clear();
            if (!respuesta.Disponible)
            {
                AvisoCard.IsVisible = true;
                AvisoTitulo.Text = "La biblioteca de cursos no está disponible.";
                AvisoDetalle.Text = "Pide a la administración que revise la biblioteca de cursos del aula y vuelve a intentarlo.";
                ConteoLabel.Text = string.Empty;
                return;
            }
            AvisoCard.IsVisible = false;
            ConteoLabel.Text = respuesta.Cursos.Count == 1 ? "1 curso" : $"{respuesta.Cursos.Count} cursos";
            var indice = 0;
            foreach (var curso in respuesta.Cursos)
            {
                var color = Sesion.Paleta[indice++ % Sesion.Paleta.Length];
                HexHost.Children.Add(Hexagono(curso, color));
                ListaHost.Add(Fila(curso, color));
            }
            if (respuesta.Cursos.Count == 0)
                ListaHost.Add(new Label { Text = "Todavía no hay cursos en la biblioteca.", Style = Estilo("Muted") });
        }
        finally { _cargando = false; }
    }

    private void PintarEstado(EstadoBiblioteca estado)
    {
        var ok = estado.Disponible;
        EstadoChip.BackgroundColor = Color.FromArgb(ok ? "#E1F5EC" : "#FDE7E7");
        EstadoChipLabel.TextColor = Color.FromArgb(ok ? "#047857" : "#C81E24");
        EstadoChipLabel.Text = ok
            ? "●  Biblioteca conectada"
            : "●  Biblioteca no disponible";
    }

    private ProfessorHexTile Hexagono(CursoResumen curso, string color)
    {
        var tile = new ProfessorHexTile
        {
            Text = curso.Titulo,
            AccentColor = Color.FromArgb(color),
            IconGeometry = Sesion.IconoLibro,
            IconSource = Glass.IconoMateria(curso.Asignatura),
            Margin = new Thickness(6, 4),
            BindingContext = curso,
        };
        tile.Tapped += async (_, _) => await AbrirAsync(curso);
        return tile;
    }

    private View Fila(CursoResumen curso, string color)
    {
        var grid = new Grid
        {
            ColumnDefinitions = [new ColumnDefinition(56), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)],
            ColumnSpacing = 16,
        };
        grid.Add(new Border
        {
            BackgroundColor = Color.FromArgb(color), StrokeThickness = 0, WidthRequest = 48, HeightRequest = 48,
            StrokeShape = new RoundRectangle { CornerRadius = 14 },
            Content = new Label { Text = "▤", TextColor = Colors.White, FontSize = 22, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        }, 0, 0);
        var textos = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = curso.Titulo, FontSize = 18, FontFamily = "LexendSemiBold" });
        textos.Add(new Label { Text = curso.Subtitulo, Style = Estilo("Muted") });
        textos.Add(new Label { Text = $"{curso.Detalle} · ref {curso.CursoRef}", FontSize = 12, TextColor = Color.FromArgb("#5F6474") });
        grid.Add(textos, 1, 0);
        var abrir = new Button { Text = "Abrir curso", Style = Estilo("PrimaryButton"), WidthRequest = 150, VerticalOptions = LayoutOptions.Center };
        abrir.Clicked += async (_, _) => await AbrirAsync(curso);
        grid.Add(abrir, 2, 0);
        var borde = new Border { Padding = 20, Content = grid };
        var tap = new TapGestureRecognizer();
        tap.Tapped += async (_, _) => await AbrirAsync(curso);
        borde.GestureRecognizers.Add(tap);
        return borde;
    }

    private static Task AbrirAsync(CursoResumen curso) =>
        Shell.Current.GoToAsync($"curso-biblioteca?curso={Uri.EscapeDataString(curso.CursoRef)}&titulo={Uri.EscapeDataString(curso.Titulo)}");

    private async void OnActualizar(object? sender, EventArgs e) => await CargarAsync();
    private async void OnBack(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");

    /// <summary>Los estilos viven en Application.Resources; Resources de la página no los ve desde código.</summary>
    private static Style Estilo(string clave) =>
        Application.Current?.Resources.TryGetValue(clave, out var valor) == true && valor is Style estilo ? estilo : new Style(typeof(View));
}
