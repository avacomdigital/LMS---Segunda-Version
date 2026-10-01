using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Pestaña «Errores» (PAN-240/242): las últimas líneas de los logs del nodo y de los equipos (<c>GET /api/logs/</c>) por canal, nivel y app,
/// con el chip de ruta happy/sad/bad; sin datos personales. Y «Estado del equipo» (PAN-242, técnico): servidor, versión, aparato, cola
/// de logs pendiente, espacio y «Exportar diagnóstico» (§3.6: un ZIP con los logs, la versión y la configuración no sensible).
/// </summary>
public partial class BitacoraPage
{
    private string? _lApp, _lCanal, _lNivel;

    private async Task<View> ErroresAsync()
    {
        var api = Sesion.Logs;
        var logs = await api.LeerAsync(new FiltrosLogs(App: _lApp, Canal: _lCanal, Nivel: _lNivel, Ultimos: 80));
        if (logs is null) return TarjetaDeError("No se pudieron leer los logs del nodo", api.UltimoMotivo, () => MostrarAsync(Pestana.Errores), api.UltimoError);

        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(FiltrosDeLogs(logs));
        if (logs.Lineas.Count == 0) pila.Add(Vacio("Sin líneas con estos filtros", "Los logs de diagnóstico se purgan por rotación; no son evidencia. La bitácora sí."));
        foreach (var l in logs.Lineas.AsEnumerable().Reverse()) pila.Add(FilaLog(l));
        return pila;
    }

    private View FiltrosDeLogs(LogsDelNodo logs)
    {
        var app = new FilterPicker { Placeholder = "Todas las apps", WidthRequest = 180 };
        app.Poblar(["backend", "ops", "student"]);
        app.Elegir(_lApp);
        var canal = new FilterPicker { Placeholder = "Todos los canales", WidthRequest = 200 };
        canal.Poblar(["escritura", "comunicacion", "dispositivo", "aplicacion", "auditoria", "instalacion"]);
        canal.Elegir(_lCanal);
        var nivel = new FilterPicker { Placeholder = "Todos los niveles", WidthRequest = 180 };
        nivel.Poblar(["WARNING", "ERROR", "CRITICAL", "INFO", "DEBUG"]);
        nivel.Elegir(_lNivel);
        app.SelectionChanged += async (_, _) => { _lApp = app.Selected; await MostrarAsync(Pestana.Errores); };
        canal.SelectionChanged += async (_, _) => { _lCanal = canal.Selected; await MostrarAsync(Pestana.Errores); };
        nivel.SelectionChanged += async (_, _) => { _lNivel = nivel.Selected; await MostrarAsync(Pestana.Errores); };
        var fila = new HorizontalStackLayout { Spacing = 10, Children = { app, canal, nivel } };
        var resumen = logs.Resumen is { } r ? $"happy {r.Happy} · sad {r.Sad} · bad {r.Bad} · {logs.Total} líneas, se muestran las últimas {logs.Lineas.Count}" : $"{logs.Total} líneas";
        var pila = new VerticalStackLayout { Spacing = 8, Children = { fila, Ds.Secundario(resumen, 14) } };
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(18, 14), Colors.White);
    }

    private View FilaLog(LineaLog l)
    {
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(150), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(110), new ColumnDefinition(80), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        var ts = l.Ts is { Length: >= 19 } t ? t.Substring(5, 14).Replace('T', ' ') : l.Ts ?? "—";
        fila.Add(Ds.Secundario(ts, 12), 0, 0);
        var nivel = l.Nivel switch
        {
            "ERROR" or "CRITICAL" => Chip(l.Nivel, Ds.PeligroSuave, TintaPeligro),
            "WARNING" => Chip("WARNING", Ds.AlertaSuave, TintaAlerta),
            _ => Chip(l.Nivel ?? "—", Color.FromArgb("#EEEEF0"), Ds.TintaSuave),
        };
        fila.Add(nivel, 1, 0);
        fila.Add(Ds.Secundario(l.Canal ?? "—", 12), 2, 0);
        fila.Add(Ds.Secundario(l.App ?? "—", 12), 3, 0);
        // Una línea por renglón (el texto completo está en el detalle): un Label que envuelve dentro de una columna «*» provoca ciclos de
        // layout en WinUI con mensajes largos (LayoutCycleException), así que aquí se recorta.
        var texto = new VerticalStackLayout { Spacing = 2 };
        var mensaje = Ds.Cuerpo(l.Mensaje ?? "—", 14);
        mensaje.LineBreakMode = LineBreakMode.TailTruncation; mensaje.MaxLines = 1;
        texto.Add(mensaje);
        var secundario = Ds.Secundario(string.Join(" · ", new[] { l.Evento, l.DispositivoId is null ? null : $"equipo {Abreviar(l.DispositivoId, 8)}", l.Corr is null ? null : $"corr {Abreviar(l.Corr, 8)}" }.Where(x => x is not null)), 12);
        secundario.LineBreakMode = LineBreakMode.TailTruncation; secundario.MaxLines = 1;
        texto.Add(secundario);
        fila.Add(texto, 4, 0);
        fila.Add(ChipRuta(l.Ruta), 5, 0);
        foreach (var hijo in fila.Children.OfType<View>()) hijo.VerticalOptions = LayoutOptions.Center;
        var contenedor = new VerticalStackLayout { Spacing = 8, Children = { fila } };
        var tarjeta = FilaPlana(contenedor);
        View? detalle = null;
        Ds.Tocable(tarjeta, () =>
        {
            if (detalle is not null) { contenedor.Remove(detalle); detalle = null; return Task.CompletedTask; }
            var pila = new VerticalStackLayout { Spacing = 6 };
            pila.Add(Ds.Separador());
            if (l.Detalle is not null) pila.Add(Mono(Bonito(l.Detalle)));
            if (!string.IsNullOrWhiteSpace(l.Traza)) pila.Add(Mono(string.Join("\n", l.Traza.Split('\n').TakeLast(8)), 12));
            pila.Add(Ds.Secundario($"{l.Archivo ?? "—"} · módulo {l.Modulo ?? "—"} · corr {l.Corr ?? "—"} · caso {l.Caso ?? "—"}", 12));
            detalle = pila;
            contenedor.Add(detalle);
            return Task.CompletedTask;
        });
        return tarjeta;
    }

    // ------------------------------------------------------------------ PAN-242 · Estado del equipo (técnico)

    private async Task<View> EstadoDelEquipoAsync()
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        var salud = await Sesion.Acceso.ConfiguracionAsync();
        var estado = salud is null ? ("Sin respuesta del nodo", Ds.PeligroSuave, TintaPeligro) : salud.Instalado ? ("Nodo en servicio", Ds.ExitoSuave, TintaExito) : ("Nodo sin instalar", Ds.AlertaSuave, TintaAlerta);
        pila.Add(Ds.Alerta_(estado.Item1, $"Servidor {Sesion.BaseUri} · {(salud?.SesionObligatoria == true ? "exige sesión" : "sin sesión obligatoria")}", estado.Item2, estado.Item3));

        var datos = new VerticalStackLayout { Spacing = 6 };
        datos.Add(Ds.Cuerpo("Este equipo", 16));
        var espacio = EspacioLibreMb();
        datos.Add(Ds.Secundario($"AVACOM LMS OPS {AppInfo.Current.VersionString} · {DeviceInfo.Current.Name} · {DeviceInfo.Current.Platform} {DeviceInfo.Current.VersionString}", 14));
        datos.Add(Ds.Secundario($"Identificado ante el nodo como {AparatoRegistrado.Id ?? "(sin registrar todavía)"}", 14));
        datos.Add(Ds.Secundario($"Espacio libre: {(espacio is null ? "no disponible" : $"{espacio / 1024d:0.0} GB")} · logs en {RegistroLocal.Carpeta}", 14));
        var entregador = Sesion.EntregadorDeLogs;
        datos.Add(Ds.Secundario($"Logs pendientes de entregar al nodo: {RegistroLocal.CuentaPendientes} · última entrega: {(entregador.UltimaEntregaEn is { } e ? e.ToString("dd/MM HH:mm") : "ninguna")} ({entregador.Entregados} renglones entregados)", 14));
        var acciones = new HorizontalStackLayout { Spacing = 12 };
        var estadoAcciones = Ds.Secundario(string.Empty, 13);
        var entregar = Ds.Boton("Entregar logs ahora", Ds.Rango.Secondary, async (_, _) =>
        {
            var r = await Sesion.EntregadorDeLogs.EntregarAhoraAsync();
            estadoAcciones.Text = r is null ? "No había nada pendiente o el nodo no contestó." : $"Entregados {r.Escritos} renglones.";
        }, 52, 200);
        var diagnostico = Ds.Boton("Exportar diagnóstico", Ds.Rango.Primary, (_, _) =>
        {
            try
            {
                var ruta = RegistroLocal.ExportarDiagnostico(Path.Combine(CarpetaDescargas(), $"diagnostico-ops-{DateTime.Now:yyyyMMdd-HHmmss}.zip"),
                    new { servidor = Sesion.BaseUri.ToString(), fuente_aula = Sesion.FuenteAula, sesion_obligatoria = Sesion.SesionObligatoria, rol = Sesion.Usuario?.Rol });
                estadoAcciones.Text = $"Diagnóstico guardado en {ruta}";
            }
            catch (Exception ex) { estadoAcciones.Text = "No se pudo crear el diagnóstico: " + ex.Message; RegistroDeFallos.Escribir("ops", "BitacoraPage.ExportarDiagnostico", ex); }
        }, 52, 220);
        entregar.FontSize = diagnostico.FontSize = 15;
        acciones.Add(entregar); acciones.Add(diagnostico);
        datos.Add(acciones);
        datos.Add(estadoAcciones);
        pila.Add(Ds.Tarjeta(datos, Ds.RadioTarjeta, new Thickness(20, 16), Colors.White));

        pila.Add(Ds.Cuerpo("Últimos avisos de este equipo", 16));
        var locales = RegistroLocal.Leer(soloErrores: true, ultimos: 20);
        if (locales.Count == 0) pila.Add(Vacio("Sin avisos en este equipo", "Cuando falle una escritura, la red o el aparato, quedará aquí y se entregará al nodo."));
        foreach (var r in locales.AsEnumerable().Reverse())
            pila.Add(FilaLog(new LineaLog(r.Ts, r.Nivel, r.Canal, r.App, r.Modulo, r.Evento, r.Ruta, null, r.DispositivoId, null, r.Corr, r.Mensaje,
                r.Detalle is null ? null : System.Text.Json.JsonSerializer.SerializeToElement(r.Detalle), r.Traza, "local")));
        return pila;
    }

    private static int? EspacioLibreMb()
    {
        try
        {
            var raiz = Path.GetPathRoot(FileSystem.AppDataDirectory);
            return string.IsNullOrEmpty(raiz) ? null : (int)(new DriveInfo(raiz).AvailableFreeSpace / (1024 * 1024));
        }
        catch { return null; }
    }
}
