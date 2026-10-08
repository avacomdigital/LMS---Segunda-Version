using Avacom.Lms.Core.Diagnostico;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Pestaña «Medios»: la cola de medios del nodo (<c>GET /api/medios/cola/</c>). Los videos, audios, imágenes, PDF y páginas html de un curso vienen de AVACOM
/// Contenido; el nodo los trae UNA vez a su caché de disco y los reparte a las tabletas, con un límite de descargas y de transferencias a la vez. Aquí se ve
/// cuánto hay en la caché, qué se está preparando y qué falló, sin ningún dato de alumnos ni de cursos más allá de las referencias de los medios.
/// Es sólo de lectura salvo tres acciones del personal: cancelar una preparación, reintentar una fallida y vaciar la caché (que se vuelve a llenar sola).
/// </summary>
public partial class BitacoraPage
{
    private bool _confirmarVaciar;
    private string _mensajeMedios = string.Empty;

    private static readonly Color FondoNeutro = Color.FromArgb("#EEEEF0");

    private async Task<View> MediosAsync()
    {
        var api = Sesion.ColaDeMedios;
        var estado = await api.EstadoAsync();
        if (estado is null) return TarjetaDeError("No se pudo leer la cola de medios", api.UltimoMotivo, () => MostrarAsync(Pestana.Medios), api.UltimoError);
        var lista = await api.RecursosAsync(limite: 60);

        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(ResumenDeMedios(estado));
        pila.Add(CifrasDeMedios(estado));
        pila.Add(AccionesDeMedios(estado));
        if (_mensajeMedios.Length > 0) pila.Add(Ds.Secundario(_mensajeMedios, 14));

        pila.Add(Ds.Cuerpo("Recursos recientes", 16));
        var recursos = lista?.Recursos ?? [];
        if (recursos.Count == 0)
            pila.Add(Vacio("Todavía no hay recursos en la caché", "Aparecen cuando una tableta pide un medio, el profesor proyecta o lanza algo, un alumno prepara un paquete de estudio o empieza un examen con imágenes."));
        foreach (var r in recursos) pila.Add(FilaDeRecurso(r));
        if (lista is { Total: var total } && total > recursos.Count) pila.Add(Ds.Secundario($"Se muestran {recursos.Count} de {total}.", 13));
        return pila;
    }

    private static View ResumenDeMedios(EstadoDeLaCola e)
    {
        if (!e.Activa)
            return Ds.Alerta_("La cola de medios está apagada",
                string.IsNullOrWhiteSpace(e.MotivoApagada)
                    ? "Cada tableta pide sus medios directo a AVACOM Contenido, como antes. Para encenderla, AVACOM_COLA_ACTIVA=1 en la configuración del nodo."
                    : $"Se apagó sola y las tabletas siguen recibiendo los medios directo de AVACOM Contenido, como antes. {e.MotivoApagada}", Ds.AlertaSuave, TintaAlerta);
        var fallidos = e.En("fallido");
        var enCurso = e.En("pendiente") + e.En("descargando");
        if (fallidos > 0)
            return Ds.Alerta_($"{fallidos} {(fallidos == 1 ? "recurso falló" : "recursos fallaron")}", "Las tabletas los siguen recibiendo directo de AVACOM Contenido. Reintenta desde la lista o revisa que la biblioteca esté abierta.", Ds.AlertaSuave, TintaAlerta);
        return enCurso > 0
            ? Ds.Alerta_($"Preparando {enCurso} {(enCurso == 1 ? "recurso" : "recursos")}", "Las tabletas ya pueden pedirlos: reciben lo que llegó y el resto sigue bajando.", Ds.ExitoSuave, TintaExito)
            : Ds.Alerta_("La cola de medios está al día", "Nada pendiente. Lo que ya está en la caché se reparte a las tabletas sin volver a pedirlo a AVACOM Contenido.", Ds.ExitoSuave, TintaExito);
    }

    private static View CifrasDeMedios(EstadoDeLaCola e)
    {
        var datos = new VerticalStackLayout { Spacing = 6 };
        datos.Add(Ds.Cuerpo("Caché del nodo", 16));
        if (e.Cache is { } c)
        {
            var uso = c.BytesMaximo > 0 ? (int)Math.Min(100, c.BytesOcupados * 100 / c.BytesMaximo) : 0;
            datos.Add(Ds.Secundario($"{Tamano(c.BytesOcupados)} de {Tamano(c.BytesMaximo)} ({uso} %) · espacio libre en el disco {Tamano(c.BytesLibresDisco)} (se deja libre al menos {Tamano(c.BytesLibresMinimo)})", 14));
        }
        datos.Add(Ds.Secundario($"Recursos: {e.En("disponible")} listos · {e.En("descargando")} descargando · {e.En("pendiente")} en espera · {e.En("fallido")} fallidos · {e.En("cancelado")} cancelados", 14));
        if (e.Transferencias is { } t && e.Limites is { } l)
        {
            datos.Add(Ds.Secundario($"Hacia las tabletas: {t.EnUso} de {t.Maximo} transferencias a la vez (máximo visto {t.Pico}) · desde AVACOM Contenido: hasta {l.DescargasSimultaneas} descargas a la vez", 14));
            datos.Add(Ds.Secundario($"Ancho de banda: entrada {Tope(l.AnchoEntradaBps)} · salida {Tope(l.AnchoSalidaBps)}", 14));
        }
        if (e.Contadores is { Count: > 0 } k)
        {
            long Dato(string clave) => k.TryGetValue(clave, out var v) ? v : 0;
            datos.Add(Ds.Secundario($"Desde que arrancó el nodo: {Dato("aciertos")} peticiones servidas de la caché · {Dato("siguiendo")} siguiendo una descarga · {Dato("directos")} directas a la biblioteca · {Tamano(Dato("bytes_servidos"))} entregados", 14));
        }
        return Ds.Tarjeta(datos, Ds.RadioTarjeta, new Thickness(20, 16), Colors.White);
    }

    /// <summary>El tamaño en la unidad que se lee bien: un icono de 40 KB no es «0,0 MB».</summary>
    private static string Tamano(long bytes) => bytes switch
    {
        >= 1024L * 1024 * 1024 => $"{bytes / 1024d / 1024d / 1024d:0.0} GB",
        >= 1024L * 1024 => $"{bytes / 1024d / 1024d:0.0} MB",
        >= 1024 => $"{bytes / 1024d:0} KB",
        _ => $"{bytes} B",
    };

    private static string Tope(long bytesPorSegundo) => bytesPorSegundo <= 0 ? "sin tope" : $"{bytesPorSegundo / 1024d / 1024d:0.0} MB/s";

    private View AccionesDeMedios(EstadoDeLaCola e)
    {
        var acciones = new HorizontalStackLayout { Spacing = 12 };
        var vaciar = Ds.Boton(_confirmarVaciar ? "Toca otra vez para vaciar" : "Vaciar la caché", _confirmarVaciar ? Ds.Rango.Destructive : Ds.Rango.Secondary, async (_, _) =>
        {
            if (!_confirmarVaciar) { _confirmarVaciar = true; await MostrarAsync(Pestana.Medios); return; }
            _confirmarVaciar = false;
            var n = await Sesion.ColaDeMedios.LimpiarAsync();
            _mensajeMedios = n is null ? "No se pudo vaciar la caché." : $"Se vació la caché: {n} {(n == 1 ? "recurso" : "recursos")}. Se vuelven a traer solos cuando alguien los pida.";
            await MostrarAsync(Pestana.Medios);
        }, 52, 260);
        vaciar.FontSize = 15;
        vaciar.IsEnabled = e.Activa && e.En("disponible") > 0;
        acciones.Add(vaciar);
        return acciones;
    }

    private View FilaDeRecurso(RecursoDeMedios r)
    {
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(130), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        var nombre = Ds.Cuerpo(string.IsNullOrEmpty(r.Ruta) ? r.MediaRef : $"{r.MediaRef}/{r.Ruta}", 14);
        nombre.LineBreakMode = LineBreakMode.TailTruncation; nombre.MaxLines = 1;
        var secundario = Ds.Secundario(string.Join(" · ", new[] { r.CursoRef, r.TipoMime, r.Prioridad is null ? null : $"prioridad {r.Prioridad}", r.Estado == "fallido" ? r.ErrorDetalle ?? r.ErrorCodigo : null }.Where(x => !string.IsNullOrEmpty(x))), 12);
        secundario.LineBreakMode = LineBreakMode.TailTruncation; secundario.MaxLines = 1;
        fila.Add(new VerticalStackLayout { Spacing = 2, Children = { nombre, secundario } }, 0, 0);
        fila.Add(ChipDeRecurso(r.Estado), 1, 0);
        var avance = r.Estado == "disponible" || r.Porcentaje is null
            ? Ds.Secundario(r.BytesTotal is { } total ? Tamano(total) : "—", 12)
            : Ds.Secundario($"{r.Porcentaje} % · {Tamano(r.BytesHechos)}", 12);
        fila.Add(avance, 2, 0);
        if (r.EnCurso || r.Fallo)
        {
            var boton = Ds.Boton(r.Fallo ? "Reintentar" : "Cancelar", Ds.Rango.Quiet, async (_, _) =>
            {
                var bien = r.Fallo ? await Sesion.ColaDeMedios.ReintentarAsync(r.Id) : await Sesion.ColaDeMedios.CancelarAsync(r.Id);
                _mensajeMedios = bien ? string.Empty : "No se pudo hacer eso con ese recurso (ya cambió de estado).";
                await MostrarAsync(Pestana.Medios);
            }, 44, 120);
            boton.FontSize = 13;
            fila.Add(boton, 3, 0);
        }
        foreach (var hijo in fila.Children.OfType<View>()) hijo.VerticalOptions = LayoutOptions.Center;
        return FilaPlana(fila);
    }

    private static Border ChipDeRecurso(string estado) => estado switch
    {
        "disponible" => Chip("Listo", Ds.ExitoSuave, TintaExito),
        "descargando" => Chip("Descargando", Ds.AlertaSuave, TintaAlerta),
        "pendiente" => Chip("En espera", FondoNeutro, Ds.TintaSuave),
        "fallido" => Chip("Falló", Ds.PeligroSuave, TintaPeligro),
        "cancelado" => Chip("Cancelado", FondoNeutro, Ds.TintaSuave),
        _ => Chip(estado, FondoNeutro, Ds.TintaSuave),
    };
}
