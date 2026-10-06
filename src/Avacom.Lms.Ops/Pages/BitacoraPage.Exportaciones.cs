using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Pestaña «Exportaciones» (PAN-240, FUN-200, BR-105): alcance declarado (un tramo), motivo de una lista cerrada, el paso explícito «autorizar
/// esta salida» (PAN-241: otra persona de administración concede la escalada de <c>audit.export</c>, que vale una operación) y la lista de
/// exportaciones con descarga. Sin autorización vigente el nodo niega (403 <c>autorizacion_requerida</c>) y lo asienta; con éxito, MSG-054.
/// </summary>
public partial class BitacoraPage
{
    private async Task<View> ExportacionesAsync()
    {
        var api = Sesion.Auditoria;
        var lista = await api.ExportacionesAsync();
        if (lista is null) return TarjetaDeError("No se pudieron leer las exportaciones", api.UltimoMotivo, () => MostrarAsync(Pestana.Exportaciones), api.UltimoError);
        var tramos = await api.TramosAsync();

        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Autorizacion(lista.AutorizacionVigente));
        pila.Add(Exportador(lista, tramos?.Tramos ?? []));
        pila.Add(Ds.Cuerpo("Exportaciones realizadas", 18));
        if (lista.Exportaciones.Count == 0) pila.Add(Vacio("Todavía no se exportó ningún tramo", "Cada exportación queda asentada con su alcance, su autor y su motivo."));
        else foreach (var e in lista.Exportaciones) pila.Add(FilaExportacion(e));
        return pila;
    }

    private View Autorizacion(bool vigente)
    {
        if (vigente)
            return Ds.Alerta_("Autorización de salida vigente", "Vale para UNA exportación y caduca sola. Todo lo que hagas con ella queda registrado (MSG-052).", Ds.ExitoSuave, TintaExito);
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(Ds.Alerta_("Exportar exige una autorización de salida",
            "Otra persona de administración debe concederte, aquí mismo, una escalada temporal de «exportar la bitácora» con motivo y caducidad (30 minutos, una operación). No existe la autoconcesión.",
            Ds.AlertaSuave, TintaAlerta));
        var autorizar = Ds.Boton("Autorizar esta salida", Ds.Rango.Secondary, null, 56, 240);
        autorizar.FontSize = 15;
        autorizar.HorizontalOptions = LayoutOptions.Start;
        var formulario = FormularioDeAutorizacion();
        formulario.IsVisible = false;
        autorizar.Clicked += (_, _) => formulario.IsVisible = !formulario.IsVisible;
        pila.Add(autorizar);
        pila.Add(formulario);
        return pila;
    }

    /// <summary>PAN-241: el documento y la clave de la OTRA persona, y el motivo de lista. Lo único que esta pantalla pide escribir.</summary>
    private View FormularioDeAutorizacion()
    {
        var documento = new Entry { Placeholder = "Documento de quien autoriza", FontSize = 16, HeightRequest = 48, Keyboard = Keyboard.Numeric };
        var clave = new Entry { Placeholder = "Su clave", IsPassword = true, FontSize = 16, HeightRequest = 48 };
        var motivo = new FilterPicker { Placeholder = "Motivo de la autorización", WidthRequest = 320 };
        motivo.Poblar(Autorizaciones.MotivosDeAutorizacion);
        var estado = Ds.Secundario("La persona que autoriza no deja sesión abierta en este equipo: se identifica, concede y se despide en el mismo paso.", 13);
        var conceder = Ds.Boton("Conceder 30 minutos", Ds.Rango.Primary, null, 56, 240);
        conceder.FontSize = 15;
        // Si quien autoriza es de administración, el nodo pide además el PIN maestro: teclado propio de seis puntos (el equipo no tiene teclado). Mientras
        // se marca, el documento y la clave siguen en sus campos; al terminar, la clave se borra pase lo que pase.
        var teclado = Avacom.Lms.Ops.Controls.MarcoDeAcceso.TecladoMaestro();
        var cancelarPin = Ds.Boton("Cancelar", Ds.Rango.Quiet, null, 46);
        cancelarPin.MinimumWidthRequest = 150;
        cancelarPin.HorizontalOptions = LayoutOptions.Center;
        var pinGrupo = new VerticalStackLayout
        {
            Spacing = 8, IsVisible = false, HorizontalOptions = LayoutOptions.Start,
            Children = { new Label { Text = "PIN maestro de la escuela", FontSize = 15, FontAttributes = FontAttributes.Bold, HorizontalTextAlignment = TextAlignment.Center }, teclado, cancelarPin },
        };
        async Task AutorizarAsync(string? pin)
        {
            if (Sesion.Usuario is null) { estado.Text = "Hace falta una sesión de usuario en este equipo."; return; }
            if (motivo.Selected is null) { estado.Text = "Elige el motivo de la autorización."; return; }
            if (string.IsNullOrWhiteSpace(documento.Text) || string.IsNullOrWhiteSpace(clave.Text)) { estado.Text = "Escribe el documento y la clave de quien autoriza."; return; }
            Ds.Habilitar(conceder, false);
            teclado.Habilitado = false;
            try
            {
                var (ok, mensaje, requierePin) = await Autorizaciones.AutorizarSalidaAsync(documento.Text.Trim(), clave.Text, motivo.Selected, pin);
                estado.Text = mensaje;
                if (requierePin && Sesion.Acceso.UltimoError is not { PinMaestroBloqueado: true })
                {
                    if (pin is not null) await teclado.SacudirAsync();
                    pinGrupo.IsVisible = true;
                    return;   // la clave se conserva hasta que se marque el PIN
                }
                pinGrupo.IsVisible = false;
                teclado.Limpiar();
                clave.Text = string.Empty;
                if (ok) await MostrarAsync(Pestana.Exportaciones);
            }
            finally { Ds.Habilitar(conceder, true); teclado.Habilitado = true; }
        }
        teclado.PinCompleto += async (_, pin) => await AutorizarAsync(pin);
        cancelarPin.Clicked += (_, _) => { pinGrupo.IsVisible = false; teclado.Limpiar(); clave.Text = string.Empty; estado.Text = "Autorización cancelada."; };
        conceder.Clicked += async (_, _) => await AutorizarAsync(null);
        var fila = new HorizontalStackLayout { Spacing = 10, Children = { documento, clave, motivo, conceder } };
        documento.WidthRequest = 240; clave.WidthRequest = 200;
        var pila = new VerticalStackLayout { Spacing = 10, Children = { Ds.Cuerpo("Quien autoriza", 16), fila, estado, pinGrupo } };
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(20, 16), Colors.White);
    }

    private View Exportador(ListaExportaciones lista, IReadOnlyList<TramoBitacora> tramos)
    {
        var candidatos = tramos.Where(t => t.Hasta >= t.Desde).OrderByDescending(t => t.Desde).ToList();
        var tramo = new FilterPicker { Placeholder = "Elige el tramo", WidthRequest = 360 };
        tramo.Poblar(candidatos.Select(t => $"Tramo {t.Rango} · {t.EstadoLegible}"));
        var motivo = new FilterPicker { Placeholder = "Motivo de la exportación", WidthRequest = 320 };
        motivo.Poblar(lista.Motivos.Select(m => m.Etiqueta));
        var estado = Ds.Secundario("El archivo lleva el manifiesto firmado por el nodo y los asientos del tramo. Sólo se exporta un tramo verificado sin saltos.", 13);
        var exportar = Ds.Boton("Exportar", Ds.Rango.Primary, null, 56, 180);
        exportar.FontSize = 15;
        Ds.Habilitar(exportar, lista.AutorizacionVigente);
        exportar.Clicked += async (_, _) =>
        {
            var elegido = candidatos.ElementAtOrDefault(candidatos.FindIndex(t => $"Tramo {t.Rango} · {t.EstadoLegible}" == tramo.Selected));
            var codigo = lista.Motivos.FirstOrDefault(m => m.Etiqueta == motivo.Selected)?.Codigo;
            if (elegido is null || codigo is null) { estado.Text = "Elige el tramo y el motivo."; return; }
            Ds.Habilitar(exportar, false);
            try { await ExportarTramoAsync(elegido.Id, codigo, estado); }
            finally { Ds.Habilitar(exportar, lista.AutorizacionVigente); }
        };
        var fila = new HorizontalStackLayout { Spacing = 10, Children = { tramo, motivo, exportar } };
        var pila = new VerticalStackLayout { Spacing = 10, Children = { Ds.Cuerpo("Exportar un tramo firmado", 16), fila, estado } };
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(20, 16), Colors.White);
    }

    /// <summary>FUN-200: exporta el tramo y, con éxito, repinta la pestaña con MSG-054; los errores de negocio van al rótulo de estado.</summary>
    private async Task ExportarTramoAsync(string tramoId, string codigo, Label estado)
    {
        var resultado = await Sesion.Auditoria.ExportarAsync(codigo, tramoId: tramoId);
        if (resultado is null)
        {
            var error = Sesion.Auditoria.UltimoError;
            estado.Text = error?.Codigo switch
            {
                "autorizacion_requerida" => "Hace falta una autorización de salida vigente. El intento quedó registrado.",
                "cadena_con_salto" => $"El tramo tiene un salto en la secuencia {error.Numero("salto_en")}: hay que aclararlo antes de exportar.",
                "tramo_no_verificado" => "Verifica el tramo en «Integridad» antes de exportarlo.",
                _ => error?.Detalle ?? "No se pudo exportar.",
            };
            return;
        }
        await MostrarAsync(Pestana.Exportaciones);
        ContenidoHost.Insert(0, Ds.Alerta_(resultado.Mensaje ?? $"Queda registrado que exportaste {resultado.Alcance}.",
            $"{resultado.Total} asientos · archivo {resultado.Archivo}. Descárgalo desde la lista; la autorización se consumió con esta operación.", Ds.ExitoSuave, TintaExito));
    }

    /// <summary>Baja el archivo firmado a la carpeta de descargas del equipo y lo dice en la fila.</summary>
    private async Task DescargarAsync(Exportacion e, Label estado, Button descargar)
    {
        Ds.Habilitar(descargar, false);
        var destino = System.IO.Path.Combine(CarpetaDescargas(), e.Archivo ?? $"exportacion-{e.ExportacionId}.jsonl");
        var ruta = await Sesion.Auditoria.DescargarExportacionAsync(e.ExportacionId, destino);
        estado.Text = ruta is null ? (Sesion.Auditoria.UltimoMotivo ?? "No se pudo descargar.") : $"Guardado en {ruta}";
        Ds.Habilitar(descargar, true);
    }

    private View FilaExportacion(Exportacion e)
    {
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(150), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        fila.Add(Ds.Secundario(Fecha(e.ExportadoEn), 13), 0, 0);
        var texto = new VerticalStackLayout { Spacing = 2 };
        texto.Add(Ds.Cuerpo($"{e.Alcance ?? "—"} · {e.Total} asientos", 15));
        texto.Add(Ds.Secundario($"{e.Motivo ?? "—"} · {e.Archivo ?? "—"}", 12));
        fila.Add(texto, 1, 0);
        fila.Add(e.Disponible == false ? Chip("Archivo no disponible", Ds.AlertaSuave, TintaAlerta) : Chip("Firmado", Ds.ExitoSuave, TintaExito), 2, 0);
        var estado = Ds.Secundario(string.Empty, 12);
        texto.Add(estado);
        var descargar = Ds.Boton("Descargar", Ds.Rango.Quiet, null, 48, 150);
        descargar.FontSize = 14;
        Ds.Habilitar(descargar, e.Disponible != false);
        descargar.Clicked += async (_, _) => await DescargarAsync(e, estado, descargar);
        fila.Add(descargar, 3, 0);
        foreach (var hijo in fila.Children.OfType<View>()) hijo.VerticalOptions = LayoutOptions.Center;
        return FilaPlana(fila);
    }
}
