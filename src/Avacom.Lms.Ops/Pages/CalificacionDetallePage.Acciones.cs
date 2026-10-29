using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

// Lo que el profesor hace con una calificación: reabrir, publicar o retirar la publicación, valorar el nivel de desempeño, retroalimentar y ajustar. Cada acción lleva el permiso que
// el nodo le exige (la pantalla sólo evita ofrecer lo que no aplica), su motivo en frases y la versión que se leyó. Tocar la frase de un motivo es la confirmación: no se pregunta dos veces.
// Si el cambio no llega al nodo NO se da por hecho: se avisa «pendiente de confirmación» y tocar la misma acción otra vez con el mismo motivo reenvía LA MISMA solicitud (el nodo no duplica).
public partial class CalificacionDetallePage
{
    private const string QuitarValoracion = "__quitar_valoracion";

    // ----------------------------------------------------------------------------------------- qué puedes hacer

    private View QueHacer(Calificacion c)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion("Qué puedes hacer"));
        if (!CalificacionesUi.PuedeCalificar)
        {
            pila.Add(Ds.Secundario("Esta pantalla es de sólo lectura con tu rol: calificar, ajustar, reabrir y publicar lo hace el profesor del grupo.", 15));
            return ExamenUi.Tarjeta(pila);
        }
        if (c.Estado == EstadosDeCalificacion.Anulada)
        {
            pila.Add(Ds.Secundario("Esta calificación está anulada porque el intento se anuló: no cuenta y no hay cambios que hacer.", 15));
            return ExamenUi.Tarjeta(pila);
        }

        pila.Add(Ds.Secundario(c.Estado switch
        {
            EstadosDeCalificacion.Revisada => "Está revisada y el estudiante todavía no la ve. Puedes ajustarla aquí abajo, retroalimentar, publicarla o reabrirla para recalificar.",
            EstadosDeCalificacion.Definitiva => "Está publicada: el estudiante la ve. Un ajuste posterior queda marcado en el historial. Puedes retirar la publicación o reabrirla.",
            EstadosDeCalificacion.Reabierta => "Está reabierta: se recalifica desde la revisión y se vuelve a registrar al confirmarla.",
            _ => string.Empty,
        }, 14));

        var acciones = ExamenUi.Fila();
        if (c.Estado == EstadosDeCalificacion.Reabierta)
            acciones.Add(ExamenUi.Accion("Revisar y recalificar", Ds.Rango.Primary, CalificacionesUi.Seguro(nameof(CalificacionDetallePage), "Revisar",
                () => Shell.Current.GoToAsync($"revision-docente?intento={Uri.EscapeDataString(c.IntentoId)}")), null, "calificacion-revisar").Vista);
        if (GradebookTexto.PuedePublicar(c))
            acciones.Add(ExamenUi.Accion("Publicar", Ds.Rango.Primary, CalificacionesUi.Seguro(nameof(CalificacionDetallePage), "Publicar", PublicarAsync), null, "calificacion-publicar").Vista);
        if (GradebookTexto.PuedeRetirar(c))
            acciones.Add(ExamenUi.Accion("Retirar publicación", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionDetallePage), "Retirar", RetirarAsync), null, "calificacion-retirar").Vista);
        if (GradebookTexto.PuedeReabrir(c))
            acciones.Add(ExamenUi.Accion("Reabrir para recalificar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionDetallePage), "Reabrir", ReabrirAsync), null, "calificacion-reabrir").Vista);
        // La valoración sólo se ofrece si se pudieron leer los niveles de la escala (si no, se omite la acción).
        if (c.EsEditable && _tramos.Count > 0)
            acciones.Add(ExamenUi.Accion("Valorar el nivel de desempeño", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionDetallePage), "Valorar", ValorarAsync), null, "calificacion-valorar").Vista);
        acciones.Add(ExamenUi.Accion(_retroAbierta ? "Cerrar la retroalimentación" : "Retroalimentación", Ds.Rango.Secondary,
            CalificacionesUi.Seguro(nameof(CalificacionDetallePage), "Retroalimentacion", AlternarRetroalimentacionAsync), null, "calificacion-retroalimentar").Vista);
        pila.Add(acciones);
        return ExamenUi.Tarjeta(pila);
    }

    private Task AlternarRetroalimentacionAsync()
    {
        _retroAbierta = !_retroAbierta;
        if (_retro is not null) _retro.IsVisible = _retroAbierta && Actual.Estado != EstadosDeCalificacion.Anulada;
        Pintar();
        return Task.CompletedTask;
    }

    // --------------------------------------------------------------------------------- cambios de un solo toque

    /// <summary>
    /// Manda un cambio y cuenta cómo salió. <paramref name="firma"/> identifica la operación: la misma firma reutiliza la <c>solicitud_id</c> (reintento tras perder la señal) y cambiarla
    /// estrena otra. Un conflicto de versión avisa, vuelve a leer la calificación y no pierde nada; sin conexión, el cambio queda «pendiente de confirmación» y NUNCA se muestra como hecho.
    /// </summary>
    private async Task EjecutarCambioAsync(string que, SolicitudReintentable solicitud, string firma, Func<string, Task<CambioDeCalificacion?>> mandar, string exito, string? detalleDelExito)
    {
        var api = Api;
        var r = await mandar(solicitud.Para(firma));
        if (!_visible) return;
        if (r is null)
        {
            var error = api.UltimoError;
            var texto = CalificacionesUi.Error(api);
            if (GradebookTexto.EsConflictoDeVersion(error))
            {
                var (versionActual, puntajeActual) = TextoDeCalificaciones.ValorActualDelConflicto(error);
                var releida = await RelerAsync();
                var actual = releida ? $" Valor actual: {GradebookTexto.Puntaje(Actual.PuntajeEfectivo)} (versión {Actual.Version})."
                    : puntajeActual is { } p && versionActual is { } v ? $" Valor actual: {GradebookTexto.Puntaje(p)}." : string.Empty;
                _aviso.Mostrar("Otra persona cambió esta calificación", texto + actual, Tono.Ambar);
                return;
            }
            if (GradebookTexto.SinConexion(error))
                _aviso.Mostrar("Pendiente de confirmación", $"No se pudo conectar con el aula: «{que}» no se confirmó. Vuelve a tocarla con el mismo motivo para reintentar sin duplicar el cambio.", Tono.Ambar);
            else
                _aviso.Mostrar($"No se pudo: {que}", texto, Tono.Ambar);
            return;
        }
        solicitud.Soltar();
        AplicarCambio(r);
        _ajuste?.Actualizar(Actual);
        await CargarTramosAsync(Actual);
        _aviso.Mostrar(r.Reintento ? $"{exito} (ya estaba registrado)" : exito, detalleDelExito, Tono.Exito);
    }

    private async Task ReabrirAsync()
    {
        var c = Actual;
        var motivo = await _hoja.PedirMotivoAsync("¿Por qué reabres esta calificación?",
            "Deja de contar, el estudiante deja de verla y entra a la bandeja de revisión para que la recalifiques. El motivo queda en el historial.", FrasesDeCalificaciones.MotivosDeReapertura);
        if (motivo is null) return;
        await EjecutarCambioAsync("reabrir la calificación", _solReabrir, $"reabrir|{c.Id}|{c.Version}|{motivo}",
            id => Api.ReabrirAsync(CalificacionesUi.Actor, c.Id, motivo, c.Version, id), "Calificación reabierta", "Entró a la bandeja de revisión. Recalifícala y confirma la revisión para volver a registrarla.");
    }

    private async Task PublicarAsync()
    {
        var c = Actual;
        await EjecutarCambioAsync("publicar la calificación", _solPublicar, $"publicar|{c.Id}|{c.Version}",
            id => Api.PublicarAsync(CalificacionesUi.Actor, c.Id, c.Version, id), "Calificación publicada", "El estudiante ya puede ver la calificación presentada.");
    }

    private async Task RetirarAsync()
    {
        var c = Actual;
        var motivo = await _hoja.PedirMotivoAsync("¿Por qué retiras la publicación?", "El estudiante deja de ver la calificación y vuelve a quedar revisada, sin publicar.", FrasesDeCalificaciones.MotivosDeRetiro);
        if (motivo is null) return;
        await EjecutarCambioAsync("retirar la publicación", _solRetirar, $"retirar|{c.Id}|{c.Version}|{motivo}",
            id => Api.RetirarPublicacionAsync(CalificacionesUi.Actor, c.Id, motivo, c.Version, id), "Publicación retirada", "El estudiante ya no ve la calificación.");
    }

    /// <summary>
    /// La valoración pedagógica del nivel de desempeño (el profesor puede fijar un nivel distinto del que sale de la cuenta): se elige un nivel de la escala (o se quita la valoración) y después
    /// el motivo. No cambia el resultado interno. Tocar un nivel y tocar un motivo son las dos únicas decisiones.
    /// </summary>
    private async Task ValorarAsync()
    {
        var c = Actual;
        if (_tramos.Count == 0) return;
        var actual = c.Presentacion?.Desempeno.Clave;
        var opciones = _tramos.Select(t => new OpcionDeHoja(t.Clave, t.Clave == actual ? $"✓  {t.Etiqueta}" : t.Etiqueta)).ToList();
        if (!string.IsNullOrWhiteSpace(c.DesempenoDocente)) opciones.Add(new OpcionDeHoja(QuitarValoracion, "Quitar mi valoración (vuelve el nivel de la cuenta)"));
        var elegido = await _hoja.PedirAsync("¿Qué nivel de desempeño valoras?", "Es tu criterio pedagógico: no cambia el resultado interno ni la nota presentada por la cuenta.", opciones);
        if (elegido is null) return;
        var tramo = elegido == QuitarValoracion ? string.Empty : elegido;

        var motivo = await _hoja.PedirMotivoAsync(tramo.Length == 0 ? "¿Por qué quitas tu valoración?" : "¿Por qué valoras así el desempeño?", "Queda en el historial junto al nivel anterior y el nuevo.", FrasesDeCalificaciones.MotivosDeValoracion);
        if (motivo is null) return;
        var etiqueta = _tramos.FirstOrDefault(t => t.Clave == tramo)?.Etiqueta;
        await EjecutarCambioAsync("valorar el nivel de desempeño", _solValorar, $"valorar|{c.Id}|{c.Version}|{tramo}|{motivo}",
            id => Api.ValorarAsync(CalificacionesUi.Actor, c.Id, tramo, motivo, c.Version, id),
            tramo.Length == 0 ? "Valoración retirada" : "Nivel de desempeño valorado", tramo.Length == 0 ? "Vuelve el nivel que sale de la cuenta." : $"Nivel fijado por ti: {etiqueta}.");
    }

    // ------------------------------------------------------------------------------------ retroalimentar

    /// <summary>El panel pidió guardar la retroalimentación. El nodo conserva los apartados que no vienen.</summary>
    private async Task<RespuestaDeRetroalimentacion> RetroalimentarAsync(PeticionDeRetroalimentacion p)
    {
        var api = Api;
        var r = await api.RetroalimentarAsync(CalificacionesUi.Actor, CalificacionId, p.Campos, null, p.VersionEsperada, p.SolicitudId);
        if (r is not null)
        {
            AplicarCambio(r);
            _ajuste?.Actualizar(Actual);
            _aviso.Mostrar(r.Reintento ? "La retroalimentación ya estaba guardada" : "Retroalimentación guardada", "El estudiante la ve junto a su calificación cuando se publique.", Tono.Exito);
            return new RespuestaDeRetroalimentacion(ResultadoDeRetroalimentacion.Guardado);
        }
        var texto = CalificacionesUi.Error(api);
        if (GradebookTexto.EsConflictoDeVersion(api.UltimoError))
        {
            var releida = await RelerAsync();
            return new RespuestaDeRetroalimentacion(ResultadoDeRetroalimentacion.Conflicto, texto + (releida ? $" Valor actual: versión {Actual.Version}. Lo que elegiste sigue aquí: guárdalo de nuevo." : string.Empty));
        }
        return new RespuestaDeRetroalimentacion(GradebookTexto.SinConexion(api.UltimoError) ? ResultadoDeRetroalimentacion.SinConexion : ResultadoDeRetroalimentacion.Rechazado, texto);
    }

    // --------------------------------------------------------------------------------------------- ajustar

    /// <summary>
    /// El panel pidió confirmar un ajuste. Un 2xx es lo único que lo confirma. Con un conflicto de versión se vuelve a leer la calificación y se devuelve el valor actual para mostrarlo sin que el
    /// panel pierda lo que el profesor escribió; sin conexión, el panel queda «pendiente de confirmación» con la misma solicitud.
    /// </summary>
    private async Task<RespuestaDeAjuste> AjustarAsync(PeticionDeAjuste p)
    {
        var api = Api;
        var antes = Actual.PuntajeEfectivo;
        var r = await api.AjustarAsync(CalificacionesUi.Actor, CalificacionId, p.Puntaje, p.Motivo, p.VersionEsperada, p.SolicitudId);
        if (r is not null)
        {
            AplicarCambio(r);
            var c = r.Calificacion;
            var texto = r.Reintento
                ? $"El ajuste ya estaba registrado: no se duplicó (versión {c.Version})."
                : $"Ajuste registrado: de {GradebookTexto.Puntaje(antes)} a {GradebookTexto.Puntaje(c.PuntajeEfectivo)}, versión {c.Version}. Quedó en el historial con su motivo.";
            _aviso.Mostrar(r.Reintento ? "El ajuste ya estaba registrado" : "Ajuste confirmado", texto, Tono.Exito);
            return new RespuestaDeAjuste(ResultadoDeAjuste.Confirmado, texto);
        }

        var error = api.UltimoError;
        var mensaje = CalificacionesUi.Error(api);
        if (GradebookTexto.EsConflictoDeVersion(error))
        {
            var (versionActual, puntajeActual) = TextoDeCalificaciones.ValorActualDelConflicto(error);
            // Se vuelve a leer para mostrar el valor vigente (y dejar lista la versión nueva); lo que el profesor escribió sigue en el panel.
            var releida = await RelerAsync();
            string vigente;
            if (releida) vigente = $"El valor actual es {GradebookTexto.Puntaje(Actual.PuntajeEfectivo)} (versión {Actual.Version}).";
            else if (puntajeActual is { } p2 && versionActual is { } v2) vigente = $"El valor actual es {GradebookTexto.Puntaje(p2)}.";
            else vigente = "No se pudo volver a leer el valor actual: actualiza la pantalla.";
            return new RespuestaDeAjuste(ResultadoDeAjuste.Conflicto, $"{mensaje} {vigente} Lo que escribiste se conserva: revísalo y confirma de nuevo.");
        }
        return new RespuestaDeAjuste(GradebookTexto.SinConexion(error) ? ResultadoDeAjuste.SinConexion : ResultadoDeAjuste.Rechazado, mensaje);
    }
}
