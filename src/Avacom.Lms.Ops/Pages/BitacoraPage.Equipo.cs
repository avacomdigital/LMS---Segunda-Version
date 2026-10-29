using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Core.Nodo;
using Avacom.Lms.Ops.Nodo;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// PAN-242 · lo que MOD-015 añade a «Estado del equipo» (P-18): el chip de estado del nodo (Operativo, Restringido, Recuperándose) con sus motivos, la base, el disco, el reloj, la
/// cola por consumidor (pendientes, rezagados, apartados) con [Reproducir], el último punto de recuperación, los eventos apartados con [Reprocesar] (una confirmación; el nodo exige
/// <c>node.queue.replay</c>: la administración lo tiene y el técnico sólo por escalada) y [Reintentar] para volver a leer. Sólo <c>Border</c>, <c>Label</c> y <c>Button</c> (R-17);
/// la lógica vive en <see cref="ResumenDelEquipo"/> y <see cref="FlujoDeReproceso"/>, que <c>Ops.Tests</c> enlaza. El técnico nunca ve la carga de un evento: el nodo no la entrega.
/// </summary>
public partial class BitacoraPage
{
    private FlujoDeReproceso? _reproceso;

    private async Task<View> SeccionDelNodoAsync()
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Ds.Cuerpo("Nodo del aula y cola de salida", 16));
        var api = Sesion.Nodo;
        using var limite = new CancellationTokenSource(TimeSpan.FromSeconds(6));
        var estado = await api.EstadoAsync(Sesion.ProfesorId, limite.Token);
        if (estado is null)
        {
            pila.Add(TarjetaDeError("No se pudo leer el estado del nodo", NodoTexto.DeError(api.UltimoError).Completo, () => MostrarAsync(Pestana.Equipo), api.UltimoError));
            return pila;
        }
        pila.Add(TarjetaDeEstado(estado));
        var cola = await api.ColaAsync(Sesion.ProfesorId, limite.Token);
        if (cola is null) pila.Add(TarjetaDeError("No se pudo leer la cola", NodoTexto.DeError(api.UltimoError).Completo, () => MostrarAsync(Pestana.Equipo), api.UltimoError));
        else pila.Add(TarjetaDeCola(cola));
        var problemas = await api.ProblemasAsync(Sesion.ProfesorId, ct: limite.Token);
        pila.Add(Ds.Cuerpo("Eventos apartados", 16));
        if (problemas is null) pila.Add(TarjetaDeError("No se pudieron leer los eventos apartados", NodoTexto.DeError(api.UltimoError).Completo, () => MostrarAsync(Pestana.Equipo), api.UltimoError));
        else if (problemas.Problemas.Count == 0) pila.Add(Vacio("Sin eventos apartados", "Cuando un consumidor no pueda aplicar un evento tras varios intentos, quedará aquí para reprocesarlo."));
        else foreach (var p in problemas.Problemas) pila.Add(FilaProblema(p));
        return pila;
    }

    // ------------------------------------------------------------------ el estado

    private static (Color Fondo, Color Tinta) ColoresDe(TonoDelNodo tono) => tono switch
    {
        TonoDelNodo.Bien => (Ds.ExitoSuave, TintaExito),
        TonoDelNodo.Atencion => (Ds.AlertaSuave, TintaAlerta),
        TonoDelNodo.Problema => (Ds.PeligroSuave, TintaPeligro),
        _ => (Color.FromArgb("#E3E6EC"), Ds.TintaSuave),
    };

    private View TarjetaDeEstado(EstadoDelNodo e)
    {
        var (fondo, tinta) = ColoresDe(NodoTexto.TonoDeEstado(e.Estado));
        var pila = new VerticalStackLayout { Spacing = 10 };
        var cabecera = new HorizontalStackLayout { Spacing = 12 };
        var chip = Chip(NodoTexto.Estado(e.Estado), fondo, tinta);
        chip.AutomationId = "nodo-estado";
        cabecera.Add(chip);
        var explicacion = Ds.Cuerpo(NodoTexto.ExplicacionDeEstado(e.Estado), 15);
        explicacion.LineBreakMode = LineBreakMode.WordWrap;
        explicacion.VerticalOptions = LayoutOptions.Center;
        cabecera.Add(explicacion);
        pila.Add(cabecera);
        foreach (var motivo in ResumenDelEquipo.Motivos(e)) pila.Add(Ds.Alerta_("Por qué está restringido", motivo, Ds.PeligroSuave, TintaPeligro));
        foreach (var linea in ResumenDelEquipo.Lineas(e))
        {
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(230), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
            fila.Add(Ds.Secundario(linea.Rotulo, 14), 0, 0);
            var valor = Ds.Cuerpo(linea.Valor, 14, linea.Tono == TonoDelNodo.Neutro ? null : ColoresDe(linea.Tono).Tinta);
            valor.LineBreakMode = LineBreakMode.WordWrap;
            fila.Add(valor, 1, 0);
            pila.Add(fila);
        }
        var acciones = new HorizontalStackLayout { Spacing = 12 };
        var reintentar = Ds.Boton("Reintentar", Ds.Rango.Secondary, async (_, _) => await MostrarAsync(Pestana.Equipo), 52, 160);
        reintentar.FontSize = 15;
        reintentar.AutomationId = "nodo-reintentar";
        acciones.Add(reintentar);
        pila.Add(acciones);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(20, 16), Colors.White);
    }

    // ------------------------------------------------------------------ la cola

    private View TarjetaDeCola(ColaDelNodo cola)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(Ds.Secundario(ResumenDelEquipo.ResumenDeCola(cola), 14));
        var filas = ResumenDelEquipo.Consumidores(cola);
        if (filas.Count == 0) pila.Add(Ds.Secundario("Todavía no hay consumidores registrados en la cola única: los módulos se irán conectando a ella por fases.", 14));
        foreach (var f in filas)
        {
            var (fondo, tinta) = ColoresDe(f.Tono);
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
            fila.Add(Chip(f.EstadoVisible, fondo, tinta), 0, 0);
            var texto = new VerticalStackLayout { Spacing = 2 };
            texto.Add(Ds.Cuerpo($"{f.NombreVisible} · {NodoTexto.Pendientes(f.Pendientes)} · {NodoTexto.Apartados(f.Problemas)}", 15));
            foreach (var fuente in f.Fuentes) texto.Add(Ds.Secundario(fuente, 13));
            if (f.Reintento is { } r) texto.Add(Ds.Secundario(r, 13));
            fila.Add(texto, 1, 0);
            if (ReglasDeNodo.OfrecerReproceso(Sesion.Usuario))
            {
                var nombre = f.Nombre;
                var reproducir = Ds.Boton("Reproducir", Ds.Rango.Quiet, async (_, _) => await ReproducirAsync(nombre), 48, 150);
                reproducir.FontSize = 14;
                reproducir.AutomationId = $"nodo-reproducir-{nombre}";
                reproducir.VerticalOptions = LayoutOptions.Center;
                fila.Add(reproducir, 2, 0);
            }
            foreach (var hijo in fila.Children.OfType<View>()) hijo.VerticalOptions = LayoutOptions.Center;
            pila.Add(FilaPlana(fila));
        }
        // Fase 3: los módulos que ya escriben sólo en la cola única (su cola antigua queda como historia de sólo lectura).
        var cortes = ResumenDelEquipo.Cortes(cola);
        pila.Add(Ds.Cuerpo("Módulos conectados a la cola única", 15));
        if (cortes.Count == 0) pila.Add(Ds.Secundario("Ninguno todavía: cada módulo sigue con su cola propia hasta que se conecte.", 13));
        foreach (var corte in cortes)
        {
            var texto = Ds.Secundario(corte, 13);
            texto.LineBreakMode = LineBreakMode.WordWrap;
            pila.Add(texto);
        }
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(20, 16), Colors.White);
    }

    private View FilaProblema(ProblemaDeCola p)
    {
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        var (fondo, tinta) = p.Apartado ? (Ds.AlertaSuave, TintaAlerta) : (Ds.ExitoSuave, TintaExito);
        fila.Add(Chip(NodoTexto.EstadoDeProblema(p.Estado), fondo, tinta), 0, 0);
        var texto = new VerticalStackLayout { Spacing = 2 };
        var titulo = Ds.Cuerpo(NodoTexto.Problema(p), 15);
        titulo.LineBreakMode = LineBreakMode.TailTruncation; titulo.MaxLines = 1;
        texto.Add(titulo);
        var error = Ds.Secundario($"{NodoTexto.FechaCorta(p.ApartadoEn)} · {NodoTexto.ErrorDeProblema(p)}", 13);
        error.LineBreakMode = LineBreakMode.TailTruncation; error.MaxLines = 1;
        texto.Add(error);
        fila.Add(texto, 1, 0);
        if (ReglasDeNodo.OfrecerReprocesar(p, Sesion.Usuario))
        {
            var reprocesar = Ds.Boton("Reprocesar", Ds.Rango.Primary, async (_, _) => await ReprocesarAsync(p), 48, 160);
            reprocesar.FontSize = 14;
            reprocesar.AutomationId = $"nodo-reprocesar-{p.Id}";
            fila.Add(reprocesar, 2, 0);
        }
        foreach (var hijo in fila.Children.OfType<View>()) hijo.VerticalOptions = LayoutOptions.Center;
        return FilaPlana(fila);
    }

    // ------------------------------------------------------------------ las acciones (una confirmación, un envío)

    private FlujoDeReproceso Reproceso => _reproceso ??= new FlujoDeReproceso(Sesion.Nodo, Sesion.ProfesorId);

    private async Task ReprocesarAsync(ProblemaDeCola p)
    {
        if (!await this.AlertaAsync("Reprocesar el evento", NodoTexto.ConfirmarReproceso(p), "Reprocesar", "Cancelar")) return;
        var mensaje = await Reproceso.ReprocesarAsync(p.Id);
        await MostrarAsync(Pestana.Equipo);
        ContenidoHost.Insert(0, AvisoDe(mensaje, Reproceso.UltimoReprocesado is { } r && r.Id == p.Id));
    }

    private async Task ReproducirAsync(string consumidor)
    {
        if (!await this.AlertaAsync("Reproducir desde el principio", NodoTexto.ConfirmarReproduccion(consumidor), "Reproducir", "Cancelar")) return;
        var mensaje = await Reproceso.ReproducirAsync(consumidor);
        await MostrarAsync(Pestana.Equipo);
        ContenidoHost.Insert(0, AvisoDe(mensaje, Reproceso.UltimaReproduccion is { } r && r.Consumidor == consumidor));
    }

    private static Border AvisoDe(MensajeDeNodo mensaje, bool bien) =>
        bien ? Ds.Alerta_(mensaje.Titulo, mensaje.Completo, Ds.ExitoSuave, TintaExito) : Ds.Alerta_(mensaje.Titulo, mensaje.Completo, Ds.AlertaSuave, TintaAlerta);
}
