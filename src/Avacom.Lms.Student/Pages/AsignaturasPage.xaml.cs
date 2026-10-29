using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Student.Pages;

/// <summary>
/// Los cursos que la biblioteca ofrece al estudiante, con su progreso. Si la
/// biblioteca está cerrada, el expediente sigue legible: se muestran los cursos
/// conocidos con aviso, y nunca una pantalla en blanco.
/// </summary>
public partial class AsignaturasPage : ContentPage
{
    private bool _cargando;

    public AsignaturasPage() => InitializeComponent();

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        SaludoLabel.Text = $"Tus cursos, {Sesion.Nombre.Split(' ')[0]}";
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
            var respuesta = await biblioteca.CursosAsync(Sesion.PersonaId);
            HexHost.Children.Clear();
            ListaHost.Clear();
            DemoBtn.IsVisible = false;

            // Los avisos de «sin conexión» de BibliotecaDeContenido decían «backend»; ahora dicen «conexión con el aula» o «no respondió».
            var aviso = respuesta.Aviso ?? string.Empty;
            var sinBackend = !respuesta.Disponible && respuesta.Cursos.Count == 0
                && (aviso.Contains("backend", StringComparison.OrdinalIgnoreCase) || aviso.Contains("conexión con el aula", StringComparison.OrdinalIgnoreCase)
                    || aviso.Contains("biblioteca de cursos no respondió", StringComparison.OrdinalIgnoreCase));
            EstadoChip.BackgroundColor = Color.FromArgb(respuesta.Disponible ? "#E1F5EC" : "#FDE7E7");
            EstadoChipLabel.TextColor = Color.FromArgb(respuesta.Disponible ? "#047857" : "#C81E24");
            EstadoChipLabel.Text = respuesta.Disponible ? (respuesta.Cursos.Count == 1 ? "●  1 curso disponible" : $"●  {respuesta.Cursos.Count} cursos disponibles") : "●  Biblioteca no disponible";

            AvisoCard.IsVisible = !respuesta.Disponible;
            if (!respuesta.Disponible)
            {
                AvisoTitulo.Text = sinBackend ? "No hay conexión con el aula." : "Los cursos no están disponibles en este momento.";
                AvisoDetalle.Text = (sinBackend ? "Revisa que la tableta esté conectada a la red del aula." : "Avisa a tu profesor.") +
                    (respuesta.Cursos.Count > 0 ? " Puedes seguir viendo tu progreso; el contenido se abrirá cuando vuelva." : string.Empty);
                DemoBtn.IsVisible = sinBackend;
            }

            var indice = 0;
            foreach (var curso in respuesta.Cursos)
            {
                var color = Sesion.Paleta[indice++ % Sesion.Paleta.Length];
                HexHost.Children.Add(Hexagono(curso, color));
                ListaHost.Add(Fila(curso, color));
            }
            if (respuesta.Cursos.Count == 0 && respuesta.Disponible)
                ListaHost.Add(new Label { Text = "La biblioteca no ofrece ningún curso en este equipo todavía.", Style = Estilo("Muted") });
        }
        finally { _cargando = false; }
    }

    private ProfessorHexTile Hexagono(CursoResumen curso, string color)
    {
        var tile = new ProfessorHexTile
        {
            Text = curso.Titulo,
            AccentColor = Color.FromArgb(curso.Disponible == false ? "#6A788E" : color),
            IconGeometry = Sesion.IconoLibro,
            IconSource = Glass.IconoMateria(curso.Asignatura),
            Margin = new Thickness(4, 2),
            BindingContext = curso,
        };
        tile.Tapped += async (_, _) => await AbrirAsync(curso);
        return tile;
    }

    private View Fila(CursoResumen curso, string color)
    {
        var grid = new Grid { ColumnDefinitions = [new ColumnDefinition(52), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
        grid.Add(new Border
        {
            BackgroundColor = Color.FromArgb(curso.Disponible == false ? "#6A788E" : color), StrokeThickness = 0, WidthRequest = 46, HeightRequest = 46,
            StrokeShape = new RoundRectangle { CornerRadius = 14 },
            Content = new Label { Text = "▤", TextColor = Colors.White, FontSize = 20, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        }, 0, 0);
        var textos = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = curso.Titulo, FontSize = 17, FontFamily = "LexendSemiBold" });
        textos.Add(new Label { Text = curso.Disponible == false ? curso.Aviso ?? "No disponible" : curso.Subtitulo, Style = Estilo("Muted") });
        var barra = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
        barra.Add(new ProgressBar { Progress = curso.ProgresoFraccion, ProgressColor = Color.FromArgb(color), VerticalOptions = LayoutOptions.Center }, 0, 0);
        barra.Add(new Label { Text = $"{curso.Progreso ?? 0:0}% completado", FontSize = 12, FontFamily = "LexendSemiBold", TextColor = Color.FromArgb(color) }, 1, 0);
        textos.Add(barra);
        grid.Add(textos, 1, 0);
        var abrir = new Button { Text = curso.Disponible == false ? "Ver avance" : "Entrar", Style = Estilo("PrimaryButton"), WidthRequest = 130, VerticalOptions = LayoutOptions.Center };
        abrir.Clicked += async (_, _) => await AbrirAsync(curso);
        grid.Add(abrir, 2, 0);
        return new Border { Padding = 18, Content = grid };
    }

    private static Task AbrirAsync(CursoResumen curso) =>
        Shell.Current.GoToAsync($"curso-biblioteca?curso={Uri.EscapeDataString(curso.CursoRef)}&titulo={Uri.EscapeDataString(curso.Titulo)}");

    private async void OnActualizar(object? sender, EventArgs e) => await CargarAsync();
    private async void OnDemo(object? sender, EventArgs e) => await Shell.Current.GoToAsync("course");
    private async void OnBack(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");

    /// <summary>Los estilos viven en Application.Resources; Resources de la página no los ve desde código.</summary>
    private static Style Estilo(string clave) =>
        Application.Current?.Resources.TryGetValue(clave, out var valor) == true && valor is Style estilo ? estilo : new Style(typeof(View));
}
