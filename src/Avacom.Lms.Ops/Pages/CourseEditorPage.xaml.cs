using Avacom.Lms.Ui.Controls;
namespace Avacom.Lms.Ops.Pages;
public partial class CourseEditorPage : ContentPage
{
    public IReadOnlyList<string> Grades { get; } = ["7°", "8°", "9°", "10°", "11°"];
    public CourseEditorPage() { InitializeComponent(); BindingContext = this; }
    private async void OnBack(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");
    private async void OnSave(object? sender, EventArgs e) { await this.AlertaAsync("Curso guardado", $"{CourseName.Text} está listo para asignarse a estudiantes.", "Entendido"); await Shell.Current.GoToAsync(".."); }
    private void OnAddUnit(object? sender, EventArgs e) => UnitsContainer.Add(new Border { Padding = 22, Content = new Label { Text = $"Unidad {UnitsContainer.Count + 1} · Nueva unidad", FontFamily = "LexendSemiBold", FontSize = 18 } });
}
