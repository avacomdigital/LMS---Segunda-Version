namespace Avacom.Lms.Ops;
public partial class AppShell : Shell
{
    public AppShell()
    {
        InitializeComponent();
        Routing.RegisterRoute("dashboard", typeof(Pages.DashboardPage));
        // MOD-001 · acceso (requisitos 2026-10-05): primer arranque y hoja de acceso, alta y recuperación del profesor con el PIN maestro, la contraseña
        // propia tras la provisional y la seguridad del aula (sólo administración)
        Routing.RegisterRoute("primer-arranque", typeof(Pages.PrimerArranquePage));
        Routing.RegisterRoute("registro-docente", typeof(Pages.RegistroDocentePage));
        Routing.RegisterRoute("restablecer-contrasena", typeof(Pages.RestablecerContrasenaPage));
        Routing.RegisterRoute("elegir-contrasena", typeof(Pages.ElegirContrasenaPage));
        Routing.RegisterRoute("seguridad-aula", typeof(Pages.SeguridadAulaPage));
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
        Routing.RegisterRoute("examen-aplicar", typeof(Pages.ExamenAplicarPage));
        Routing.RegisterRoute("examen-panel", typeof(Pages.ExamenPanelPage));
        Routing.RegisterRoute("examen-expediente", typeof(Pages.ExamenExpedientePage));
        Routing.RegisterRoute("examen-resultados", typeof(Pages.ExamenResultadosPage));
    }
}
