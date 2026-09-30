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
    }
}
