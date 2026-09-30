namespace Avacom.Lms.Ops;
public partial class AppShell : Shell
{
    public AppShell()
    {
        InitializeComponent();
        Routing.RegisterRoute("dashboard", typeof(Pages.DashboardPage));
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
        // MOD-008 · Modo Estudio: asignar lecciones a los alumnos y ver quién las completó
        Routing.RegisterRoute("estudio", typeof(Pages.EstudioPage));
    }
}
