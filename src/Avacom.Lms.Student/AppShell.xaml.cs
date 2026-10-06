namespace Avacom.Lms.Student;
public partial class AppShell : Shell
{
    public AppShell()
    {
        InitializeComponent();
        Routing.RegisterRoute("menu", typeof(Pages.StudentMenuPage));
        Routing.RegisterRoute("course", typeof(Pages.CoursePage));
        Routing.RegisterRoute("quiz", typeof(Pages.QuizPage));
        Routing.RegisterRoute("asignaturas", typeof(Pages.AsignaturasPage));
        Routing.RegisterRoute("curso-biblioteca", typeof(Pages.CursoBibliotecaPage));
        // MOD-007 · Classroom Engine: reflejo de la clase en la tableta (S1 → S2)
        Routing.RegisterRoute("clase-unirse", typeof(Pages.ClaseUnirsePage));
        Routing.RegisterRoute("clase-siguiendo", typeof(Pages.ClaseSiguiendoPage));
        // MOD-008 · Modo Estudio: «Mis lecciones», la lección, su práctica (sólo en un aparato asignado al alumno)
        Routing.RegisterRoute("estudio", typeof(ModoEstudio.Views.StudyModePage));
        Routing.RegisterRoute("estudio-leccion", typeof(ModoEstudio.Views.StudyLessonPage));
        Routing.RegisterRoute("estudio-practica", typeof(ModoEstudio.Views.StudyPracticePage));
        // MOD-010 · Evaluation & Delivery Engine: mis evaluaciones, la antesala, el examen (sin salida mientras dura) y la entrega con su resultado
        Routing.RegisterRoute("evaluaciones", typeof(Examen.EvaluacionesPage));
        Routing.RegisterRoute("examen-antesala", typeof(Examen.ExamenAntesalaPage));
        Routing.RegisterRoute("examen", typeof(Examen.ExamenPage));
        Routing.RegisterRoute("examen-entrega", typeof(Examen.ExamenEntregaPage));
    }

    /// <summary>RF-23: con sesión de visitante, cada pantalla que se ve lleva la banda amarilla; al cerrar la visita se quita.</summary>
    protected override void OnNavigated(ShellNavigatedEventArgs args)
    {
        base.OnNavigated(args);
        BandaDeVisitante.Aplicar(CurrentPage);
    }
}
