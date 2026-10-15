using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

// Un grupo SIN nivel educativo está siempre en modo simple: el sistema de calificación se elige por nivel (preescolar, primaria, secundaria…), así que aunque la administración configure uno,
// ese grupo no lo recibe hasta que tenga nivel. Los grupos creados sin nivel (la pantalla de Grupos lo deja opcional) caían en un callejón sin salida: ninguna pantalla permitía ponérselo
// después. Aquí se dice y se arregla en el mismo sitio, con fichas que se tocan: lo hace quien administra el grupo (su profesor o la administración); el nodo decide si puede.
public partial class CalificacionesPage
{
    private string? _nivelPorAsignar;
    private bool _asignandoNivel;

    /// <summary>La tarjeta «Este grupo no tiene nivel». Nada si el grupo ya tiene uno.</summary>
    private View? AsignarNivel(LibroDelGrupo libro)
    {
        if (!string.IsNullOrWhiteSpace(libro.Grupo.NivelClave)) return null;
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(new Label { Text = "Este grupo no tiene nivel educativo", FontFamily = Ds.FuenteMedia, FontSize = 22, TextColor = Ds.Tinta, AutomationId = "calificaciones-sin-nivel" });
        pila.Add(Ds.Secundario("El sistema de calificación (el de Colombia, México, Estados Unidos, Chile…) se elige por nivel. Mientras el grupo no tenga uno, sus resultados quedan en modo simple, sin notas, "
            + "aunque la administración configure un sistema. Elige su nivel.", 15));
        pila.Add(EstudioUi.Eyebrow("NIVEL DEL GRUPO"));
        var fichas = EstudioUi.Envolver();
        foreach (var nivel in NivelesEducativos.Todos)
        {
            var clave = nivel;
            fichas.Add(EstudioUi.Chip(SelectorDeGrupo.RotuloDeNivel(clave), _nivelPorAsignar == clave,
                CalificacionesUi.Seguro(nameof(CalificacionesPage), "NivelDelGrupo", () => ProponerNivelAsync(clave)), $"calificaciones-grupo-nivel-{clave}", 56));
        }
        pila.Add(fichas);
        var asignar = ExamenUi.Accion(_asignandoNivel ? "Un momento…" : _nivelPorAsignar is { } elegido ? $"Poner el nivel {SelectorDeGrupo.RotuloDeNivel(elegido).ToLowerInvariant()}" : "Elige un nivel",
            Ds.Rango.Primary, CalificacionesUi.Seguro(nameof(CalificacionesPage), "AsignarNivel", () => AsignarNivelAsync(libro.Grupo.Id)), 320, "calificaciones-grupo-asignar-nivel", 56, margen: false);
        Ds.Habilitar(asignar.Boton, _nivelPorAsignar is not null && !_asignandoNivel);
        asignar.Vista.HorizontalOptions = LayoutOptions.Start;
        pila.Add(asignar.Vista);
        pila.Add(Ds.Secundario("Cambiar el nivel no modifica ninguna evaluación ni calificación del grupo: sólo decide con qué sistema se presentan sus notas.", 13));
        return ExamenUi.Tarjeta(pila);
    }

    private Task ProponerNivelAsync(string nivel)
    {
        _nivelPorAsignar = nivel;
        Pintar();
        return Task.CompletedTask;
    }

    /// <summary>
    /// Pone el nivel al grupo y vuelve a leer: el grupo pasa a la ficha de su nivel nuevo (se sigue con él, no se queda en «Sin nivel») y su libro se arma con el sistema de ese nivel, si lo
    /// tiene. Sin permiso (un grupo ajeno) o sin conexión, el nodo no cambió nada y se dice.
    /// </summary>
    private async Task AsignarNivelAsync(string grupoId)
    {
        if (_asignandoNivel || _nivelPorAsignar is not { } nivel) return;
        _asignandoNivel = true;
        Pintar();
        try
        {
            var padron = Sesion.Padron;
            if (!await padron.AsignarNivelAsync(grupoId, nivel))
            {
                if (!_visible) return;
                var error = padron.UltimoError;
                _aviso.Mostrar("No se pudo poner el nivel",
                    GradebookTexto.SinConexion(error) ? "Sin conexión con el nodo del aula: nada cambió. Puedes volver a tocar el botón."
                    : error?.Codigo == "sin_permiso" ? "Sólo el profesor del grupo o la administración pueden cambiar su nivel."
                    : error?.Detalle ?? padron.UltimoMotivo ?? "El nodo no contestó.", Tono.Ambar);
                return;
            }
            if (!_visible) return;
            _aviso.Mostrar($"Nivel puesto: {SelectorDeGrupo.RotuloDeNivel(nivel)}", "El libro del grupo se presenta ahora con el sistema de ese nivel. Si el nivel aún no tiene sistema, la administración lo elige en «Sistema de calificación».", Tono.Exito);
            _nivelPorAsignar = null;
            (_nivelElegido, _grupoElegido) = (nivel, grupoId);
            _firma = _firmaDeSelector = string.Empty;
        }
        finally
        {
            _asignandoNivel = false;
            if (_visible && _libro is not null) Pintar();
        }
        await CargarAsync(forzar: true);
    }
}
