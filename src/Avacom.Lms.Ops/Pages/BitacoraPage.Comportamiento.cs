using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>Pestaña «Comportamiento» (PAN-240): la bitácora paginada por cursor, filtros por selectores y fechas, y el detalle de cada asiento.</summary>
public partial class BitacoraPage
{
    // Los filtros viven en la página para que «Actualizar» y «Cargar más» los conserven.
    private string? _fModulo, _fResultado, _fAccion, _fActor, _fCorrelacion;
    private DateTime? _fDesde, _fHasta;
    private readonly Dictionary<string, string> _actores = new();   // usuario_id → rótulo, para el selector de personas

    private async Task<View> ComportamientoAsync()
    {
        _catalogo ??= await Sesion.Auditoria.CatalogoAsync();
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Filtros());
        var lista = new VerticalStackLayout { Spacing = 10 };
        pila.Add(lista);
        await CargarAsientosAsync(lista, antes: null);
        return pila;
    }

    private View Filtros()
    {
        var modulo = new FilterPicker { Placeholder = "Todos los módulos", WidthRequest = 220 };
        var modulos = _catalogo?.Modulos.Select(m => m.Etiqueta).ToList() ?? [];
        modulo.Poblar(modulos);
        if (_fModulo is not null) Seleccionar(modulo, modulos, _catalogo?.Modulos.FirstOrDefault(m => m.Clave == _fModulo)?.Etiqueta);

        var resultado = new FilterPicker { Placeholder = "Todos los resultados", WidthRequest = 200 };
        resultado.Poblar(["Correcto", "Denegado", "Fallido"]);
        if (_fResultado is not null) Seleccionar(resultado, ["Correcto", "Denegado", "Fallido"], _fResultado switch { "ok" => "Correcto", "denegado" => "Denegado", _ => "Fallido" });

        var accion = new FilterPicker { Placeholder = "Todas las acciones", WidthRequest = 260 };
        var acciones = AccionesDe(_fModulo);
        accion.Poblar(acciones.Select(a => a.Etiqueta));
        if (_fAccion is not null) Seleccionar(accion, acciones.Select(a => a.Etiqueta).ToList(), acciones.FirstOrDefault(a => a.Clave == _fAccion)?.Etiqueta);

        var actor = new FilterPicker { Placeholder = "Todas las personas", WidthRequest = 220 };
        var personas = _actores.OrderBy(p => p.Value).ToList();
        actor.Poblar(personas.Select(p => p.Value));
        if (_fActor is not null) Seleccionar(actor, personas.Select(p => p.Value).ToList(), personas.FirstOrDefault(p => p.Key == _fActor).Value);

        var desde = FechaPicker(_fDesde ?? DateTime.Today.AddDays(-7));
        var hasta = FechaPicker(_fHasta ?? DateTime.Today);

        modulo.SelectionChanged += async (_, _) => { _fModulo = _catalogo?.Modulos.FirstOrDefault(m => m.Etiqueta == modulo.Selected)?.Clave; _fAccion = null; await MostrarAsync(Pestana.Comportamiento); };
        resultado.SelectionChanged += async (_, _) => { _fResultado = resultado.Selected switch { "Correcto" => "ok", "Denegado" => "denegado", "Fallido" => "fallido", _ => null }; await MostrarAsync(Pestana.Comportamiento); };
        accion.SelectionChanged += async (_, _) => { _fAccion = AccionesDe(_fModulo).FirstOrDefault(a => a.Etiqueta == accion.Selected)?.Clave; await MostrarAsync(Pestana.Comportamiento); };
        actor.SelectionChanged += async (_, _) => { _fActor = personas.FirstOrDefault(p => p.Value == actor.Selected).Key; await MostrarAsync(Pestana.Comportamiento); };

        var aplicarFechas = Ds.Boton("Aplicar fechas", Ds.Rango.Secondary, async (_, _) => { _fDesde = desde.Date; _fHasta = hasta.Date; await MostrarAsync(Pestana.Comportamiento); }, 48, 150);
        var limpiar = Ds.Boton("Limpiar", Ds.Rango.Quiet, async (_, _) => { _fModulo = _fResultado = _fAccion = _fActor = _fCorrelacion = null; _fDesde = _fHasta = null; await MostrarAsync(Pestana.Comportamiento); }, 48, 120);
        aplicarFechas.FontSize = limpiar.FontSize = 14;

        var fila1 = new HorizontalStackLayout { Spacing = 10, Children = { modulo, accion, resultado, actor } };
        var fila2 = new HorizontalStackLayout { Spacing = 10, VerticalOptions = LayoutOptions.Center };
        fila2.Add(Ds.Secundario("Desde", 14)); fila2.Add(desde); fila2.Add(Ds.Secundario("hasta", 14)); fila2.Add(hasta); fila2.Add(aplicarFechas); fila2.Add(limpiar);
        if (_fCorrelacion is not null)
        {
            var quitar = Ds.Boton($"Operación {Abreviar(_fCorrelacion, 8)} ✕", Ds.Rango.Quiet, async (_, _) => { _fCorrelacion = null; await MostrarAsync(Pestana.Comportamiento); }, 48, 200);
            quitar.FontSize = 14;
            fila2.Add(quitar);
        }
        var contenido = new VerticalStackLayout { Spacing = 10, Children = { fila1, fila2 } };
        return Ds.Tarjeta(contenido, Ds.RadioTarjeta, new Thickness(18, 14), Colors.White);
    }

    /// <summary>Restaura el filtro elegido al repintar, sin disparar una nueva consulta.</summary>
    private static void Seleccionar(FilterPicker picker, IReadOnlyList<string> valores, string? valor)
    {
        if (valor is not null && valores.Contains(valor)) picker.Elegir(valor);
    }

    private IReadOnlyList<AccionCatalogo> AccionesDe(string? modulo) =>
        (_catalogo?.Acciones ?? []).Where(a => modulo is null || a.Modulo == modulo).OrderBy(a => a.Etiqueta).ToList();

    private FiltrosBitacora FiltrosActuales(long? antes) => new(
        Actor: _fActor, Modulo: _fModulo, Accion: _fAccion, Resultado: _fResultado, Correlacion: _fCorrelacion,
        Desde: _fDesde is { } d ? InicioDelDia(d) : null, Hasta: _fHasta is { } h ? FinDelDia(h) : null, Limite: 50, Antes: antes);

    private async Task CargarAsientosAsync(VerticalStackLayout lista, long? antes)
    {
        var api = Sesion.Auditoria;
        var pagina = await api.AsientosAsync(FiltrosActuales(antes));
        if (pagina is null)
        {
            lista.Add(TarjetaDeError("No se pudo leer la bitácora", api.UltimoMotivo, () => MostrarAsync(Pestana.Comportamiento), api.UltimoError));
            return;
        }
        foreach (var a in pagina.Asientos)
            if (a.Actor?.UsuarioId is { Length: > 0 } uid && !string.IsNullOrWhiteSpace(a.Actor.Rotulo)) _actores[uid] = a.Actor.Rotulo!;
        if (antes is null)
        {
            var resumen = pagina.Total == 0 ? "Sin asientos con estos filtros" : $"{pagina.Total} asiento{(pagina.Total == 1 ? "" : "s")} · del más reciente al más antiguo";
            if (pagina.Enmascarado) resumen += " · los datos personales y las calificaciones se muestran enmascarados (BR-131)";
            lista.Add(Ds.Secundario(resumen, 14));
        }
        if (pagina.Asientos.Count == 0 && antes is null)
        {
            lista.Add(Vacio("La bitácora sólo se agrega; nadie puede editarla.", "Con estos filtros no hay asientos. Amplía las fechas o quita un filtro."));
            return;
        }
        foreach (var asiento in pagina.Asientos) lista.Add(FilaAsiento(asiento));
        if (pagina.Siguiente is { } siguiente)
        {
            var mas = Ds.Boton("Cargar más", Ds.Rango.Quiet, null, 52, 200);
            mas.FontSize = 15;
            mas.HorizontalOptions = LayoutOptions.Center;
            mas.Clicked += async (_, _) => { lista.Remove(mas); await CargarAsientosAsync(lista, siguiente); };
            lista.Add(mas);
        }
    }

    /// <summary>Una fila de la bitácora: hora, actor, acción, objeto, resultado y dispositivo. Al tocarla se despliega el detalle debajo.</summary>
    private View FilaAsiento(Asiento a)
    {
        var fila = new Grid
        {
            ColumnDefinitions = [new ColumnDefinition(118), new ColumnDefinition(190), new ColumnDefinition(GridLength.Star), new ColumnDefinition(230), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(110)],
            ColumnSpacing = 14,
        };
        fila.Add(Ds.Secundario(Hora(a.OcurridoEn), 13), 0, 0);
        var actor = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        actor.Add(Ds.Cuerpo(a.Actor?.Legible ?? "—", 15));
        if (a.RolesActivos is { Count: > 0 }) actor.Add(Ds.Secundario(string.Join(", ", a.RolesActivos), 12));
        fila.Add(actor, 1, 0);
        var accion = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        accion.Add(Ds.Cuerpo(a.EtiquetaLegible, 15));
        accion.Add(Ds.Secundario($"{a.ModuloEtiqueta ?? a.Modulo} · {a.Accion}", 12));
        fila.Add(accion, 2, 0);
        fila.Add(Ds.Secundario(a.Objeto?.Legible ?? "—", 13), 3, 0);
        fila.Add(ChipResultado(a.Resultado), 4, 0);
        fila.Add(Ds.Secundario(Abreviar(a.DispositivoId, 8), 12), 5, 0);
        foreach (var hijo in fila.Children.OfType<View>()) hijo.VerticalOptions = LayoutOptions.Center;

        var contenedor = new VerticalStackLayout { Spacing = 10, Children = { fila } };
        var tarjeta = FilaPlana(contenedor, a.Resultado == "ok" ? Colors.White : a.Resultado == "denegado" ? Ds.AlertaSuave : Ds.PeligroSuave);
        View? detalle = null;
        Ds.Tocable(tarjeta, async () =>
        {
            if (detalle is not null) { contenedor.Remove(detalle); detalle = null; return; }
            detalle = await DetalleAsync(a);
            contenedor.Add(detalle);
        });
        return tarjeta;
    }

    /// <summary>El detalle: valor anterior → nuevo (con la diferencia resaltada por el color), motivo, origen, correlación, huella completa y «ver operación completa».</summary>
    private async Task<View> DetalleAsync(Asiento resumen)
    {
        var completo = await Sesion.Auditoria.AsientoAsync(resumen.Id) ?? resumen;
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(Ds.Separador());
        var valores = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 16 };
        var anterior = new VerticalStackLayout { Spacing = 4 };
        anterior.Add(Ds.Secundario("Valor anterior", 12));
        anterior.Add(Ds.Tarjeta(Mono(Bonito(completo.ValorAnterior)), Ds.RadioInterno, new Thickness(12), Color.FromArgb("#F7F7F8")));
        var nuevo = new VerticalStackLayout { Spacing = 4 };
        nuevo.Add(Ds.Secundario("Valor nuevo", 12));
        nuevo.Add(Ds.Tarjeta(Mono(Bonito(completo.ValorNuevo)), Ds.RadioInterno, new Thickness(12), completo.ValorAnterior is null ? Color.FromArgb("#F7F7F8") : Ds.ExitoSuave));
        valores.Add(anterior, 0, 0);
        valores.Add(nuevo, 1, 0);
        pila.Add(valores);
        if (completo.Enmascarado)
            pila.Add(Ds.Secundario("Los valores de este asiento se muestran enmascarados: toca datos personales o calificaciones (BR-131). Con una escalada vigente de audit.read se ven completos y queda registrado.", 13));
        var datos = new VerticalStackLayout { Spacing = 3 };
        datos.Add(Ds.Secundario($"Motivo: {completo.Motivo ?? "—"}", 14));
        datos.Add(Ds.Secundario($"Origen: {completo.Origen ?? "—"} · Dispositivo: {completo.DispositivoId ?? "—"} · Secuencia #{completo.Secuencia} · Tramo {Abreviar(completo.TramoId, 8)}", 13));
        datos.Add(Ds.Secundario($"Correlación: {completo.CorrelacionId ?? "—"}", 13));
        datos.Add(Mono($"Huella: {completo.Huella ?? "—"}", 12));
        if (!string.IsNullOrEmpty(completo.HuellaPrevia)) datos.Add(Mono($"Previa: {completo.HuellaPrevia}", 12));
        pila.Add(datos);
        if (!string.IsNullOrWhiteSpace(completo.CorrelacionId))
        {
            var operacion = Ds.Boton("Ver operación completa", Ds.Rango.Quiet, async (_, _) => { _fCorrelacion = completo.CorrelacionId; _fDesde = _fHasta = null; await MostrarAsync(Pestana.Comportamiento); }, 48, 240);
            operacion.FontSize = 14;
            operacion.HorizontalOptions = LayoutOptions.Start;
            pila.Add(operacion);
        }
        return pila;
    }
}
