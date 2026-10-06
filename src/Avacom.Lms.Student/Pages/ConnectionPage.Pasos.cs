using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.Acceso;
using Avacom.Lms.Student.Controls;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student.Pages;

/// <summary>
/// Los pasos del acceso del alumno (RF-20…RF-28) dentro de la tarjeta de <see cref="ConnectionPage"/>. La tarjeta, el lápiz y el panal no cambian: en el tercio
/// de arriba el título dice qué hacer y «Aviso» qué pasó y qué sigue (§5); en los dos tercios de abajo va lo que se toca (grupos, nombres, el teclado del PIN o
/// los dibujos) y, fijas debajo, «No estoy en la lista · soy nuevo» y «Entrar como visitante». Todo lo que se toca es un botón del orden de los del acceso (52 de alto) (así la UI
/// Automation lo puede invocar por su nombre). Nunca se abre el teclado del sistema para el PIN; lo único que se escribe es el nombre de quien es nuevo.
/// </summary>
public partial class ConnectionPage
{
    private enum SubpasoNuevo { Datos, Pin }

    // Del mismo orden que los botones del acceso («Entrar al aula», 52): lo que se toca nunca domina la tarjeta (corrección de diseño 2026-10-06).
    private const double AltoTecla = 52, AnchoTecla = 68, LadoDibujo = 56, AltoGrupo = 64;

    private FlujoDeAcceso? flujo;
    private Uri? baseDelFlujo;
    private bool ocupado, confirmandoVisitante, avisoSinRed;
    private string? aviso;
    private string? primerDibujo;
    private SubpasoNuevo subNuevo;
    private IDispatcherTimer? relojPausa;
    private TecladoPinView? teclado;
    private AvatarPickerView? dibujos;

    // Lo único que se escribe con el teclado del sistema: el nombre de quien es nuevo (RF-21) y, en la salida de siempre, el código y la clave.
    private readonly Entry nombreNuevo = Campo("nuevo-nombre", "Tu nombre", Keyboard.Text);
    private readonly Entry apellidoNuevo = Campo("nuevo-apellido", "Tu apellido (si quieres)", Keyboard.Text);
    private readonly Entry codigoEntry = Campo("codigo-codigo", "Tu código de estudiante", Keyboard.Plain);
    private readonly Entry claveEntry = Campo("codigo-clave", "Tu clave", Keyboard.Plain, clave: true);

    private static Entry Campo(string id, string ayuda, Keyboard teclado, bool clave = false) => new()
    {
        AutomationId = id, Placeholder = ayuda, Keyboard = teclado, IsPassword = clave, HeightRequest = AltoTecla, FontSize = 17,
        IsSpellCheckEnabled = false, IsTextPredictionEnabled = false,
    };

    // ======================================================================================================================== preparar

    /// <summary>El aula exige sesión: el flujo se arma sobre su cliente de acceso (uno por dirección del aula) y empieza de cero.</summary>
    private void PrepararFlujo(ConfiguracionAcceso config)
    {
        var api = Sesion.Acceso;
        if (flujo is null || baseDelFlujo != api.BaseUri)
        {
            flujo = new FlujoDeAcceso(api, Sesion.Dispositivo, Sesion.PresentarTabletaAsync);
            baseDelFlujo = api.BaseUri;
        }
        flujo.Iniciar(config);
    }

    /// <summary>«Entrar al aula» con sesión obligatoria: la tableta se presenta y se piden los grupos.</summary>
    private async Task AbrirPasosAsync(string direccion)
    {
        Preferences.Default.Set("student_server", direccion);
        if (flujo is null) return;
        Estado("●  Buscando los grupos del aula…", AzulSuave, Azul);
        await AtenderAsync(c => flujo.CargarGruposAsync(c));
        if (flujo.Paso != PasoAcceso.Conexion) Estado("●  Conectado al aula correctamente", VerdeSuave, Verde);
    }

    /// <summary>
    /// Se vuelve al acceso («Salir», sesión terminada, arranque). Nada de quien estuvo antes: ni grupo, ni nombre, ni PIN, ni lo escrito para darse de alta
    /// (BR-053, RF-00d). El código sólo se conserva si la misma persona vuelve a identificarse tras un aviso de sesión terminada.
    /// </summary>
    private void AlVolverAlAcceso()
    {
        confirmandoVisitante = false; aviso = null; avisoSinRed = false; primerDibujo = null; subNuevo = SubpasoNuevo.Datos;
        nombreNuevo.Text = string.Empty; apellidoNuevo.Text = string.Empty; claveEntry.Text = string.Empty;
        var recordar = Sesion.RecordarCodigo && !string.IsNullOrWhiteSpace(codigoEntry.Text);
        if (!recordar) codigoEntry.Text = string.Empty;
        Sesion.RecordarCodigo = false;
        if (flujo is not null && exigeSesion)
        {
            flujo.Limpiar();
            if (recordar && flujo.Paso != PasoAcceso.Conexion) flujo.EmpezarConCodigo();
            PintarPaso();
            // La lista puede haber cambiado (alguien se dio de alta, el profesor dejó un PIN pendiente): se vuelve a pedir.
            if (flujo.Paso == PasoAcceso.Grupo) _ = AtenderAsync(c => flujo.CargarGruposAsync(c));
            return;
        }
        PintarPaso();
    }

    // ======================================================================================================================== acciones

    /// <summary>
    /// Ejecuta una acción del flujo con la pantalla quieta (nada de toques dobles) y pinta lo que contestó. Si ya entró, va al menú; si no, el aviso dice
    /// qué pasó y qué sigue. Lo marcado en el teclado se borra siempre al repintar: el PIN nunca queda a la vista (RF-00d).
    /// </summary>
    private async Task AtenderAsync(Func<CancellationToken, Task<RespuestaDeAcceso>> accion)
    {
        if (ocupado || flujo is null) return;
        ocupado = true;
        PasoHost.IsEnabled = false; Pie.IsEnabled = false; VolverButton.IsEnabled = false;
        try
        {
            var r = await accion(CancellationToken.None);
            if (r.Sesion is not null)
            {
                confirmandoVisitante = false; aviso = null; avisoSinRed = false; primerDibujo = null; subNuevo = SubpasoNuevo.Datos;
                nombreNuevo.Text = string.Empty; apellidoNuevo.Text = string.Empty; claveEntry.Text = string.Empty; codigoEntry.Text = string.Empty;
                PintarPaso();
                await AlEntrarAsync(r.Sesion);
                return;
            }
            aviso = r.PideConfirmar ? null : r.Mensaje;
            avisoSinRed = r.SinConexion;
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "ConnectionPage.Acceso", ex);
            aviso = MensajesDeAcceso.Generico;
            avisoSinRed = false;
        }
        finally
        {
            ocupado = false;
            PasoHost.IsEnabled = true; Pie.IsEnabled = true; VolverButton.IsEnabled = true;
        }
        confirmandoVisitante = false;
        PintarPaso();
    }

    private void OnVolver(object? sender, EventArgs e)
    {
        if (flujo is null || ocupado) return;
        aviso = null; avisoSinRed = false; primerDibujo = null;
        if (confirmandoVisitante) confirmandoVisitante = false;
        else if (flujo.Paso == PasoAcceso.Nuevo && subNuevo == SubpasoNuevo.Pin) { subNuevo = SubpasoNuevo.Datos; flujo.Doble.Reiniciar(); }
        else
        {
            flujo.Volver();
            if (flujo.Paso == PasoAcceso.Conexion) Estado("●  Lista para comprobar la red local", AzulSuave, Azul);
        }
        PintarPaso();
    }

    private void OnSoyNuevo(object? sender, EventArgs e)
    {
        if (flujo is null || ocupado) return;
        confirmandoVisitante = false; aviso = null; avisoSinRed = false; primerDibujo = null;
        flujo.EmpezarRegistro();
        subNuevo = SubpasoNuevo.Datos;
        PintarPaso();
    }

    /// <summary>RF-23: un botón y un toque de confirmación. Con la tableta en pausa también (RN-33).</summary>
    private void OnVisitante(object? sender, EventArgs e)
    {
        if (flujo is null || ocupado) return;
        confirmandoVisitante = true; aviso = null; avisoSinRed = false;
        PintarPaso();
    }

    private Task MarcarNuevoAsync(string valor) => AtenderAsync(async c =>
    {
        var r = await flujo!.MarcarPinNuevoAsync(valor, c);
        primerDibujo = r.PideConfirmar ? valor : null;
        return r;
    });

    // ======================================================================================================================== pintar

    /// <summary>Pinta el paso en curso. Es la única que toca la tarjeta; se llama tras cada acción y al cambiar el tamaño de la ventana.</summary>
    private void PintarPaso()
    {
        relojPausa?.Stop();
        teclado = null; dibujos = null;
        var paso = exigeSesion && flujo is not null ? flujo.Paso : PasoAcceso.Conexion;
        var enPasos = paso != PasoAcceso.Conexion;
        FormularioScroll.IsVisible = !enPasos;
        PasoScroll.IsVisible = enPasos;
        // En los pasos el logo se achica un poco para que el título, la instrucción y el aviso quepan en el tercio de arriba.
        Logo.HeightRequest = enPasos ? (esBaja ? 52 : 72) : (esBaja ? 64 : 100);
        Logo.Margin = enPasos ? new Thickness(-6, 0, 0, -12) : new Thickness(-8, 0, 0, -18);
        PasoHost.Clear();

        if (!enPasos || flujo is null)
        {
            Titulo.Text = "Conéctate a tu aula";
            Descripcion.Text = exigeSesion ? DescripcionConSesion : DescripcionPrototipo;
            VolverButton.IsVisible = false;
            Pie.IsVisible = false;
            PonerAviso(null);
            if (aviso is not null && exigeSesion) Estado("●  " + aviso, RojoSuave, Rojo);
            return;
        }

        VolverButton.IsVisible = !confirmandoVisitante;
        if (confirmandoVisitante)
        {
            PintarConfirmarVisitante();
            PintarPie(nuevo: false, visitante: false);
            return;
        }
        switch (paso)
        {
            case PasoAcceso.Grupo: PintarGrupos(); break;
            case PasoAcceso.Nombre: PintarNombres(); break;
            case PasoAcceso.Pin: PintarPin(); break;
            case PasoAcceso.ElegirPin: PintarElegirPin(); break;
            case PasoAcceso.Nuevo: PintarNuevo(); break;
            case PasoAcceso.Codigo: PintarCodigo(); break;
        }
        PintarPie(nuevo: paso != PasoAcceso.Nuevo, visitante: true);
    }

    private void PonerAviso(string? texto)
    {
        Aviso.Text = texto ?? string.Empty;
        Aviso.IsVisible = !string.IsNullOrWhiteSpace(texto);
    }

    /// <summary>Las dos acciones fijas (RF-20). Si la institución apagó una (RN-37, RN-47) la otra ocupa todo el ancho.</summary>
    private void PintarPie(bool nuevo, bool visitante)
    {
        var n = nuevo && flujo?.OfreceRegistro == true;
        var v = visitante && flujo?.OfreceVisitante == true;
        NuevoButton.IsVisible = n;
        VisitanteButton.IsVisible = v;
        Pie.IsVisible = n || v;
        Grid.SetColumn(VisitanteButton, n ? 1 : 0);
        Grid.SetColumnSpan(VisitanteButton, n ? 1 : 2);
        Grid.SetColumnSpan(NuevoButton, v ? 1 : 2);
    }

    // ------------------------------------------------------------------------------------------------------------ (1) grupo

    private void PintarGrupos()
    {
        Titulo.Text = "¿Cuál es tu grupo?";
        Descripcion.Text = "Toca tu grupo para ver los nombres.";
        PonerAviso(aviso);
        if (avisoSinRed && flujo!.PuedeReintentar) PasoHost.Add(BotonReintentar());
        var botones = flujo!.Grupos.Select(g => (View)BotonOpcion(g.Nombre, AltoGrupo, async (_, _) => await AtenderAsync(c => flujo.ElegirGrupoAsync(g, c)), $"grupo-{g.Codigo}")).ToList();
        if (botones.Count > 0) PasoHost.Add(Rejilla(botones, ColumnasPara(anchoTarjeta, 170)));
        PasoHost.Add(BotonQuieto("Entrar con mi código", (_, _) => { flujo.EmpezarConCodigo(); aviso = null; PintarPaso(); }, "acceso-codigo"));
    }

    // ------------------------------------------------------------------------------------------------------------ (2) nombre

    private void PintarNombres()
    {
        Titulo.Text = "¿Quién eres?";
        Descripcion.Text = $"{flujo!.Grupo?.Nombre} · toca tu nombre.";
        PonerAviso(aviso ?? (flujo.EnPausa ? PausaTexto() : flujo.Alumnos.Count == 0
            ? "Todavía no hay nombres en este grupo. Si eres nuevo, toca «No estoy en la lista · soy nuevo»."
            : null));
        if (avisoSinRed && flujo.PuedeReintentar) PasoHost.Add(BotonReintentar());
        var botones = flujo.Alumnos.Select(a => (View)BotonOpcion(a.Alias, AltoTecla, (_, _) =>
        {
            if (ocupado) return;
            flujo.ElegirAlumno(a);
            aviso = null; avisoSinRed = false; primerDibujo = null;
            PintarPaso();
        }, $"alumno-{a.Id}")).ToList();
        if (botones.Count > 0) PasoHost.Add(Rejilla(botones, ColumnasPara(anchoTarjeta, 150)));
        PasoHost.Add(BotonQuieto("Entrar con mi código", (_, _) => { flujo.EmpezarConCodigo(); aviso = null; PintarPaso(); }, "acceso-codigo"));
    }

    // ------------------------------------------------------------------------------------------------------------ (3) PIN

    private void PintarPin()
    {
        Titulo.Text = $"Hola, {flujo!.Alumno?.Alias}";
        Descripcion.Text = flujo.UsaAvatar ? "Toca tu dibujo para entrar." : "Marca tu PIN para entrar.";
        PonerAviso(aviso);
        AgregarEntrada(valor => AtenderAsync(c => flujo.EntrarAsync(valor, c)));
        if (flujo.EnPausa) EmpezarPausa();
    }

    /// <summary>RF-22: «Todavía no tienes PIN. Elige uno de 4 números que recuerdes.» Se marca dos veces.</summary>
    private void PintarElegirPin()
    {
        var avatar = flujo!.UsaAvatar;
        Titulo.Text = avatar ? "Elige tu dibujo" : "Elige tu PIN";
        Descripcion.Text = flujo.Doble.Confirmando
            ? avatar ? FlujoDeAcceso.ConfirmaDibujo : FlujoDeAcceso.ConfirmaPin
            : avatar ? FlujoDeAcceso.PendienteDibujo
            : flujo.LongitudMinima == 4 ? MensajesDeAcceso.PinPendiente : $"Todavía no tienes PIN. Elige uno de {flujo.LongitudMinima} números que recuerdes.";
        PonerAviso(aviso);
        AgregarEntrada(MarcarNuevoAsync, flujo.Doble.Confirmando ? primerDibujo : null);
        if (flujo.EnPausa) EmpezarPausa();
    }

    /// <summary>El teclado propio (RF-00a) o, en preescolar, los dibujos (RF-28). Con «Reintentar» encima si lo último no llegó al nodo (RF-00e).</summary>
    private void AgregarEntrada(Func<string, Task> alEntregar, string? marcado = null)
    {
        if (avisoSinRed && flujo!.PuedeReintentar) PasoHost.Add(BotonReintentar());
        if (flujo!.UsaAvatar)
        {
            var util = Math.Max(200, anchoTarjeta - 80);
            var caben = (int)((util + 8) / (LadoDibujo + 8));
            dibujos = new AvatarPickerView { Lado = LadoDibujo, Separacion = 8, Columnas = caben >= 6 ? 6 : caben >= 4 ? 4 : caben >= 3 ? 3 : 2, HorizontalOptions = LayoutOptions.Center };
            dibujos.Marcar(marcado);
            dibujos.DibujoElegido += async (_, clave) => await alEntregar(clave);
            PasoHost.Add(dibujos);
            return;
        }
        teclado = new TecladoPinView
        {
            Longitud = FlujoDeAcceso.LongitudMaxima, LongitudMinima = flujo.LongitudMinima, TeclaAncho = AnchoTecla, TeclaAlto = AltoTecla, Separacion = 8,
            Acento = Ds.Rojo, HorizontalOptions = LayoutOptions.Center, AutomationId = "acceso-teclado",
        };
        teclado.PinCompleto += async (_, pin) => await alEntregar(pin);
        PasoHost.Add(teclado);
    }

    private string PausaTexto() =>
        $"Esperemos un momento: vuelve a probar en {FlujoDeAcceso.Cuenta(flujo!.SegundosDePausa)}, o entra como visitante.";

    /// <summary>RF-26: la tableta espera. El teclado se apaga y la cuenta baja cada segundo; «Entrar como visitante» sigue a la vista. No se nombra a nadie.</summary>
    private void EmpezarPausa()
    {
        if (teclado is not null) teclado.Habilitado = false;
        if (dibujos is not null) dibujos.Habilitado = false;
        PonerAviso(PausaTexto());
        relojPausa ??= Dispatcher.CreateTimer();
        relojPausa.Interval = TimeSpan.FromSeconds(1);
        relojPausa.Tick -= AlLatirLaPausa;
        relojPausa.Tick += AlLatirLaPausa;
        relojPausa.Start();
    }

    private void AlLatirLaPausa(object? sender, EventArgs e)
    {
        if (flujo is null) { relojPausa?.Stop(); return; }
        if (flujo.EnPausa) { PonerAviso(PausaTexto()); return; }
        relojPausa?.Stop();
        aviso = "Ya puedes volver a probar.";
        PintarPaso();
    }

    // ------------------------------------------------------------------------------------------------------------ soy nuevo

    private void PintarNuevo()
    {
        Titulo.Text = "Soy nuevo";
        if (subNuevo == SubpasoNuevo.Datos)
        {
            Descripcion.Text = "Escribe tu nombre y elige tu grupo. Después eliges tu PIN.";
            PonerAviso(aviso);
            PasoHost.Add(Etiqueta("Tu nombre"));
            PasoHost.Add(nombreNuevo);
            PasoHost.Add(Etiqueta("Tu apellido (si quieres)"));
            PasoHost.Add(apellidoNuevo);
            var grupos = flujo!.GruposParaRegistro;
            if (grupos.Count > 1 || flujo.Grupo is null)
            {
                PasoHost.Add(Etiqueta("Tu grupo"));
                PasoHost.Add(Rejilla(grupos.Select(g => (View)BotonOpcion(g.Nombre, AltoTecla, (_, _) =>
                {
                    flujo.ElegirGrupoParaRegistro(g);
                    aviso = null;
                    PintarPaso();
                }, $"nuevo-grupo-{g.Codigo}", marcado: g.Id == flujo.Grupo?.Id)).ToList(), ColumnasPara(anchoTarjeta, 150)));
            }
            else PasoHost.Add(Etiqueta($"Tu grupo: {flujo.Grupo!.Nombre}"));
            PasoHost.Add(BotonPrimario("Siguiente", (_, _) =>
            {
                var r = flujo.PrepararRegistro(nombreNuevo.Text, apellidoNuevo.Text);
                aviso = r.Ok ? null : r.Mensaje;
                if (r.Ok) { subNuevo = SubpasoNuevo.Pin; primerDibujo = null; }
                PintarPaso();
            }, "nuevo-siguiente"));
            return;
        }

        var avatar = flujo!.UsaAvatar;
        if (flujo.Sugerencia is { Length: > 0 } sugerencia)
        {
            // RN-34: el alias ya existe; con un toque se usa la variante con una letra más, sin volver a escribir ni a marcar nada.
            Descripcion.Text = "Tu nombre ya está en este grupo.";
            PonerAviso(aviso);
            PasoHost.Add(BotonPrimario($"Usar «{sugerencia}»", async (_, _) => await AtenderAsync(c => flujo.AceptarSugerenciaAsync(c)), "nuevo-sugerencia"));
            PasoHost.Add(BotonQuieto("Cambiar mi nombre", (_, _) => { flujo.EmpezarRegistro(); subNuevo = SubpasoNuevo.Datos; aviso = null; PintarPaso(); }, "nuevo-cambiar"));
            return;
        }
        Descripcion.Text = flujo.Doble.Confirmando
            ? avatar ? FlujoDeAcceso.ConfirmaDibujo : FlujoDeAcceso.ConfirmaPin
            : avatar ? "Elige un dibujo que recuerdes." : $"Elige un PIN de {flujo.LongitudMinima} números que recuerdes.";
        PonerAviso(aviso);
        AgregarEntrada(MarcarNuevoAsync, flujo.Doble.Confirmando ? primerDibujo : null);
    }

    // ------------------------------------------------------------------------------------------------------------ código y visitante

    private void PintarCodigo()
    {
        Titulo.Text = "Entrar con mi código";
        Descripcion.Text = "Escribe tu código y tu clave, como siempre.";
        PonerAviso(aviso);
        if (avisoSinRed && flujo!.PuedeReintentar) PasoHost.Add(BotonReintentar());
        PasoHost.Add(Etiqueta("Tu código"));
        PasoHost.Add(codigoEntry);
        PasoHost.Add(Etiqueta("Tu clave"));
        PasoHost.Add(claveEntry);
        PasoHost.Add(BotonPrimario("Entrar", async (_, _) =>
        {
            var codigo = codigoEntry.Text; var clave = claveEntry.Text;
            claveEntry.Text = string.Empty;   // la clave no se queda escrita (RF-00d)
            await AtenderAsync(c => flujo!.EntrarConCodigoAsync(codigo, clave, c));
        }, "codigo-entrar"));
    }

    private void PintarConfirmarVisitante()
    {
        Titulo.Text = "¿Entrar como visitante?";
        Descripcion.Text = "Podrás seguir la clase y practicar, pero lo que hagas no se guardará en tu historial.";
        PonerAviso(aviso);
        PasoHost.Add(BotonPrimario("Sí, entrar como visitante", async (_, _) => await AtenderAsync(c => flujo!.EntrarComoVisitanteAsync(c)), "visitante-si"));
        PasoHost.Add(BotonQuieto("No, volver", (_, _) => { confirmandoVisitante = false; aviso = null; PintarPaso(); }, "visitante-no"));
    }

    // ======================================================================================================================== piezas

    private View BotonReintentar() =>
        BotonPrimario("Reintentar", async (_, _) => await AtenderAsync(c => flujo!.ReintentarAsync(c)), "acceso-reintentar");

    /// <summary>La acción principal del paso (una sola por pantalla): el botón del kit, a la altura de «Entrar al aula».</summary>
    private static View BotonPrimario(string texto, EventHandler alTocar, string id)
    {
        var b = Ds.Boton(texto, Ds.Rango.Primary, alTocar, AltoTecla);
        b.AutomationId = id;
        return Ds.Capsula(b);
    }

    private static Button BotonQuieto(string texto, EventHandler alTocar, string id)
    {
        var b = Ds.Boton(texto, Ds.Rango.Quiet, alTocar, AltoTecla);
        b.AutomationId = id;
        b.FontSize = 15;
        b.TextColor = Ds.TintaSuave;
        return b;
    }

    /// <summary>Una opción grande (grupo o nombre): blanca, con filo, el texto en dos líneas si hace falta.</summary>
    private static Button BotonOpcion(string texto, double alto, EventHandler alTocar, string id, bool marcado = false)
    {
        var b = new Button
        {
            Text = texto, AutomationId = id, HeightRequest = alto, MinimumHeightRequest = alto, CornerRadius = 14, Padding = new Thickness(12, 0),
            FontSize = alto > AltoTecla ? 18 : 16, FontFamily = Ds.FuenteMedia, LineBreakMode = LineBreakMode.WordWrap,
            BackgroundColor = marcado ? Ds.Tinta : Colors.White, TextColor = marcado ? Colors.White : Ds.Tinta,
            BorderColor = Color.FromArgb("#26000000"), BorderWidth = 1,
        };
        b.Clicked += alTocar;
        return b;
    }

    private static Label Etiqueta(string texto) => new() { Text = texto, FontSize = 14, TextColor = Ds.TintaSuave, Margin = new Thickness(0, 4, 0, -6) };

    private static Grid Rejilla(IReadOnlyList<View> vistas, int columnas)
    {
        var rejilla = new Grid { ColumnSpacing = 10, RowSpacing = 10 };
        for (var c = 0; c < columnas; c++) rejilla.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Star));
        for (var f = 0; f < (vistas.Count + columnas - 1) / columnas; f++) rejilla.RowDefinitions.Add(new RowDefinition(GridLength.Auto));
        for (var i = 0; i < vistas.Count; i++) rejilla.Add(vistas[i], i % columnas, i / columnas);
        return rejilla;
    }
}
