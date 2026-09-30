using System.Windows.Input;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.ModoEstudio.Models;

/// <summary>
/// Un nombre de la pantalla «¿Quién eres?». Se elige con un toque y se confirma con otro: elegir por error el nombre de un compañero significaría ver
/// sus lecciones y que el profesor le anote a él lo que hagas.
/// </summary>
public sealed class StudyStudentItem : ObservableObject
{
    public StudyStudentItem(StudyStudent student, bool isOwner, Action<StudyStudentItem> onSelect)
    {
        Student = student;
        IsOwner = isOwner;
        SelectCommand = new Command(() => onSelect(this));
    }

    public StudyStudent Student { get; }
    public string Id => Student.Id;
    public string Name => Student.Name;
    public string Initials => Identidad.InicialesDe(Name);

    /// <summary>La tableta está asignada a esta persona: se le ofrece primero, pero nadie está obligado a serlo.</summary>
    public bool IsOwner { get; }

    public string AutomationName => $"estudio-alumno-{Id}";
    public string Description => IsOwner ? $"{Name}. Esta tableta es de esta persona." : Name;

    private bool _seleccionado;
    public bool IsSelected
    {
        get => _seleccionado;
        set => SetProperty(ref _seleccionado, value, tambien: [nameof(DisplayName)]);
    }

    /// <summary>Con ✓ cuando está elegido: el estado nunca se lee sólo por el color.</summary>
    public string DisplayName => IsSelected ? $"✓  {Name}" : Name;

    public ICommand SelectCommand { get; }
}

/// <summary>Un grupo de la pantalla «¿Quién eres?» (sólo se ofrece cuando hay más de uno).</summary>
public sealed class StudyRosterGroupItem : ObservableObject
{
    public StudyRosterGroupItem(StudyRosterGroup group, Action<StudyRosterGroupItem> onSelect)
    {
        Group = group;
        SelectCommand = new Command(() => onSelect(this));
    }

    public StudyRosterGroup Group { get; }
    public string Id => Group.Id;
    public string Name => Group.Name;
    public string Label => $"{Group.Name} · {Group.Students.Count}";
    public string AutomationName => $"estudio-grupo-{(string.IsNullOrEmpty(Id) ? "sin-grupo" : Id)}";

    private bool _seleccionado;
    public bool IsSelected
    {
        get => _seleccionado;
        set => SetProperty(ref _seleccionado, value, tambien: [nameof(DisplayLabel)]);
    }

    public string DisplayLabel => IsSelected ? $"✓  {Label}" : Label;

    public ICommand SelectCommand { get; }
}
