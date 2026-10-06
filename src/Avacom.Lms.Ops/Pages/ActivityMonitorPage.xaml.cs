using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Monitor de actividad. Arriba, con datos reales del nodo, los visitantes (RN-46 · RF-09c): «Visitante · tableta N», cuántos y desde qué tableta —la rendición
/// de cuentas contra el sabotaje es la tableta, no la persona— y «Vincular a un alumno» para acreditarle lo que hizo esa visita cuando el profesor sabe quién
/// fue (RN-44). Debajo sigue la maqueta del cuestionario en vivo.
/// </summary>
public partial class ActivityMonitorPage : ContentPage
{
    private static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");

    public IEnumerable<StudentRow> Students { get; } = DemoCatalog.Students.Select(s => new StudentRow(s.Initials, s.Name, s.Status, s.CurrentQuestion, s.TotalQuestions == 0 ? 0 : (double)s.CurrentQuestion / s.TotalQuestions, s.Score is null ? "—" : $"{s.Score:0}/100"));

    private IReadOnlyList<VisitanteEnClase>? _visitantes;
    private IReadOnlyList<(string Grupo, EstudiantePadron Alumno)>? _alumnos;
    private string? _vinculando;
    private (string Texto, bool Problema)? _aviso;

    public ActivityMonitorPage() { InitializeComponent(); BindingContext = this; }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _aviso = null;
        _vinculando = null;
        await CargarVisitantesAsync();
    }

    private async void OnBack(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");

    private async Task CargarVisitantesAsync()
    {
        var acceso = Sesion.Acceso;
        _visitantes = await acceso.ListarVisitantesAsync();
        if (_visitantes is null && _aviso is null) _aviso = (MensajesDeAcceso.Texto(acceso.UltimoError), true);
        PintarVisitantes();
    }

    private void PintarVisitantes()
    {
        VisitantesHost.Clear();
        var titulo = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        var textos = new VerticalStackLayout { Spacing = 2 };
        textos.Add(new Label { Text = "Visitantes", FontSize = 21, FontAttributes = FontAttributes.Bold });
        textos.Add(new Label { Text = "Quien olvidó su PIN entra como visitante: lo que hace no va al historial de nadie hasta que lo vincules a un alumno.", Style = Estilo("Muted"), LineBreakMode = LineBreakMode.WordWrap });
        titulo.Add(textos, 0, 0);
        if (_visitantes is not null)
            titulo.Add(Ds.Pildora(_visitantes.Count == 1 ? "1 ahora" : $"{_visitantes.Count} ahora", _visitantes.Count > 0 ? Ds.AlertaSuave : Ds.Lienzo, Ds.Tinta, 15), 1, 0);
        var actualizar = Ds.Boton("Actualizar", Ds.Rango.Quiet, async (_, _) => { _aviso = null; await CargarVisitantesAsync(); }, 40);
        actualizar.MinimumWidthRequest = 110;
        titulo.Add(actualizar, 2, 0);
        VisitantesHost.Add(titulo);

        if (_aviso is { } aviso)
            VisitantesHost.Add(Ds.Alerta_(aviso.Problema ? "No se pudo" : "Listo", aviso.Texto, aviso.Problema ? Ds.PeligroSuave : Ds.ExitoSuave, aviso.Problema ? TintaPeligro : Ds.Tinta));
        if (_visitantes is null) return;
        if (_visitantes.Count == 0)
        {
            VisitantesHost.Add(Ds.Tarjeta(Ds.Secundario("Nadie entró como visitante en este momento.", 16), Ds.RadioTarjeta, new Thickness(20, 14), Colors.White));
            return;
        }
        // Cuántos por tableta: si una tableta acumula visitas, es ahí donde hay que mirar.
        var porTableta = _visitantes.GroupBy(v => v.Dispositivo ?? "tableta sin nombre").Where(g => g.Count() > 1).ToList();
        if (porTableta.Count > 0)
            VisitantesHost.Add(Ds.Secundario("Varias visitas desde " + string.Join(", ", porTableta.Select(g => $"{g.Key} ({g.Count()})")) + ".", 14));
        foreach (var v in _visitantes.OrderBy(v => v.EmitidaEn)) VisitantesHost.Add(TarjetaVisitante(v));
    }

    private View TarjetaVisitante(VisitanteEnClase v)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        var textos = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        textos.Add(Ds.Cuerpo(v.Alias, 18));
        var desde = string.IsNullOrWhiteSpace(v.Dispositivo) ? string.Empty : $"desde {v.Dispositivo} · ";
        textos.Add(Ds.Secundario($"{desde}entró a las {DateTimeOffset.FromUnixTimeMilliseconds(v.EmitidaEn).ToLocalTime():HH:mm}", 14));
        fila.Add(textos, 0, 0);
        var abierto = _vinculando == v.UsuarioId;
        var vincular = Ds.Boton(abierto ? "Cancelar" : "Vincular a un alumno", abierto ? Ds.Rango.Quiet : Ds.Rango.Secondary, async (_, _) =>
        {
            _vinculando = abierto ? null : v.UsuarioId;
            if (_vinculando is not null && _alumnos is null) await CargarAlumnosAsync();
            PintarVisitantes();
        }, 40);
        vincular.FontSize = 14;
        vincular.MinimumWidthRequest = 110;
        AutomationProperties.SetName(vincular, abierto ? "Cancelar" : $"Vincular {v.Alias} a un alumno");
        fila.Add(Ds.Capsula(vincular), 1, 0);
        pila.Add(fila);
        if (abierto) pila.Add(ListaDeAlumnos(v));
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(20, 14), Colors.White);
    }

    private async Task CargarAlumnosAsync()
    {
        var padron = await Sesion.Padron.EstadoAsync();
        _alumnos = padron?.Grupos.SelectMany(g => g.Estudiantes.Select(e => (g.Nombre, e))).OrderBy(x => x.Nombre).ThenBy(x => x.e.Alias).ToList();
        if (_alumnos is null) _aviso = (MensajesDeAcceso.Texto(Sesion.Padron.UltimoError), true);
    }

    private View ListaDeAlumnos(VisitanteEnClase visita)
    {
        var pila = new VerticalStackLayout { Spacing = 6 };
        if (_alumnos is null || _alumnos.Count == 0)
        {
            pila.Add(Ds.Secundario("No hay alumnos en tus grupos con quien vincular esta visita.", 14));
            return pila;
        }
        pila.Add(Ds.Secundario("¿Quién era? Toca su nombre: lo que hizo esta visita pasa a su historial.", 14));
        foreach (var grupo in _alumnos.GroupBy(x => x.Grupo))
        {
            pila.Add(Ds.Secundario(grupo.Key, 13));
            var fichas = new FlexLayout { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap };
            foreach (var (_, alumno) in grupo)
            {
                var b = Ds.Boton(alumno.Alias, Ds.Rango.Secondary, async (_, _) => await VincularAsync(visita, alumno), 40);
                b.FontSize = 14;
                b.MinimumWidthRequest = 96;
                var c = Ds.Capsula(b);
                c.Margin = new Thickness(0, 0, 8, 8);
                fichas.Add(c);
            }
            pila.Add(fichas);
        }
        return pila;
    }

    private async Task VincularAsync(VisitanteEnClase visita, EstudiantePadron alumno)
    {
        var acceso = Sesion.Acceso;
        _aviso = await acceso.VincularVisitanteAsync(visita.UsuarioId, alumno.Id)
            ? ($"Lo que hizo {visita.Alias} quedó acreditado a {alumno.Alias}.", false)
            : (MensajesDeAcceso.Texto(acceso.UltimoError), true);
        _vinculando = null;
        await CargarVisitantesAsync();
    }

    private static Style? Estilo(string clave) => Application.Current?.Resources.TryGetValue(clave, out var s) == true ? s as Style : null;

    public sealed record StudentRow(string Initials, string Name, string Status, int CurrentQuestion, double Progress, string ScoreLabel);
}
