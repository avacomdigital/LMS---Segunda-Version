using System.Globalization;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Estado y ajustes de los reportes (BR-007 y FUN-144). Para quien puede reconstruirlos o configurarlos (lo dice el nodo): qué tan al día están los números —dicho como antigüedad del
/// dato, no como estado interno—, de qué fuentes se alimentan, «Actualizar ahora» (pone al día lo que falte) y «Reconstruir» (borra lo calculado y lo vuelve a calcular desde lo que el aula
/// registró: no pierde ningún dato). Reconstruir espera a que no haya una clase en curso, para no competir con las tabletas. La administración, además, fija cómo se guardan los reportes:
/// si se permiten las memorias USB, si se pide un motivo (se elige de una lista) y si la privacidad recorta los grupos pequeños. Cada cambio avisa si alguien más cambió lo mismo.
/// </summary>
public sealed class ReportesEstadoPage : PaginaDeReporte
{
    private static readonly TablaDeReporte Fuentes = new(
        new ColumnaDeTabla("Fuente", GridLength.Star),
        new ColumnaDeTabla("Novedades leídas", new GridLength(190), Derecha: true),
        new ColumnaDeTabla("Pendientes", new GridLength(170)),
        new ColumnaDeTabla("Estado", new GridLength(190)));

    private EstadoDeAgregados? _estado;
    private ConfiguracionDeReportes? _config;
    private PermisosDeReportes? _puede;
    private bool _ocupado;

    public ReportesEstadoPage() : base("REPORTES · ESTADO Y AJUSTES", "Estado de los reportes", "Qué tan al día están los números y cómo se guardan los archivos.") { }

    protected override async Task LeerAsync(bool forzar)
    {
        var api = ReportesUi.Api;
        var estado = await LeerYPintarAsync(api, () => api.EstadoAsync(ReportesUi.Actor), e => _estado = e, "No se pudo leer el estado de los reportes");
        if (estado is null) return;
        var filtros = await ReportesUi.FiltrosAsync(forzar: true);
        _puede = filtros?.Puede;
        _config = (_puede?.Configurar ?? false) ? (await api.ConfiguracionAsync(ReportesUi.Actor))?.Configuracion : null;
        if (!EstaVisible) return;
        Pintar();
    }

    private static string NombreDeFuente(string fuente) => fuente switch
    {
        "aula" => "Clases en el aula",
        "evaluacion" => "Evaluaciones",
        "calificacion" => "Calificaciones",
        "estudio" => "Modo de estudio",
        _ => fuente,
    };

    private void Pintar()
    {
        var e = _estado!;
        CorteHost.Clear();
        EncabezadoFijo(null);
        ContenidoHost.Clear();

        // ---- qué tan al día
        var (pildora, tono, frase) = e.Estado switch
        {
            EstadosDeProyeccion.Reconstruyendose => ("Actualizándose", Tono.Info, "Se están recalculando los reportes. Mientras tanto se ve lo último que estaba listo."),
            EstadosDeProyeccion.Rezagada => ("Con retraso", Tono.Ambar, $"Faltan novedades por reflejar: los datos tienen {FormatoDeReportes.Duracion(e.AntiguedadMs)}."),
            _ => ("Al día", Tono.Exito, "Los reportes reflejan todo lo que el aula ha registrado."),
        };
        var pila = new VerticalStackLayout { Spacing = 8 };
        var cabecera = ExamenUi.Fila();
        cabecera.Add(ExamenUi.PildoraEnFila(pildora, tono, 15));
        pila.Add(cabecera);
        pila.Add(new Label { Text = frase, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "estado-frase" });
        pila.Add(ExamenUi.Dato("Datos al", FormatoDeReportes.FechaLarga(e.CorteEn), 200));
        if (e.ActualizadaEn is { } a) pila.Add(ExamenUi.Dato("Última actualización", FormatoDeReportes.FechaLarga(a), 200));
        pila.Add(ExamenUi.Dato("Clases con reporte", e.Clases.ToString(CultureInfo.InvariantCulture), 200));
        pila.Add(ExamenUi.Dato("Grupos", e.Grupos.Desactualizados == 0 ? FormatoDeReportes.Plural(e.Grupos.Total, "grupo", "grupos") : $"{FormatoDeReportes.Plural(e.Grupos.Total, "grupo", "grupos")} · {e.Grupos.Desactualizados} por recalcular", 200));
        if (e.ClaseEnCurso) pila.Add(ExamenUi.Aviso("Hay una clase en curso", "Reconstruir los reportes espera a que termine, para no competir con las tabletas.", Tono.Info));
        if (e.Reconstruccion.Error is { Length: > 0 } error) pila.Add(ExamenUi.Aviso("La última reconstrucción no terminó", error, Tono.Ambar));
        ContenidoHost.Add(ReportesUi.Tarjeta(pila));

        // ---- de qué se alimentan
        ContenidoHost.Add(ReportesUi.Seccion("De dónde salen los números", "Cada fuente se lee por lo que avisa, no por sus tablas."));
        ContenidoHost.Add(Fuentes.EnTarjeta(e.Fuentes.Select((f, i) => Fuentes.Fila([
            ReportesUi.Celda(NombreDeFuente(f.Fuente), medio: true),
            f.Marca.ToString(CultureInfo.InvariantCulture),
            f.Pendientes ? ReportesUi.ConPunto("Hay novedades", ReportesUi.ColorDeAdvertencia) : ReportesUi.ConPunto("Sin pendientes", Ds.Exito),
            f.FallosSeguidos > 0 ? ReportesUi.ConPunto($"Falló {f.FallosSeguidos} {(f.FallosSeguidos == 1 ? "vez" : "veces")}", Ds.Peligro) : ReportesUi.ConPunto("Bien", Ds.Exito),
        ], cebra: i % 2 == 1)).ToList()));

        // ---- acciones de mantenimiento
        if (_puede?.Reconstruir == true)
        {
            var acciones = ExamenUi.Fila();
            acciones.Add(ExamenUi.Accion("Actualizar ahora", Ds.Rango.Secondary, ReportesUi.Seguro(nameof(ReportesEstadoPage), "Actualizar", ActualizarAhoraAsync), 220, "estado-actualizar").Vista);
            var (reconstruir, vista) = ExamenUi.Accion("Reconstruir los reportes", Ds.Rango.Destructive, ReportesUi.Seguro(nameof(ReportesEstadoPage), "Reconstruir", ReconstruirAsync), 280, "estado-reconstruir");
            Ds.Habilitar(reconstruir, e.PuedeReconstruir && !_ocupado);
            acciones.Add(vista);
            ContenidoHost.Add(ReportesUi.Seccion("Mantenimiento", "«Actualizar» pone al día lo que falte. «Reconstruir» vuelve a calcular todo desde cero y no pierde ningún dato."));
            ContenidoHost.Add(acciones);
        }

        // ---- ajustes de exportación y privacidad (sólo administración)
        if (_config is { } c) PintarAjustes(c);
    }

    // ------------------------------------------------------------------------------------------------------------ mantenimiento

    private async Task ActualizarAhoraAsync()
    {
        if (_ocupado) return;
        _ocupado = true;
        try
        {
            var api = ReportesUi.Api;
            var r = await api.ActualizarAsync(ReportesUi.Actor);
            if (r is null) { Aviso.Mostrar("No se pudo actualizar", ReportesUi.Error(api), Tono.Ambar); return; }
            var novedades = r.Eventos ?? 0;
            Aviso.Mostrar("Listo", novedades == 0 ? "No había novedades por reflejar." : $"Se reflejaron {FormatoDeReportes.Plural(novedades, "novedad", "novedades")}.", Tono.Exito);
        }
        finally { _ocupado = false; }
        await CargarAsync(forzar: true);
    }

    private async Task ReconstruirAsync()
    {
        if (_ocupado) return;
        var respuesta = await Opciones.PedirAsync("¿Reconstruir los reportes?",
            "Se borran los números calculados y se vuelven a calcular desde lo que el aula registró. No se pierde ningún dato de clases, evaluaciones ni notas. Puede tardar unos segundos.",
            [new OpcionDeHoja("si", "Sí, reconstruir ahora", true)]);
        if (respuesta != "si") return;
        _ocupado = true;
        Pintar();
        try
        {
            var api = ReportesUi.Api;
            var r = await api.ReconstruirAsync(ReportesUi.Actor);
            if (r is null) { Aviso.Mostrar("No se pudo reconstruir", ReportesUi.Error(api), Tono.Ambar); return; }
            if (r.GruposFallidos.Count > 0)
                Aviso.Mostrar("Se reconstruyó, pero no todo", $"Se recalcularon {FormatoDeReportes.Plural(r.Grupos, "grupo", "grupos")}; {FormatoDeReportes.Plural(r.GruposFallidos.Count, "grupo no se pudo recalcular", "grupos no se pudieron recalcular")}. Vuelve a intentarlo.", Tono.Ambar);
            else
                Aviso.Mostrar("Listo", $"Se recalcularon {FormatoDeReportes.Plural(r.Grupos, "grupo", "grupos")} a partir de {FormatoDeReportes.Plural(r.Eventos ?? 0, "novedad", "novedades")}. Los números son los mismos de antes, calculados de nuevo.", Tono.Exito);
        }
        finally { _ocupado = false; }
        await CargarAsync(forzar: true);
    }

    // ------------------------------------------------------------------------------------------------------------ ajustes

    private void PintarAjustes(ConfiguracionDeReportes c)
    {
        ContenidoHost.Add(ReportesUi.Seccion("Ajustes de los reportes", "Sólo la administración los cambia. Valen para todo el aula y quedan anotados en el historial."));
        var pila = new VerticalStackLayout { Spacing = 18 };
        pila.Add(Ajuste("Guardar reportes en memorias USB", "Si se desactiva, las memorias y discos externos desaparecen de la lista de destinos.",
            ("Permitido", c.ExtraiblesPermitidos, new CambioDeConfiguracion(ExtraiblesPermitidos: true)), ("Desactivado", !c.ExtraiblesPermitidos, new CambioDeConfiguracion(ExtraiblesPermitidos: false)), "ajuste-extraibles"));
        pila.Add(Ajuste("Pedir para qué se guarda un reporte", "Quien guarda elige el motivo de una lista antes de continuar. No se escribe nada.",
            ("No", !c.ExigirRazon, new CambioDeConfiguracion(ExigirRazon: false)), ("Sí", c.ExigirRazon, new CambioDeConfiguracion(ExigirRazon: true)), "ajuste-razon"));
        pila.Add(Ajuste($"Privacidad en grupos de menos de {c.MinimoDeAlumnos} estudiantes", "Con la privacidad activa, esos reportes (y sus archivos) muestran sólo los totales, sin comparar a las personas.",
            ("Apagada", !c.UmbralPrivacidad, new CambioDeConfiguracion(UmbralPrivacidad: false)), ("Activa", c.UmbralPrivacidad, new CambioDeConfiguracion(UmbralPrivacidad: true)), "ajuste-privacidad"));
        ContenidoHost.Add(ReportesUi.Tarjeta(pila));
        PintarAjustesDelBoletin(c);
    }

    /// <summary>
    /// El boletín académico: con qué plantilla se arma (automática por el país del colegio, Colombia, México o genérica) y cómo se llaman los periodos de la institución (su propio sistema de
    /// evaluación los define: ni tres ni cuatro son universales). Todo son fichas: nada exige escribir.
    /// </summary>
    private void PintarAjustesDelBoletin(ConfiguracionDeReportes c)
    {
        ContenidoHost.Add(ReportesUi.Seccion("Boletín académico", "Cómo se arma el boletín de cada estudiante. No es un documento oficial: es la base para el que la institución expide."));
        var pila = new VerticalStackLayout { Spacing = 18 };

        var plantilla = new VerticalStackLayout { Spacing = 6 };
        plantilla.Add(new Label { Text = "Plantilla", FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta });
        var fichas = EstudioUi.Envolver();
        foreach (var codigo in c.PlantillasDeBoletin ?? [PlantillasDeBoletin.Auto, PlantillasDeBoletin.Colombia, PlantillasDeBoletin.Mexico, PlantillasDeBoletin.Generica])
        {
            var elegido = codigo;
            fichas.Add(EstudioUi.Chip(PlantillasDeBoletin.Rotulo(codigo), (c.PlantillaBoletin ?? PlantillasDeBoletin.Auto) == codigo,
                ReportesUi.Seguro(nameof(ReportesEstadoPage), "PlantillaBoletin", () => CambiarAsync(new CambioDeConfiguracion(PlantillaBoletin: elegido))), $"ajuste-plantilla-{codigo}"));
        }
        plantilla.Add(fichas);
        pila.Add(plantilla);

        var periodos = new VerticalStackLayout { Spacing = 6 };
        periodos.Add(new Label { Text = "Periodos de la institución", FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta });
        periodos.Add(Ds.Secundario("Los que define el sistema de evaluación del colegio (en Colombia, el SIEE). Sin fijarlos, el boletín usa los de la plantilla o el periodo del grupo.", 14));
        var opciones = EstudioUi.Envolver();
        var actuales = c.PeriodosBoletin ?? [];
        foreach (var (rotulo, lista) in PeriodosPredefinidos)
        {
            var elegida = lista;
            opciones.Add(EstudioUi.Chip(rotulo, actuales.SequenceEqual(lista), ReportesUi.Seguro(nameof(ReportesEstadoPage), "PeriodosBoletin", () => CambiarAsync(new CambioDeConfiguracion(PeriodosBoletin: elegida))),
                $"ajuste-periodos-{lista.Count}"));
        }
        periodos.Add(opciones);
        if (actuales.Count > 0) periodos.Add(Ds.Secundario("Ahora: " + string.Join(" · ", actuales), 13));
        pila.Add(periodos);
        ContenidoHost.Add(ReportesUi.Tarjeta(pila));
    }

    private static readonly (string Rotulo, IReadOnlyList<string> Lista)[] PeriodosPredefinidos =
    [
        ("Sin fijar", []),
        ("Dos semestres", ["Primer semestre", "Segundo semestre"]),
        ("Tres periodos", ["1.er periodo", "2.º periodo", "3.er periodo"]),
        ("Cuatro periodos", ["1.er periodo", "2.º periodo", "3.er periodo", "4.º periodo"]),
        ("Tres trimestres", ["1.er trimestre", "2.º trimestre", "3.er trimestre"]),
    ];

    private View Ajuste(string titulo, string ayuda, (string Rotulo, bool Activo, CambioDeConfiguracion Cambio) a, (string Rotulo, bool Activo, CambioDeConfiguracion Cambio) b, string id)
    {
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        pila.Add(Ds.Secundario(ayuda, 14));
        var fila = EstudioUi.Envolver();
        foreach (var (rotulo, activo, cambio) in new[] { a, b })
        {
            var c = cambio;
            fila.Add(EstudioUi.Chip(rotulo, activo, ReportesUi.Seguro(nameof(ReportesEstadoPage), id, () => CambiarAsync(c)), $"{id}-{rotulo.ToLowerInvariant()}"));
        }
        pila.Add(fila);
        return pila;
    }

    private async Task CambiarAsync(CambioDeConfiguracion cambio)
    {
        if (_config is null || _ocupado) return;
        _ocupado = true;
        try
        {
            var api = ReportesUi.Api;
            var r = await api.CambiarConfiguracionAsync(ReportesUi.Actor, cambio with { VersionEsperada = _config.Version });
            if (r is null)
            {
                Aviso.Mostrar("No se pudo guardar el ajuste", ReportesUi.Error(api), Tono.Ambar);
                if (api.UltimoError?.Codigo == "conflicto_de_version") { _ocupado = false; await CargarAsync(forzar: true); }
                return;
            }
            _config = r.Configuracion;
            ReportesUi.OlvidarFiltros();
            Aviso.Mostrar(r.Cambiado == false ? "Ya estaba así" : "Ajuste guardado", r.Cambiado == false ? null : "Vale desde ya para quien guarde un reporte.", r.Cambiado == false ? Tono.Info : Tono.Exito);
        }
        finally { _ocupado = false; }
        Pintar();
    }
}
