using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;
using Microsoft.Maui.Layouts;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// P3 · Clase en curso: PAN-001 y PAN-022 en una sola superficie táctil. El profesor ve lo que
/// se proyecta y lo controla desde aquí: código de unión, conectados, secuencia de la lección,
/// proyección (el selector), y la barra de controles (bloquear, seguimiento, lanzar actividad,
/// aviso, terminar). La sesión se refresca cada 3 s (BR-049 pide ≤ 3 s en las tabletas; el canal
/// en vivo llegará con Q-51). Nada exige teclado: los avisos son frases prehechas.
///
/// Dos cosas distintas para el profesor, aunque las dos «envíen algo a las tabletas»: el selector
/// (lo que se proyecta; cambia muchas veces por clase, no espera confirmación) y el lanzamiento
/// (una actividad que las tabletas confirman y responden). Desde el 2026-09-28 la lista de
/// participantes muestra la tableta de cada uno y permite bloquearla o desbloquearla (MOD-009):
/// una tableta bloqueada no recibe lanzamientos y consta en «excluidos».
/// </summary>
[QueryProperty(nameof(SesionId), "sesion")]
public partial class ClaseSesionPage : ContentPage
{
    private static readonly string[] Frases = ["Miren al frente", "Dos minutos", "Guarden lo que llevan", "Levanten la mano si terminaron", "Vamos a cerrar"];
    private static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");

    private IDispatcherTimer? _temporizador;
    private SesionDeClase? _sesion;
    private VistaCurso? _vista;
    private string? _selectorPintado;
    private bool _refrescando;
    private Button? _bloqueoBtn, _seguimientoBtn, _actividadBtn, _avisoBtn, _terminarBtn;
    private readonly Button _participantesBtn;

    public string SesionId { get; set; } = string.Empty;

    public ClaseSesionPage()
    {
        InitializeComponent();
        Proyeccion.PuedeNavegar = true;
        Proyeccion.Escala = 1.15;
        Proyeccion.Absoluta = ruta => Sesion.Aula.Absoluta(ruta);
        Proyeccion.UnidadPedida += async (_, unidad) => { if (Proyeccion.Objeto is { } o) await ProyectarAsync(o.ObjetoRef, unidad); };
        // El botón de participantes se fabrica con el kit para compartir relieve, bisel y hundimiento con la barra de controles.
        _participantesBtn = Ds.Boton("Participantes", Ds.Rango.Secondary, OnParticipantes, 56);
        _participantesBtn.FontSize = 16;
        ParticipantesSlot.Content = Ds.Capsula(_participantesBtn);
        PintarControles();
        foreach (var frase in Frases)
        {
            var b = Ds.Boton(frase, Ds.Rango.Secondary, async (_, _) => await AvisarAsync(frase), 64);
            b.Margin = new Thickness(0, 0, 10, 10);
            FrasesHost.Add(Ds.Capsula(b));
        }
        var cerrarAviso = Ds.Boton("Cerrar", Ds.Rango.Quiet, (_, _) => AvisoPanel.IsVisible = false, 64);
        FrasesHost.Add(cerrarAviso);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await RefrescarAsync();
        _temporizador ??= Dispatcher.CreateTimer();
        _temporizador.Interval = TimeSpan.FromSeconds(3);
        _temporizador.Tick -= OnTick;
        _temporizador.Tick += OnTick;
        _temporizador.Start();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _temporizador?.Stop();
    }

    private async void OnTick(object? sender, EventArgs e) => await RefrescarAsync();

    // ------------------------------------------------------------- refresco

    private async Task RefrescarAsync()
    {
        if (_refrescando || string.IsNullOrWhiteSpace(SesionId)) return;
        _refrescando = true;
        try
        {
            var aula = Sesion.Aula;
            var sesion = await aula.SesionAsync(SesionId);
            if (sesion is null)
            {
                Conexion("Sin señal", Ds.Peligro);
                HabilitarControles(false);
                return;
            }
            Conexion(sesion.Estado == "suspendida" ? "Clase suspendida" : "Conectado", sesion.Estado == "suspendida" ? Ds.Alerta : Ds.Exito);
            var primeraVez = _sesion is null;
            _sesion = sesion;
            if (sesion.Estado is "cerrada" or "archivada")
            {
                _temporizador?.Stop();
                Sesion.ClaseAbiertaId = null;
                await Shell.Current.GoToAsync($"clase-cierre?sesion={Uri.EscapeDataString(sesion.Id)}");
                return;
            }
            if (_vista is null && !string.IsNullOrWhiteSpace(sesion.CursoRef))
            {
                _vista = await aula.CursoAsync(sesion.CursoRef!, docente: true);
                PintarSecuencia();
            }
            else if (primeraVez) PintarSecuencia();

            CodigoLabel.Text = sesion.CodigoUnion ?? "······";
            ConectadosLabel.Text = (sesion.Conteo?.Conectados ?? 0).ToString();
            LeccionLabel.Text = sesion.LeccionRotulo ?? sesion.CursoRotulo ?? "Clase libre";
            CursoLabel.Text = string.Join(" · ", new[] { sesion.CursoRotulo, sesion.Estado == "suspendida" ? "suspendida · mismo código" : null }.Where(x => !string.IsNullOrWhiteSpace(x)));
            HabilitarControles(sesion.Estado == "abierta");
            PintarEstadoControles(sesion);
            PintarSelector(sesion.Selector);
            PintarActividad(sesion);
            if (ParticipantesPanel.IsVisible) PintarParticipantes(sesion);
            var bloqueadas = sesion.Participantes?.Count(p => p.Admitido && p.TabletaBloqueada) ?? 0;
            _participantesBtn.Text = sesion.Conteo is { Esperando: > 0 } c ? $"Participantes · {c.Esperando} esperando"
                : bloqueadas > 0 ? $"Participantes · {bloqueadas} tableta{(bloqueadas == 1 ? "" : "s")} bloqueada{(bloqueadas == 1 ? "" : "s")}"
                : "Participantes";
        }
        finally { _refrescando = false; }
    }

    /// <summary>El chip va sobre glass chrome: el punto lleva el color semántico y el fondo su versión suave; el texto queda en tinta.</summary>
    private void Conexion(string texto, Color color)
    {
        ConexionLabel.Text = texto;
        ConexionPunto.Fill = new SolidColorBrush(color);
        ConexionChip.BackgroundColor = color == Ds.Exito ? Ds.ExitoSuave : color == Ds.Peligro ? Ds.PeligroSuave : Ds.AlertaSuave;
    }

    // ------------------------------------------------------------- secuencia

    private void PintarSecuencia()
    {
        SecuenciaHost.Clear();
        if (_vista is null || _sesion is null)
        {
            SecuenciaHost.Add(Ds.Secundario(_sesion?.ViaOrigen == "libre" ? "Clase libre: proyecta desde el curso que quieras." : "Sin curso.", 15));
            return;
        }
        var lecciones = string.IsNullOrWhiteSpace(_sesion.LeccionRef) ? _vista.Lecciones : _vista.Lecciones.Where(l => l.LeccionRef == _sesion.LeccionRef).ToList();
        foreach (var leccion in lecciones)
        {
            if (lecciones.Count > 1) SecuenciaHost.Add(Ds.Secundario(leccion.Titulo, 14));
            foreach (var objeto in leccion.Objetos ?? [])
                SecuenciaHost.Add(FilaObjeto(objeto));
        }
    }

    private View FilaObjeto(ObjetoAula objeto)
    {
        var seleccionado = _sesion?.Selector?.ObjetoRef == objeto.ObjetoRef;
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(40), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
        fila.Add(Ds.IconoCategoria(objeto.Componente, 40), 0, 0);
        var textos = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        textos.Add(Ds.Cuerpo(objeto.Titulo, 15));
        textos.Add(Ds.Secundario(string.Join(" · ", new[] { objeto.ComponenteLegible, objeto.DuracionTexto, objeto.FueraDeAlcance ? "lo aplica MOD-010" : null }.Where(x => !string.IsNullOrWhiteSpace(x))), 13));
        fila.Add(textos, 1, 0);
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(fila);
        if (seleccionado && objeto.Unidades.Count > 0)
        {
            var laminas = new FlexLayout { Wrap = FlexWrap.Wrap, Direction = FlexDirection.Row, JustifyContent = FlexJustify.Start, AlignItems = FlexAlignItems.Center };
            foreach (var u in objeto.Unidades)
            {
                var activa = _sesion?.Selector?.UnidadRef == u.UnidadRef;
                // Ficha de lámina en relieve: degradado, bisel y una sombra corta (la tarjeta recorta lo que sobresale).
                var chip = new Border
                {
                    Background = Ds.Degradado(activa ? Ds.Rojo : Colors.White), Stroke = Ds.Bisel(), StrokeThickness = 1,
                    WidthRequest = 46, HeightRequest = 46, Margin = new Thickness(0, 0, 8, 8),
                    StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioControl },
                    Shadow = new Shadow { Brush = new SolidColorBrush(activa ? Ds.Rojo : Ds.Tinta), Offset = new Point(0, 4), Radius = 10, Opacity = activa ? 0.35f : 0.12f },
                    Content = new Label { Text = u.Indice.ToString(), FontSize = 17, FontFamily = Ds.FuenteMedia, TextColor = activa ? Colors.White : Ds.Tinta, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
                };
                Ds.Tocable(chip, () => ProyectarAsync(objeto.ObjetoRef, u.UnidadRef));
                laminas.Add(chip);
            }
            pila.Add(laminas);
        }
        var tarjeta = new Border
        {
            BackgroundColor = seleccionado ? Ds.VioletaSuave : Colors.Transparent,
            Stroke = new SolidColorBrush(seleccionado ? Ds.CatClaseEnVivo : Colors.Transparent), StrokeThickness = seleccionado ? 2 : 0,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Padding = new Thickness(10, 8), Content = pila,
            Opacity = objeto.FueraDeAlcance ? 0.6 : 1,
        };
        if (!objeto.FueraDeAlcance) Ds.Tocable(tarjeta, () => ProyectarAsync(objeto.ObjetoRef, null));
        return tarjeta;
    }

    // -------------------------------------------------------------- selector

    private void PintarSelector(SelectorAula? selector)
    {
        if (selector is null || string.IsNullOrWhiteSpace(selector.ObjetoRef))
        {
            if (_selectorPintado is not null) { Proyeccion.MostrarVacio(); _selectorPintado = null; PintarSecuencia(); }
            return;
        }
        var llave = $"{selector.ObjetoRef}|{selector.UnidadRef}";
        if (llave == _selectorPintado) return;
        var objeto = _vista?.Objeto(selector.ObjetoRef!);
        if (objeto is null)
        {
            Proyeccion.MostrarVacio("Objeto fuera de este curso", selector.Rotulo ?? selector.ObjetoRef!);
        }
        else Proyeccion.Mostrar(objeto, string.IsNullOrWhiteSpace(selector.UnidadRef) ? null : selector.UnidadRef);
        _selectorPintado = llave;
        PintarSecuencia();
        PintarEstadoControles(_sesion);
    }

    private async Task ProyectarAsync(string objetoRef, string? unidadRef)
    {
        if (_sesion is null) return;
        var selector = await Sesion.Aula.ProyectarAsync(_sesion.Id, Sesion.ProfesorId, objetoRef, unidadRef);
        if (selector is null)
        {
            await Aviso("No se pudo proyectar", Sesion.Aula.UltimoMotivo);
            return;
        }
        _sesion = _sesion with { Selector = selector };
        PintarSelector(selector);
    }

    // -------------------------------------------------------------- controles

    private void PintarControles()
    {
        ControlesHost.Clear();
        _bloqueoBtn = Ds.Interruptor("Bloquear pantallas", false, Ds.Alerta, async (_, _) => await ControlAsync("bloqueo", !(_sesion?.PantallasBloqueadas ?? false)));
        _seguimientoBtn = Ds.Interruptor("Seguimiento", true, Ds.Info, async (_, _) => await ControlAsync("seguimiento", !(_sesion?.Seguimiento ?? true)));
        _actividadBtn = Ds.Boton("Lanzar actividad", Ds.Rango.Secondary, async (_, _) => await LanzarOCerrarAsync(), 64);
        _avisoBtn = Ds.Boton("Aviso", Ds.Rango.Secondary, (_, _) => AvisoPanel.IsVisible = !AvisoPanel.IsVisible, 64);
        _terminarBtn = Ds.Boton("Terminar clase", Ds.Rango.Destructive, async (_, _) => await TerminarAsync(), 64);
        ControlesHost.Add(Ds.Capsula(_bloqueoBtn));
        ControlesHost.Add(Ds.Capsula(_seguimientoBtn));
        ControlesHost.Add(Ds.Capsula(_actividadBtn));
        ControlesHost.Add(Ds.Capsula(_avisoBtn));
        ControlesHost.Add(new BoxView { WidthRequest = 24, Color = Colors.Transparent });
        ControlesHost.Add(Ds.Capsula(_terminarBtn));
    }

    private void HabilitarControles(bool activo)
    {
        foreach (var b in new[] { _bloqueoBtn, _seguimientoBtn, _actividadBtn, _avisoBtn })
            if (b is not null) Ds.Habilitar(b, activo);
        if (_terminarBtn is not null) Ds.Habilitar(_terminarBtn, _sesion is not null);
    }

    private void PintarEstadoControles(SesionDeClase? s)
    {
        if (s is null) return;
        if (_bloqueoBtn is not null)
        {
            Ds.PintarInterruptor(_bloqueoBtn, s.PantallasBloqueadas, Ds.Alerta);
            _bloqueoBtn.Text = s.PantallasBloqueadas ? "Pantallas bloqueadas · liberar" : "Bloquear pantallas";
        }
        if (_seguimientoBtn is not null)
        {
            Ds.PintarInterruptor(_seguimientoBtn, s.Seguimiento, Ds.Info);
            _seguimientoBtn.Text = s.Seguimiento ? "Seguimiento activo" : "Navegación libre";
        }
        if (_actividadBtn is not null)
        {
            // Un solo botón para el lanzamiento (CAP-040): lo que está en el selector se envía a las tabletas.
            // Si es una actividad, se lanza como actividad (entregas, intentos); si es una lámina, lectura o
            // laboratorio, se envía como recurso para que cada tableta lo abra y lo recorra a su ritmo.
            // Con una actividad abierta el mismo botón cierra la recepción.
            var abierta = s.ActividadAbierta;
            var selectorEsActividad = s.Selector?.ObjetoTipo == "activity";
            var haySelector = !string.IsNullOrWhiteSpace(s.Selector?.ObjetoRef);
            _actividadBtn.Text = abierta is not null ? "Cerrar recepción" : selectorEsActividad ? "Lanzar actividad" : "Enviar a tabletas";
            var puede = s.Estado == "abierta" && (abierta is not null || haySelector);
            Ds.Habilitar(_actividadBtn, puede);
        }
    }

    private async Task ControlAsync(string tipo, bool activo)
    {
        if (_sesion is null) return;
        if (!await Sesion.Aula.ControlAsync(_sesion.Id, Sesion.ProfesorId, tipo, activo))
        {
            await Aviso("No se pudo cambiar el control", Sesion.Aula.UltimoMotivo);
            return;
        }
        _sesion = tipo == "bloqueo" ? _sesion with { PantallasBloqueadas = activo } : _sesion with { Seguimiento = activo };
        PintarEstadoControles(_sesion);
    }

    private async Task LanzarOCerrarAsync()
    {
        if (_sesion is null) return;
        var aula = Sesion.Aula;
        if (_sesion.ActividadAbierta is { } abierta)
        {
            var cerrada = await aula.CerrarDistribucionAsync(_sesion.Id, Sesion.ProfesorId, abierta.Id);
            if (cerrada is null) await Aviso("No se pudo cerrar la recepción", aula.UltimoMotivo);
            await RefrescarAsync();
            return;
        }
        if (_sesion.Selector?.ObjetoRef is not { } objetoRef || string.IsNullOrWhiteSpace(objetoRef)) return;
        var esActividad = _sesion.Selector.ObjetoTipo == "activity";
        // Un recurso nuevo sustituye al anterior en las tabletas: se retira el que siga abierto antes de enviar.
        if (!esActividad && _sesion.RecursoAbierto is { } anterior)
            await aula.CerrarDistribucionAsync(_sesion.Id, Sesion.ProfesorId, anterior.Id);
        // El lanzamiento va a todo el grupo admitido; el backend deja fuera las tabletas bloqueadas y lo dice en «excluidos».
        var distribucion = await aula.DistribuirAsync(_sesion.Id, Sesion.ProfesorId,
            new DistribuirSolicitud(esActividad ? "actividad" : "recurso", objetoRef, null, _sesion.Selector.Rotulo, false));
        if (distribucion is null)
        {
            var error = aula.UltimoError;
            var titulo = error?.Codigo == "sin_participantes_admitidos"
                ? (error.Texto("excluidos_bloqueados") is null && error.Extra is { } e && e.TryGetProperty("excluidos_bloqueados", out var ex) && ex.GetArrayLength() > 0
                    ? "Todas las tabletas conectadas están bloqueadas" : "Todavía no hay tabletas conectadas")
                : esActividad ? "No se pudo lanzar la actividad" : "No se pudo enviar a las tabletas";
            await Aviso(titulo, error?.Detalle);
            return;
        }
        await RefrescarAsync();
    }

    /// <summary>Retirar de las tabletas el recurso enviado: cierra la distribución; las tabletas vuelven a seguir el selector.</summary>
    private async Task RetirarRecursoAsync(DistribucionAula recurso)
    {
        if (_sesion is null) return;
        if (await Sesion.Aula.CerrarDistribucionAsync(_sesion.Id, Sesion.ProfesorId, recurso.Id) is null)
            await Aviso("No se pudo retirar el recurso", Sesion.Aula.UltimoMotivo);
        await RefrescarAsync();
    }

    private void PintarActividad(SesionDeClase s)
    {
        ActividadHost.Clear();
        // El recurso enviado a las tabletas (si lo hay) y la actividad en curso (si la hay) se ven en el mismo rincón.
        if (s.RecursoAbierto is { } recurso)
        {
            var pilaRecurso = new VerticalStackLayout { Spacing = 8 };
            pilaRecurso.Add(Ds.Pildora("Enviado a las tabletas", Ds.Info));
            pilaRecurso.Add(Ds.Cuerpo(recurso.Rotulo ?? recurso.ObjetoRef ?? "Recurso", 16));
            var totalR = recurso.Entregas?.Total ?? 0;
            var abiertasR = recurso.Entregas?.Entregadas ?? 0;
            pilaRecurso.Add(Ds.Secundario(totalR == 0 ? "Sin destinatarios" : $"{abiertasR} de {totalR} tabletas lo abrieron", 14));
            if (recurso.Excluidos > 0)
                pilaRecurso.Add(Ds.Pildora(recurso.Excluidos == 1 ? "1 tableta bloqueada no lo recibió" : $"{recurso.Excluidos} tabletas bloqueadas no lo recibieron", Ds.PeligroSuave, TintaPeligro));
            var retirar = Ds.Boton("Retirar de las tabletas", Ds.Rango.Quiet, async (_, _) => await RetirarRecursoAsync(recurso), 48);
            retirar.FontSize = 14;
            retirar.HorizontalOptions = LayoutOptions.Start;
            pilaRecurso.Add(Ds.Capsula(retirar));
            ActividadHost.Add(Ds.Tarjeta(pilaRecurso, Ds.RadioInterno, new Thickness(14), Ds.InfoSuave));
        }
        var abierta = s.ActividadAbierta;
        if (abierta is null) return;
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(Ds.Pildora("Actividad en curso", Ds.CatQuiz));
        pila.Add(Ds.Cuerpo(abierta.Rotulo ?? abierta.ObjetoRef ?? "Actividad", 16));
        var total = abierta.Entregas?.Total ?? 0;
        var entregadas = abierta.Entregas?.Entregadas ?? 0;
        pila.Add(new ProgressBar { Progress = total == 0 ? 0 : (double)entregadas / total, ProgressColor = Ds.CatQuiz });
        pila.Add(Ds.Secundario(total == 0 ? "Sin destinatarios" : $"{entregadas} de {total} tabletas la recibieron", 14));
        if (abierta.Excluidos > 0)
            pila.Add(Ds.Pildora(abierta.Excluidos == 1 ? "1 tableta bloqueada no la recibió" : $"{abierta.Excluidos} tabletas bloqueadas no la recibieron", Ds.PeligroSuave, TintaPeligro));
        if (!string.IsNullOrEmpty(abierta.ReglasTexto)) pila.Add(Ds.Secundario(abierta.ReglasTexto, 13));
        ActividadHost.Add(Ds.Tarjeta(pila, Ds.RadioInterno, new Thickness(14), Ds.ExitoSuave));
    }

    private async Task AvisarAsync(string texto)
    {
        if (_sesion is null) return;
        AvisoPanel.IsVisible = false;
        if (!await Sesion.Aula.AvisarAsync(_sesion.Id, Sesion.ProfesorId, texto, null))
            await Aviso("No se pudo enviar el aviso", Sesion.Aula.UltimoMotivo);
    }

    private async Task TerminarAsync()
    {
        if (_sesion is null) return;
        var aula = Sesion.Aula;
        if (!await DisplayAlertAsync("¿Terminar la clase?", "Se libera la sala y se consolida el resumen. Una clase cerrada no se reabre.", "Terminar", "Seguir en clase")) return;
        var cerrada = await aula.CerrarAsync(_sesion.Id, Sesion.ProfesorId, forzar: false);
        if (cerrada is null && aula.UltimoError?.Codigo == "actividades_abiertas")
        {
            var forzar = await DisplayAlertAsync("Hay una actividad abierta", "Algunos alumnos siguen respondiendo. Si cierras ahora, se entrega lo que llevan.", "Terminar de todos modos", "Esperar");
            if (!forzar) return;
            cerrada = await aula.CerrarAsync(_sesion.Id, Sesion.ProfesorId, forzar: true);
        }
        if (cerrada is null)
        {
            await Aviso("No se pudo cerrar la clase", aula.UltimoMotivo);
            return;
        }
        _temporizador?.Stop();
        Sesion.ClaseAbiertaId = null;
        await Shell.Current.GoToAsync($"clase-cierre?sesion={Uri.EscapeDataString(cerrada.Id)}");
    }

    // ---------------------------------------------------------- participantes

    private void OnParticipantes(object? sender, EventArgs e)
    {
        ParticipantesPanel.IsVisible = !ParticipantesPanel.IsVisible;
        if (ParticipantesPanel.IsVisible && _sesion is not null) PintarParticipantes(_sesion);
    }

    private void PintarParticipantes(SesionDeClase s)
    {
        ParticipantesHost.Clear();
        var lista = s.Participantes ?? [];
        if (lista.Count == 0)
        {
            ParticipantesHost.Add(Ds.Secundario("Todavía nadie ha escrito el código.", 16));
            return;
        }
        foreach (var p in lista.OrderBy(p => p.Estado == "esperando" ? 0 : p.Admitido ? 1 : 2).ThenBy(p => p.Nombre))
        {
            // Dos renglones en el ancho del panel (420): arriba el nombre con su estado y su tableta, abajo los botones.
            // Así el texto no compite con dos botones por el mismo ancho y la píldora de bloqueo cabe entera.
            var fila = new Grid
            {
                ColumnDefinitions = [new ColumnDefinition(48), new ColumnDefinition(GridLength.Star)],
                RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Auto)],
                ColumnSpacing = 12, RowSpacing = 8,
            };
            var avatar = new Border
            {
                BackgroundColor = p.Admitido ? Ds.Exito : p.Estado == "esperando" ? Ds.Alerta : Ds.TintaSuave, StrokeThickness = 0, WidthRequest = 48, HeightRequest = 48,
                StrokeShape = new RoundRectangle { CornerRadius = 999 }, VerticalOptions = LayoutOptions.Start,
                Content = new Label { Text = p.Iniciales, FontFamily = Ds.FuenteMedia, TextColor = p.Estado == "esperando" ? Ds.Tinta : Colors.White, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
            };
            fila.Add(avatar, 0, 0);
            Grid.SetRowSpan(avatar, 2);
            // Nombre, estado y la tableta con la que entró (MOD-009); si está bloqueada, se ve de un vistazo.
            var textos = new VerticalStackLayout { VerticalOptions = LayoutOptions.Center, Spacing = 2 };
            textos.Add(Ds.Cuerpo(p.Nombre, 16));
            textos.Add(Ds.Secundario(string.Join(" · ", new[] { p.EstadoLegible, p.AdmisionNominal ? "invitado" : null, string.IsNullOrWhiteSpace(p.Dispositivo) ? null : p.Dispositivo }.Where(x => x is not null)), 13));
            if (p.TabletaBloqueada)
            {
                var pildora = Ds.Pildora("Tableta bloqueada · sin lanzamientos", Ds.PeligroSuave, TintaPeligro, 13);
                pildora.HorizontalOptions = LayoutOptions.Start;
                pildora.Margin = new Thickness(0, 4, 0, 0);
                textos.Add(pildora);
            }
            fila.Add(textos, 1, 0);
            var acciones = new HorizontalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Start };
            if (p.TieneTableta)
            {
                var bloqueo = Ds.Boton(p.TabletaBloqueada ? "Desbloquear" : "Bloquear tableta", Ds.Rango.Quiet, async (_, _) => await BloqueoTabletaAsync(p), 52);
                bloqueo.FontSize = 15;
                acciones.Add(Ds.Capsula(bloqueo));
            }
            Button accion = p.Estado == "esperando"
                ? Ds.Boton("Admitir", Ds.Rango.Secondary, async (_, _) => await ParticipanteAsync(p.Id, "admitir"), 52)
                : p.Admitido
                    ? Ds.Boton("Expulsar", Ds.Rango.Quiet, async (_, _) => { if (await DisplayAlertAsync("¿Expulsar de la clase?", $"{p.Nombre} saldrá de la sesión. Sus respuestas se conservan.", "Expulsar", "Cancelar")) await ParticipanteAsync(p.Id, "expulsar"); }, 52)
                    : Ds.Boton("Readmitir", Ds.Rango.Quiet, async (_, _) => await ParticipanteAsync(p.Id, "admitir"), 52);
            accion.FontSize = 15;
            acciones.Add(Ds.Capsula(accion));
            fila.Add(acciones, 1, 1);
            ParticipantesHost.Add(fila);
            ParticipantesHost.Add(Ds.Separador());
        }
    }

    private async Task ParticipanteAsync(string participanteId, string accion)
    {
        if (_sesion is null) return;
        if (await Sesion.Aula.ParticipanteAsync(_sesion.Id, Sesion.ProfesorId, participanteId, accion) is null)
        {
            var error = Sesion.Aula.UltimoError;
            await Aviso(error?.Codigo == "dispositivo_bloqueado" ? "La tableta está bloqueada" : "No se pudo aplicar", error?.Detalle ?? Sesion.Aula.UltimoMotivo);
        }
        await RefrescarAsync();
    }

    /// <summary>Bloquear o desbloquear la tableta del participante (MOD-009). Reversible; el alumno no pierde nada.</summary>
    private async Task BloqueoTabletaAsync(ParticipanteAula p)
    {
        if (_sesion is null || !p.TieneTableta) return;
        var api = Sesion.Dispositivos;
        var resultado = p.TabletaBloqueada
            ? await api.DesbloquearAsync(p.DispositivoId!, Sesion.ProfesorId)
            : await api.BloquearAsync(p.DispositivoId!, Sesion.ProfesorId, "desde la clase");
        if (resultado is null) await Aviso(p.TabletaBloqueada ? "No se pudo desbloquear la tableta" : "No se pudo bloquear la tableta", api.UltimoMotivo);
        await RefrescarAsync();
        if (ParticipantesPanel.IsVisible && _sesion is not null) PintarParticipantes(_sesion);
    }

    private Task Aviso(string titulo, string? detalle) => DisplayAlertAsync(titulo, detalle ?? "Sin detalle.", "Entendido");
}
