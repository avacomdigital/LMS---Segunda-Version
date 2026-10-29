using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

// El editor de UN nivel: modo, escala (adoptada o plantilla por adoptar), vista previa de la conversión, validación y aplicar. Todo se elige con fichas y botones de 52–56 px; no hay texto libre.
// El orden del flujo es el de la especificación: elegir → ver la vista previa → «Validar el cambio» (bloqueos y advertencias del nodo) → «Aplicar». «Aplicar» sólo se habilita cuando la última
// validación de ESTA propuesta dijo que se puede: cambiar el modo o la escala invalida la validación.
public partial class CalificacionesConfigPage
{
    private string? _nivelEditando;
    private string _modoPropuesto = ModosDeNivel.Simple;
    private string? _escalaPropuesta;
    private bool _verPlantillas, _ocupado, _calculandoVista;
    private PlantillasDeEscalas? _plantillas;
    private string? _filtroDePais;
    private (string Rotulo, VistaPreviaDeEscala Vista)? _vistaPrevia;
    private ValidacionDeNivel? _validacion;
    private string? _validacionClave;

    private bool EnCalificaciones => _modoPropuesto == ModosDeNivel.Calificaciones;

    /// <summary>Lo que se propone, como firma: el nivel, el modo y (sólo en calificaciones) la escala. La validación vale únicamente para esta firma.</summary>
    private string ClaveDeLoPropuesto(string nivel) => $"{nivel}|{_modoPropuesto}|{(EnCalificaciones ? _escalaPropuesta : string.Empty)}";

    private bool HayCambio(NivelConfigurado nivel) =>
        _modoPropuesto != nivel.Modo || (EnCalificaciones && _escalaPropuesta != nivel.Escala?.EscalaId);

    // ------------------------------------------------------------------------------------------ abrir y cerrar

    private async Task AlternarEdicionAsync(NivelConfigurado nivel)
    {
        if (_nivelEditando == nivel.NivelClave)
        {
            _nivelEditando = null;
            Pintar();
            return;
        }
        _nivelEditando = nivel.NivelClave;
        _modoPropuesto = nivel.Modo;
        _escalaPropuesta = nivel.Escala?.EscalaId;
        _verPlantillas = false;
        _vistaPrevia = null;
        _validacion = null;
        _validacionClave = null;
        Pintar();
        // Un nivel que ya tiene escala enseña de entrada cómo convierte.
        if (EnCalificaciones && _escalaPropuesta is { } escala) await VerEscalaAsync(escala);
    }

    // ----------------------------------------------------------------------------------------------- editor

    private View Editor(NivelConfigurado nivel)
    {
        var pila = new VerticalStackLayout { Spacing = 14 };
        pila.Add(Ds.Separador());

        // ---- modo
        pila.Add(EstudioUi.Eyebrow("MODO DEL NIVEL"));
        var modos = EstudioUi.Envolver();
        modos.Add(EstudioUi.Chip("Simple", !EnCalificaciones, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Modo", () => ElegirModoAsync(ModosDeNivel.Simple)), $"config-{nivel.NivelClave}-modo-simple", 56));
        modos.Add(EstudioUi.Chip("Calificaciones", EnCalificaciones, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Modo", () => ElegirModoAsync(ModosDeNivel.Calificaciones)), $"config-{nivel.NivelClave}-modo-calificaciones", 56));
        pila.Add(modos);
        pila.Add(Ds.Secundario(EnCalificaciones
            ? "Calificaciones: el estudiante ve su nota presentada con la escala que elijas, cuando el profesor la publica."
            : "Simple: el estudiante ve sólo si completó cada evaluación (○ ◐ ●), sin notas, letras ni números. Es lo más sencillo para los más pequeños.", 14));

        // ---- escala
        if (EnCalificaciones)
        {
            pila.Add(EstudioUi.Eyebrow("ESCALA DEL NIVEL"));
            var adoptadas = _config!.Escalas.Where(e => e.Activa).ToList();
            if (adoptadas.Count == 0) pila.Add(Ds.Secundario("Todavía no hay escalas adoptadas. Adopta una plantilla orientativa, revísala y úsala para este nivel.", 14));
            var fichas = EstudioUi.Envolver();
            foreach (var e in adoptadas)
            {
                var id = e.Id;
                fichas.Add(EstudioUi.Chip(e.Nombre, id == _escalaPropuesta, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Escala", () => ElegirEscalaAsync(id)), $"config-{nivel.NivelClave}-escala-{e.Codigo}", 56));
            }
            pila.Add(fichas);
            var plantillas = ExamenUi.Accion(_verPlantillas ? "Cerrar las plantillas" : "Adoptar una plantilla…", Ds.Rango.Secondary,
                CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Plantillas", AlternarPlantillasAsync), 280, $"config-{nivel.NivelClave}-plantillas", 56, margen: false);
            plantillas.Vista.HorizontalOptions = LayoutOptions.Start;
            pila.Add(plantillas.Vista);
            if (_verPlantillas) pila.Add(Plantillas());
        }

        // ---- vista previa
        if (EnCalificaciones && (_vistaPrevia is not null || _calculandoVista)) pila.Add(VistaPrevia());

        // ---- validar y aplicar
        pila.Add(Ds.Separador());
        var clave = ClaveDeLoPropuesto(nivel.NivelClave);
        var hayCambio = HayCambio(nivel);
        var falta = EnCalificaciones && _escalaPropuesta is null;
        if (_validacion is { } v && _validacionClave == clave) pila.Add(Validacion(v));

        var acciones = ExamenUi.Fila();
        var validar = ExamenUi.Accion(_ocupado ? "Un momento…" : "Validar el cambio", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Validar", () => ValidarAsync(nivel)), null, $"config-{nivel.NivelClave}-validar");
        Ds.Habilitar(validar.Boton, hayCambio && !falta && !_ocupado);
        acciones.Add(validar.Vista);
        var aplicar = ExamenUi.Accion("Aplicar", Ds.Rango.Primary, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Aplicar", () => AplicarAsync(nivel)), 190, $"config-{nivel.NivelClave}-aplicar");
        Ds.Habilitar(aplicar.Boton, _validacion is { Permitido: true } && _validacionClave == clave && !_ocupado);
        acciones.Add(aplicar.Vista);
        pila.Add(acciones);
        pila.Add(Ds.Secundario(!hayCambio ? "Sin cambios: así está configurado ahora."
            : falta ? "Elige una escala para poder validar el cambio."
            : _validacion is null || _validacionClave != clave ? "Primero valida el cambio: verás si se puede y qué conviene saber. Después podrás aplicarlo."
            : _validacion.Permitido ? "Se puede aplicar. El cambio no convierte ni borra nada solo: las calificaciones ya registradas se quedan como están."
            : "Ahora no se puede aplicar. Lee el motivo, resuélvelo y vuelve a validar.", 13));
        return pila;
    }

    // ------------------------------------------------------------------------------------------- lo que se toca

    private Task ElegirModoAsync(string modo)
    {
        _modoPropuesto = modo;
        _validacion = null;
        _validacionClave = null;
        Pintar();
        if (modo == ModosDeNivel.Calificaciones && _escalaPropuesta is { } escala && _vistaPrevia is null) return VerEscalaAsync(escala);
        return Task.CompletedTask;
    }

    private async Task ElegirEscalaAsync(string escalaId)
    {
        _escalaPropuesta = escalaId;
        _validacion = null;
        _validacionClave = null;
        Pintar();
        await VerEscalaAsync(escalaId);
    }

    // ---------------------------------------------------------------------------------------- vista previa

    /// <summary>La conversión de una escala ADOPTADA con su última versión (la que el nodo usa al elegirla para un nivel). La calcula el nodo; aquí sólo se muestra.</summary>
    private async Task VerEscalaAsync(string escalaId)
    {
        _calculandoVista = true;
        _vistaPrevia = null;
        Pintar();
        try
        {
            var lector = LectorDeEscalas.Actual;
            var escala = await lector.EscalaAsync(CalificacionesUi.Actor, escalaId);
            if (!_visible) return;
            if (escala is null || LectorDeEscalas.UltimaVersion(escala) is not { } version)
            {
                _aviso.Mostrar("No se pudo preparar la vista previa", lector.UltimoMotivo ?? "No se pudo leer la escala.", Tono.Ambar);
                return;
            }
            if (_escalaPropuesta != escalaId) return;       // la persona ya eligió otra mientras tanto
            var api = Api;
            var vista = await api.VistaPreviaAsync(CalificacionesUi.Actor, null, version.Id, TextoDeCalificaciones.MuestrasDeVistaPrevia);
            if (!_visible || _escalaPropuesta != escalaId) return;
            if (vista is null) _aviso.Mostrar("No se pudo preparar la vista previa", CalificacionesUi.Error(api), Tono.Ambar);
            else _vistaPrevia = ($"{escala.Nombre} · versión {version.Numero}", vista);
        }
        finally
        {
            _calculandoVista = false;
            if (_visible) Pintar();
        }
    }

    /// <summary>La conversión de una PLANTILLA antes de adoptarla: lo que haría esa escala con los valores de muestra. No guarda nada.</summary>
    private async Task VerPlantillaAsync(PlantillaDeEscala plantilla)
    {
        _calculandoVista = true;
        _vistaPrevia = null;
        Pintar();
        try
        {
            var api = Api;
            var vista = await api.VistaPreviaAsync(CalificacionesUi.Actor, plantilla.Codigo, null, TextoDeCalificaciones.MuestrasDeVistaPrevia);
            if (!_visible) return;
            if (vista is null) _aviso.Mostrar("No se pudo preparar la vista previa", CalificacionesUi.Error(api), Tono.Ambar);
            else _vistaPrevia = ($"{plantilla.Nombre} · plantilla orientativa, aún sin adoptar", vista);
        }
        finally
        {
            _calculandoVista = false;
            if (_visible) Pintar();
        }
    }

    private View VistaPrevia()
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(new Label { Text = "Vista previa de la conversión", FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta });
        if (_vistaPrevia is not { } previa)
        {
            pila.Add(Ds.Secundario("Calculando cómo convierte la escala…", 14));
            return ExamenUi.Zona(pila, ExamenUi.FondoNeutro);
        }
        pila.Add(Ds.Secundario($"{previa.Rotulo}. Es sólo una muestra: no guarda nada.", 14));
        var encabezado = FilaDeTabla();
        string[] titulos = ["RESULTADO INTERNO", "NOTA PRESENTADA", "NIVEL DE DESEMPEÑO", "CRITERIO DE APROBACIÓN"];
        for (var i = 0; i < titulos.Length; i++) encabezado.Add(EstudioUi.Eyebrow(titulos[i]), i, 0);
        pila.Add(encabezado);
        foreach (var c in previa.Vista.Conversiones)
        {
            var fila = FilaDeTabla();
            fila.Add(new Label { Text = GradebookTexto.Puntaje(c.Interno), FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta }, 0, 0);
            fila.Add(new Label { Text = TextoDeCalificaciones.Presentada(c.Presentada), FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta }, 1, 0);
            fila.Add(new Label { Text = c.Desempeno.Nivel is { Length: > 0 } nivel ? nivel : "—", FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.TintaMedia }, 2, 0);
            fila.Add(new Label { Text = GradebookTexto.Aprobacion(c.Aprobacion), FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap }, 3, 0);
            pila.Add(fila);
        }
        return ExamenUi.Zona(pila, ExamenUi.FondoNeutro);
    }

    private static Grid FilaDeTabla() => new()
    {
        ColumnDefinitions = [new ColumnDefinition(new GridLength(160)), new ColumnDefinition(new GridLength(170)), new ColumnDefinition(GridLength.Star), new ColumnDefinition(new GridLength(1.2, GridUnitType.Star))],
        ColumnSpacing = 14, Padding = new Thickness(0, 2),
    };

    // ----------------------------------------------------------------------------------------- plantillas

    private async Task AlternarPlantillasAsync()
    {
        _verPlantillas = !_verPlantillas;
        Pintar();
        if (!_verPlantillas || _plantillas is not null) return;
        var api = Api;
        var plantillas = await api.PlantillasAsync(CalificacionesUi.Actor);
        if (!_visible) return;
        if (plantillas is null)
        {
            _verPlantillas = false;
            _aviso.Mostrar("No se pudieron leer las plantillas", CalificacionesUi.Error(api), Tono.Ambar);
        }
        else _plantillas = plantillas;
        Pintar();
    }

    /// <summary>
    /// El catálogo de plantillas, filtrable por país. La advertencia (orientativa: la institución debe revisarla y adoptarla) se muestra SIEMPRE: arriba del catálogo y en cada plantilla. Una plantilla
    /// no presenta nada mientras no se adopta.
    /// </summary>
    private View Plantillas()
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(new Label { Text = "Plantillas de escala", FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta });
        if (_plantillas is not { } catalogo)
        {
            pila.Add(Ds.Secundario("Leyendo las plantillas…", 14));
            return ExamenUi.Zona(pila, ExamenUi.FondoNeutro);
        }
        pila.Add(ExamenUi.Aviso("Plantillas orientativas", catalogo.Advertencia, Tono.Ambar));

        var paises = FiltroDePlantillas.Paises(catalogo.Plantillas);
        if (paises.Count > 0 || FiltroDePlantillas.HayGenericas(catalogo.Plantillas))
        {
            pila.Add(EstudioUi.Eyebrow("PAÍS"));
            var fichas = EstudioUi.Envolver();
            fichas.Add(EstudioUi.Chip("Todos", _filtroDePais is null, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Pais", () => FiltrarPaisAsync(null)), "config-pais-todos"));
            if (FiltroDePlantillas.HayGenericas(catalogo.Plantillas))
                fichas.Add(EstudioUi.Chip("Genéricas", _filtroDePais == FiltroDePlantillas.Genericas, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Pais", () => FiltrarPaisAsync(FiltroDePlantillas.Genericas)), "config-pais-genericas"));
            foreach (var codigo in paises)
            {
                var pais = codigo;
                fichas.Add(EstudioUi.Chip(FiltroDePlantillas.NombreDePais(pais), _filtroDePais == pais, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Pais", () => FiltrarPaisAsync(pais)), $"config-pais-{pais}"));
            }
            pila.Add(fichas);
        }

        var visibles = FiltroDePlantillas.Filtrar(catalogo.Plantillas, _filtroDePais);
        if (visibles.Count == 0) pila.Add(Ds.Secundario("No hay plantillas con este filtro.", 14));
        foreach (var p in visibles) pila.Add(FilaDePlantilla(p));
        return ExamenUi.Zona(pila, ExamenUi.FondoNeutro);
    }

    private Task FiltrarPaisAsync(string? pais)
    {
        _filtroDePais = pais;
        Pintar();
        return Task.CompletedTask;
    }

    private View FilaDePlantilla(PlantillaDeEscala p)
    {
        var textos = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = p.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        textos.Add(Ds.Secundario($"{FiltroDePlantillas.Origen(p)} · {TramosDeEscala.TipoLegible(p.Tipo)}", 13));
        if (!string.IsNullOrWhiteSpace(p.Referencia)) textos.Add(Ds.Secundario(p.Referencia!, 13));
        // La advertencia va siempre con la plantilla: orientativa, la institución debe revisarla y adoptarla.
        textos.Add(new Label { Text = p.Advertencia, FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = ExamenUi.TintaAmbar, LineBreakMode = LineBreakMode.WordWrap });

        var botones = new VerticalStackLayout { Spacing = 8, VerticalOptions = LayoutOptions.Center };
        botones.Add(ExamenUi.Accion("Ver conversión", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "VerPlantilla", () => VerPlantillaAsync(p)), 190, $"config-plantilla-ver-{p.Codigo}", 48, margen: false).Vista);
        var adoptar = ExamenUi.Accion(_ocupado ? "Un momento…" : "Adoptar", Ds.Rango.Primary, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Adoptar", () => AdoptarAsync(p)), 190, $"config-plantilla-adoptar-{p.Codigo}", 48, margen: false);
        Ds.Habilitar(adoptar.Boton, !_ocupado);
        botones.Add(adoptar.Vista);

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        fila.Add(textos, 0, 0);
        fila.Add(botones, 1, 0);
        return CalificacionesUi.Fila(fila, new Thickness(16, 10));
    }

    /// <summary>
    /// Adoptar una plantilla: la institución la hace SUYA (nace la escala y su versión 1). No presenta nada hasta que se elija para un nivel y se aplique. Adoptar no manda una solicitud que el nodo
    /// reconozca como repetida: si no hubo conexión, no se sabe si llegó, y se dice así en lugar de prometer que reintentar es seguro.
    /// </summary>
    private async Task AdoptarAsync(PlantillaDeEscala plantilla)
    {
        if (_ocupado) return;
        _ocupado = true;
        Pintar();
        try
        {
            var api = Api;
            var escala = await api.AdoptarPlantillaAsync(CalificacionesUi.Actor, plantilla.Codigo);
            if (!_visible) return;
            if (escala is null)
            {
                _aviso.Mostrar("No se adoptó la plantilla",
                    CalificacionesUi.SinConexion(api)
                        ? "No se pudo conectar con el aula y no se sabe si la plantilla llegó a adoptarse. Actualiza la pantalla y mira las escalas adoptadas antes de volver a intentarlo."
                        : CalificacionesUi.Error(api), Tono.Ambar);
                return;
            }
            _aviso.Mostrar($"Plantilla adoptada: {escala.Nombre}", "Desde ahora es una escala de la institución. Revisa la vista previa y, si te sirve, valida y aplica el cambio al nivel.", Tono.Exito);
            _escalaPropuesta = escala.Id;
            _modoPropuesto = ModosDeNivel.Calificaciones;
            _verPlantillas = false;
            _validacion = null;
            _validacionClave = null;
            _ocupado = false;
            await CargarAsync();
            await VerEscalaAsync(escala.Id);
        }
        finally
        {
            _ocupado = false;
            if (_visible) Pintar();
        }
    }

    // -------------------------------------------------------------------------------------- validar y aplicar

    private View Validacion(ValidacionDeNivel v)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        var fila = ExamenUi.Fila();
        fila.Add(CalificacionesUi.PildoraEnFila(v.Permitido ? "Se puede aplicar" : "No se puede aplicar todavía", v.Permitido ? Matiz.Exito : Matiz.Ambar, 14));
        fila.Add(CalificacionesUi.PildoraEnFila($"{GradebookTexto.Modo(v.De)} → {GradebookTexto.Modo(v.A)}", Matiz.Neutro, 14));
        pila.Add(fila);
        if (v.EnCurso > 0) pila.Add(Ds.Secundario(v.EnCurso == 1 ? "Hay 1 evaluación en curso en este nivel." : $"Hay {v.EnCurso} evaluaciones en curso en este nivel.", 14));
        foreach (var b in v.Bloqueos) pila.Add(ExamenUi.Aviso("Lo que lo impide", b, Tono.Ambar));
        foreach (var a in v.Advertencias) pila.Add(ExamenUi.Aviso("Conviene saber", a, Tono.Info));
        if (v.Bloqueos.Count == 0 && v.Advertencias.Count == 0) pila.Add(Ds.Secundario("Nada que advertir.", 14));
        return pila;
    }

    private async Task ValidarAsync(NivelConfigurado nivel)
    {
        if (_ocupado) return;
        _ocupado = true;
        var clave = ClaveDeLoPropuesto(nivel.NivelClave);
        Pintar();
        try
        {
            var api = Api;
            var v = await api.ValidarNivelAsync(CalificacionesUi.Actor, nivel.NivelClave, _modoPropuesto, EnCalificaciones ? _escalaPropuesta : null);
            if (!_visible) return;
            if (v is null)
            {
                _aviso.Mostrar("No se pudo validar el cambio", TextoDeCalificaciones.ErrorDeNivel(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
                return;
            }
            _validacion = v;
            _validacionClave = clave;
        }
        finally
        {
            _ocupado = false;
            if (_visible) Pintar();
        }
    }

    /// <summary>
    /// Aplica el cambio. Es idempotente en el nodo (aplicar lo que ya está así no hace nada), así que reintentar tras perder la señal es seguro. Si hay evaluaciones en curso el nodo lo rechaza y se
    /// dice con su cuenta; la validación se vuelve a pedir.
    /// </summary>
    private async Task AplicarAsync(NivelConfigurado nivel)
    {
        if (_ocupado || _validacion is not { Permitido: true } || _validacionClave != ClaveDeLoPropuesto(nivel.NivelClave)) return;
        _ocupado = true;
        Pintar();
        try
        {
            var api = Api;
            var r = await api.ConfigurarNivelAsync(CalificacionesUi.Actor, nivel.NivelClave, _modoPropuesto, EnCalificaciones ? _escalaPropuesta : null);
            if (!_visible) return;
            if (r is null)
            {
                _aviso.Mostrar("No se pudo aplicar el cambio", TextoDeCalificaciones.ErrorDeNivel(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
                if (api.UltimoError?.Codigo == "evaluaciones_en_curso") _validacion = null;     // lo que se validó dejó de ser cierto: se valida de nuevo
                return;
            }
            var detalle = r.Advertencias.Count == 0 ? null : string.Join(" ", r.Advertencias);
            _aviso.Mostrar(r.Cambiado ? $"Nivel actualizado: {SelectorDeGrupo.RotuloDeNivel(r.Nivel.NivelClave)} en modo {GradebookTexto.Modo(r.Nivel.Modo).ToLowerInvariant()}" : "Sin cambios: el nivel ya estaba así", detalle, Tono.Exito);
            _nivelEditando = null;
            _validacion = null;
            _validacionClave = null;
            _vistaPrevia = null;
            _ocupado = false;
            await CargarAsync();
        }
        finally
        {
            _ocupado = false;
            if (_visible) Pintar();
        }
    }
}
