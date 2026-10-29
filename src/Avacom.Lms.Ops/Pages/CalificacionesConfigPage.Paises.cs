using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

// El sistema de calificación por país, a la vista y de primer nivel (no escondido tras «Cambiar» de un nivel): el país de la institución, sus sistemas con su rango y su mínimo para
// aprobar, y en qué niveles usarlo. «Usar en…» adopta el sistema (si aún no es de la institución; queda versionado) y valida y aplica cada nivel elegido, uno por uno, con las mismas
// reglas del nodo que el editor de un nivel: lo que un nivel no admita (evaluaciones en curso) se dice con sus palabras y no impide los demás. Todo con toques: no hay texto libre.
// El profesor ve el sistema resultante en el libro de calificaciones y el estudiante junto a su nota publicada.
public partial class CalificacionesConfigPage
{
    private string? _paisDelSistema;
    private string? _sistemaElegido;
    private readonly HashSet<string> _nivelesDelSistema = [];
    private bool _aplicandoSistema;

    private PlantillaDeEscala? SistemaElegido => _sistemaElegido is null ? null : _plantillas?.Plantillas.FirstOrDefault(p => p.Codigo == _sistemaElegido);

    // ----------------------------------------------------------------------------------------------- leer

    /// <summary>El catálogo de sistemas (las plantillas de escala) se lee una vez al abrir la pantalla: es lo primero que se ve, no algo que se pide al abrir un nivel.</summary>
    private async Task CargarPlantillasAsync()
    {
        if (_plantillas is not null || !_visible) return;
        var api = Api;
        var plantillas = await api.PlantillasAsync(CalificacionesUi.Actor);
        if (!_visible) return;
        if (plantillas is null)
        {
            _aviso.Mostrar("No se pudieron leer los sistemas de calificación", CalificacionesUi.Error(api), Tono.Ambar);
            return;
        }
        _plantillas = plantillas;
        Pintar();
    }

    // ----------------------------------------------------------------------------------------------- pintar

    private View SistemaPorPais(ConfiguracionAcademica c)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion("Sistema de calificación por país"));
        pila.Add(Ds.Secundario("Elige el país de tu institución y el sistema con que se califica cada nivel. El profesor lo ve en el libro de calificaciones al calificar y cada estudiante lo ve junto a su nota cuando el profesor la publica.", 14));
        var actual = Ds.Secundario(SistemaActual(c), 14);
        actual.AutomationId = "sistema-actual";
        pila.Add(actual);

        if (_plantillas is not { } catalogo)
        {
            pila.Add(Ds.Secundario("Leyendo los sistemas de calificación…", 14));
            return ExamenUi.Tarjeta(pila);
        }
        pila.Add(ExamenUi.Aviso("Sistemas orientativos", catalogo.Advertencia, Tono.Ambar));

        // ---- país
        var mostrado = PaisMostrado(catalogo);
        pila.Add(EstudioUi.Eyebrow("PAÍS"));
        var fichas = EstudioUi.Envolver();
        foreach (var codigo in FiltroDePlantillas.Paises(catalogo.Plantillas))
        {
            var pais = codigo;
            fichas.Add(EstudioUi.Chip(FiltroDePlantillas.NombreDePais(pais), mostrado == pais, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "País del sistema", () => ElegirPaisAsync(pais)), $"sistema-pais-{pais}", 56));
        }
        if (FiltroDePlantillas.HayGenericas(catalogo.Plantillas))
            fichas.Add(EstudioUi.Chip("Genéricos", mostrado == FiltroDePlantillas.Genericas, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "País del sistema", () => ElegirPaisAsync(FiltroDePlantillas.Genericas)), "sistema-pais-genericas", 56));
        pila.Add(fichas);

        // ---- sus sistemas
        var visibles = FiltroDePlantillas.Filtrar(catalogo.Plantillas, mostrado);
        if (visibles.Count == 0) pila.Add(Ds.Secundario("No hay sistemas para este país.", 14));
        foreach (var p in visibles) pila.Add(FilaDeSistema(p));

        // ---- dónde usarlo
        if (SistemaElegido is { } elegido && visibles.Any(p => p.Codigo == elegido.Codigo)) pila.Add(NivelesDelSistema(elegido));

        // ---- cómo convierte (la vista del editor de un nivel es la de ese nivel)
        if (_nivelEditando is null && (_vistaPrevia is not null || _calculandoVista)) pila.Add(VistaPrevia());
        return ExamenUi.Tarjeta(pila);
    }

    /// <summary>Lo que hay hoy en dos frases: qué niveles califican con notas y con qué sistema, y que el resto está en modo simple.</summary>
    private static string SistemaActual(ConfiguracionAcademica c)
    {
        var conNotas = c.Niveles.Where(n => n.EnModoCalificaciones && n.Escala is not null).OrderBy(n => OrdenDeNivel(n.NivelClave))
                        .Select(n => $"{SelectorDeGrupo.RotuloDeNivel(n.NivelClave)}: {GradebookTexto.Sistema(n.Escala)}").ToList();
        return conNotas.Count == 0
            ? "Ahora ningún nivel usa notas: todos están en modo simple (sin números), que es lo más sencillo para los más pequeños."
            : $"Ahora: {string.Join(" · ", conNotas)}. Los demás niveles están en modo simple (sin notas).";
    }

    private static int OrdenDeNivel(string nivel) => NivelesEducativos.Todos.ToList().IndexOf(nivel) is var i and >= 0 ? i : int.MaxValue;

    /// <summary>El país que se enseña: el que se tocó o, de entrada, el de la institución, o el del sistema que ya usa un nivel, o el primero del catálogo (siempre que tenga sistemas).</summary>
    private string? PaisMostrado(PlantillasDeEscalas catalogo)
    {
        if (_paisDelSistema is not null) return _paisDelSistema;
        var paises = FiltroDePlantillas.Paises(catalogo.Plantillas);
        var propio = _config?.Politica.Pais?.Trim().ToUpperInvariant();
        if (!string.IsNullOrEmpty(propio) && paises.Contains(propio)) return propio;
        var enUso = _config?.Niveles.Where(n => n.EnModoCalificaciones).OrderBy(n => OrdenDeNivel(n.NivelClave)).Select(n => n.Escala?.Pais?.Trim().ToUpperInvariant())
                            .FirstOrDefault(pais => !string.IsNullOrEmpty(pais) && paises.Contains(pais));
        if (enUso is not null) return enUso;
        if (paises.Count > 0) return paises[0];
        return FiltroDePlantillas.HayGenericas(catalogo.Plantillas) ? FiltroDePlantillas.Genericas : null;
    }

    private View FilaDeSistema(PlantillaDeEscala p)
    {
        var elegido = p.Codigo == _sistemaElegido;
        var textos = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = p.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        var lectura = GradebookTexto.ResumenDelSistema(p.Sistema);
        if (lectura.Length > 0) textos.Add(Ds.Secundario(lectura, 14));
        var niveles = GradebookTexto.Niveles(p.Sistema);
        if (niveles.Length > 0) textos.Add(Ds.Secundario($"Niveles de desempeño: {niveles}", 14));
        if (p.Niveles is { Count: > 0 } sugeridos) textos.Add(Ds.Secundario($"Suele usarse en: {string.Join(", ", sugeridos.Select(SelectorDeGrupo.RotuloDeNivel))}", 13));
        if (!string.IsNullOrWhiteSpace(p.Referencia)) textos.Add(Ds.Secundario(p.Referencia!, 13));
        // La advertencia va siempre con el sistema: orientativo, la institución debe revisarlo y adoptarlo.
        textos.Add(new Label { Text = p.Advertencia, FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = ExamenUi.TintaAmbar, LineBreakMode = LineBreakMode.WordWrap });

        var botones = new VerticalStackLayout { Spacing = 8, VerticalOptions = LayoutOptions.Center };
        botones.Add(ExamenUi.Accion("Ver conversión", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Ver sistema", () => VerSistemaAsync(p)), 220, $"sistema-ver-{p.Codigo}", 48, margen: false).Vista);
        botones.Add(ExamenUi.Accion(elegido ? "✓ Elegido" : "Elegir este sistema", elegido ? Ds.Rango.Primary : Ds.Rango.Secondary,
            CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Elegir sistema", () => ElegirSistemaAsync(p)), 220, $"sistema-elegir-{p.Codigo}", 48, margen: false).Vista);

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        fila.Add(textos, 0, 0);
        fila.Add(botones, 1, 0);
        return CalificacionesUi.Fila(fila, new Thickness(16, 10));
    }

    /// <summary>Los cinco niveles, para marcar en cuáles se usa el sistema elegido. Los que ya lo usan llevan ✓ y no se vuelven a aplicar.</summary>
    private View NivelesDelSistema(PlantillaDeEscala p)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(Ds.Separador());
        pila.Add(EstudioUi.Eyebrow("USAR ESTE SISTEMA EN"));
        var fichas = EstudioUi.Envolver();
        foreach (var nivel in NivelesEducativos.Todos)
        {
            var clave = nivel;
            var rotulo = SelectorDeGrupo.RotuloDeNivel(clave) + (UsaEsteSistema(clave, p) ? "  ✓" : string.Empty);
            fichas.Add(EstudioUi.Chip(rotulo, _nivelesDelSistema.Contains(clave), CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Nivel del sistema", () => AlternarNivelDelSistemaAsync(clave)), $"sistema-nivel-{clave}", 56));
        }
        pila.Add(fichas);
        pila.Add(Ds.Secundario($"«{p.Nombre}». Los niveles sugeridos vienen marcados; puedes elegir otros. ✓ = ese nivel ya usa este sistema. Un nivel con evaluaciones en curso no cambia hasta que terminen: se dice cuál.", 13));

        var pendientes = _nivelesDelSistema.Count(n => !UsaEsteSistema(n, p));
        var aplicar = ExamenUi.Accion(_aplicandoSistema ? "Un momento…" : pendientes == 0 ? "Elige al menos un nivel" : pendientes == 1 ? "Usar en 1 nivel" : $"Usar en {pendientes} niveles", Ds.Rango.Primary,
            CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Aplicar sistema", AplicarSistemaAsync), 320, "sistema-aplicar", 56, margen: false);
        Ds.Habilitar(aplicar.Boton, pendientes > 0 && !_aplicandoSistema);
        aplicar.Vista.HorizontalOptions = LayoutOptions.Start;
        pila.Add(aplicar.Vista);
        return pila;
    }

    private bool UsaEsteSistema(string nivelClave, PlantillaDeEscala p) =>
        _config?.Niveles.FirstOrDefault(n => n.NivelClave == nivelClave) is { EnModoCalificaciones: true, Escala: { } escala } && string.Equals(escala.Codigo, p.Codigo, StringComparison.OrdinalIgnoreCase);

    // ----------------------------------------------------------------------------------------------- lo que se toca

    private Task ElegirPaisAsync(string pais)
    {
        _paisDelSistema = pais;
        Pintar();
        return Task.CompletedTask;
    }

    private Task ElegirSistemaAsync(PlantillaDeEscala p)
    {
        _sistemaElegido = p.Codigo;
        _nivelesDelSistema.Clear();
        foreach (var nivel in p.Niveles ?? []) if (NivelesEducativos.Todos.Contains(nivel)) _nivelesDelSistema.Add(nivel);
        Pintar();
        return Task.CompletedTask;
    }

    private Task AlternarNivelDelSistemaAsync(string nivel)
    {
        if (!_nivelesDelSistema.Add(nivel)) _nivelesDelSistema.Remove(nivel);
        Pintar();
        return Task.CompletedTask;
    }

    /// <summary>Cómo convierte un sistema con los valores de muestra, sin adoptarlo. Si había un nivel abierto en el editor, se cierra: la vista previa es de este sistema.</summary>
    private Task VerSistemaAsync(PlantillaDeEscala p)
    {
        _nivelEditando = null;
        return VerPlantillaAsync(p);
    }

    /// <summary>
    /// Adopta el sistema (si la institución aún no lo tiene) y lo aplica a cada nivel elegido: valida y, si el nodo dice que se puede, cambia el nivel a modo calificaciones con él. Cada nivel
    /// es independiente: uno bloqueado (por evaluaciones en curso, por ejemplo) no impide los demás, y al final se cuenta qué pasó con cada uno. Adoptar no manda una solicitud que el nodo
    /// reconozca como repetida: si no hubo conexión no se sabe si llegó, y se dice así.
    /// </summary>
    private async Task AplicarSistemaAsync()
    {
        if (_aplicandoSistema || SistemaElegido is not { } sistema || _config is not { } config) return;
        var niveles = _nivelesDelSistema.Where(n => !UsaEsteSistema(n, sistema)).OrderBy(OrdenDeNivel).ToList();
        if (niveles.Count == 0) return;
        _aplicandoSistema = true;
        Pintar();
        try
        {
            var api = Api;
            var escalaId = config.Escalas.FirstOrDefault(e => e.Activa && string.Equals(e.PlantillaOrigen, sistema.Codigo, StringComparison.OrdinalIgnoreCase))?.Id;
            if (escalaId is null)
            {
                var adoptada = await api.AdoptarPlantillaAsync(CalificacionesUi.Actor, sistema.Codigo);
                if (!_visible) return;
                if (adoptada is null)
                {
                    _aviso.Mostrar("No se adoptó el sistema",
                        CalificacionesUi.SinConexion(api)
                            ? "No se pudo conectar con el aula y no se sabe si el sistema llegó a adoptarse. Actualiza la pantalla y mira si ya está antes de volver a intentarlo."
                            : CalificacionesUi.Error(api), Tono.Ambar);
                    return;
                }
                escalaId = adoptada.Id;
            }

            var informe = new List<string>();
            var fallos = 0;
            foreach (var nivel in niveles)
            {
                var rotulo = SelectorDeGrupo.RotuloDeNivel(nivel);
                var validacion = await api.ValidarNivelAsync(CalificacionesUi.Actor, nivel, ModosDeNivel.Calificaciones, escalaId);
                if (!_visible) return;
                if (validacion is null)
                {
                    fallos++;
                    informe.Add($"{rotulo}: no se pudo validar ({TextoDeCalificaciones.ErrorDeNivel(api.UltimoError, api.UltimoMotivo)})");
                    continue;
                }
                if (!validacion.Permitido)
                {
                    fallos++;
                    informe.Add($"{rotulo}: no se cambió. {string.Join(" ", validacion.Bloqueos)}");
                    continue;
                }
                var cambio = await api.ConfigurarNivelAsync(CalificacionesUi.Actor, nivel, ModosDeNivel.Calificaciones, escalaId);
                if (!_visible) return;
                if (cambio is null)
                {
                    fallos++;
                    informe.Add($"{rotulo}: no se cambió. {TextoDeCalificaciones.ErrorDeNivel(api.UltimoError, api.UltimoMotivo)}");
                    continue;
                }
                var avisos = validacion.Advertencias.Count == 0 ? string.Empty : $" (conviene saber: {string.Join(" ", validacion.Advertencias)})";
                informe.Add($"{rotulo}: {(cambio.Cambiado ? "listo" : "ya usaba este sistema")}{avisos}");
            }
            var titulo = fallos == 0 ? $"Sistema aplicado: {sistema.Nombre}" : fallos == niveles.Count ? "No se aplicó el sistema" : "El sistema se aplicó en parte";
            _aviso.Mostrar(titulo, string.Join(" · ", informe), fallos == 0 ? Tono.Exito : Tono.Ambar);
        }
        finally
        {
            _aplicandoSistema = false;
            if (_visible) Pintar();
        }
        await CargarAsync();
    }
}
