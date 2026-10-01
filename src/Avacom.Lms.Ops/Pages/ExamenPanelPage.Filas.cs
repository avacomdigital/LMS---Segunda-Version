using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

// Las filas del panel: una por alumno, en el orden que manda el nodo. Cada fila dice en palabras de aula en qué punto va el alumno (nunca el nombre del enum), su
// tableta y si alcanza el nivel, cuánto lleva respondido, el cronómetro (nunca rojo, nunca parpadea) y, sólo si hace falta, las acciones que el profesor puede
// tomar ahí mismo. Tocar la fila abre el expediente. La fila NO ofrece anular.
public partial class ExamenPanelPage
{
    /// <summary>Lo que el cronómetro de una fila necesita para seguir corriendo entre dos lecturas del nodo.</summary>
    private sealed class RelojDeFila
    {
        public required Label Reloj { get; init; }
        public Label? Pie { get; init; }
        public Label? Silencio { get; init; }
        public long? RestanteMs { get; set; }
        public long? SilencioMs { get; set; }
        public bool Corriendo { get; set; }
        public long LeidoEn { get; set; }
    }

    private readonly Dictionary<string, RelojDeFila> _relojes = [];

    private void PintarFilas(PanelDeExamen p)
    {
        var y = Desplazable.ScrollY;
        FilasHost.Clear();
        _relojes.Clear();
        if (p.Filas.Count == 0)
        {
            FilasHost.Add(ExamenUi.Tarjeta(Ds.Secundario("Este grupo no tiene alumnos todavía. Cuando se inscriban, aparecerán aquí.", 16)));
            return;
        }
        if (BannerDeElegibilidad(p) is { } banner) FilasHost.Add(banner);
        var leidoEn = Environment.TickCount64;
        foreach (var f in p.Filas) FilasHost.Add(Fila(p, f, leidoEn));
        if (y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }

    // ---------------------------------------------------------------------------------------------- cronómetros

    /// <summary>Entre dos lecturas del nodo, el cronómetro avanza cada segundo con la hora que el nodo dio. No consulta nada.</summary>
    private void OnSegundo(object? sender, EventArgs e) => AvanzarRelojes();

    private void AvanzarRelojes()
    {
        var ahora = Environment.TickCount64;
        foreach (var r in _relojes.Values)
        {
            var pasado = ahora - r.LeidoEn;
            if (r.RestanteMs is { } restante) r.Reloj.Text = ExamenTexto.Reloj(r.Corriendo ? restante - pasado : restante);
            if (r.Silencio is not null && r.SilencioMs is { } silencio) r.Silencio.Text = $"Sin señal hace {ExamenTexto.Silencio(silencio + pasado)}";
        }
    }

    /// <summary>La lista no cambió: sólo se renuevan las horas de base de cada fila.</summary>
    private void PonerAlDiaLosRelojes(PanelDeExamen p)
    {
        var leidoEn = Environment.TickCount64;
        foreach (var f in p.Filas)
        {
            if (f.Reloj is not { } reloj || !_relojes.TryGetValue(f.AlumnoId, out var r)) continue;
            r.RestanteMs = reloj.RestanteMs;
            r.Corriendo = reloj.Corriendo;
            r.SilencioMs = f.SilencioMs;
            r.LeidoEn = leidoEn;
        }
        AvanzarRelojes();
    }

    // ------------------------------------------------------------------------------------------------ una fila

    /// <summary>
    /// ¿Esta fila espera de verdad una decisión de admisión? Una solicitud en espera deja de pedir nada si el profesor bajó el nivel del examen y la tableta ya lo
    /// alcanza: cuando el alumno vuelva a pulsar «Comenzar», el nodo abre su intento sin más trámite.
    /// </summary>
    private static bool AdmisionVigente(FilaDelPanel f, AsignacionDeExamen a) =>
        f.Admision is { Estado: "en_espera" } adm && !Niveles.Alcanza(adm.NivelAlcanzado, a.NivelExamen) && a.Abierta;

    private static bool Terminada(FilaDelPanel f) => f.Estado is EstadosIntento.Entregado or EstadosIntento.EnRevision or EstadosIntento.Calificado or EstadosIntento.Anulado;

    private static Border Mini(string texto, Tono tono, double tamano = 12)
    {
        var p = ExamenUi.Pildora(texto, tono, tamano);
        p.Margin = new Thickness(0, 2, 6, 2);
        return p;
    }

    private View Fila(PanelDeExamen panel, FilaDelPanel f, long leidoEn)
    {
        var a = panel.Asignacion;
        var terminada = Terminada(f);
        var info = new Grid
        {
            ColumnDefinitions =
            [
                new ColumnDefinition(300), new ColumnDefinition(270), new ColumnDefinition(190), new ColumnDefinition(130),
                new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto),
            ],
            ColumnSpacing = 18, VerticalOptions = LayoutOptions.Center,
        };
        info.Add(Alumno(f, a, terminada), 0, 0);
        info.Add(Estado(f, a, terminada, leidoEn), 1, 0);
        info.Add(Avance(f, terminada), 2, 0);
        info.Add(Cronometro(f, leidoEn), 3, 0);
        info.Add(Marcas(f, a, terminada), 4, 0);
        // Tocar la información abre el expediente; los botones de abajo no, para que un toque en «Reactivar» nunca abra otra pantalla.
        if (f.IntentoId is { } intento)
        {
            info.Add(new Label { Text = "›", FontFamily = Ds.FuenteLigera, FontSize = 32, TextColor = Ds.TintaSuave, VerticalOptions = LayoutOptions.Center }, 5, 0);
            Ds.Tocable(info, () => Shell.Current.GoToAsync($"examen-expediente?intento={Uri.EscapeDataString(intento)}"));
            SemanticProperties.SetDescription(info, $"Expediente de {f.Rotulo}");
        }

        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(info);
        if (Acciones(panel, f) is { } acciones) pila.Add(acciones);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 14), Colors.White);
    }

    private static View Alumno(FilaDelPanel f, AsignacionDeExamen a, bool terminada)
    {
        var pila = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        pila.Add(new Label { Text = f.Rotulo, FontFamily = Ds.FuenteMedia, FontSize = 19, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation });
        var tableta = ExamenUi.Fila();
        if (f.Dispositivo is { } d)
        {
            tableta.Add(new Label
            {
                Text = string.IsNullOrWhiteSpace(d.Nombre) ? "Tableta" : d.Nombre, FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaSuave,
                VerticalOptions = LayoutOptions.Center, Margin = new Thickness(0, 2, 8, 2), LineBreakMode = LineBreakMode.TailTruncation,
            });
            tableta.Add(Mini(ExamenTexto.Capacidad(d.Capacidad), Tono.Neutro));
            if (!d.Alcanza && !terminada && a.Abierta) tableta.Add(Mini("No alcanza el nivel", Tono.Ambar));
        }
        else tableta.Add(Ds.Secundario("Sin tableta conocida todavía", 14));
        pila.Add(tableta);
        return pila;
    }

    private View Estado(FilaDelPanel f, AsignacionDeExamen a, bool terminada, long leidoEn)
    {
        var pila = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        // Con el examen ya cerrado, quien no llegó a presentar no está «esperando» nada: no presentó.
        var noPresento = !a.Abierta && f.Estado is "no_iniciado" or "sin_intento";
        var enEspera = a.Abierta && AdmisionVigente(f, a);
        var yaPuede = a.Abierta && f.Admision is { Estado: "en_espera" } && !enEspera;
        string texto;
        Tono tono;
        if (noPresento) { texto = "No presentó"; tono = Tono.Gris; }
        else if (enEspera) { texto = "Esperando tu decisión"; tono = Tono.Ambar; }
        else if (yaPuede) { texto = "Ya puede comenzar"; tono = Tono.Info; }
        else if (f.EnvioTardio == "pendiente_decision") { texto = "Envío tardío: tú decides"; tono = Tono.Violeta; }
        else if (f.Admision is { Estado: "rechazado" } && f.Estado is "no_iniciado" or "sin_intento") { texto = "Tableta no admitida"; tono = Tono.Gris; }
        else { texto = ExamenTexto.EstadoIntento(f.Estado); tono = ExamenTexto.TonoIntento(f.Estado); }
        var pastilla = ExamenUi.Pildora(texto, tono, 14);
        SemanticProperties.SetDescription(pastilla, $"{f.Rotulo}: {texto}");
        pila.Add(pastilla);

        if (enEspera)
            pila.Add(Ds.Secundario($"Su tableta declara {ExamenTexto.Capacidad(f.Admision!.NivelAlcanzado).ToLowerInvariant()}; el examen pide {Niveles.Rotulo(a.NivelExamen).ToLowerInvariant()}", 13));
        else if (yaPuede)
            pila.Add(Ds.Secundario("Con el nivel nuevo su tableta ya alcanza", 13));
        else if (f.Estado == EstadosIntento.Anulado)
            pila.Add(Ds.Secundario($"Anulado por {ExamenTexto.Persona(f.AnuladoPor)}", 13));
        else if (terminada && ExamenTexto.OrigenEntrega(f.OrigenEntrega) is { Length: > 0 } origen)
            pila.Add(Ds.Secundario(origen, 13));
        else if (f.Numero is > 1) pila.Add(Ds.Secundario($"Intento {f.Numero}", 13));

        // La señal: sólo cuando hace falta decirla (un alumno suspendido, o una tableta que lleva un buen rato callada). Nunca un color de alarma.
        var silencio = f.SilencioMs ?? 0;
        if (f.Reloj is not null && (f.RequiereReactivacion || silencio >= SilencioVisibleMs))
        {
            var etiqueta = Ds.Secundario($"Sin señal hace {ExamenTexto.Silencio(silencio)}", 13);
            pila.Add(etiqueta);
            _relojes[f.AlumnoId] = new RelojDeFila { Reloj = new Label(), Silencio = etiqueta, SilencioMs = f.SilencioMs, LeidoEn = leidoEn };   // el reloj de la fila se registra abajo
        }
        return pila;
    }

    private static View Avance(FilaDelPanel f, bool terminada)
    {
        var pila = new VerticalStackLayout { Spacing = 5, VerticalOptions = LayoutOptions.Center };
        if (f.IntentoId is null || f.Total == 0)
        {
            pila.Add(Ds.Secundario("—", 17));
            return pila;
        }
        pila.Add(new Label { Text = $"{f.Respondidas} de {f.Total}", FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta });
        pila.Add(EstudioUi.Barra(f.Total == 0 ? 0 : (double)f.Respondidas / f.Total, terminada ? Ds.Exito : Ds.Info, 8));
        if (f.Porcentaje is { } pct && f.Estado != EstadosIntento.Anulado)
            pila.Add(Ds.Secundario(f.Estado == EstadosIntento.EnRevision ? $"Parcial: {ExamenTexto.Porcentaje(pct)}" : ExamenTexto.Porcentaje(pct), 13));
        return pila;
    }

    private View Cronometro(FilaDelPanel f, long leidoEn)
    {
        var pila = new VerticalStackLayout { Spacing = 1, VerticalOptions = LayoutOptions.Center };
        if (f.Reloj is not { } reloj)
        {
            pila.Add(Ds.Secundario("—", 17));
            return pila;
        }
        var etiqueta = new Label
        {
            Text = ExamenTexto.Reloj(reloj.RestanteMs), FontFamily = Ds.FuenteMedia, FontSize = 22, TextColor = Ds.Tinta,
        };
        var pie = Ds.Secundario(reloj.RestanteMs is null ? "sin cronómetro" : reloj.Corriendo ? "restante" : "detenido", 13);
        pila.Add(etiqueta);
        pila.Add(pie);
        // Si la señal ya se registró en Estado(), se conserva su etiqueta y se le suma el cronómetro.
        _relojes.TryGetValue(f.AlumnoId, out var previo);
        _relojes[f.AlumnoId] = new RelojDeFila
        {
            Reloj = etiqueta, Pie = pie, Silencio = previo?.Silencio, SilencioMs = f.SilencioMs, RestanteMs = reloj.RestanteMs, Corriendo = reloj.Corriendo, LeidoEn = leidoEn,
        };
        return pila;
    }

    private static View Marcas(FilaDelPanel f, AsignacionDeExamen a, bool terminada)
    {
        var fila = ExamenUi.Fila();
        fila.VerticalOptions = LayoutOptions.Center;
        if (f.Incidentes is { Total: > 0 } inc)
        {
            var tono = inc.Alta > 0 ? Tono.AmbarFuerte : inc.Atencion > 0 ? Tono.Ambar : Tono.Neutro;
            fila.Add(Mini(ExamenTexto.Plural(inc.Total, "aviso", "avisos"), tono, 13));
        }
        if (!terminada && ExamenTexto.Bloqueo(f.Bloqueo?.Resultado) is { } bloqueo && f.Bloqueo?.Resultado is ResultadosDeBloqueo.Parcial or ResultadosDeBloqueo.Fallido)
            fila.Add(Mini(bloqueo, Tono.Ambar, 13));
        if (f.FueraDePlazo) fila.Add(Mini("Fuera de plazo", Tono.Ambar, 13));
        if (!terminada && !string.IsNullOrWhiteSpace(f.NivelEfectivo) && Niveles.Normalizar(f.NivelEfectivo) != Niveles.Normalizar(a.NivelExamen))
            fila.Add(Mini($"Presenta en nivel {Niveles.Rotulo(f.NivelEfectivo)}", Tono.Neutro, 13));
        return fila;
    }

    // ------------------------------------------------------------------------- lo que se puede hacer con un alumno

    /// <summary>Sólo las filas que necesitan al profesor traen acciones: admisión, reactivación o un envío tardío. Ninguna ofrece anular.</summary>
    private View? Acciones(PanelDeExamen panel, FilaDelPanel f)
    {
        var texto = new Label { FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = ExamenUi.TintaAmbar, LineBreakMode = LineBreakMode.WordWrap, VerticalOptions = LayoutOptions.Center };
        // Los botones van en una sola línea, a la derecha del texto: ninguna fila crece por tener decisiones pendientes.
        var botones = new HorizontalStackLayout { Spacing = 10, VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.End };
        View Boton(string rotulo, Ds.Rango rango, Func<Task> accion, double? ancho, string id) => ExamenUi.Accion(rotulo, rango, accion, ancho, id, 56, margen: false).Vista;
        var id = f.AlumnoId;

        if (panel.Asignacion.Abierta && f.Admision is { Estado: "en_espera" or "rechazado" } adm && f.Estado is "no_iniciado" or "sin_intento"
            && (adm.Estado == "rechazado" || AdmisionVigente(f, panel.Asignacion)))
        {
            var rechazada = adm.Estado == "rechazado";
            var pide = Niveles.Rotulo(panel.Asignacion.NivelExamen).ToLowerInvariant();
            texto.Text = rechazada
                ? $"Rechazaste la tableta de {f.Rotulo}. Si cambias de idea, puedes admitirla."
                : $"La tableta de {f.Rotulo} declara {ExamenTexto.Capacidad(adm.NivelAlcanzado).ToLowerInvariant()} y el examen pide {pide}. Tú decides: puede presentar en un nivel menor o cambiar de tableta.";
            foreach (var nivel in ExamenTexto.NivelesMasBajos(panel.Asignacion.NivelExamen))
            {
                var n = nivel;
                botones.Add(Boton($"Admitir en {Niveles.Rotulo(n)}", Ds.Rango.Secondary, () => AdmitirAsync(f, n), null, $"examen-admitir-{n}-{id}"));
            }
            if (!rechazada) botones.Add(Boton("Rechazar", Ds.Rango.Quiet, () => RechazarAsync(f), null, $"examen-rechazar-{id}"));
        }
        else if (f.RequiereReactivacion && f.IntentoId is not null)
        {
            texto.Text = $"El tiempo de {f.Rotulo} está detenido y todo lo que respondió está guardado. Cuando lo reactives, sigue desde donde iba.";
            botones.Add(Boton("Reactivar", Ds.Rango.Secondary, () => ReactivarAsync(f), 190, $"examen-reactivar-{id}"));
            botones.Add(Boton("Cerrar su examen", Ds.Rango.Quiet, () => CerrarSuExamenAsync(f), null, $"examen-cerrar-intento-{id}"));
        }
        else if (f.EnvioTardio == "pendiente_decision" && f.IntentoId is not null)
        {
            texto.Text = $"{f.Rotulo} respondió a tiempo, pero su tableta lo mandó después de la gracia. Tú decides si cuenta.";
            botones.Add(Boton("Aceptar", Ds.Rango.Secondary, () => DecidirEnvioAsync(f, "aceptar"), 170, $"examen-aceptar-{id}"));
            botones.Add(Boton("Descartar", Ds.Rango.Quiet, () => DecidirEnvioAsync(f, "descartar"), 170, $"examen-descartar-{id}"));
        }
        else return null;

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 24 };
        fila.Add(texto, 0, 0);
        fila.Add(botones, 1, 0);
        var zona = ExamenUi.Zona(fila, Ds.AlertaSuave);
        zona.Padding = new Thickness(18, 10);
        return zona;
    }

    private async Task ReactivarAsync(FilaDelPanel f)
    {
        if (f.IntentoId is null) return;
        var api = Sesion.Evaluacion;
        var r = await api.ReactivarAsync(Actor, f.IntentoId);
        if (r is null) Avisar($"No se pudo reactivar a {f.Rotulo}", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else Avisar($"{f.Rotulo} puede continuar", r.RestanteMs is { } restante ? $"Le quedan {ExamenTexto.Reloj(restante)}." : null, Tono.Exito);
        await RefrescarAsync(forzar: true);
    }

    /// <summary>«Cierre forzado»: entrega lo que el alumno respondió. Es para quien no va a volver; una sola confirmación, en la hoja.</summary>
    private async Task CerrarSuExamenAsync(FilaDelPanel f)
    {
        if (f.IntentoId is null) return;
        var elegido = await _hoja.PedirAsync($"¿Cerrar el examen de {f.Rotulo}?",
            $"Se entrega lo que respondió hasta ahora ({f.Respondidas} de {f.Total}). Úsalo cuando no va a volver; si todavía puede volver, mejor reactívalo.",
            [new OpcionDeHoja("cerrar", "Cerrar su examen", Principal: true)]);
        if (elegido is null) return;
        var api = Sesion.Evaluacion;
        if (await api.CerrarIntentoAsync(Actor, f.IntentoId)) Avisar($"Se entregó el examen de {f.Rotulo}", "Quedó lo que había respondido.", Tono.Exito);
        else Avisar($"No se pudo cerrar el examen de {f.Rotulo}", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        await RefrescarAsync(forzar: true);
    }

    private async Task AdmitirAsync(FilaDelPanel f, string nivel)
    {
        if (f.Admision is not { } adm) return;
        var motivo = await _hoja.PedirMotivoAsync($"¿Por qué admites a {f.Rotulo} en {Niveles.Rotulo(nivel)}?",
            $"Presentará con nivel {Niveles.Rotulo(nivel).ToLowerInvariant()}, más bajo que {Niveles.Rotulo(_panel?.Asignacion.NivelExamen ?? adm.NivelExigido).ToLowerInvariant()}. Queda registrado.", ExamenTexto.MotivosAdmitir);
        if (motivo is null) return;
        var api = Sesion.Evaluacion;
        var r = await api.DecidirAdmisionAsync(Actor, AsignacionId, adm.Id, "admitir", nivel, motivo);
        if (r is null) Avisar($"No se pudo admitir a {f.Rotulo}", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else Avisar($"{f.Rotulo} puede entrar", $"Cuando vuelva a pulsar «Comenzar», empezará su examen en nivel {Niveles.Rotulo(nivel).ToLowerInvariant()}.", Tono.Exito);
        await RefrescarAsync(forzar: true);
    }

    private async Task RechazarAsync(FilaDelPanel f)
    {
        if (f.Admision is not { } adm) return;
        var motivo = await _hoja.PedirMotivoAsync($"¿Por qué rechazas la tableta de {f.Rotulo}?",
            "No presentará con esa tableta. Puede cambiar de tableta, o puedes admitirla después si cambias de idea.", ExamenTexto.MotivosRechazar);
        if (motivo is null) return;
        var api = Sesion.Evaluacion;
        var r = await api.DecidirAdmisionAsync(Actor, AsignacionId, adm.Id, "rechazar", null, motivo);
        if (r is null) Avisar($"No se pudo rechazar la tableta de {f.Rotulo}", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else Avisar("Tableta rechazada", $"{f.Rotulo} verá que debe avisarte para continuar.", Tono.Info);
        await RefrescarAsync(forzar: true);
    }

    private async Task DecidirEnvioAsync(FilaDelPanel f, string decision)
    {
        if (f.IntentoId is null) return;
        var acepta = decision == "aceptar";
        var motivo = await _hoja.PedirMotivoAsync(acepta ? $"¿Por qué aceptas el envío de {f.Rotulo}?" : $"¿Por qué descartas el envío de {f.Rotulo}?",
            acepta ? "Lo que mandó se suma a su examen y se vuelve a calificar." : "Lo que mandó se conserva como evidencia, pero no cuenta.",
            acepta ? ExamenTexto.MotivosAceptarEnvio : ExamenTexto.MotivosDescartarEnvio);
        if (motivo is null) return;
        var api = Sesion.Evaluacion;
        if (await api.DecidirEnvioAsync(Actor, f.IntentoId, decision, motivo))
            Avisar("Listo", acepta ? $"Aceptaste el envío de {f.Rotulo}." : $"Descartaste el envío de {f.Rotulo}; queda como evidencia.", Tono.Exito);
        else Avisar("No se pudo guardar tu decisión", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        await RefrescarAsync(forzar: true);
    }
}
