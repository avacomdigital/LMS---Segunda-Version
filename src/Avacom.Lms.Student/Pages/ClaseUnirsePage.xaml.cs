using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Student.Pages;

/// <summary>
/// S1 · Entrar a la clase (PAN-100/101). Seis casillas y un teclado numérico en pantalla:
/// el código de unión es lo único que se escribe en todo el journey, y se escribe aquí. Si la
/// tableta ya participaba en una clase activa, se readmite sola (FUN-077).
/// </summary>
public partial class ClaseUnirsePage : ContentPage
{
    private readonly List<Label> _casillas = new();
    private string _codigo = string.Empty;
    private Button? _entrarBtn;
    private bool _enviando;
    private IDispatcherTimer? _esperaTimer;

    public ClaseUnirsePage()
    {
        InitializeComponent();
        for (var i = 0; i < 6; i++)
        {
            var label = new Label { Text = string.Empty, FontSize = 34, FontAttributes = FontAttributes.Bold, TextColor = Ds.Tinta, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center };
            _casillas.Add(label);
            CasillasHost.Add(new Border
            {
                WidthRequest = 62, HeightRequest = 76, BackgroundColor = Colors.White, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1,
                StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioBoton }, Content = label, Shadow = Ds.SombraTarjeta(),
            });
        }
        var teclas = new[] { "1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "Borrar" };
        for (var i = 0; i < teclas.Length; i++)
        {
            var tecla = teclas[i];
            var b = Ds.Boton(tecla, tecla is "⌫" or "Borrar" ? Ds.Rango.Quiet : Ds.Rango.Secondary, (_, _) => Tecla(tecla), 76);
            b.FontSize = tecla == "Borrar" ? 18 : 28;
            Teclado.Add(b, i % 3, i / 3);
        }
        _entrarBtn = Ds.Boton("Entrar a la clase", Ds.Rango.Primary, async (_, _) => await EntrarAsync(), 64);
        _entrarBtn.IsEnabled = false;
        _entrarBtn.Opacity = 0.5;
        AccionesHost.Add(_entrarBtn);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        NombreLabel.Text = Sesion.Nombre;
        await ReadmitirSiHaceFaltaAsync();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _esperaTimer?.Stop();
    }

    private async Task ReadmitirSiHaceFaltaAsync()
    {
        if (Sesion.ClaseSesionId is not { } sesionId || Sesion.ClaseParticipanteId is not { } participanteId) return;
        var estado = await Sesion.Aula.EstadoAsync(sesionId, participanteId);
        if (estado is { Activa: true, Participante: { } p } && p.Estado is not ("expulsado" or "rechazado"))
        {
            AvisoHost.Clear();
            AvisoHost.Add(Ds.Alerta_("Seguías en una clase", $"{estado.Sesion.LeccionRotulo ?? estado.Sesion.CursoRotulo} · {estado.Sesion.ProfesorRotulo}. Volviendo…", Ds.InfoSuave, Ds.Tinta));
            await Sesion.Aula.PresenciaAsync(sesionId, participanteId, "conectado", Sesion.Dispositivo);
            await Shell.Current.GoToAsync($"clase-siguiendo?sesion={Uri.EscapeDataString(sesionId)}&participante={Uri.EscapeDataString(participanteId)}");
            return;
        }
        if (estado is not null) Sesion.OlvidarClase();
    }

    private void Tecla(string tecla)
    {
        switch (tecla)
        {
            case "⌫": if (_codigo.Length > 0) _codigo = _codigo[..^1]; break;
            case "Borrar": _codigo = string.Empty; break;
            default: if (_codigo.Length < 6) _codigo += tecla; break;
        }
        for (var i = 0; i < 6; i++) _casillas[i].Text = i < _codigo.Length ? _codigo[i].ToString() : string.Empty;
        AvisoHost.Clear();
        if (_entrarBtn is not null)
        {
            _entrarBtn.IsEnabled = _codigo.Length == 6;
            _entrarBtn.Opacity = _codigo.Length == 6 ? 1 : 0.5;
        }
    }

    private async Task EntrarAsync()
    {
        if (_enviando || _codigo.Length != 6) return;
        _enviando = true;
        if (_entrarBtn is not null) _entrarBtn.IsEnabled = false;
        try
        {
            var aula = Sesion.Aula;
            var estado = await aula.UnirseAsync(_codigo, Sesion.PersonaId, Sesion.Nombre, Sesion.Dispositivo, Sesion.ClaseParticipanteId,
                                                Sesion.Plataforma, Sesion.VersionApp);
            AvisoHost.Clear();
            if (estado is null)
            {
                var error = aula.UltimoError;
                var (titulo, detalle) = error?.Codigo switch
                {
                    "codigo_invalido" => ("Ese código no es", "Pídele a tu profesor que lo muestre en la pantalla."),
                    "participante_expulsado" => ("No puedes entrar por ahora", "Habla con tu profesor para volver a la clase."),
                    "dispositivo_bloqueado" => ("Esta tableta está bloqueada", "Tu profesor la bloqueó desde el aula. Pídele que la desbloquee o usa otra tableta."),
                    "dispositivo_inactivo" => ("Esta tableta fue retirada del aula", "Habla con tu profesor para usar otra tableta."),
                    "sin_conexion" => ("No hay conexión con el aula", error?.Sugerencia ?? "Revisa la red."),
                    _ => ("No se pudo entrar", error?.Detalle ?? aula.UltimoMotivo),
                };
                AvisoHost.Add(Ds.Alerta_(titulo, detalle, Ds.PeligroSuave, Color.FromArgb("#8A1C1F")));
                return;
            }
            Sesion.ClaseSesionId = estado.Sesion.Id;
            Sesion.ClaseParticipanteId = estado.Participante?.Id;
            Sesion.ClaseCodigo = _codigo;
            if (estado.EnEspera == true)
            {
                AvisoHost.Add(Ds.Alerta_("Tu profesor te va a admitir", "Espera un momento en esta pantalla.", Ds.AlertaSuave, Ds.Tinta));
                EsperarAdmision(estado.Sesion.Id, estado.Participante!.Id);
                return;
            }
            await Shell.Current.GoToAsync($"clase-siguiendo?sesion={Uri.EscapeDataString(estado.Sesion.Id)}&participante={Uri.EscapeDataString(estado.Participante!.Id)}");
        }
        finally
        {
            _enviando = false;
            if (_entrarBtn is not null) _entrarBtn.IsEnabled = _codigo.Length == 6;
        }
    }

    private void EsperarAdmision(string sesionId, string participanteId)
    {
        _esperaTimer ??= Dispatcher.CreateTimer();
        _esperaTimer.Interval = TimeSpan.FromSeconds(2);
        _esperaTimer.Tick -= OnEsperaTick;
        _esperaTimer.Tick += OnEsperaTick;
        _esperaTimer.Start();

        async void OnEsperaTick(object? s, EventArgs e)
        {
            var estado = await Sesion.Aula.EstadoAsync(sesionId, participanteId);
            if (estado?.Participante is null) return;
            if (estado.Participante.Admitido)
            {
                _esperaTimer.Stop();
                await Shell.Current.GoToAsync($"clase-siguiendo?sesion={Uri.EscapeDataString(sesionId)}&participante={Uri.EscapeDataString(participanteId)}");
            }
            else if (estado.Participante.Estado is "rechazado" or "expulsado")
            {
                _esperaTimer.Stop();
                AvisoHost.Clear();
                AvisoHost.Add(Ds.Alerta_("No puedes entrar por ahora", "Habla con tu profesor para volver a la clase.", Ds.PeligroSuave, Color.FromArgb("#8A1C1F")));
                Sesion.OlvidarClase();
            }
        }
    }

    private async void OnVolver(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");
}
