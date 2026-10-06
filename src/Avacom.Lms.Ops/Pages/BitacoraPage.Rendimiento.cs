using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Pestaña «Rendimiento» (depuración): CPU, RAM, descarga, carga, latencia, pérdida, disco, conexiones activas, latencia de aplicación y errores de
/// este equipo y del nodo, para las pruebas de descarga de contenido y de red con 25 a 35 tabletas. El panel es el mismo de Student; aquí las
/// «conexiones activas» son los alumnos con canal abierto que el nodo cuenta. Mide desde que se abre la pantalla (y sigue midiendo en segundo plano).
/// </summary>
public partial class BitacoraPage
{
    private PanelDeRendimiento? _rendimiento;

    private Task<View> RendimientoAsync()
    {
        Sesion.IniciarMonitor();
        _rendimiento ??= new PanelDeRendimiento { App = "ops", CarpetaDeExportacion = CarpetaDescargas() };
        // Un panel por pestaña abierta: si ya tenía padre (de otra visita) se suelta antes de volver a mostrarlo.
        if (_rendimiento.Parent is Layout anterior) anterior.Remove(_rendimiento);
        return Task.FromResult<View>(_rendimiento);
    }
}
