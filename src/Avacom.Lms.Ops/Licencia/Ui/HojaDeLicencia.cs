using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Licencia.Ui;

/// <summary>
/// La hoja de la licencia: se abre SOBRE la pantalla «Licencia» (un velo tenue y una tarjeta en el tercio central de la ventana, de 1/6 a 5/6 de su alto, como la hoja de exportar) y lleva a
/// la persona, sin teclado, por cada acción:
/// <list type="bullet">
/// <item><b>Activar o renovar</b> en tres pasos (P-18): guardar la solicitud en una memoria, lo que hace AVACOM, y elegir el <c>.avlic</c> entre las tarjetas de las memorias y carpetas
/// conocidas → una sola confirmación → el resultado.</item>
/// <item><b>Guardar copia de la licencia</b> (CAP-111): elegir el destino → los tres archivos.</item>
/// <item><b>Liberar este equipo</b> (JRN-020): elegir dónde guardar el <c>.avrel</c> → una confirmación que dice qué pasa y que se puede deshacer → el resultado.</item>
/// <item><b>Confirmar la fecha de hoy</b> (P-06): una confirmación → el resultado.</item>
/// </list>
/// Toda la lógica vive en <see cref="FlujoDeActivacion"/>, <see cref="CopiaDeCustodia"/>, <see cref="FlujoDeLiberacion"/> y <see cref="ConfirmacionDeFecha"/>; aquí sólo se pinta lo que
/// dicen. Usar desde el hilo de la interfaz. Sólo Border, Label y Button; todo lo que se toca mide 64 px.
/// </summary>
internal sealed class HojaDeLicencia : ContentView
{
    private enum Modo { Ninguno, Activar, Copia, Liberar, Fecha }

    private readonly Grid _raiz = new();
    private readonly Border _tarjeta;
    private readonly Label _eyebrow, _titulo, _subtitulo;
    private readonly VerticalStackLayout _cuerpo = new() { Spacing = 14 };
    private readonly FlexLayout _pie = new()
    {
        Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.End,
        AlignItems = Microsoft.Maui.Layouts.FlexAlignItems.Start,
    };

    private TaskCompletionSource<bool>? _cierre;
    private Modo _modo;
    private int _version;
    private bool _cambio;
    private CancellationTokenSource? _cancelacion;

    // ---- los destinos (paso 1, la copia, la liberación)
    private Avacom.Lms.Ops.Reportes.ResultadoDeBusqueda? _destinos;
    private DestinoDeExportacion? _ultima, _elegido;
    private bool _buscandoDestinos, _verDestinos;
    private VigilanteDeUnidades? _vigilante;

    // ---- cada acción
    private FlujoDeActivacion? _activacion;
    private CopiaDeCustodia? _copia;
    private ResultadoDeCopia? _resultadoCopia;
    private bool _copiando;
    private FlujoDeLiberacion? _liberacion;
    private ConfirmacionDeFecha? _fecha;
    private MensajeDeLicencia? _resultadoFecha;
    private bool _confirmandoFecha;
    private long _ahoraDelNodo;

    public HojaDeLicencia()
    {
        IsVisible = false;
        ZIndex = 50;
        // El velo es hermano de la tarjeta: un toque dentro de la tarjeta nunca llega a él. Tocar fuera NO cierra la hoja (nada de esto se cancela de un roce).
        var velo = new Border { BackgroundColor = Color.FromArgb("#73141417"), StrokeThickness = 0 };
        _eyebrow = EstudioUi.Eyebrow(string.Empty);
        _titulo = new Label { FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "licencia-hoja-titulo" };
        _subtitulo = new Label { FontFamily = Ds.FuenteLigera, FontSize = 15, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap };
        var cabecera = new VerticalStackLayout { Spacing = 4, Margin = new Thickness(0, 0, 0, 12) };
        cabecera.Add(_eyebrow);
        cabecera.Add(_titulo);
        cabecera.Add(_subtitulo);
        var contenido = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star), new RowDefinition(GridLength.Auto)] };
        contenido.Add(cabecera, 0, 0);
        contenido.Add(new ScrollView { Content = _cuerpo }, 0, 1);
        contenido.Add(new Border { Padding = new Thickness(0, 14, 0, 0), StrokeThickness = 0, BackgroundColor = Colors.Transparent, Content = _pie }, 0, 2);
        _tarjeta = new Border
        {
            BackgroundColor = Ds.SuperficieContenido, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioGrande },
            Padding = new Thickness(28, 24), HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, Content = contenido,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.Tinta), Offset = new Point(0, 12), Radius = 32, Opacity = 0.28f }, AutomationId = "licencia-hoja",
        };
        _raiz.Add(velo);
        _raiz.Add(_tarjeta);
        _raiz.SizeChanged += (_, _) =>
        {
            if (_raiz.Width <= 0 || _raiz.Height <= 0) return;
            // La tarjeta en el tercio central: un tercio del ancho y de 1/6 a 5/6 del alto. El cuerpo se desplaza si no cabe; los botones quedan siempre a la vista.
            _tarjeta.WidthRequest = Math.Min(_raiz.Width, Math.Max(600, _raiz.Width / 3));
            _tarjeta.HeightRequest = Math.Min(_raiz.Height, Math.Max(560, _raiz.Height * 4 / 6));
        };
        Content = _raiz;
    }

    // =============================================================================================================== abrir y cerrar

    /// <summary>Activar o renovar en tres pasos. Devuelve si algo cambió en el nodo (para volver a leer el estado).</summary>
    public Task<bool> ActivarAsync(FlujoDeActivacion flujo)
    {
        _activacion = flujo;
        return AbrirAsync(Modo.Activar, async () => await BuscarDestinosAsync());
    }

    public Task<bool> CopiaAsync(CopiaDeCustodia copia)
    {
        _copia = copia;
        _resultadoCopia = null;
        return AbrirAsync(Modo.Copia, async () => await BuscarDestinosAsync());
    }

    public Task<bool> LiberarAsync(FlujoDeLiberacion flujo)
    {
        _liberacion = flujo;
        return AbrirAsync(Modo.Liberar, async () => await BuscarDestinosAsync());
    }

    public Task<bool> FechaAsync(ConfirmacionDeFecha fecha, long ahoraDelNodo)
    {
        _fecha = fecha;
        _resultadoFecha = null;
        _ahoraDelNodo = ahoraDelNodo;
        return AbrirAsync(Modo.Fecha, () => Task.CompletedTask);
    }

    private async Task<bool> AbrirAsync(Modo modo, Func<Task> preparar)
    {
        Cerrar();
        _modo = modo;
        _cambio = false;
        (_destinos, _ultima, _elegido, _verDestinos) = (null, null, null, false);
        _cierre = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var tarea = _cierre.Task;
        IsVisible = true;
        Pintar();
        try { await preparar(); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "HojaDeLicencia.Preparar", ex); }
        if (_modo == modo) Pintar();
        IniciarVigilante();
        return await tarea;
    }

    private void Cerrar()
    {
        var cierre = Interlocked.Exchange(ref _cierre, null);
        _cancelacion?.Cancel();
        _cancelacion = null;
        DetenerVigilante();
        _version++;
        _modo = Modo.Ninguno;
        IsVisible = false;
        cierre?.TrySetResult(_cambio);
    }

    /// <summary>Si la pantalla se cierra con la hoja abierta, nadie se queda esperando.</summary>
    protected override void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        base.OnPropertyChanged(propertyName);
        if (propertyName == nameof(IsVisible) && !IsVisible && _cierre is not null) Cerrar();
    }

    protected override void OnHandlerChanging(HandlerChangingEventArgs args)
    {
        base.OnHandlerChanging(args);
        if (args.NewHandler is null && _cierre is not null) Cerrar();
    }

    // =============================================================================================================== las memorias y carpetas

    /// <summary>Lee los destinos fuera del hilo de la pantalla (una unidad de red caída puede tardar) y la última carpeta usada para la licencia.</summary>
    private async Task BuscarDestinosAsync()
    {
        _buscandoDestinos = true;
        try
        {
            var actor = LicenciaUi.Actor;
            var (destinos, ultima) = await Task.Run(() =>
            {
                // Los archivos de la licencia no llevan datos de personas: ningún destino se prohíbe (la política de memorias del administrador es de los reportes).
                var encontrados = new CatalogoDeDestinos(LicenciaUi.Unidades, new CarpetasConocidasDelSistema(), new PoliticaDeDestinos()).Buscar();
                DestinoDeExportacion? recordada = null;
                if (LicenciaUi.Preferencias.UltimaCarpeta(actor) is { } ruta)
                    recordada = new DestinoDeExportacion($"ultima:{ruta}", "Última carpeta que usaste", ruta, ClasificadorDeRuta.Clasificar(ruta, LicenciaUi.Unidades), null, null, null, EsAtajo: false, Listo: true);
                return (encontrados, recordada);
            });
            _destinos = destinos;
            _ultima = ultima;
            if (_elegido is { } e && !Destinos().Any(d => d.Id == e.Id)) _elegido = null;
        }
        finally { _buscandoDestinos = false; }
    }

    private static string Clave(string ruta) => ruta.TrimEnd('\\', '/');

    /// <summary>La última carpeta usada primero (si es una unidad o un atajo que la lista ya tiene, se muestra ése), luego los atajos y las unidades.</summary>
    private IEnumerable<DestinoDeExportacion> Destinos()
    {
        var vistos = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var conocidos = _destinos?.Destinos ?? [];
        if (_ultima is { } u)
        {
            var primero = conocidos.FirstOrDefault(d => string.Equals(Clave(d.Ruta), Clave(u.Ruta), StringComparison.OrdinalIgnoreCase)) ?? u;
            if (vistos.Add(Clave(primero.Ruta))) yield return primero;
        }
        foreach (var d in conocidos)
            if (vistos.Add(Clave(d.Ruta))) yield return d;
    }

    private void IniciarVigilante()
    {
        if (_vigilante is not null || _modo is Modo.Fecha or Modo.Ninguno) return;
        // Una memoria que se conecta o se retira aparece sola: en la lista de destinos y en las tarjetas del paso 3. El aviso llega en otra hebra: se pasa a la de la interfaz.
        var vigilante = new VigilanteDeUnidades(LicenciaUi.Unidades, TimeSpan.FromSeconds(2));
        vigilante.Cambio += () => Dispatcher.Dispatch(async () =>
        {
            try
            {
                if (!IsVisible) return;
                if (_activacion is { Paso: PasoDeActivacion.Eligiendo } flujo && _modo == Modo.Activar)
                {
                    var version = _version;
                    await flujo.BuscarAsync();
                    if (version == _version) Pintar();
                    return;
                }
                if (EligiendoDestino())
                {
                    var version = _version;
                    await BuscarDestinosAsync();
                    if (version == _version) Pintar();
                }
            }
            catch (Exception ex) { RegistroDeFallos.Escribir("ops", "HojaDeLicencia.Vigilante", ex); }
        });
        _vigilante = vigilante;
        _ = Task.Run(vigilante.Iniciar);
    }

    private void DetenerVigilante()
    {
        _vigilante?.Dispose();
        _vigilante = null;
    }

    private bool EligiendoDestino() => _modo switch
    {
        Modo.Activar => _activacion?.Paso is PasoDeActivacion.Solicitud || (_activacion?.Paso is PasoDeActivacion.SolicitudGuardada && _verDestinos),
        Modo.Copia => !_copiando && _resultadoCopia is not { Ok: true },
        Modo.Liberar => _liberacion?.Paso is PasoDeLiberacion.ElegirDestino or PasoDeLiberacion.LiberadaSinGuardar,
        _ => false,
    };

    private async Task RefrescarDestinosAsync()
    {
        var version = _version;
        await BuscarDestinosAsync();
        if (version == _version) Pintar();
    }

    // =============================================================================================================== pintar

    private void Pintar()
    {
        _cuerpo.Clear();
        _pie.Clear();
        switch (_modo)
        {
            case Modo.Activar: PintarActivacion(); break;
            case Modo.Copia: PintarCopia(); break;
            case Modo.Liberar: PintarLiberacion(); break;
            case Modo.Fecha: PintarFecha(); break;
        }
    }

    private void Boton(string texto, Ds.Rango rango, Func<Task> alPulsar, string id, bool activo = true)
    {
        var (boton, vista) = LicenciaUi.Accion(texto, rango, LicenciaUi.Seguro($"Hoja.{id}", alPulsar), id);
        if (!activo) Ds.Habilitar(boton, false);
        _pie.Add(vista);
    }

    private void BotonCerrar(string texto = "Cancelar", Ds.Rango rango = Ds.Rango.Quiet) =>
        Boton(texto, rango, () => { Cerrar(); return Task.CompletedTask; }, "licencia-hoja-cerrar");

    private void Aviso(MensajeDeLicencia? m, Tono tono, string? id = null)
    {
        if (m is null) return;
        var aviso = ExamenUi.Aviso(m.Titulo, string.IsNullOrWhiteSpace(m.Accion) ? m.Texto : $"{m.Texto} {m.Accion}", tono);
        if (id is not null) aviso.AutomationId = id;
        _cuerpo.Add(aviso);
    }

    /// <summary>Lo que se ve mientras el aula trabaja: una frase y nada que tocar (son operaciones de un par de segundos; no se inventa un porcentaje).</summary>
    private void Avance(string texto) =>
        _cuerpo.Add(new Label { Text = texto, FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "licencia-avance" });

    private void PintarDestinos(string titulo = LicenciaTexto.ElegirDestino)
    {
        _cuerpo.Add(LicenciaUi.Eyebrow(titulo.ToUpperInvariant()));
        var herramientas = ExamenUi.Fila();
        herramientas.Add(LicenciaUi.Accion("Buscar de nuevo", Ds.Rango.Secondary, LicenciaUi.Seguro("Hoja.BuscarDestinos", RefrescarDestinosAsync), "licencia-destinos-buscar").Vista);
        _cuerpo.Add(herramientas);
        if (_destinos is null)
        {
            _cuerpo.Add(Ds.Secundario(_buscandoDestinos ? "Buscando memorias y carpetas…" : "Toca «Buscar de nuevo» para ver las memorias y carpetas.", 15));
            return;
        }
        if (_destinos.Aviso is { } aviso) _cuerpo.Add(ExamenUi.Aviso(aviso, null, Tono.Info));
        var i = 0;
        foreach (var d in Destinos())
        {
            var destino = d;
            var elegido = _elegido?.Id == destino.Id;
            var pila = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
            pila.Add(new Label { Text = elegido ? $"✓  {destino.Nombre}" : destino.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation });
            pila.Add(new Label { Text = DetalleDe(destino), FontFamily = Ds.FuenteRegular, FontSize = 13, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.MiddleTruncation });
            var marca = TextoDeExportacion.Marca(destino.Tipo);
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
            fila.Add(pila, 0, 0);
            if (marca is not null) fila.Add(ExamenUi.Pildora(marca, destino.Tipo == TipoDeDestino.Extraible ? Tono.Info : Tono.Violeta, 12), 1, 0);
            _cuerpo.Add(LicenciaUi.Tocable(fila, LicenciaUi.Seguro("Hoja.Destino", () => { _elegido = destino; Pintar(); return Task.CompletedTask; }),
                $"{destino.Nombre}{(marca is null ? string.Empty : ", " + marca)}", $"licencia-destino-{i++}", elegido));
        }
    }

    private static string DetalleDe(DestinoDeExportacion d)
    {
        if (d.Letra is not null && d.LibreBytes is { } libre) return $"{d.Letra} · {FormatoDeReportes.Tamano(libre)} libres";
        return d.Ruta;
    }

    private DestinoElegido? Elegido() => _elegido is { } d ? new DestinoElegido(d.Ruta, d.Tipo) : null;

    // ---------------------------------------------------------------------------------------------------- activar o renovar

    private void PintarPasos(int actual)
    {
        var fila = ExamenUi.Fila();
        string[] nombres = ["1 · Solicitud", "2 · AVACOM firma", "3 · Elegir el archivo"];
        for (var n = 1; n <= 3; n++)
            fila.Add(ExamenUi.PildoraEnFila(n < actual ? $"✓  {nombres[n - 1]}" : nombres[n - 1], n == actual ? Tono.Violeta : n < actual ? Tono.Exito : Tono.Neutro, 13));
        _cuerpo.Add(fila);
    }

    private void PintarActivacion()
    {
        var f = _activacion!;
        _eyebrow.Text = $"PASO {f.NumeroDePaso} DE 3";
        _titulo.Text = f.Via == ViasDeInstalacion.Renovar ? "Renovar la licencia" : LicenciaTexto.ActivarTitulo;
        _subtitulo.Text = string.Empty;
        PintarPasos(f.NumeroDePaso);
        switch (f.Paso)
        {
            case PasoDeActivacion.Solicitud:
            {
                _cuerpo.Add(LicenciaUi.Seccion(LicenciaTexto.Paso1Titulo, LicenciaTexto.Paso1Texto));
                Aviso(f.Aviso, Tono.Ambar, "licencia-aviso");
                PintarDestinos();
                _cuerpo.Add(Ds.Secundario(LicenciaTexto.Paso1YaTengo, 14));
                BotonCerrar();
                Boton("Ya tengo el archivo de licencia", Ds.Rango.Secondary, BuscarLicenciasAsync, "licencia-ya-tengo");
                Boton(f.Aviso is null ? "Guardar la solicitud" : "Guardar otra vez", Ds.Rango.Primary, GuardarSolicitudAsync, "licencia-guardar-solicitud", _elegido is not null);
                break;
            }
            case PasoDeActivacion.GuardandoSolicitud:
                _cuerpo.Add(LicenciaUi.Seccion(LicenciaTexto.Paso1Titulo));
                Avance(_elegido?.Tipo == TipoDeDestino.Extraible ? $"{LicenciaTexto.Guardando} {LicenciaTexto.NoRetiresLaMemoria}" : LicenciaTexto.Guardando);
                break;
            case PasoDeActivacion.SolicitudGuardada:
            {
                _cuerpo.Add(LicenciaUi.Seccion(LicenciaTexto.Paso1Titulo));
                Aviso(f.Aviso, Tono.Exito, "licencia-aviso");
                if (_verDestinos) PintarDestinos("Guardarla también en");
                BotonCerrar();
                if (_verDestinos) Boton("Guardar aquí", Ds.Rango.Secondary, GuardarSolicitudAsync, "licencia-guardar-solicitud", _elegido is not null);
                else Boton("Guardar en otro lugar", Ds.Rango.Secondary, () => { _verDestinos = true; _elegido = null; Pintar(); return Task.CompletedTask; }, "licencia-otro-lugar");
                Boton("Continuar", Ds.Rango.Primary, () => { _verDestinos = false; f.Continuar(); Pintar(); return Task.CompletedTask; }, "licencia-continuar");
                break;
            }
            case PasoDeActivacion.EsperandoLicencia:
                _cuerpo.Add(LicenciaUi.Seccion(LicenciaTexto.Paso2Titulo, LicenciaTexto.Paso2Texto));
                if (f.RutaDeLaSolicitud is { } ruta) _cuerpo.Add(LicenciaUi.Dato("Solicitud", ruta, 110));
                Boton("‹  Paso 1", Ds.Rango.Quiet, () => { f.VolverAlPaso1(); Pintar(); return Task.CompletedTask; }, "licencia-paso1");
                BotonCerrar();
                Boton("Ya tengo el archivo de licencia", Ds.Rango.Primary, BuscarLicenciasAsync, "licencia-ya-tengo");
                break;
            case PasoDeActivacion.Buscando:
                _cuerpo.Add(LicenciaUi.Seccion(LicenciaTexto.Paso3Titulo));
                Avance(LicenciaTexto.Buscando);
                break;
            case PasoDeActivacion.Eligiendo:
                PintarCandidatos(f);
                break;
            case PasoDeActivacion.Confirmando:
                PintarConfirmacion(f);
                break;
            case PasoDeActivacion.Instalando:
                _cuerpo.Add(LicenciaUi.Seccion("Instalando la licencia"));
                Avance(LicenciaTexto.Instalando);
                break;
            case PasoDeActivacion.Instalada:
                _titulo.Text = f.Aviso?.Titulo ?? "Licencia instalada";
                _cuerpo.Add(new Label { Text = f.Aviso?.Texto ?? string.Empty, FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap,
                    AutomationId = "licencia-resultado" });
                if (f.EstadoNuevo is { } nuevo)
                {
                    _cuerpo.Add(ExamenUi.Aviso(LicenciaTexto.Titulo(nuevo), LicenciaTexto.Frase(nuevo), Tono.Exito));
                    if (LicenciaTexto.Vigencia(nuevo) is { } vigencia) _cuerpo.Add(LicenciaUi.Dato("Vigencia", vigencia, 110));
                }
                Boton("Listo", Ds.Rango.Primary, () => { Cerrar(); return Task.CompletedTask; }, "licencia-listo");
                break;
            case PasoDeActivacion.NoInstalada:
                _titulo.Text = f.Aviso?.Titulo ?? "La licencia no se instaló";
                _cuerpo.Add(new Label { Text = f.Aviso?.Texto ?? string.Empty, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap,
                    AutomationId = "licencia-resultado" });
                if (!string.IsNullOrWhiteSpace(f.Aviso?.Accion)) _cuerpo.Add(ExamenUi.Aviso("Qué hacer", f.Aviso!.Accion, Tono.Ambar));
                _cuerpo.Add(Ds.Secundario("No se cambió nada en la licencia de este equipo. Las clases siguen igual.", 14));
                BotonCerrar("Cerrar");
                Boton("Elegir otro archivo", f.PuedeReintentar ? Ds.Rango.Secondary : Ds.Rango.Primary, () => { f.VolverALaLista(); Pintar(); return Task.CompletedTask; }, "licencia-otro-archivo");
                if (f.PuedeReintentar) Boton("Intentar de nuevo", Ds.Rango.Primary, InstalarAsync, "licencia-reintentar");
                break;
        }
    }

    private void PintarCandidatos(FlujoDeActivacion f)
    {
        _cuerpo.Add(LicenciaUi.Seccion(LicenciaTexto.Paso3Titulo, LicenciaTexto.Paso3Texto));
        var herramientas = ExamenUi.Fila();
        herramientas.Add(LicenciaUi.Accion("Buscar de nuevo", Ds.Rango.Secondary, LicenciaUi.Seguro("Hoja.BuscarLicencias", BuscarLicenciasAsync), "licencia-buscar").Vista);
        _cuerpo.Add(herramientas);
        var busqueda = f.Busqueda;
        if (busqueda is null || busqueda.Vacia)
        {
            Aviso(f.Aviso ?? new MensajeDeLicencia("No hay archivos de licencia", LicenciaTexto.SinArchivos, LicenciaTexto.SinArchivosAccion), Tono.Ambar, "licencia-sin-archivos");
        }
        else
        {
            for (var i = 0; i < busqueda.Candidatos.Count; i++)
            {
                var c = busqueda.Candidatos[i];
                var pila = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
                pila.Add(new Label { Text = c.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.MiddleTruncation });
                var detalle = $"{c.Lugar} · guardado el {LicenciaTexto.FechaYHora(c.ModificadoMs)}" + (c.OtrosLugares > 0 ? $" · también en {(c.OtrosLugares == 1 ? "1 lugar más" : $"{c.OtrosLugares} lugares más")}" : string.Empty);
                pila.Add(new Label { Text = detalle, FontFamily = Ds.FuenteRegular, FontSize = 13, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap });
                var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
                fila.Add(pila, 0, 0);
                if (c.Forma == FormaDeLicencia.Texto) fila.Add(ExamenUi.Pildora("En texto", Tono.Neutro, 12), 1, 0);
                var candidato = c;
                _cuerpo.Add(LicenciaUi.Tocable(fila, LicenciaUi.Seguro("Hoja.Candidato", () => { if (f.Elegir(candidato)) Pintar(); return Task.CompletedTask; }),
                    $"{c.Nombre}. {detalle}", $"licencia-candidato-{i}"));
            }
            if (busqueda.Recortada) _cuerpo.Add(Ds.Secundario($"Se muestran los {BuscadorDeLicencias.Tope} archivos más recientes.", 13));
        }
        Boton("‹  Paso 1", Ds.Rango.Quiet, () => { f.VolverAlPaso1(); Pintar(); return Task.CompletedTask; }, "licencia-paso1");
        BotonCerrar();
    }

    private void PintarConfirmacion(FlujoDeActivacion f)
    {
        var c = f.Elegido!;
        _titulo.Text = "Confirma antes de instalar";
        _cuerpo.Add(new Label { Text = f.Confirmacion() ?? string.Empty, FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap,
            AutomationId = "licencia-confirmacion" });
        _cuerpo.Add(LicenciaUi.Dato("Archivo", c.Nombre, 120));
        _cuerpo.Add(LicenciaUi.Dato("Dónde está", c.Lugar, 120));
        _cuerpo.Add(LicenciaUi.Dato("Guardado el", LicenciaTexto.FechaYHora(c.ModificadoMs), 120));
        _cuerpo.Add(LicenciaUi.Dato("Tamaño", FormatoDeReportes.Tamano(c.Bytes), 120));
        _cuerpo.Add(ExamenUi.Aviso("Lo comprueba el equipo del aula", "Antes de instalarla verifica que sea de AVACOM y de este equipo. Si no lo es, no cambia nada.", Tono.Info));
        Boton("Elegir otro archivo", Ds.Rango.Quiet, () => { f.VolverALaLista(); Pintar(); return Task.CompletedTask; }, "licencia-otro-archivo");
        Boton(f.Via == ViasDeInstalacion.Renovar ? "Renovar la licencia" : "Instalar la licencia", Ds.Rango.Primary, InstalarAsync, "licencia-instalar");
    }

    private async Task GuardarSolicitudAsync()
    {
        if (_activacion is not { } f || Elegido() is not { } destino) return;
        var version = _version;
        _cancelacion = new CancellationTokenSource();
        var tarea = f.GuardarSolicitudAsync(destino, null, _cancelacion.Token);
        Pintar();                                                     // «Guardando…»
        var ok = await tarea;
        if (version != _version) return;
        if (!ok && f.Aviso is { } aviso) LicenciaUi.Anotar("licencia.solicitud_no_guardada", "No se pudo guardar la solicitud de licencia.", new { titulo = aviso.Titulo });
        _verDestinos = false;
        Pintar();
    }

    private async Task BuscarLicenciasAsync()
    {
        if (_activacion is not { } f) return;
        var version = _version;
        var buscar = f.BuscarAsync();
        Pintar();                                                     // «Buscando…»
        await buscar;
        if (version == _version) Pintar();
    }

    private async Task InstalarAsync()
    {
        if (_activacion is not { } f) return;
        var version = _version;
        var tarea = f.Paso == PasoDeActivacion.NoInstalada ? f.ReintentarAsync() : f.InstalarAsync();
        Pintar();                                                     // «Instalando…»
        var ok = await tarea;
        if (ok) _cambio = true;
        if (version == _version) Pintar();
    }

    // ---------------------------------------------------------------------------------------------------- la copia de custodia

    private void PintarCopia()
    {
        _eyebrow.Text = "COPIA DE CUSTODIA";
        _titulo.Text = LicenciaTexto.CopiaTitulo;
        _subtitulo.Text = string.Empty;
        if (_copiando)
        {
            Avance(_elegido?.Tipo == TipoDeDestino.Extraible ? $"{LicenciaTexto.Guardando} {LicenciaTexto.NoRetiresLaMemoria}" : LicenciaTexto.Guardando);
            return;
        }
        if (_resultadoCopia is { Ok: true } bien)
        {
            _cuerpo.Add(new Label { Text = bien.Mensaje.Texto, FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "licencia-resultado" });
            foreach (var ruta in bien.Rutas) _cuerpo.Add(LicenciaUi.Dato("Archivo", System.IO.Path.GetFileName(ruta), 90));
            if (_elegido?.Tipo == TipoDeDestino.Extraible) _cuerpo.Add(ExamenUi.Aviso("Espera un momento antes de retirar la memoria.", null, Tono.Info));
            Boton("Listo", Ds.Rango.Primary, () => { Cerrar(); return Task.CompletedTask; }, "licencia-listo");
            return;
        }
        _cuerpo.Add(Ds.Secundario(LicenciaTexto.CopiaTexto, 16));
        if (_resultadoCopia is { } mal) Aviso(mal.Mensaje, Tono.Ambar, "licencia-aviso");
        PintarDestinos();
        BotonCerrar();
        Boton(_resultadoCopia is { Ok: false, SePuedeRepetir: true } ? "Guardar otra vez" : "Guardar la copia", Ds.Rango.Primary, GuardarCopiaAsync, "licencia-copia-guardar", _elegido is not null);
    }

    private async Task GuardarCopiaAsync()
    {
        if (_copia is null || Elegido() is not { } destino || _copiando) return;
        var version = _version;
        _copiando = true;
        Pintar();
        ResultadoDeCopia r;
        try { r = await _copia.GuardarAsync(destino); }
        finally { _copiando = false; }
        if (version != _version) return;
        _resultadoCopia = r;
        if (r.Ok) LicenciaUi.RecordarCarpeta(destino.Carpeta);
        else LicenciaUi.Anotar("licencia.copia_no_guardada", "No se pudo guardar la copia de la licencia.", new { motivo = r.Fallo?.Codigo, detalle = r.Detalle });
        Pintar();
    }

    // ---------------------------------------------------------------------------------------------------- liberar este equipo

    private void PintarLiberacion()
    {
        var f = _liberacion!;
        _eyebrow.Text = "LIBERAR ESTE EQUIPO";
        _titulo.Text = LicenciaTexto.LiberarTitulo;
        _subtitulo.Text = string.Empty;
        switch (f.Paso)
        {
            case PasoDeLiberacion.ElegirDestino:
                _cuerpo.Add(Ds.Secundario(LicenciaTexto.LiberarQueEs, 16));
                Aviso(f.Aviso, Tono.Ambar, "licencia-aviso");
                _cuerpo.Add(Ds.Secundario(LicenciaTexto.LiberarElegirDestino, 15));
                PintarDestinos();
                BotonCerrar();
                Boton("Continuar", Ds.Rango.Primary, () => { if (Elegido() is { } d && f.ElegirDestino(d)) Pintar(); return Task.CompletedTask; }, "licencia-continuar", _elegido is not null);
                break;
            case PasoDeLiberacion.Confirmando:
                _titulo.Text = "Confirma la liberación";
                _cuerpo.Add(new Label { Text = LicenciaTexto.LiberarQueEs, FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap,
                    AutomationId = "licencia-confirmacion" });
                _cuerpo.Add(ExamenUi.Aviso("Qué pasa", LicenciaTexto.LiberarQuePasa, Tono.Ambar));
                _cuerpo.Add(ExamenUi.Aviso("Se puede deshacer", LicenciaTexto.LiberarDeshacer, Tono.Info));
                _cuerpo.Add(LicenciaUi.Dato("Se guarda en", _elegido?.Nombre ?? f.Destino?.Carpeta, 120));
                Boton("Cambiar", Ds.Rango.Quiet, () => { f.CambiarDestino(); Pintar(); return Task.CompletedTask; }, "licencia-cambiar");
                Boton(LicenciaTexto.LiberarTitulo, Ds.Rango.Primary, LiberarAhoraAsync, "licencia-liberar-confirmar");
                break;
            case PasoDeLiberacion.Liberando:
                Avance(_elegido?.Tipo == TipoDeDestino.Extraible ? $"Liberando y guardando el archivo… {LicenciaTexto.NoRetiresLaMemoria}" : "Liberando y guardando el archivo…");
                break;
            case PasoDeLiberacion.Liberada:
                _titulo.Text = f.Aviso?.Titulo ?? "Equipo liberado";
                _cuerpo.Add(new Label { Text = f.Aviso?.Texto ?? string.Empty, FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.CharacterWrap,
                    AutomationId = "licencia-resultado" });
                if (f.Aviso?.Accion is { } deshacer) _cuerpo.Add(ExamenUi.Aviso("Se puede deshacer", deshacer, Tono.Info));
                Boton("Listo", Ds.Rango.Primary, () => { Cerrar(); return Task.CompletedTask; }, "licencia-listo");
                break;
            case PasoDeLiberacion.LiberadaSinGuardar:
            {
                _titulo.Text = "Falta guardar el archivo de liberación";
                Aviso(f.Aviso, Tono.Ambar, "licencia-resultado");
                PintarDestinos();
                var mismo = _elegido is { } e && f.Destino is { } previo && string.Equals(Clave(e.Ruta), Clave(previo.Carpeta), StringComparison.OrdinalIgnoreCase);
                Boton(mismo ? "Guardar otra vez" : "Guardar aquí", Ds.Rango.Primary, GuardarLiberacionDeNuevoAsync, "licencia-guardar-liberacion", _elegido is not null);
                break;
            }
            case PasoDeLiberacion.NoLiberada:
                _titulo.Text = f.Aviso?.Titulo ?? "El equipo no se liberó";
                _cuerpo.Add(new Label { Text = f.Aviso?.Texto ?? string.Empty, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap,
                    AutomationId = "licencia-resultado" });
                if (!string.IsNullOrWhiteSpace(f.Aviso?.Accion)) _cuerpo.Add(ExamenUi.Aviso("Qué hacer", f.Aviso!.Accion, Tono.Ambar));
                _cuerpo.Add(Ds.Secundario("No se cambió nada en la licencia de este equipo.", 14));
                BotonCerrar("Cerrar");
                Boton("Intentar de nuevo", Ds.Rango.Primary, () => { if (f.Destino is { } d) f.ElegirDestino(d); Pintar(); return Task.CompletedTask; }, "licencia-reintentar");
                break;
        }
    }

    private async Task LiberarAhoraAsync()
    {
        if (_liberacion is not { } f) return;
        var version = _version;
        var tarea = f.LiberarAsync();
        Pintar();                                                     // «Liberando…»
        var liberada = await tarea;
        if (liberada)
        {
            _cambio = true;
            if (f.Destino is { } d && f.Paso == PasoDeLiberacion.Liberada) LicenciaUi.RecordarCarpeta(d.Carpeta);
            if (f.Paso == PasoDeLiberacion.LiberadaSinGuardar) LicenciaUi.Anotar("licencia.liberacion_sin_guardar", "El equipo se liberó y el archivo de liberación no se pudo guardar.");
        }
        if (version == _version) Pintar();
    }

    private async Task GuardarLiberacionDeNuevoAsync()
    {
        if (_liberacion is not { } f || Elegido() is not { } destino) return;
        var version = _version;
        var tarea = f.GuardarEnOtroDestinoAsync(destino);
        Pintar();
        await tarea;
        if (f.Paso == PasoDeLiberacion.Liberada) LicenciaUi.RecordarCarpeta(destino.Carpeta);
        if (version == _version) Pintar();
    }

    // ---------------------------------------------------------------------------------------------------- confirmar la fecha

    private void PintarFecha()
    {
        _eyebrow.Text = "FECHA DEL EQUIPO";
        _titulo.Text = LicenciaTexto.FechaTitulo;
        _subtitulo.Text = string.Empty;
        if (_confirmandoFecha)
        {
            Avance("Confirmando la fecha…");
            return;
        }
        if (_resultadoFecha is { } r)
        {
            var bien = _fecha?.EstadoNuevo is not null;
            _cuerpo.Add(new Label { Text = r.Texto, FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "licencia-resultado" });
            if (!bien && !string.IsNullOrWhiteSpace(r.Accion)) _cuerpo.Add(ExamenUi.Aviso("Qué hacer", r.Accion, Tono.Ambar));
            Boton("Listo", Ds.Rango.Primary, () => { Cerrar(); return Task.CompletedTask; }, "licencia-listo");
            return;
        }
        _cuerpo.Add(new Label { Text = LicenciaTexto.ConfirmacionDeFecha(_ahoraDelNodo), FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.Tinta,
            LineBreakMode = LineBreakMode.WordWrap, AutomationId = "licencia-confirmacion" });
        BotonCerrar();
        Boton("Confirmar la fecha", Ds.Rango.Primary, ConfirmarFechaAsync, "licencia-fecha-confirmar");
    }

    private async Task ConfirmarFechaAsync()
    {
        if (_fecha is null || _confirmandoFecha) return;
        var version = _version;
        _confirmandoFecha = true;
        Pintar();
        try { _resultadoFecha = await _fecha.ConfirmarAsync(); }
        finally { _confirmandoFecha = false; }
        if (_fecha.EstadoNuevo is not null) _cambio = true;
        if (version == _version) Pintar();
    }
}
