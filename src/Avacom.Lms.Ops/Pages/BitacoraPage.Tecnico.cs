using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>Pestaña «Accesos del técnico» (PAN-240, 019-10): acciones y denegaciones del rol técnico y el indicador «sin acceso a datos personales en el periodo».</summary>
public partial class BitacoraPage
{
    private DateTime? _tDesde, _tHasta;

    private async Task<View> AccesosDelTecnicoAsync()
    {
        var api = Sesion.Auditoria;
        var desdeMs = _tDesde is { } d ? InicioDelDia(d) : (long?)null;
        var hastaMs = _tHasta is { } h ? FinDelDia(h) : (long?)null;
        var accesos = await api.AccesosDelTecnicoAsync(desdeMs, hastaMs, limite: 100);
        if (accesos is null) return TarjetaDeError("No se pudieron leer los accesos del técnico", api.UltimoMotivo, () => MostrarAsync(Pestana.Tecnico), api.UltimoError);

        var pila = new VerticalStackLayout { Spacing = 12 };
        var (fondo, tinta, titulo, detalle) = accesos.SinAccesoADatosPersonales
            ? (Ds.ExitoSuave, TintaExito, "Sin acceso a datos personales en el periodo",
               accesos.CadenaVerificada ? "Ningún asiento del rol técnico consultó datos personales ni resultados, y la cadena está verificada: es la prueba (VER-01)."
                                        : "Ningún asiento del rol técnico consultó datos personales. Verifica la cadena en «Integridad» para que la prueba sea completa.")
            : (Ds.PeligroSuave, TintaPeligro, "El rol técnico accedió a datos personales en el periodo",
               "Revisa abajo qué asiento lo registra: toda consulta de datos de menores queda como «Dato personal de menor consultado».");
        if (accesos.SaltoDetectado) { fondo = Ds.PeligroSuave; tinta = TintaPeligro; detalle += " Atención: la cadena tiene un salto detectado."; }
        pila.Add(Ds.Alerta_(titulo, detalle, fondo, tinta));

        var periodo = new HorizontalStackLayout { Spacing = 10, VerticalOptions = LayoutOptions.Center };
        var desde = FechaPicker(_tDesde ?? DateTime.Today.AddDays(-30));
        var hasta = FechaPicker(_tHasta ?? DateTime.Today);
        var aplicar = Ds.Boton("Aplicar periodo", Ds.Rango.Secondary, async (_, _) => { _tDesde = desde.Date; _tHasta = hasta.Date; await MostrarAsync(Pestana.Tecnico); }, 48, 160);
        var todo = Ds.Boton("Todo el historial", Ds.Rango.Quiet, async (_, _) => { _tDesde = _tHasta = null; await MostrarAsync(Pestana.Tecnico); }, 48, 160);
        aplicar.FontSize = todo.FontSize = 14;
        periodo.Add(Ds.Secundario("Periodo", 14)); periodo.Add(desde); periodo.Add(Ds.Secundario("hasta", 14)); periodo.Add(hasta); periodo.Add(aplicar); periodo.Add(todo);
        var resumen = new VerticalStackLayout { Spacing = 8 };
        resumen.Add(periodo);
        var tecnicos = accesos.Tecnicos.Count == 0 ? "No hay cuentas con el rol técnico." : "Técnicos: " + string.Join(", ", accesos.Tecnicos.Select(t => t.Rotulo ?? t.UsuarioId));
        resumen.Add(Ds.Secundario($"{tecnicos} · {accesos.Total} asiento{(accesos.Total == 1 ? "" : "s")} · {accesos.Denegaciones} denegaci{(accesos.Denegaciones == 1 ? "ón" : "ones")}", 14));
        pila.Add(Ds.Tarjeta(resumen, Ds.RadioTarjeta, new Thickness(18, 14), Colors.White));

        if (accesos.Asientos.Count == 0) pila.Add(Vacio("Sin acciones del técnico en el periodo", "Cuando un técnico actúe o sea denegado, aparecerá aquí con su permiso y su objeto."));
        foreach (var a in accesos.Asientos) pila.Add(FilaAsiento(a));
        return pila;
    }
}
