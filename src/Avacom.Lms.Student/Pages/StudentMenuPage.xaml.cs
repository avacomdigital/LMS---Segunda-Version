namespace Avacom.Lms.Student.Pages;
public partial class StudentMenuPage : ContentPage
{
    // Tamaño del tablero en las unidades de diseño de OPS (teselas de 146 x 168, 20 de holgura abajo para las sombras) y lo que ocupan alrededor: cabecera (86), dock (96) y el saludo (~130).
    private const double EscenarioAncho = 543.5, EscenarioAlto = 461, ReservaVertical = 86 + 96 + 130;
    // Tope de lo que «Salir» hace hacia el nodo con el pase todavía vigente (avisar la salida y vaciar la cola): JRN-022 pide ≤ 3 s en total.
    private static readonly TimeSpan TopeDeSalida = TimeSpan.FromMilliseconds(1500);
    private bool _saliendo;
    public StudentMenuPage()
    {
        InitializeComponent();
        // El nombre visible es Sesion.Nombre: el alias de quien se identificó (007-10) o, sin sesión obligatoria, el nombre escrito.
        var name = Sesion.Nombre; var primero = name.Split(' ', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? name;
        StudentName.Text = primero; WelcomeLabel.Text = $"Bienvenido, {primero}"; Iniciales.Text = Avacom.Lms.Core.Models.Identidad.InicialesDe(name);
        AplicarPermisos();
    }

    /// <summary>
    /// RF-25 · RN-43: las teselas siguen los permisos de la sesión. Un visitante sigue la clase, lee sus asignaturas y practica, pero no tiene progreso, perfil ni
    /// evaluaciones (el nodo se lo negaría con <c>sesion_visitante_limitada</c>): esas teselas se atenúan y no responden, y «Exámenes» sale del dock.
    /// «Modo de estudio» se queda: con visitante muestra sólo la práctica y avisa que no se guarda (RF-24).
    /// </summary>
    private void AplicarPermisos()
    {
        var visitante = Sesion.EsVisitante;
        foreach (var tesela in new View[] { TeselaPerfil, TeselaProgreso })
        {
            tesela.Opacity = visitante ? 0.32 : 1;
            tesela.IsEnabled = !visitante;
            tesela.InputTransparent = visitante;
        }
        DockEvaluaciones.IsVisible = !visitante;
        RolLabel.Text = visitante ? "Visitante" : "Estudiante";
        if (visitante) { StudentName.Text = "Visitante"; WelcomeLabel.Text = "Bienvenido"; Iniciales.Text = "V"; }
    }
    /// <summary>
    /// «Modo de estudio» está en cualquier tableta. Con sesión obligatoria estudia quien entró por el acceso (RF-24: ya no se pregunta «¿Quién eres?»); con
    /// una visita sólo se ofrece dónde practicar. En modo prototipo (nodo sin sesión) se sigue eligiendo el nombre, como pedía D-15.
    /// </summary>
    private async void OnEstudio(object? sender, EventArgs e) => await Shell.Current.GoToAsync("estudio");
    /// <summary>«Exámenes» (MOD-010): lo que el profesor aplicó a esta persona. Sin sesión de usuario pregunta quién eres, sin código ni contraseña.</summary>
    private async void OnEvaluaciones(object? sender, EventArgs e) => await Shell.Current.GoToAsync("evaluaciones");
    private async void OnCourses(object? sender, EventArgs e) => await Shell.Current.GoToAsync("asignaturas");
    private async void OnClaseEnVivo(object? sender, EventArgs e) => await Shell.Current.GoToAsync("clase-unirse");

    /// <summary>
    /// «Salir» deja la tableta lista para la persona siguiente (BR-053, INV-011, JRN-022): sin confirmación ni animación de borrado y
    /// en ≤ 3 s. Lo local se limpia al instante (que nadie readmita a quien salió ni encuentre su nombre); con el pase todavía
    /// vigente se declara la salida al nodo y se empuja la cola de respuestas, ambas con tope de tiempo y sin bloquear la pantalla;
    /// después se cierra la sesión de la persona. El trabajo sin entregar NO se pierde: la cola sigue en disco y se envía sola (BR-137).
    /// </summary>
    private async void OnLogout(object? sender, EventArgs e)
    {
        if (_saliendo) return;
        _saliendo = true;
        try
        {
            var sesionId = Sesion.ClaseSesionId; var participanteId = Sesion.ClaseParticipanteId; var dispositivo = Sesion.Dispositivo;
            Sesion.OlvidarClase();
            Preferences.Default.Remove("student_name");   // la próxima persona no encuentra el nombre de la anterior

            using var tope = new CancellationTokenSource(TopeDeSalida);
            Task salida = sesionId is not null && participanteId is not null ? DeclararSalidaAsync(sesionId, participanteId, dispositivo, tope.Token) : Task.CompletedTask;
            Task cola = VaciarColaAsync(tope.Token);
            Task estudio = ModoEstudio.EstudioCompose.AlSalirAsync(tope.Token);   // FUN-089: cierra la sesión de estudio; lo pendiente sale solo (BR-137)
            await Task.WhenAny(Task.WhenAll(salida, cola, estudio), Task.Delay(TopeDeSalida));
            tope.Cancel();
            await Sesion.CerrarSesionDeUsuarioAsync();

            await Shell.Current.GoToAsync("//connection");
            Avisos.Mostrar("Listo. Tu trabajo queda guardado y se enviará solo. La tableta ya está libre para el siguiente.");   // MSG-024
        }
        catch (Exception ex)
        {
            Avacom.Lms.Core.Services.RegistroDeFallos.Escribir("student", "StudentMenuPage.Salir", ex);
            try { await Shell.Current.GoToAsync("//connection"); } catch { }
        }
        finally { _saliendo = false; }
    }

    private static async Task DeclararSalidaAsync(string sesionId, string participanteId, string dispositivo, CancellationToken ct)
    {
        try { await Sesion.Aula.PresenciaAsync(sesionId, participanteId, "salio", dispositivo, ct); } catch { /* el nodo lo resolverá por latido vencido (007-04) */ }
    }

    private static async Task VaciarColaAsync(CancellationToken ct)
    {
        try { await Sesion.Sincronizador.VaciarAsync(ct); } catch { /* lo que quede en la cola sale solo más tarde */ }
    }

    /// <summary>
    /// Escala el tablero al espacio disponible, como hace OPS con el suyo, pero también hacia arriba (hasta 1,5: la tesela más grande
    /// de la referencia) porque aquí se toca con el dedo. El contenedor toma el tamaño ya escalado para que el ScrollView lo mida bien
    /// y el tablero se escala desde su esquina superior izquierda.
    /// </summary>
    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0 || Height <= 0) return;
        var escala = Math.Clamp(Math.Min((Width - 32) / EscenarioAncho, (Height - ReservaVertical) / EscenarioAlto), 0.7, 1.5);
        Escenario.Scale = escala;
        EscenarioBox.WidthRequest = EscenarioAncho * escala;
        EscenarioBox.HeightRequest = EscenarioAlto * escala;
    }
}
