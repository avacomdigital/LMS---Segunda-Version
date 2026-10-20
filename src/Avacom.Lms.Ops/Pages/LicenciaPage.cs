using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Licencia;
using Avacom.Lms.Ops.Licencia.Ui;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Licencia (MOD-018, ruta <c>licencia</c>): lo que el nodo dice de la licencia de este equipo y lo que se puede hacer con ella, sin teclado. Es una pantalla de tarjetas y sigue la
/// composición de tercios: Grid de columnas <c>*,*,*</c> y de filas <c>*,4*,*</c>, con las tres tarjetas en la fila central (de 1/6 a 5/6 del alto) y cada una en su tercio:
/// <list type="bullet">
/// <item>a la izquierda, el <b>uso</b> de lo contratado (equipos y usuarios frente al límite, con barras hechas de Border) y los <b>módulos</b> encendidos o en pausa;</item>
/// <item>en el centro, en una lámina de vidrio, el <b>estado</b>: título y frase, vigencia, aula, tipo, huella, banderas y avisos;</item>
/// <item>a la derecha, las <b>acciones</b>: [Activar o renovar] en tres pasos, [Guardar copia de la licencia], [Liberar este equipo] y, si el reloj dio un salto, [Confirmar la fecha de hoy].
/// Cada acción abre <see cref="HojaDeLicencia"/> encima.</item>
/// </list>
/// El cliente no decide nada de la licencia (SEC-001): pinta lo que responde <c>/api/licencia/</c> y el nodo autoriza cada acción. La ven la administración y el soporte técnico (sin
/// sesión, el prototipo la deja ver y el nodo decide). Nada aquí interrumpe una clase. Sólo Border, Label y Button; todo lo que se toca mide 64 px.
/// </summary>
public sealed class LicenciaPage : ContentPage
{
    private const double Aire = 10;       // lo que separa cada tarjeta de las líneas de tercios: así quedan DENTRO de su tercio

    private readonly Label _subtitulo = new() { FontFamily = Ds.FuenteLigera, FontSize = 15, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap, Text = LicenciaTexto.Cargando };
    private readonly ContentView _izquierda = new() { Margin = new Thickness(Aire, 0) };
    private readonly ContentView _centro = new() { Margin = new Thickness(Aire, 0) };
    private readonly ContentView _derecha = new() { Margin = new Thickness(Aire, 0) };
    private readonly Label _pie = new() { FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap, Text = string.Empty };
    private readonly HojaDeLicencia _hoja = new();

    private EstadoLicencia? _estado;
    private ConsumoDeLicencia? _consumo;
    private bool _cargando, _visible;

    public LicenciaPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        Title = "Licencia";
        BackgroundColor = Ds.Lienzo;

        var textos = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = "LICENCIA", FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, CharacterSpacing = 2.5 });
        textos.Add(new Label { Text = "Licencia de este equipo", FontFamily = Ds.FuenteMedia, FontSize = 30, TextColor = Ds.Tinta, AutomationId = "licencia-titulo" });
        textos.Add(_subtitulo);
        var acciones = new HorizontalStackLayout { Spacing = 12, VerticalOptions = LayoutOptions.Center };
        acciones.Add(LicenciaUi.Accion("Actualizar", Ds.Rango.Secondary, LicenciaUi.Seguro("Actualizar", CargarAsync), "licencia-actualizar", 170).Vista);
        acciones.Add(LicenciaUi.Accion("‹  Menú principal", Ds.Rango.Quiet, () => Shell.Current.GoToAsync(".."), "licencia-volver", 220).Vista);
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 24, Padding = new Thickness(44, 24, 48, 0), VerticalOptions = LayoutOptions.Start };
        cabecera.Add(textos, 0, 0);
        cabecera.Add(acciones, 1, 0);

        var tarjetas = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)] };
        tarjetas.Add(_izquierda, 0, 0);
        tarjetas.Add(_centro, 1, 0);
        tarjetas.Add(_derecha, 2, 0);

        var pie = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], Padding = new Thickness(0, 12, 0, 12) };
        pie.Add(new ContentView { Margin = new Thickness(Aire, 0), Content = _pie }, 1, 0);

        var raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(new GridLength(4, GridUnitType.Star)), new RowDefinition(GridLength.Star)] };
        raiz.Add(cabecera, 0, 0);
        raiz.Add(tarjetas, 0, 1);
        raiz.Add(pie, 0, 2);
        raiz.Add(_hoja, 0, 0);
        Grid.SetRowSpan(_hoja, 3);
        Content = raiz;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!ReglasDeLicencia.VeLaLicencia(Sesion.Usuario))
            {
                _subtitulo.Text = LicenciaTexto.SoloAdministracion;
                SoloCentral(Estado(LicenciaTexto.SoloAdministracion, LicenciaTexto.SoloAdministracionDetalle));
                return;
            }
            await CargarAsync();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "LicenciaPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
        _hoja.IsVisible = false;                    // si se sale con la hoja abierta, nadie se queda esperando
    }

    // =============================================================================================================== leer

    private async Task CargarAsync()
    {
        if (_cargando || !_visible) return;
        _cargando = true;
        try
        {
            if (_estado is null) SoloCentral(Estado("Leyendo la licencia", LicenciaTexto.Cargando));
            var api = LicenciaUi.Api;
            var estado = await api.EstadoAsync(LicenciaUi.Actor);
            if (!_visible) return;
            if (estado is null)
            {
                var error = LicenciaUi.Error(api);
                _subtitulo.Text = error.Titulo;
                // Sin conexión se conserva lo último que se vio, con el aviso encima; sin nada visto, sólo el aviso en el tercio central.
                if (_estado is not null && api.UltimoError is { Estado: 0 }) { Pintar(error); return; }
                SoloCentral(Estado(error.Titulo, error.Completo, LicenciaUi.Accion("Reintentar", Ds.Rango.Secondary, LicenciaUi.Seguro("Reintentar", CargarAsync), "licencia-reintentar-carga").Vista));
                return;
            }
            _estado = estado;
            _consumo = await api.ConsumoAsync(LicenciaUi.Actor);         // si no contesta, se pinta lo que trae el estado
            if (!_visible) return;
            Pintar(null);
        }
        finally { _cargando = false; }
    }

    // =============================================================================================================== pintar

    private void SoloCentral(View vista)
    {
        _izquierda.Content = null;
        _derecha.Content = null;
        vista.VerticalOptions = LayoutOptions.Start;
        _centro.Content = vista;
        _pie.Text = string.Empty;
    }

    private static View Estado(string titulo, string texto, params View[] acciones)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "licencia-estado-titulo" });
        pila.Add(new Label { Text = texto, FontFamily = Ds.FuenteRegular, FontSize = 17, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "licencia-estado-frase" });
        if (acciones.Length > 0)
        {
            var fila = ExamenUi.Fila();
            foreach (var a in acciones) fila.Add(a);
            pila.Add(fila);
        }
        return LicenciaUi.Vidrio(pila);
    }

    private void Pintar(MensajeDeLicencia? sinConexion)
    {
        var e = _estado!;
        _subtitulo.Text = e.Ilimitada
            ? "En desarrollo y pruebas la licencia no se verifica."
            : $"{LicenciaTexto.EstadoBreve(e)} · lo que el equipo del aula dice de su licencia y lo que puedes hacer con ella.";
        _izquierda.Content = new ScrollView { Content = TarjetaDeUso(e, _consumo) };
        _centro.Content = new ScrollView { Content = TarjetaDeEstado(e, sinConexion) };
        _derecha.Content = new ScrollView { Content = TarjetaDeAcciones(e) };
        _pie.Text = "Nada de lo que hagas aquí interrumpe una clase. " + LicenciaTexto.NucleoSigue;
    }

    // ---------------------------------------------------------------------------------------------------- el estado (centro, vidrio)

    private static View TarjetaDeEstado(EstadoLicencia e, MensajeDeLicencia? sinConexion)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        if (sinConexion is not null) pila.Add(ExamenUi.Aviso(sinConexion.Titulo, sinConexion.Completo, Tono.Ambar));
        pila.Add(LicenciaUi.Eyebrow("ESTADO DE LA LICENCIA"));
        pila.Add(ExamenUi.Pildora(LicenciaTexto.EstadoBreve(e), LicenciaUi.TonoDe(LicenciaTexto.TonoDelEstado(e)), 14));
        pila.Add(new Label { Text = LicenciaTexto.Titulo(e), FontFamily = Ds.FuenteMedia, FontSize = 28, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "licencia-estado-titulo" });
        pila.Add(new Label { Text = LicenciaTexto.Frase(e), FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "licencia-estado-frase" });
        pila.Add(Ds.Separador());

        var lic = e.Licencia;
        if (lic is not null)
        {
            pila.Add(LicenciaUi.Dato("Aula", lic.Aula));
            pila.Add(LicenciaUi.Dato("Tipo", LicenciaTexto.Tipo(lic.Tipo ?? e.Tipo)));
            pila.Add(LicenciaUi.Dato("Vigencia", LicenciaTexto.Vigencia(e)));
            pila.Add(LicenciaUi.Dato("Serie", lic.Serie.ToString(System.Globalization.CultureInfo.InvariantCulture)));
        }
        else if (!e.Ilimitada)
        {
            pila.Add(LicenciaUi.Dato("Licencia", "Ninguna instalada"));
            if (e.Vigencia?.Hasta is { } hasta) pila.Add(LicenciaUi.Dato("Evaluación hasta", LicenciaTexto.Fecha(hasta)));
        }
        if (!e.Ilimitada)
        {
            pila.Add(LicenciaUi.Dato("Huella", LicenciaTexto.NivelDeHuella(e.Huella?.Nivel)));
            pila.Add(Ds.Secundario(LicenciaTexto.Huella(e.Huella), 14));
        }

        foreach (var bandera in e.BanderasActivas)
            pila.Add(ExamenUi.Aviso(LicenciaTexto.BanderaBreve(bandera), LicenciaTexto.Bandera(bandera), bandera == BanderasDeLicencia.IntegridadAlterada ? Tono.Ambar : Tono.Info));

        var avisos = ReglasDeLicencia.AvisosDelBanner(e).Where(a => !e.Tiene(a.Codigo)).ToList();       // las banderas ya se dijeron arriba
        if (avisos.Count > 0)
        {
            pila.Add(LicenciaUi.Eyebrow("AVISOS"));
            for (var i = 0; i < avisos.Count; i++)
            {
                var aviso = ExamenUi.Aviso(LicenciaTexto.Aviso(avisos[i], e), null, LicenciaUi.TonoDe(ReglasDeLicencia.TonoDe(avisos[i])));
                aviso.AutomationId = $"licencia-aviso-{i}";
                pila.Add(aviso);
            }
        }
        return LicenciaUi.Vidrio(pila);
    }

    // ---------------------------------------------------------------------------------------------------- el uso y los módulos (izquierda)

    private static View TarjetaDeUso(EstadoLicencia e, ConsumoDeLicencia? consumo)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(LicenciaUi.Eyebrow("USO DE LO CONTRATADO"));
        pila.Add(new Label { Text = "Equipos y usuarios", FontFamily = Ds.FuenteMedia, FontSize = 22, TextColor = Ds.Tinta });
        var equipos = consumo?.Equipos ?? DelEstado(e.Consumo?.Equipos, e.Limites?.Equipos);
        var usuarios = consumo?.Usuarios ?? DelEstado(e.Consumo?.Usuarios, e.Limites?.Usuarios);
        pila.Add(LicenciaUi.Barra("Equipos", equipos, "equipos"));
        pila.Add(LicenciaUi.Barra("Usuarios", usuarios, "usuarios"));
        var normal = consumo?.Concurrentes?.Normal ?? e.Limites?.ConcurrentesNormal;
        var pico = consumo?.Concurrentes?.Pico ?? e.Limites?.ConcurrentesPico;
        pila.Add(Ds.Secundario(LicenciaTexto.Concurrencia(normal, pico), 15));
        pila.Add(Ds.Secundario("El cupo sólo cuenta al crear algo nuevo: lo que ya existe sigue funcionando aunque se llegue al límite.", 13));
        pila.Add(Ds.Separador());

        pila.Add(LicenciaUi.Eyebrow("MÓDULOS CON LICENCIA"));
        if (e.Restringe) pila.Add(ExamenUi.Aviso("Algunos módulos están en pausa", LicenciaTexto.NucleoSigue, Tono.AmbarFuerte));
        var habilitadas = e.Habilitadas;
        foreach (var codigo in CapacidadesLicenciables.Todas)
            pila.Add(LicenciaUi.Modulo(codigo, habilitadas.Contains(codigo)));
        pila.Add(Ds.Secundario(LicenciaTexto.NuncaSePausa, 13));
        return LicenciaUi.Tarjeta(pila);
    }

    /// <summary>Sin respuesta de <c>consumo/</c>, la cifra que trae el estado (con su porcentaje, si hay tope).</summary>
    private static UsoDelCupo? DelEstado(int? enUso, int? limite) =>
        enUso is null ? null : new UsoDelCupo(enUso, limite, limite is > 0 ? (int)Math.Round(100.0 * enUso.Value / limite.Value) : null);

    // ---------------------------------------------------------------------------------------------------- las acciones (derecha)

    private View TarjetaDeAcciones(EstadoLicencia e)
    {
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(LicenciaUi.Eyebrow("QUÉ PUEDES HACER"));
        pila.Add(new Label { Text = "Acciones", FontFamily = Ds.FuenteMedia, FontSize = 22, TextColor = Ds.Tinta, Margin = new Thickness(0, 0, 0, 8) });
        if (e.Ilimitada)
        {
            pila.Add(Ds.Secundario(LicenciaTexto.SinAccionesEnDesarrollo, 16));
            return LicenciaUi.Tarjeta(pila);
        }
        if (ReglasDeLicencia.OfrecerActivacion(e))
        {
            var renovar = ReglasDeLicencia.Via(e, Sesion.Usuario) == ViasDeInstalacion.Renovar;
            pila.Add(LicenciaUi.AccionConDescripcion("Activar o renovar", LicenciaTexto.ActivarDescripcion, Ds.Rango.Primary,
                LicenciaUi.Seguro("Activar", () => AbrirActivacionAsync()), "licencia-activar"));
            if (renovar) pila.Add(Ds.Secundario("Con la licencia en uso, el archivo nuevo se instala como renovación.", 13));
        }
        if (ReglasDeLicencia.OfrecerCopia(e))
            pila.Add(LicenciaUi.AccionConDescripcion("Guardar copia de la licencia", LicenciaTexto.CopiaDescripcion, Ds.Rango.Secondary,
                LicenciaUi.Seguro("Copia", AbrirCopiaAsync), "licencia-copia"));
        if (ReglasDeLicencia.OfrecerLiberar(e))
            pila.Add(LicenciaUi.AccionConDescripcion(LicenciaTexto.LiberarTitulo, LicenciaTexto.LiberarDescripcion, Ds.Rango.Secondary,
                LicenciaUi.Seguro("Liberar", AbrirLiberacionAsync), "licencia-liberar"));
        if (ReglasDeLicencia.OfrecerConfirmarFecha(e))
            pila.Add(LicenciaUi.AccionConDescripcion(LicenciaTexto.FechaTitulo, LicenciaTexto.FechaDescripcion, Ds.Rango.Secondary,
                LicenciaUi.Seguro("Fecha", AbrirFechaAsync), "licencia-fecha"));
        if (Sesion.Usuario is { } u && !ReglasDeLicencia.EsAdministracion(u))
            pila.Add(Ds.Secundario("Renovar la licencia lo hace la administración del colegio.", 13));
        return LicenciaUi.Tarjeta(pila);
    }

    private async Task AbrirActivacionAsync()
    {
        var e = _estado;
        var flujo = new FlujoDeActivacion(LicenciaUi.Api, LicenciaUi.Actor, ReglasDeLicencia.Via(e, Sesion.Usuario),
            ct => Task.Run(() => LicenciaUi.Buscador().Buscar(), ct), new LectorDeArchivosDelSistema(), new EscritorDeLicencias(), LicenciaUi.RecordarCarpeta);
        if (await _hoja.ActivarAsync(flujo)) await CargarAsync();
    }

    private async Task AbrirCopiaAsync()
    {
        var copia = new CopiaDeCustodia(LicenciaUi.Api, LicenciaUi.Actor, new EscritorDeLicencias(), () => RelojNodo.AhoraMs);
        await _hoja.CopiaAsync(copia);
    }

    private async Task AbrirLiberacionAsync()
    {
        var flujo = new FlujoDeLiberacion(LicenciaUi.Api, LicenciaUi.Actor, new EscritorDeLicencias());
        if (await _hoja.LiberarAsync(flujo)) await CargarAsync();
    }

    private async Task AbrirFechaAsync()
    {
        var fecha = new ConfirmacionDeFecha(LicenciaUi.Api, LicenciaUi.Actor);
        // Lo que se confirma es la fecha que tiene el equipo: con una fecha adelantada (Q-L13) no es la hora del aula (`Ahora`), es la que el aula no aceptó.
        if (await _hoja.FechaAsync(fecha, _estado?.FechaDelEquipo ?? RelojNodo.AhoraMs)) await CargarAsync();
    }
}
