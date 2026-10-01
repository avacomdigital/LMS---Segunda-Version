using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// El expediente de un intento (MOD-010 · PAN-062): quién es, su tableta, su nivel, el cronómetro, qué pasó y a qué hora, y lo que su tableta informó del
/// bloqueo. Mientras el alumno presenta es SOLO LECTURA: ninguna decisión vive aquí. Cuando el intento ya se entregó, esta misma pantalla es el único lugar donde
/// el profesor revisa las respuestas, puntúa lo que la biblioteca no califica sola, publica la calificación, la recalifica si quedó pendiente y —como decisión
/// humana, con motivo y con su nombre— anula el intento (INV-018). Después de anular, la pantalla dice siempre «Anulado por … · motivo».
///
/// Los incidentes llevan una etiqueta de gravedad (informativa, atención, importante) en tonos neutros y ámbar: se registran, no se castigan (BR-077).
/// Mientras el intento sigue vivo la pantalla se actualiza sola cada 5 s y su cronómetro avanza cada segundo.
/// </summary>
[QueryProperty(nameof(IntentoId), "intento")]
public partial class ExamenExpedientePage : ContentPage
{
    private const int SondeoMs = 5000;

    public string IntentoId { get; set; } = string.Empty;

    private ExpedienteDeIntento? _exp;
    private ExpedienteExtra? _extra;
    private DispositivoAula? _tableta;
    private string _firma = string.Empty;
    private bool _visible, _cargando;
    private int _versionAviso;
    private IDispatcherTimer? _sondeo, _segundero;
    private Label? _relojLabel;
    private long _relojLeidoEn;
    private readonly HojaDeOpciones _hoja = new();

    private static string Actor => Sesion.ProfesorId;

    public ExamenExpedientePage()
    {
        InitializeComponent();
        Raiz.Add(_hoja);
        AccionesHost.Add(ExamenUi.Accion("‹  Volver al panel", Ds.Rango.Secondary, () => Shell.Current.GoToAsync(".."), 220, "expediente-volver").Vista);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            await CargarAsync(forzar: true);
            if (!_visible) return;
            _sondeo ??= Dispatcher.CreateTimer();
            _sondeo.Interval = TimeSpan.FromMilliseconds(SondeoMs);
            _sondeo.Tick -= OnSondeo;
            _sondeo.Tick += OnSondeo;
            _sondeo.Start();
            _segundero ??= Dispatcher.CreateTimer();
            _segundero.Interval = TimeSpan.FromSeconds(1);
            _segundero.Tick -= OnSegundo;
            _segundero.Tick += OnSegundo;
            _segundero.Start();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ExamenExpedientePage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
        _sondeo?.Stop();
        _segundero?.Stop();
    }

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var ancho = Math.Max(560, Math.Min(1280, Width - 92));
        Cabecera.WidthRequest = AvisoHost.WidthRequest = ContenidoHost.WidthRequest = ancho;
    }

    private async void OnSondeo(object? sender, EventArgs e)
    {
        try
        {
            // Un intento ya entregado sólo cambia por lo que el profesor hace aquí, y eso ya refresca: no hace falta preguntar cada 5 s.
            if (_exp is { Intento.Estado: var estado } && EstadosIntento.Terminado(estado)) return;
            await CargarAsync(forzar: false);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ExamenExpedientePage.OnSondeo", ex); }
    }

    /// <summary>El cronómetro avanza solo entre dos lecturas, con la hora que dio el nodo.</summary>
    private void OnSegundo(object? sender, EventArgs e)
    {
        if (_relojLabel is null || _exp?.Reloj is not { Corriendo: true, RestanteMs: { } restante }) return;
        _relojLabel.Text = $"Quedan {ExamenTexto.Reloj(restante - (Environment.TickCount64 - _relojLeidoEn))}";
    }

    // ----------------------------------------------------------------------------------------------- carga

    private async Task CargarAsync(bool forzar)
    {
        if (string.IsNullOrWhiteSpace(IntentoId) || _cargando) return;
        _cargando = true;
        try
        {
            var api = Sesion.Evaluacion;
            var exp = await api.ExpedienteAsync(Actor, IntentoId);
            if (!_visible) return;
            if (exp is null)
            {
                if (_exp is not null) return;   // un tropiezo del sondeo no borra lo que ya se ve
                PintarSinExpediente(api.UltimoError, api.UltimoMotivo);
                return;
            }
            RelojNodo.Aprender(exp.ServidorEn);
            var extra = await ExamenExtra.Api.ExpedienteAsync(Actor, IntentoId);
            if (extra?.Intento.DispositivoId is { Length: > 0 } dispositivoId && _tableta?.Id != dispositivoId)
            {
                var inventario = await Sesion.Dispositivos.ListarAsync(true);
                _tableta = inventario?.FirstOrDefault(d => d.Id == dispositivoId);
            }
            if (_verRevision && EstadosIntento.Terminado(exp.Intento.Estado))
                _revision = await api.RevisionAsync(Actor, IntentoId);

            // Los segundos del cronómetro no cuentan como cambio: lo que se ve es lo que pasó.
            var firma = JsonSerializer.Serialize(new { e = exp with { ServidorEn = 0, Reloj = exp.Reloj is null ? null : exp.Reloj with { RestanteMs = null, ServidorEn = 0 } }, x = extra, r = _revision, v = _verRevision });
            if (!forzar && firma == _firma)
            {
                _relojLeidoEn = Environment.TickCount64;
                _exp = exp;
                return;
            }
            _firma = firma;
            _exp = exp;
            _extra = extra;
            _relojLeidoEn = Environment.TickCount64;
            Pintar(exp);
        }
        finally { _cargando = false; }
    }

    private void PintarSinExpediente(ErrorAula? error, string? motivo)
    {
        TituloLabel.Text = "No se pudo leer el expediente";
        SubtituloLabel.Text = string.Empty;
        PastillasHost.Clear();
        ContenidoHost.Clear();
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Ds.Secundario(ExamenTexto.Error(error, motivo), 16));
        pila.Add(ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, () => CargarAsync(forzar: true), 170, "expediente-reintentar").Vista);
        ContenidoHost.Add(ExamenUi.Tarjeta(pila));
    }

    // ----------------------------------------------------------------------------------------------- pintar

    private void Pintar(ExpedienteDeIntento exp)
    {
        var y = Desplazable.ScrollY;
        var i = exp.Intento;
        TituloLabel.Text = i.AlumnoRotulo ?? "Alumno";
        SubtituloLabel.Text = $"Intento {i.Numero}";
        PastillasHost.Clear();
        PastillasHost.Add(ExamenUi.PildoraEnFila(ExamenTexto.EstadoIntento(i.Estado), ExamenTexto.TonoIntento(i.Estado), 14));
        PastillasHost.Add(ExamenUi.PildoraEnFila($"Nivel {Niveles.Rotulo(i.NivelEfectivo)}", Tono.Neutro, 14));
        if (i.FueraDePlazo) PastillasHost.Add(ExamenUi.PildoraEnFila("Fuera de plazo", Tono.Ambar, 14));
        if (i.EnvioTardio == "pendiente_decision") PastillasHost.Add(ExamenUi.PildoraEnFila("Envío tardío: espera tu decisión", Tono.Violeta, 14));
        else if (i.EnvioTardio == "aceptado") PastillasHost.Add(ExamenUi.PildoraEnFila("Envío tardío aceptado", Tono.Exito, 14));
        else if (i.EnvioTardio == "descartado") PastillasHost.Add(ExamenUi.PildoraEnFila("Envío tardío descartado", Tono.Gris, 14));
        if (_extra?.Intento.CalificacionPendiente == true) PastillasHost.Add(ExamenUi.PildoraEnFila("Calificación pendiente", Tono.Ambar, 14));
        if (exp.ResumenIncidentes.Total > 0)
            PastillasHost.Add(ExamenUi.PildoraEnFila(ExamenTexto.Plural(exp.ResumenIncidentes.Total, "aviso", "avisos"),
                exp.ResumenIncidentes.Alta > 0 ? Tono.AmbarFuerte : exp.ResumenIncidentes.Atencion > 0 ? Tono.Ambar : Tono.Neutro, 14));

        ContenidoHost.Clear();
        _relojLabel = null;
        if (i.Estado == EstadosIntento.Anulado) ContenidoHost.Add(BannerDeAnulacion(i));
        ContenidoHost.Add(Resumen(exp));
        if (_extra?.Bloqueo is { Resultado: { Length: > 0 } } bloqueo) ContenidoHost.Add(TarjetaDeBloqueo(bloqueo));
        ContenidoHost.Add(LineaDeTiempoView(exp));
        if (EstadosIntento.Terminado(i.Estado)) ContenidoHost.Add(Decisiones(exp));
        else ContenidoHost.Add(SoloLectura(i));
        if (_verRevision && EstadosIntento.Terminado(i.Estado)) ContenidoHost.Add(TarjetaDeRevision(exp));

        if (y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }

    /// <summary>Después de anular, la pantalla dice siempre quién lo hizo y por qué. En un tono neutro: es un hecho registrado, no una alarma.</summary>
    private static View BannerDeAnulacion(DatosDelExpediente i)
    {
        var motivo = string.IsNullOrWhiteSpace(i.MotivoAnulacion) ? "sin motivo" : i.MotivoAnulacion;
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(new Label { Text = $"Anulado por {ExamenTexto.Persona(i.AnuladoPor)} · {motivo}", FontFamily = Ds.FuenteMedia, FontSize = 19, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        pila.Add(Ds.Secundario("Anular es una decisión humana y queda registrada con nombre y motivo. El sistema nunca anula por sí solo.", 14));
        return ExamenUi.Tarjeta(pila, ExamenUi.FondoGris);
    }

    private View Resumen(ExpedienteDeIntento exp)
    {
        var i = exp.Intento;
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion("Resumen"));

        pila.Add(ExamenUi.Dato("Tableta", _tableta is { } t
            ? $"{t.NombreVisible} · declara {t.CapacidadLegible.ToLowerInvariant()}{(Niveles.Alcanza(t.CapacidadControl, i.NivelEfectivo) ? string.Empty : $" · no alcanza el nivel {Niveles.Rotulo(i.NivelEfectivo).ToLowerInvariant()}")}"
            : "Sin tableta conocida"));
        pila.Add(ExamenUi.Dato("Nivel con el que presenta", Niveles.Rotulo(i.NivelEfectivo)));
        if (i.IniciadoEn is { } inicio) pila.Add(ExamenUi.Dato("Empezó", $"a las {ExamenTexto.HoraCompleta(inicio)}"));
        pila.Add(ExamenUi.Dato("Avance", exp.Total > 0 ? $"{exp.Respondidas} de {exp.Total} respondidas" : "Todavía no empieza"));

        // El cronómetro sólo dice algo mientras el examen sigue abierto para el alumno; una vez entregado, queda el tiempo que usó.
        if (exp.Reloj is { } r && EstadosIntento.AceptaRespuestas(i.Estado))
        {
            string cronometro;
            if (r.RestanteMs is null) cronometro = "Sin límite de tiempo";
            else if (r.Corriendo) cronometro = $"Quedan {ExamenTexto.Reloj(r.RestanteMs)}";
            else cronometro = $"Detenido con {ExamenTexto.Reloj(r.RestanteMs)} por delante";
            var dato = ExamenUi.Dato("Cronómetro", cronometro);
            pila.Add(dato);
            if (r.Corriendo && r.RestanteMs is not null && dato is Grid g && g.Children.Count > 1 && g.Children[1] is Label etiqueta) _relojLabel = etiqueta;
        }
        if (exp.Reloj is { ConsumidoMs: > 0 } usado) pila.Add(ExamenUi.Dato("Tiempo usado", ExamenTexto.Duracion(usado.ConsumidoMs)));
        if (i.EntregadoEn is { } fin)
            pila.Add(ExamenUi.Dato("Entrega", $"a las {ExamenTexto.HoraCompleta(fin)}{(ExamenTexto.OrigenEntrega(i.OrigenEntrega) is { Length: > 0 } origen ? $" · {origen.ToLowerInvariant()}" : string.Empty)}"));
        if (i.Porcentaje is { } pct) pila.Add(ExamenUi.Dato("Resultado", ExamenTexto.Porcentaje(pct) + (i.Estado == EstadosIntento.EnRevision ? " de lo ya calificado" : string.Empty)));
        return ExamenUi.Tarjeta(pila);
    }

    private static View TarjetaDeBloqueo(BloqueoInformado b)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion("Bloqueo de la tableta"));
        var parcial = b.Resultado is ResultadosDeBloqueo.Parcial or ResultadosDeBloqueo.Fallido;
        pila.Add(ExamenUi.Pildora(ExamenTexto.BloqueoCompleto(b.Resultado), parcial ? Tono.Ambar : Tono.Exito, 14));
        if (b.Capas is { } capas)
        {
            string Si(bool v) => v ? "Sí" : "No";
            pila.Add(ExamenUi.Dato("Examen en pantalla completa", Si(capas.App)));
            pila.Add(ExamenUi.Dato("Capa del sistema", Si(capas.Sistema)));
            pila.Add(ExamenUi.Dato("Capturas de pantalla bloqueadas", Si(capas.Capturas)));
            pila.Add(ExamenUi.Dato("Otras pantallas cubiertas", Si(capas.Pantallas)));
        }
        if (!string.IsNullOrWhiteSpace(b.Motivo)) pila.Add(ExamenUi.Dato("Lo que dijo la tableta", b.Motivo!));
        if (b.InformadoEn is { } en)
            pila.Add(Ds.Secundario($"Informado a las {ExamenTexto.HoraCompleta(en)}." + (parcial ? " El examen siguió: un bloqueo parcial no invalida nada." : string.Empty), 13));
        return ExamenUi.Tarjeta(pila);
    }

    private static View LineaDeTiempoView(ExpedienteDeIntento exp)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion("Lo que pasó"));
        if (exp.LineaDeTiempo.Count == 0)
        {
            pila.Add(Ds.Secundario("Todavía no hay nada que contar: el alumno no ha empezado.", 15));
            return ExamenUi.Tarjeta(pila);
        }
        foreach (var l in exp.LineaDeTiempo)
        {
            var texto = l.Tipo switch
            {
                "entregado" => ExamenTexto.EntregaEnLinea(l.Origen, ExamenTexto.Dato(l.Detalle, "fuera_de_plazo") == "true"),
                "anulado" => $"Se anuló este intento. {ExamenTexto.Persona(ExamenTexto.Dato(l.Detalle, "por"))} · {ExamenTexto.Dato(l.Detalle, "motivo")}",
                "reactivado" => $"Reactivaste su examen{(ExamenTexto.DatoNumero(l.Detalle, "restante_ms") is { } restante ? $" (le quedaban {ExamenTexto.Reloj(restante)})" : string.Empty)}",
                _ => ExamenTexto.Incidente(l.Tipo, l.Detalle),
            };
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(96), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
            fila.Add(new Label { Text = ExamenTexto.HoraCompleta(l.En), FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.TintaSuave, VerticalOptions = LayoutOptions.Center }, 0, 0);
            fila.Add(new Label { Text = texto, FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, VerticalOptions = LayoutOptions.Center }, 1, 0);
            if (!string.IsNullOrWhiteSpace(l.Severidad))
                fila.Add(ExamenUi.Pildora(ExamenTexto.SeveridadLegible(l.Severidad), ExamenTexto.TonoSeveridad(l.Severidad), 12), 2, 0);
            pila.Add(fila);
        }
        return ExamenUi.Tarjeta(pila);
    }

    /// <summary>Mientras el alumno presenta, el expediente no ofrece ninguna decisión: se dice y se indica dónde están las que sí existen.</summary>
    private static View SoloLectura(DatosDelExpediente i)
    {
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(Ds.Secundario(
            i.Estado is EstadosIntento.Pausado or EstadosIntento.Restaurando
                ? "El examen de este alumno está en pausa. Para reactivarlo o cerrar su examen, usa el panel."
                : "Este expediente es sólo de lectura mientras el alumno presenta. Las decisiones sobre el intento aparecen cuando se entrega.", 14));
        return pila;
    }

    // ------------------------------------------------------------------------------------------------ avisos

    private void Avisar(string titulo, string? detalle, Tono tono)
    {
        AvisoHost.Clear();
        AvisoHost.Add(ExamenUi.Aviso(titulo, detalle, tono));
        var version = ++_versionAviso;
        if (tono is Tono.Exito or Tono.Info)
            Dispatcher.DispatchDelayed(TimeSpan.FromSeconds(9), () => { if (version == _versionAviso) AvisoHost.Clear(); });
    }
}
