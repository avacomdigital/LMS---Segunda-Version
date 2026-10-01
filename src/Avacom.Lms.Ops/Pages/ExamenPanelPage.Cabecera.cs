using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

// La cabecera del panel: qué examen es, en qué estado está, cuántos van en cada punto y qué se puede hacer con el examen entero (dar más tiempo,
// endurecer el plazo, bajar el nivel, cerrarlo, liberar los resultados). Cada decisión que el nodo pide motivar se ofrece como frases que se tocan; tocar
// la frase es la confirmación.
public partial class ExamenPanelPage
{
    private void PintarCabecera(PanelDeExamen p)
    {
        CabeceraHost.Clear();
        var a = p.Asignacion;
        var t = p.Totales;
        var ahora = RelojNodo.AhoraMs;

        // ---- quién es: título y grupo a la izquierda, cuántos van en cada punto a la derecha
        var izquierda = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        izquierda.Add(EstudioUi.Eyebrow($"EXAMEN{(string.IsNullOrWhiteSpace(a.CursoRotulo) ? string.Empty : " · " + a.CursoRotulo!.ToUpperInvariant())}"));
        izquierda.Add(new Label { Text = a.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 26, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 1 });
        izquierda.Add(Ds.Secundario(string.Join(" · ", new[]
        {
            a.GrupoRotulo,
            ExamenTexto.Plural(t.Destinatarios, "alumno", "alumnos"),
            a.PreguntasPorAlumno > 0 ? ExamenTexto.Plural(a.PreguntasPorAlumno, "pregunta", "preguntas") : null,
        }.Where(x => !string.IsNullOrWhiteSpace(x))), 15));

        var cuentas = new HorizontalStackLayout { Spacing = 22, VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.End };
        var esperanReactivacion = t.Suspendidos + t.Restaurando;
        var entregaron = t.Entregados + t.EnRevision + t.Calificados;
        var sinEmpezar = t.SinIntento + Math.Max(0, t.NoIniciados - p.Filas.Count(f => AdmisionVigente(f, a)));
        cuentas.Add(ExamenUi.Total(t.EnCurso, "presentando", ExamenUi.TintaInfo));
        cuentas.Add(ExamenUi.Total(esperanReactivacion, "esperan reactivación", ExamenUi.TintaAmbar));
        cuentas.Add(ExamenUi.Total(p.Filas.Count(f => AdmisionVigente(f, a)), "esperan admisión", ExamenUi.TintaAmbar));
        cuentas.Add(ExamenUi.Total(entregaron, "entregaron", ExamenUi.TintaExito));
        cuentas.Add(ExamenUi.Total(sinEmpezar, "sin empezar", Ds.TintaSuave));
        cuentas.Add(ExamenUi.Total(t.ConIncidentes, "con avisos", Ds.TintaMedia));
        if (t.PendientesDecision > 0) cuentas.Add(ExamenUi.Total(t.PendientesDecision, "envíos por decidir", ExamenUi.TintaVioleta));

        var cuerpo = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 30 };
        cuerpo.Add(izquierda, 0, 0);
        cuerpo.Add(cuentas, 1, 0);

        // ---- en qué estado está: una sola fila de pastillas a todo el ancho
        var pastillas = ExamenUi.Fila();
        pastillas.Add(ExamenUi.PildoraEnFila(ExamenTexto.EstadoAsignacion(a.Estado), ExamenTexto.TonoAsignacion(a.Estado), 13));
        pastillas.Add(ExamenUi.PildoraEnFila($"Nivel {Niveles.Rotulo(a.NivelExamen)}", Tono.Neutro, 13));
        if (!string.IsNullOrWhiteSpace(a.NivelDeclarado) && Niveles.Normalizar(a.NivelDeclarado) != Niveles.Normalizar(a.NivelExamen))
            pastillas.Add(ExamenUi.PildoraEnFila($"Bajado desde {Niveles.Rotulo(a.NivelDeclarado)}", Tono.Ambar, 13));
        // Pasada la fecha con el examen todavía abierto (plazo blando) se dice en ámbar sereno; un examen ya cerrado sólo recuerda cuál era su fecha.
        if (a.Abierta) pastillas.Add(ExamenUi.PildoraEnFila(ExamenTexto.Fecha(a.LimiteEn, ahora), a.LimiteEn is { } l && l <= ahora ? Tono.Ambar : Tono.Neutro, 13));
        else if (a.LimiteEn is { } limite) pastillas.Add(ExamenUi.PildoraEnFila($"Fecha límite: {ExamenTexto.Hora(limite)}", Tono.Neutro, 13));
        if (a.LimiteEn is not null) pastillas.Add(ExamenUi.PildoraEnFila(ExamenTexto.PlazoLegible(a.Plazo), Tono.Neutro, 13));
        pastillas.Add(ExamenUi.PildoraEnFila(a.Reactivacion == "automatica" ? "Reactivación automática" : "Reactivas tú", Tono.Neutro, 13));
        pastillas.Add(ExamenUi.PildoraEnFila(a.LiberadosEn is { } lib ? $"Resultados liberados a las {ExamenTexto.Hora(lib)}" : ExamenTexto.ResultadosLegible(a.Resultados),
            a.LiberadosEn is null ? Tono.Neutro : Tono.Exito, 13));

        var tarjeta = new VerticalStackLayout { Spacing = 8 };
        tarjeta.Add(cuerpo);
        tarjeta.Add(pastillas);
        tarjeta.Add(Acciones(p));
        CabeceraHost.Add(Ds.Tarjeta(tarjeta, Ds.RadioTarjeta, new Thickness(24, 16, 24, 8), Colors.White));
    }

    /// <summary>
    /// MSG-036: las tabletas que todavía no abrieron el examen y no alcanzan su nivel, con lo que cada una declara. Va arriba de la lista (se desplaza con ella)
    /// y desaparece sola cuando ya no queda ninguna por decidir. Los nombres van en una sola línea corrida para no crecer con el grupo.
    /// </summary>
    private View? BannerDeElegibilidad(PanelDeExamen p)
    {
        var a = p.Asignacion;
        if (!a.Abierta || _eleg is not { } eleg) return null;
        var sinAbrir = eleg.Filas
            .Where(f => f.Alcanza == false && p.Filas.FirstOrDefault(x => x.AlumnoId == f.AlumnoId) is { Estado: "sin_intento" or "no_iniciado" })
            .ToList();
        if (sinAbrir.Count == 0) return null;
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(new Label { Text = ExamenTexto.Msg036(sinAbrir.Count, a.NivelExamen), FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = ExamenUi.TintaAmbar, LineBreakMode = LineBreakMode.WordWrap });
        pila.Add(new Label
        {
            Text = string.Join("  ·  ", sinAbrir.Select(f => $"{f.Rotulo} ({(string.IsNullOrWhiteSpace(f.DispositivoNombre) ? "tableta sin nombre" : f.DispositivoNombre)}, {ExamenTexto.Capacidad(f.Capacidad).ToLowerInvariant()})")),
            FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = ExamenUi.TintaAmbar, LineBreakMode = LineBreakMode.WordWrap,
        });
        return ExamenUi.Zona(pila, Ds.AlertaSuave);
    }

    // ---------------------------------------------------------------------------- lo que se puede hacer con el examen

    private View Acciones(PanelDeExamen p)
    {
        var a = p.Asignacion;
        var t = p.Totales;
        var presentando = t.EnCurso + t.Suspendidos + t.Restaurando;
        var entregaron = t.Entregados + t.EnRevision + t.Calificados;
        var fila = ExamenUi.Fila();
        fila.Add(ExamenUi.Accion("‹  Volver", Ds.Rango.Quiet, VolverAsync, 130, "examen-volver").Vista);
        if (a.Abierta)
        {
            if (a.LimiteEn is not null) fila.Add(ExamenUi.Accion("Dar más tiempo", Ds.Rango.Secondary, DarMasTiempoAsync, null, "examen-mas-tiempo").Vista);
            if (a.Plazo != "endurecido") fila.Add(ExamenUi.Accion("Endurecer el plazo", Ds.Rango.Secondary, EndurecerPlazoAsync, null, "examen-endurecer").Vista);
            if (Niveles.Rango(a.NivelExamen) > 0) fila.Add(ExamenUi.Accion("Bajar el nivel", Ds.Rango.Secondary, BajarNivelAsync, null, "examen-bajar-nivel").Vista);
            fila.Add(ExamenUi.Accion("Cerrar el examen", Ds.Rango.Secondary, CerrarExamenAsync, null, "examen-cerrar").Vista);
        }
        // Los resultados se liberan sólo cuando nadie sigue presentando; mientras tanto el botón se ve apagado y dice por qué.
        if (a.Resultados == "tras_liberar" && a.LiberadosEn is null)
        {
            var liberar = ExamenUi.Accion("Liberar resultados", Ds.Rango.Secondary, LiberarResultadosAsync, null, "examen-liberar");
            Ds.Habilitar(liberar.Boton, presentando == 0 && entregaron > 0);
            fila.Add(liberar.Vista);
        }
        fila.Add(ExamenUi.Accion("Ver resultados", Ds.Rango.Secondary, VerResultadosAsync, null, "examen-ver-resultados").Vista);

        var pila = new VerticalStackLayout { Spacing = 2 };
        pila.Add(fila);
        if (a.Resultados == "tras_liberar" && a.LiberadosEn is null && presentando > 0)
            pila.Add(Ds.Secundario("Los resultados se pueden liberar cuando nadie siga presentando.", 14));
        return pila;
    }

    private Task VerResultadosAsync() => Shell.Current.GoToAsync($"examen-resultados?asignacion={Uri.EscapeDataString(AsignacionId)}");

    // ------------------------------------------------------------------------------ reactivar a todos (Guion, paso 12)

    private void PintarReactivarTodos(PanelDeExamen p)
    {
        ReactivarHost.Content = null;
        var n = p.Filas.Count(f => f.RequiereReactivacion);
        if (n == 0 || !p.Asignacion.Abierta) return;
        var texto = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        texto.Add(new Label
        {
            Text = n == 1 ? "1 alumno espera que lo reactives" : $"{n} alumnos esperan que los reactives",
            FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta,
        });
        texto.Add(Ds.Secundario("Todo lo que respondieron está guardado y su tiempo está detenido. Al reactivarlos, siguen desde donde iban.", 14));
        // Secondary y no Primary: en este panel nada llama la atención con el rojo de la marca; la zona ámbar y el texto ya dicen que hay alguien esperando.
        var boton = ExamenUi.Accion($"Reactivar a todos ({n})", Ds.Rango.Secondary, ReactivarATodosAsync, null, "examen-reactivar-todos", 64);
        boton.Vista.Margin = 0;
        boton.Vista.VerticalOptions = LayoutOptions.Center;
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 24 };
        fila.Add(texto, 0, 0);
        fila.Add(boton.Vista, 1, 0);
        var zona = ExamenUi.Zona(fila, Ds.AlertaSuave);
        zona.Margin = new Thickness(0, 10, 0, 0);
        zona.Padding = new Thickness(22, 12);
        ReactivarHost.Content = zona;
    }

    /// <summary>
    /// Guion, paso 12: PRIMERO se lee cuántos son (no cambia nada) y se dice «Vas a reactivar a N alumnos»; tocar el botón de la hoja es la única confirmación.
    /// </summary>
    private async Task ReactivarATodosAsync()
    {
        var api = Sesion.Evaluacion;
        var cuenta = await api.ContarSuspendidosAsync(Actor, AsignacionId);
        if (cuenta is null)
        {
            Avisar("No se pudo saber a cuántos reactivar", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
            return;
        }
        var n = cuenta.Suspendidos;
        if (n == 0)
        {
            Avisar("Nadie espera ser reactivado ahora", null, Tono.Info);
            await RefrescarAsync(forzar: true);
            return;
        }
        var cuantos = ExamenTexto.Plural(n, "alumno", "alumnos");
        var elegido = await _hoja.PedirAsync($"Vas a reactivar a {cuantos}",
            "Su examen sigue desde donde iba y el tiempo continúa desde el valor en que quedó detenido.",
            [new OpcionDeHoja("reactivar", $"Reactivar a {cuantos}", Principal: true)]);
        if (elegido is null) return;
        var hecho = await api.ReactivarTodosAsync(Actor, AsignacionId);
        if (hecho is null) Avisar("No se pudo reactivar", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else Avisar("Listo", $"Reactivaste a {ExamenTexto.Plural(hecho.Reactivados, "alumno", "alumnos")}. Su tiempo vuelve a correr.", Tono.Exito);
        await RefrescarAsync(forzar: true);
    }

    // ---------------------------------------------------------------------------------------------- dar más tiempo

    /// <summary>Prórroga: el nuevo plazo se cuenta desde la fecha vigente o desde ahora, la que sea más tarde. Frases, no un teclado.</summary>
    private async Task DarMasTiempoAsync()
    {
        if (_panel is not { } p) return;
        var a = p.Asignacion;
        var ahora = RelojNodo.AhoraMs;
        (string Clave, string Rotulo, int Minutos)[] horas = [("15", "15 minutos más", 15), ("30", "30 minutos más", 30), ("60", "1 hora más", 60), ("120", "2 horas más", 120)];
        var clave = await _hoja.PedirAsync("¿Cuánto tiempo más?",
            $"{ExamenTexto.Fecha(a.LimiteEn, ahora)}. El nuevo plazo se cuenta desde la fecha de cierre o desde ahora, la que sea más tarde.",
            horas.Select(h => new OpcionDeHoja(h.Clave, h.Rotulo)).ToList());
        if (clave is null) return;
        var minutos = horas.First(h => h.Clave == clave).Minutos;
        var limite = Math.Max(ahora, a.LimiteEn ?? 0) + minutos * 60_000L;
        var api = Sesion.Evaluacion;
        var r = await api.ProrrogarAsync(Actor, a.Id, limite);
        if (r is null) Avisar("No se pudo dar más tiempo", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else Avisar("Más tiempo", $"El examen cierra hacia las {ExamenTexto.Hora(limite)}.", Tono.Exito);
        await RefrescarAsync(forzar: true);
    }

    // ------------------------------------------------------------------------------------------ endurecer el plazo

    /// <summary>Endurecer (FUN-107): al vencer, el examen cierra y entrega lo respondido. Se elige la hora entre opciones.</summary>
    private async Task EndurecerPlazoAsync()
    {
        if (_panel is not { } p) return;
        var a = p.Asignacion;
        var ahora = RelojNodo.AhoraMs;
        var opciones = new List<OpcionDeHoja>();
        if (a.LimiteEn is { } actual && actual > ahora) opciones.Add(new OpcionDeHoja("actual", $"Con la hora de cierre actual ({ExamenTexto.Hora(actual)})"));
        opciones.Add(new OpcionDeHoja("15", "Que cierre en 15 minutos"));
        opciones.Add(new OpcionDeHoja("30", "Que cierre en 30 minutos"));
        opciones.Add(new OpcionDeHoja("60", "Que cierre en 1 hora"));
        var clave = await _hoja.PedirAsync("Endurecer el plazo",
            "Al llegar la hora, el examen se cierra y se entrega lo que cada alumno lleve. Ya no se sigue recibiendo después de la gracia.", opciones);
        if (clave is null) return;
        long? limite = clave == "actual" ? null : ahora + int.Parse(clave, System.Globalization.CultureInfo.InvariantCulture) * 60_000L;
        var api = Sesion.Evaluacion;
        var r = await api.EndurecerAsync(Actor, a.Id, limite);
        if (r is null) Avisar("No se pudo endurecer el plazo", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else Avisar("Plazo endurecido", $"El examen cierra a las {ExamenTexto.Hora(r.LimiteEn ?? limite ?? ahora)} y entrega lo respondido.", Tono.Exito);
        await RefrescarAsync(forzar: true);
    }

    // ------------------------------------------------------------------------------------------- bajar el nivel

    /// <summary>FUN-118: sólo baja (nunca sube). Primero a qué nivel, después por qué; la segunda frase es la confirmación.</summary>
    private async Task BajarNivelAsync()
    {
        if (_panel is not { } p) return;
        var a = p.Asignacion;
        var t = p.Totales;
        var presentando = t.EnCurso + t.Suspendidos + t.Restaurando;
        var bajos = ExamenTexto.NivelesMasBajos(a.NivelExamen);
        if (bajos.Count == 0) return;
        var afecta = presentando > 0
            ? $"Lo verán {ExamenTexto.Plural(presentando, "alumno que presenta ahora", "alumnos que presentan ahora")} en unos segundos, y quienes aún no empiezan comenzarán con el nivel nuevo."
            : "Nadie presenta ahora; quienes empiecen después lo harán con el nivel nuevo.";
        var nivel = await _hoja.PedirAsync("¿A qué nivel lo bajas?",
            $"Hoy es {Niveles.Rotulo(a.NivelExamen)}. Es un cambio de todo el examen y no se puede volver a subir. {afecta}",
            bajos.Select(n => new OpcionDeHoja(n, $"Bajar a {Niveles.Rotulo(n)}")).ToList());
        if (nivel is null) return;
        var motivo = await _hoja.PedirMotivoAsync($"¿Por qué lo bajas a {Niveles.Rotulo(nivel)}?", null, ExamenTexto.MotivosBajarNivel);
        if (motivo is null) return;
        var api = Sesion.Evaluacion;
        var r = await api.DegradarAsync(Actor, a.Id, nivel, motivo);
        if (r is null)
        {
            Avisar("No se pudo bajar el nivel", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
            return;
        }
        _eleg = null;   // el nivel cambió: la lista de tabletas que no alcanzan también
        Avisar("Nivel bajado", $"Ahora el examen es {Niveles.Rotulo(nivel)}. Las tabletas lo aplican en unos segundos.", Tono.Exito);
        await RefrescarAsync(forzar: true);
    }

    // ----------------------------------------------------------------------------------------------- cerrar el examen

    private async Task CerrarExamenAsync()
    {
        if (_panel is not { } p) return;
        var t = p.Totales;
        var presentando = t.EnCurso + t.Suspendidos + t.Restaurando;
        var texto = presentando > 0
            ? $"{ExamenTexto.Plural(presentando, "alumno sigue", "alumnos siguen")} presentando. Se entrega lo que lleven y nadie más podrá empezar."
            : "Nadie está presentando ahora. Nadie más podrá empezar.";
        var motivo = await _hoja.PedirMotivoAsync("¿Por qué cierras el examen?", texto, ExamenTexto.MotivosCerrarExamen);
        if (motivo is null) return;
        var api = Sesion.Evaluacion;
        var r = await api.CerrarAsync(Actor, p.Asignacion.Id, motivo);
        if (r is null) Avisar("No se pudo cerrar el examen", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else Avisar("Examen cerrado", presentando > 0 ? "Se entregó lo que cada alumno llevaba." : null, Tono.Exito);
        await RefrescarAsync(forzar: true);
    }

    // ----------------------------------------------------------------------------------------- liberar los resultados

    private async Task LiberarResultadosAsync()
    {
        if (_panel is not { } p) return;
        var elegido = await _hoja.PedirAsync("¿Liberar los resultados?",
            "Cada alumno podrá ver su resultado en su tableta. Lo que quede por revisar se libera cuando lo publiques.",
            [new OpcionDeHoja("liberar", "Liberar los resultados", Principal: true)]);
        if (elegido is null) return;
        var api = Sesion.Evaluacion;
        var r = await api.LiberarResultadosAsync(Actor, p.Asignacion.Id);
        // intentos_abiertos: todavía hay alguien presentando. El nodo lo rechaza y se dice con calma, sin culpar a nadie.
        if (r is null) Avisar("Todavía no se pueden liberar", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else Avisar("Resultados liberados", "Los alumnos ya pueden ver su resultado.", Tono.Exito);
        await RefrescarAsync(forzar: true);
    }
}
