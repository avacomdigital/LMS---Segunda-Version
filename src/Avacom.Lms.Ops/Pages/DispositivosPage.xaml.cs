using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Dispositivos del aula (MOD-009 · Device Manager, CAP-052/054): el inventario de tabletas con su
/// estado en vivo (en línea, sin señal, bloqueada, retirada), quién la está usando y desde qué app.
/// El profesor bloquea o desbloquea una tableta con un toque; una tableta bloqueada no entra a clase
/// ni recibe lanzamientos, y nunca pierde nada (regla de oro de MOD-009). Se refresca cada 5 s.
/// </summary>
public partial class DispositivosPage : ContentPage
{
    private static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");

    private IDispatcherTimer? _temporizador;
    private bool _cargando;
    private bool _todos;
    private Button? _todosBtn;

    public DispositivosPage()
    {
        InitializeComponent();
        var actualizar = Ds.Boton("Actualizar", Ds.Rango.Secondary, async (_, _) => await CargarAsync(), 56);
        _todosBtn = Ds.Boton("Ver retiradas", Ds.Rango.Quiet, async (_, _) => { _todos = !_todos; await CargarAsync(); }, 56);
        var volver = Ds.Boton("Menú principal", Ds.Rango.Quiet, async (_, _) => await Shell.Current.GoToAsync(".."), 56);
        foreach (var b in new[] { actualizar, _todosBtn, volver }) b.FontSize = 16;
        AccionesHost.Add(Ds.Capsula(actualizar));
        AccionesHost.Add(Ds.Capsula(_todosBtn));
        AccionesHost.Add(volver);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await CargarAsync();
        _temporizador ??= Dispatcher.CreateTimer();
        _temporizador.Interval = TimeSpan.FromSeconds(5);
        _temporizador.Tick -= OnTick;
        _temporizador.Tick += OnTick;
        _temporizador.Start();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _temporizador?.Stop();
    }

    private async void OnTick(object? sender, EventArgs e) => await CargarAsync();

    private async Task CargarAsync()
    {
        if (_cargando) return;
        _cargando = true;
        try
        {
            var api = Sesion.Dispositivos;
            var lista = await api.ListarAsync(_todos);
            ListaHost.Clear();
            if (_todosBtn is not null) _todosBtn.Text = _todos ? "Ocultar retiradas" : "Ver retiradas";
            if (lista is null)
            {
                var error = api.UltimoError;
                ListaHost.Add(Ds.Alerta_(error?.Codigo == "no_instalado" ? "El nodo aún no está instalado" : "No se pudo leer el inventario",
                    string.Join(" ", new[] { error?.Detalle, error?.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x))), Ds.PeligroSuave, TintaPeligro));
                return;
            }
            var enLinea = lista.Count(d => d.Activo && d.EnLinea);
            var bloqueadas = lista.Count(d => d.Activo && d.Bloqueado);
            SubtituloLabel.Text = lista.Count == 0
                ? "Todavía no hay tabletas registradas. Se registran solas la primera vez que entran a una clase."
                : string.Join(" · ", new[]
                {
                    lista.Count == 1 ? "1 tableta" : $"{lista.Count} tabletas",
                    $"{enLinea} en línea",
                    bloqueadas > 0 ? $"{bloqueadas} bloqueada{(bloqueadas == 1 ? "" : "s")}" : null,
                    "Bloquear una tableta la deja fuera de las clases y de los lanzamientos; no borra nada.",
                }.Where(x => x is not null));
            if (lista.Count == 0)
            {
                ListaHost.Add(Ds.Tarjeta(Ds.Secundario("Cuando una tableta entre a una clase con su código, aparecerá aquí con su nombre, su plataforma y su estado.", 16), Ds.RadioTarjeta, new Thickness(24), Colors.White));
                return;
            }
            foreach (var d in lista.OrderBy(d => !d.Activo).ThenBy(d => !d.Bloqueado).ThenBy(d => !d.EnLinea).ThenBy(d => d.NombreVisible))
                ListaHost.Add(Fila(d));
        }
        finally { _cargando = false; }
    }

    private View Fila(DispositivoAula d)
    {
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(56), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        var color = !d.Activo ? Ds.TintaSuave : d.Bloqueado ? Ds.Peligro : d.EnLinea ? Ds.Exito : Ds.Alerta;
        // El punto de estado: verde en línea, ámbar sin señal, rojo bloqueada, gris retirada.
        fila.Add(new Border
        {
            BackgroundColor = color, StrokeThickness = 0, WidthRequest = 20, HeightRequest = 20, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
            StrokeShape = new RoundRectangle { CornerRadius = 999 },
        }, 0, 0);
        var textos = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        textos.Add(Ds.Cuerpo(d.NombreVisible, 18));
        textos.Add(Ds.Secundario(d.Detalle, 14));
        if (!string.Equals(d.NombreVisible, d.IdentificadorHw, StringComparison.Ordinal) && !string.IsNullOrWhiteSpace(d.IdentificadorHw))
            textos.Add(Ds.Secundario($"huella {d.IdentificadorHw}", 12));
        fila.Add(textos, 1, 0);
        var estado = Ds.Pildora(d.EstadoLegible, !d.Activo ? Ds.TintaSuave : d.Bloqueado ? Ds.PeligroSuave : d.EnLinea ? Ds.ExitoSuave : Ds.AlertaSuave,
            !d.Activo ? Colors.White : d.Bloqueado ? TintaPeligro : Ds.Tinta, 14);
        estado.VerticalOptions = LayoutOptions.Center;
        fila.Add(estado, 2, 0);
        if (d.Activo)
        {
            var bloqueo = Ds.Boton(d.Bloqueado ? "Desbloquear" : "Bloquear", d.Bloqueado ? Ds.Rango.Secondary : Ds.Rango.Quiet, async (_, _) => await BloqueoAsync(d), 56, 190);
            bloqueo.FontSize = 16;
            var capsula = Ds.Capsula(bloqueo);
            capsula.VerticalOptions = LayoutOptions.Center;
            fila.Add(capsula, 3, 0);
        }
        return Ds.Tarjeta(fila, Ds.RadioTarjeta, new Thickness(22, 16), d.Bloqueado && d.Activo ? Ds.PeligroSuave : Colors.White);
    }

    private async Task BloqueoAsync(DispositivoAula d)
    {
        var api = Sesion.Dispositivos;
        var resultado = d.Bloqueado
            ? await api.DesbloquearAsync(d.Id, Sesion.ProfesorId)
            : await api.BloquearAsync(d.Id, Sesion.ProfesorId, "desde Dispositivos del aula");
        if (resultado is null)
            await DisplayAlertAsync(d.Bloqueado ? "No se pudo desbloquear" : "No se pudo bloquear", api.UltimoMotivo ?? "Sin detalle.", "Entendido");
        await CargarAsync();
    }
}
