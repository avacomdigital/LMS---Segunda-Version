using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Dispositivos del aula (MOD-009 · Device Manager, CAP-052/054): el inventario de tabletas con su
/// estado en vivo (en línea, sin señal, bloqueada, retirada), quién la está usando y desde qué app.
/// El profesor bloquea o desbloquea una tableta con un toque; una tableta bloqueada no entra a clase
/// ni recibe lanzamientos, y nunca pierde nada (regla de oro de MOD-009). Se refresca cada 5 s.
///
/// MOD-008 · 008-01: cada tableta es <b>compartida</b> (del fondo del aula) o <b>asignada</b> a un alumno. Sólo en una asignada existe el
/// modo de estudio y el alumno puede llevarse las lecciones. Aquí se asigna (grupo → alumno, con toques) y se devuelve al fondo compartido.
/// </summary>
public partial class DispositivosPage : ContentPage
{
    private static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");

    private IDispatcherTimer? _temporizador;
    private bool _cargando;
    private bool _todos;
    private Button? _todosBtn;

    // 008-01 · la tableta a la que se le está eligiendo dueño, y lo que se sabe de los grupos. Viven en la página para que el refresco cada
    // 5 s no cierre el selector a la mitad.
    private string? _asignandoId;
    private string? _grupoElegidoId;
    private GruposDocente? _grupos;
    private string? _gruposError;

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
            var asignadas = lista.Count(d => d.Activo && d.Asignado);
            SubtituloLabel.Text = lista.Count == 0
                ? "Todavía no hay tabletas registradas. Se registran solas la primera vez que entran a una clase."
                : string.Join(" · ", new[]
                {
                    lista.Count == 1 ? "1 tableta" : $"{lista.Count} tabletas",
                    $"{enLinea} en línea",
                    asignadas > 0 ? $"{asignadas} asignada{(asignadas == 1 ? "" : "s")} a un alumno" : null,
                    bloqueadas > 0 ? $"{bloqueadas} bloqueada{(bloqueadas == 1 ? "" : "s")}" : null,
                    "Bloquear una tableta la deja fuera de las clases y de los lanzamientos; no borra nada.",
                }.Where(x => x is not null));
            if (lista.Count == 0)
            {
                ListaHost.Add(Ds.Tarjeta(Ds.Secundario("Cuando una tableta entre a una clase con su código, aparecerá aquí con su nombre, su plataforma y su estado.", 16), Ds.RadioTarjeta, new Thickness(24), Colors.White));
                return;
            }
            if (_asignandoId is not null && lista.All(d => d.Id != _asignandoId)) _asignandoId = null;
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
        if (d.Activo)
        {
            // MOD-008 · 008-01: de quién es la tableta. Sin el nombre del alumno (el nodo no lo trajo) se dice «asignada» a secas.
            var perfil = d.Asignado
                ? $"Asignada a {(string.IsNullOrWhiteSpace(d.AsignadoA?.Rotulo) ? "un alumno" : d.AsignadoA!.Rotulo)} · su dueño puede llevarse las lecciones"
                : "Compartida del aula · las lecciones se estudian con el aula conectada";
            textos.Add(new Label { Text = perfil, FontFamily = Ds.FuenteMedia, FontSize = 14, TextColor = d.Asignado ? Color.FromArgb("#017A48") : Ds.TintaMedia });
        }
        if (!string.Equals(d.NombreVisible, d.IdentificadorHw, StringComparison.Ordinal) && !string.IsNullOrWhiteSpace(d.IdentificadorHw))
            textos.Add(Ds.Secundario($"huella {d.IdentificadorHw}", 12));
        fila.Add(textos, 1, 0);
        var estado = Ds.Pildora(d.EstadoLegible, !d.Activo ? Ds.TintaSuave : d.Bloqueado ? Ds.PeligroSuave : d.EnLinea ? Ds.ExitoSuave : Ds.AlertaSuave,
            !d.Activo ? Colors.White : d.Bloqueado ? TintaPeligro : Ds.Tinta, 14);
        estado.VerticalOptions = LayoutOptions.Center;
        fila.Add(estado, 2, 0);
        if (d.Activo)
        {
            var botones = new HorizontalStackLayout { Spacing = 12, VerticalOptions = LayoutOptions.Center };

            var dueno = d.Asignado
                ? Ds.Boton("Devolver al aula", Ds.Rango.Quiet, async (_, _) => await LiberarAsync(d), 56, 200)
                : Ds.Boton(_asignandoId == d.Id ? "Cerrar" : "Asignar a un alumno", Ds.Rango.Secondary, async (_, _) => await AlternarSelectorAsync(d), 56, 220);
            dueno.FontSize = 16;
            dueno.AutomationId = d.Asignado ? $"dispositivo-liberar-{d.Id}" : $"dispositivo-asignar-{d.Id}";
            SemanticProperties.SetDescription(dueno, d.Asignado ? $"Devolver {d.NombreVisible} al fondo compartido del aula" : $"Asignar {d.NombreVisible} a un alumno");
            var capsulaDueno = Ds.Capsula(dueno);
            capsulaDueno.VerticalOptions = LayoutOptions.Center;
            botones.Add(capsulaDueno);

            var bloqueo = Ds.Boton(d.Bloqueado ? "Desbloquear" : "Bloquear", d.Bloqueado ? Ds.Rango.Secondary : Ds.Rango.Quiet, async (_, _) => await BloqueoAsync(d), 56, 190);
            bloqueo.FontSize = 16;
            var capsula = Ds.Capsula(bloqueo);
            capsula.VerticalOptions = LayoutOptions.Center;
            botones.Add(capsula);
            fila.Add(botones, 3, 0);
        }
        var tarjeta = Ds.Tarjeta(fila, Ds.RadioTarjeta, new Thickness(22, 16), d.Bloqueado && d.Activo ? Ds.PeligroSuave : Colors.White);
        if (_asignandoId != d.Id || d.Asignado) return tarjeta;

        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(tarjeta);
        pila.Add(Selector(d));
        return pila;
    }

    // ------------------------------------------------------------------ MOD-008 · asignar a un alumno

    private async Task AlternarSelectorAsync(DispositivoAula d)
    {
        if (_asignandoId == d.Id)
        {
            _asignandoId = null;
            await CargarAsync();
            return;
        }
        _asignandoId = d.Id;
        _grupoElegidoId = null;
        _grupos = null;
        _gruposError = null;
        await CargarAsync();          // pinta el selector con «buscando grupos…»
        var api = Sesion.Estudio;
        _grupos = await api.GruposAsync(Sesion.ProfesorId);
        _gruposError = _grupos is null ? EstudioTexto.Error(api.UltimoError, api.UltimoMotivo) : null;
        if (_grupos is { Instalado: true, Grupos.Count: 1 }) _grupoElegidoId = _grupos.Grupos[0].Id;
        await CargarAsync();
    }

    /// <summary>Grupo y después alumno, con toques (el nodo principal no tiene teclado). Al tocar a un alumno se pide confirmación.</summary>
    private View Selector(DispositivoAula d)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Ds.Titulo($"¿De quién es «{d.NombreVisible}»?", 20));
        pila.Add(Ds.Secundario("En cualquier tableta se puede estudiar con el aula conectada (cada alumno elige su nombre); sólo en una tableta asignada su dueño puede llevarse las lecciones para estudiar sin conexión. Elige el grupo y toca al alumno.", 14));
        if (_grupos is null)
        {
            pila.Add(_gruposError is null ? Ds.Secundario("Buscando tus grupos…", 15) : Ds.Alerta_("No se pudieron leer tus grupos", _gruposError, Ds.PeligroSuave, TintaPeligro));
        }
        else if (!_grupos.Instalado)
        {
            pila.Add(Ds.Alerta_("El nodo aún no tiene organización instalada", "Sin organización no hay alumnos a quienes asignar la tableta.", Ds.AlertaSuave, Color.FromArgb("#806600")));
        }
        else if (_grupos.Grupos.Count == 0)
        {
            pila.Add(Ds.Alerta_("No tienes grupos a tu cargo", "Los grupos los define la administración.", Ds.AlertaSuave, Color.FromArgb("#806600")));
        }
        else
        {
            if (_grupos.Grupos.Count > 1)
            {
                var grupos = EstudioUi.Envolver();
                foreach (var grupo in _grupos.Grupos)
                {
                    var g = grupo;
                    grupos.Add(EstudioUi.Chip($"{g.Nombre ?? g.Codigo ?? g.Id} · {g.Alumnos.Count}", _grupoElegidoId == g.Id,
                        async () => { _grupoElegidoId = g.Id; await CargarAsync(); }, $"dispositivo-grupo-{g.Id}", 48));
                }
                pila.Add(grupos);
            }
            var elegido = _grupos.Grupos.FirstOrDefault(g => g.Id == _grupoElegidoId);
            if (elegido is null) pila.Add(Ds.Secundario("Elige un grupo para ver a sus alumnos.", 15));
            else if (elegido.Alumnos.Count == 0) pila.Add(Ds.Secundario("Este grupo no tiene alumnos todavía.", 15));
            else
            {
                var alumnos = EstudioUi.Envolver();
                foreach (var alumno in elegido.Alumnos.OrderBy(a => a.Rotulo ?? a.Id, StringComparer.CurrentCultureIgnoreCase))
                {
                    var a = alumno;
                    alumnos.Add(EstudioUi.Chip(a.Rotulo ?? a.Id, false, async () => await AsignarAsync(d, a), $"dispositivo-alumno-{a.Id}", 48));
                }
                pila.Add(alumnos);
            }
        }
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(24, 18), Color.FromArgb("#FBFBFC"));
    }

    private async Task AsignarAsync(DispositivoAula d, AlumnoDeGrupo alumno)
    {
        var nombre = alumno.Rotulo ?? alumno.Id;
        var seguro = await DisplayAlertAsync("¿Asignar esta tableta?", $"«{d.NombreVisible}» será de {nombre}. Sólo {nombre} podrá llevarse las lecciones en ella para estudiar sin conexión.", "Asignar", "Mejor no");
        if (!seguro) return;
        var api = Sesion.Dispositivos;
        var resultado = await api.AsignarAsync(d.Id, alumno.Id, Sesion.ProfesorId);
        if (resultado is null)
        {
            await DisplayAlertAsync("No se pudo asignar", EstudioTexto.Error(api.UltimoError, api.UltimoMotivo), "Entendido");
            return;
        }
        _asignandoId = null;
        await CargarAsync();
    }

    private async Task LiberarAsync(DispositivoAula d)
    {
        var dueno = string.IsNullOrWhiteSpace(d.AsignadoA?.Rotulo) ? "su alumno" : d.AsignadoA!.Rotulo;
        var seguro = await DisplayAlertAsync("¿Devolver esta tableta al aula?",
            $"«{d.NombreVisible}» dejará de ser de {dueno} y volverá al fondo compartido: ahí ya no se descargan lecciones para estudiar sin conexión.", "Devolver", "Mejor no");
        if (!seguro) return;
        var api = Sesion.Dispositivos;
        var resultado = await api.LiberarAsync(d.Id, Sesion.ProfesorId);
        if (resultado is null)
            await DisplayAlertAsync("No se pudo devolver", EstudioTexto.Error(api.UltimoError, api.UltimoMotivo), "Entendido");
        await CargarAsync();
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
