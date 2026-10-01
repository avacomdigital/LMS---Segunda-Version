using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>Pestaña «Integridad» (PAN-240): semáforo de la cadena, «Verificar ahora», tamaño frente al umbral de rotación y los tramos.</summary>
public partial class BitacoraPage
{
    private async Task<View> IntegridadAsync()
    {
        var api = Sesion.Auditoria;
        var estado = await api.EstadoAsync();
        if (estado is null) return TarjetaDeError("No se pudo leer el estado de la cadena", api.UltimoMotivo, () => MostrarAsync(Pestana.Integridad), api.UltimoError);
        var tramos = await api.TramosAsync();

        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Semaforo(estado));
        pila.Add(Tamano(estado));
        pila.Add(Ds.Cuerpo("Tramos de la cadena", 18));
        if (tramos is null || tramos.Tramos.Count == 0) pila.Add(Vacio("Todavía no hay tramos", "El primer asiento abre la bitácora y crea el tramo activo."));
        else foreach (var t in tramos.Tramos.OrderByDescending(t => t.Desde)) pila.Add(FilaTramo(t));
        return pila;
    }

    /// <summary>Verde «Cadena verificada» con fecha · rojo «Salto detectado en la secuencia N» con causa · ámbar «Sin verificar todavía».</summary>
    private View Semaforo(EstadoBitacora estado)
    {
        var (fondo, tinta, titulo, detalle) = estado.Semaforo switch
        {
            "rojo" when !estado.TriggersOk => (Ds.PeligroSuave, TintaPeligro, "Protección de la bitácora ausente",
                "Faltan los triggers de inmutabilidad en la base de datos: la verificación lo registra como salto. Avisa a soporte técnico."),
            "rojo" => (Ds.PeligroSuave, TintaPeligro, $"Salto detectado en la secuencia {estado.Salto?.Secuencia}",
                $"Causa: {Causa(estado.Salto?.Causa)}. La cadena deja de ser evidencia a partir de ahí hasta que se aclare; no se puede exportar ese tramo."),
            "verde" => (Ds.ExitoSuave, TintaExito, "Cadena verificada",
                $"Última verificación: {Fecha(estado.UltimoVerificadoEn)}. Cabeza en el asiento #{estado.Cabeza.Secuencia} · huella {estado.Cabeza.Huella ?? "—"} · {estado.TotalAsientos} asientos en {estado.Tramos} tramo{(estado.Tramos == 1 ? "" : "s")}."),
            _ => (Ds.AlertaSuave, TintaAlerta, "Sin verificar todavía",
                $"El nodo verifica cada {estado.VerificarCadaS / 60} minutos. Cabeza en el asiento #{estado.Cabeza.Secuencia} · {estado.TotalAsientos} asientos."),
        };
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        var texto = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        texto.Add(new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 26, TextColor = tinta });
        texto.Add(new Label { Text = detalle, FontSize = 15, TextColor = tinta, LineBreakMode = LineBreakMode.WordWrap });
        fila.Add(texto, 0, 0);
        var verificar = Ds.Boton("Verificar ahora", Ds.Rango.Primary, async (_, _) => await VerificarAhoraAsync(), 60, 220);
        verificar.VerticalOptions = LayoutOptions.Center;
        fila.Add(verificar, 1, 0);
        return Ds.Tarjeta(fila, Ds.RadioTarjeta, new Thickness(24, 20), fondo);
    }

    private async Task VerificarAhoraAsync()
    {
        var resultado = await Sesion.Auditoria.VerificarAsync();
        if (resultado is null)
        {
            ContenidoHost.Insert(0, TarjetaDeError("No se pudo verificar", Sesion.Auditoria.UltimoMotivo, () => MostrarAsync(Pestana.Integridad), Sesion.Auditoria.UltimoError));
            return;
        }
        await MostrarAsync(Pestana.Integridad);
        var aviso = resultado.Estado switch
        {
            "verificada" => Ds.Alerta_($"Verificación terminada: {resultado.Verificados} asientos comprobados", "La cadena no tiene saltos. El resultado quedó asentado en la bitácora.", Ds.ExitoSuave, TintaExito),
            "con_salto" => Ds.Alerta_($"Salto en la secuencia {resultado.SaltoEn}", $"Causa: {Causa(resultado.Causa)}. Quedó asentado y avisado como alerta administrativa.", Ds.PeligroSuave, TintaPeligro),
            _ => Ds.Alerta_("Todavía no hay suficientes asientos para verificar", "La cadena exige al menos dos asientos.", Ds.AlertaSuave, TintaAlerta),
        };
        ContenidoHost.Insert(0, aviso);
    }

    private static View Tamano(EstadoBitacora estado)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        var porcentaje = estado.UmbralBytes > 0 ? Math.Min(1, (double)estado.TamanoBytes / estado.UmbralBytes) : 0;
        pila.Add(Ds.Cuerpo("Tamaño frente al umbral de rotación", 16));
        pila.Add(new ProgressBar { Progress = porcentaje, ProgressColor = porcentaje > 0.9 ? Ds.Peligro : porcentaje > 0.7 ? Ds.Alerta : Ds.Exito, HeightRequest = 10 });
        pila.Add(Ds.Secundario($"{Mb(estado.TamanoBytes)} de {Mb(estado.UmbralBytes)} ({porcentaje * 100:0.0} %). Al superar el umbral el tramo se cierra, se archiva firmado y empieza uno nuevo; las filas no se borran.", 14));
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(20, 16), Colors.White);
    }

    private View FilaTramo(TramoBitacora t)
    {
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(200), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        fila.Add(Ds.Cuerpo($"Tramo {t.Rango}", 16), 0, 0);
        var chip = t.Estado switch
        {
            "verificada" => Chip("Verificada", Ds.ExitoSuave, TintaExito),
            "con_salto" => Chip($"Salto en #{t.SaltoEn}", Ds.PeligroSuave, TintaPeligro),
            "rotada" => Chip("Rotada", Color.FromArgb("#EEEEF0"), Ds.TintaSuave),
            _ => Chip("Activa", Ds.InfoSuave, Ds.Tinta),
        };
        fila.Add(chip, 1, 0);
        var detalle = string.Join(" · ", new[]
        {
            $"{t.Asientos} asientos",
            t.VerificadoEn is null ? "sin verificar" : $"verificado {Fecha(t.VerificadoEn)}" + (t.VerificadoHasta is { } vh && vh < t.Hasta ? $" hasta #{vh}" : ""),
            t.ExportadoEn is null ? null : $"exportado {Fecha(t.ExportadoEn)}",
            t.RotadoEn is null ? null : $"rotado {Fecha(t.RotadoEn)}",
            string.IsNullOrEmpty(t.SaltoCausa) ? null : $"causa {Causa(t.SaltoCausa)}",
        }.Where(x => x is not null));
        fila.Add(Ds.Secundario(detalle, 13), 2, 0);
        fila.Add(Ds.Secundario(t.HuellaCierre ?? "—", 12), 3, 0);
        foreach (var hijo in fila.Children.OfType<View>()) hijo.VerticalOptions = LayoutOptions.Center;
        return FilaPlana(fila);
    }

    private static string Causa(string? causa) => causa switch
    {
        "huella_discordante" => "la huella de un asiento no coincide con su contenido",
        "secuencia_con_hueco" => "falta un asiento en la secuencia",
        "secuencia_repetida" => "una secuencia aparece dos veces",
        "huella_previa_no_enlaza" => "un asiento no enlaza con el anterior",
        "cabeza_discordante" => "la cabeza del tramo no coincide con sus asientos",
        "triggers_ausentes" => "faltan los triggers de inmutabilidad",
        null or "" => "desconocida",
        _ => causa,
    };
}
