using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Navegacion;

namespace Avacom.Lms.Ops;
public partial class AppShell : Shell
{
    private readonly GuardiaDeNavegacion _guardia = new();

    public AppShell()
    {
        InitializeComponent();
        Navigating += AlNavegar;
        Routing.RegisterRoute("dashboard", typeof(Pages.DashboardPage));
        // MOD-001 · acceso (requisitos 2026-10-05): primer arranque y hoja de acceso, alta y recuperación del profesor con el PIN maestro, la contraseña
        // propia tras la provisional y la seguridad del aula (sólo administración)
        Routing.RegisterRoute("primer-arranque", typeof(Pages.PrimerArranquePage));
        Routing.RegisterRoute("registro-docente", typeof(Pages.RegistroDocentePage));
        Routing.RegisterRoute("restablecer-contrasena", typeof(Pages.RestablecerContrasenaPage));
        Routing.RegisterRoute("elegir-contrasena", typeof(Pages.ElegirContrasenaPage));
        Routing.RegisterRoute("seguridad-aula", typeof(Pages.SeguridadAulaPage));
        // MOD-018 · Licensing: el estado de la licencia del nodo, su activación y renovación sin internet en tres pasos, la copia de custodia y la liberación (administración y técnico)
        Routing.RegisterRoute("licencia", typeof(Pages.LicenciaPage));
        // MOD-017 · Update Manager: los paquetes .avupd de las memorias USB, traerlos al aula, programarlos, aplicarlos y volver a la versión anterior sin teclado (administración y técnico)
        Routing.RegisterRoute("actualizaciones", typeof(Pages.ActualizacionesPage));
        Routing.RegisterRoute("course-editor", typeof(Pages.CourseEditorPage));
        Routing.RegisterRoute("activity-monitor", typeof(Pages.ActivityMonitorPage));
        Routing.RegisterRoute("asignaturas", typeof(Pages.AsignaturasPage));
        Routing.RegisterRoute("curso-biblioteca", typeof(Pages.CursoBibliotecaPage));
        // MOD-007 · Classroom Engine: el journey «Clase de hoy» (P1 → P4)
        Routing.RegisterRoute("clase-hoy", typeof(Pages.ClaseHoyPage));
        Routing.RegisterRoute("clase-curso", typeof(Pages.ClaseCursoPage));
        Routing.RegisterRoute("clase-sesion", typeof(Pages.ClaseSesionPage));
        Routing.RegisterRoute("clase-cierre", typeof(Pages.ClaseCierrePage));
        // MOD-009 · Device Manager: el inventario de tabletas del aula, con bloqueo por tableta
        Routing.RegisterRoute("dispositivos", typeof(Pages.DispositivosPage));
        Routing.RegisterRoute("grupos", typeof(Pages.GruposPage));
        // MOD-008 · Modo Estudio: asignar lecciones a los alumnos y ver quién las completó
        Routing.RegisterRoute("estudio", typeof(Pages.EstudioPage));
        // MOD-019 · Audit: la bitácora (Administrador) y el estado del equipo con sus errores (Técnico)
        Routing.RegisterRoute("logs-bitacora", typeof(Pages.BitacoraPage));
        // MOD-010 · Evaluation & Delivery Engine: aplicar un examen a la clase, vigilarlo sin vigilar, ver el expediente de un intento y los resultados
        Routing.RegisterRoute("evaluaciones", typeof(Pages.EvaluacionesPage));
        Routing.RegisterRoute("examen-aplicar", typeof(Pages.ExamenAplicarPage));
        Routing.RegisterRoute("examen-panel", typeof(Pages.ExamenPanelPage));
        Routing.RegisterRoute("examen-expediente", typeof(Pages.ExamenExpedientePage));
        Routing.RegisterRoute("examen-resultados", typeof(Pages.ExamenResultadosPage));
        // MOD-011 · Gradebook: el libro de calificaciones del grupo, la bandeja de revisión docente, la revisión de un intento, el detalle de una calificación con su ajuste y
        // la configuración académica (sólo administración)
        Routing.RegisterRoute("calificaciones", typeof(Pages.CalificacionesPage));
        Routing.RegisterRoute("calificaciones-revision", typeof(Pages.RevisionBandejaPage));
        Routing.RegisterRoute("revision-docente", typeof(Pages.RevisionDocentePage));
        Routing.RegisterRoute("calificacion-detalle", typeof(Pages.CalificacionDetallePage));
        Routing.RegisterRoute("calificacion-estudiante", typeof(Pages.CalificacionEstudiantePage));
        Routing.RegisterRoute("calificaciones-config", typeof(Pages.CalificacionesConfigPage));
        // MOD-021 · Search: la búsqueda del menú principal (cursos, lecciones, recursos, evaluaciones, estudios y clases) y sus resultados, que abren la pantalla del módulo dueño
        Routing.RegisterRoute("buscar", typeof(Pages.BuscarPage));
        // MOD-013 · Reporting: el inicio de Reportes, elegir una clase, un grupo o un estudiante, los cuatro reportes (clase, grupo, estudiante, uso de equipos) y el estado y los ajustes
        Routing.RegisterRoute(Reportes.RutasDeReportes.Inicio, typeof(Pages.ReportesPage));
        Routing.RegisterRoute(Reportes.RutasDeReportes.Elegir, typeof(Pages.ReportesElegirPage));
        Routing.RegisterRoute(Reportes.RutasDeReportes.Clase, typeof(Pages.ReporteClasePage));
        Routing.RegisterRoute(Reportes.RutasDeReportes.Grupo, typeof(Pages.ReporteGrupoPage));
        Routing.RegisterRoute(Reportes.RutasDeReportes.Alumno, typeof(Pages.ReporteAlumnoPage));
        Routing.RegisterRoute(Reportes.RutasDeReportes.Uso, typeof(Pages.ReporteUsoPage));
        Routing.RegisterRoute(Reportes.RutasDeReportes.Estado, typeof(Pages.ReportesEstadoPage));
        Routing.RegisterRoute(Reportes.RutasDeReportes.Boletin, typeof(Pages.ReporteBoletinPage));
        Routing.RegisterRoute(Reportes.RutasDeReportes.Boletines, typeof(Pages.ReporteBoletinesPage));
    }

    /// <summary>
    /// Un doble toque (o el reintento de una prueba de UI Automation) repite una petición de navegación. Shell resuelve cada «..» contra el estado del momento en que le toca: el segundo
    /// «Menú principal» sacaba también el menú y dejaba a OPS en el acceso, con el proceso vivo y la sesión abierta (sin ningún 401). La regla está en <see cref="GuardiaDeNavegacion"/>;
    /// aquí sólo se le pregunta y se cancela lo que ella ignora. Cubre de una vez todos los botones «Menú principal» y «Volver», que usan <c>GoToAsync("..")</c> pelado.
    /// </summary>
    private void AlNavegar(object? sender, ShellNavigatingEventArgs e)
    {
        if (!e.CanCancel) return;
        var destino = e.Target?.Location?.OriginalString;
        var veredicto = _guardia.Evaluar(destino, CurrentPage is Pages.DashboardPage);
        if (veredicto == GuardiaDeNavegacion.Veredicto.Pasa) return;
        e.Cancel();
        RegistroLocal.Info(Canal.Aplicacion, "navegacion.ignorada", veredicto == GuardiaDeNavegacion.Veredicto.YaEstaEnElMenu
            ? "Un «volver» pedido con el menú principal ya a la vista se ignoró (habría llevado al acceso)."
            : "Una petición de navegación repetida dentro del doble toque se ignoró.", new { destino, motivo = veredicto.ToString() });
    }
}
