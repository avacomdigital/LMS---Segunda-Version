using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Avacom.Lms.Student.ModoEstudio.Models;

/// <summary>
/// La base mínima de los modelos y ViewModels del modo de estudio (INotifyPropertyChanged). Sin librería externa: el proyecto no
/// depende de CommunityToolkit y la pantalla sólo necesita esto.
/// </summary>
public abstract class ObservableObject : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;

    /// <summary>
    /// Cambia el campo y avisa de la propiedad y, si se dan, de las derivadas (<c>tambien: [nameof(Otra)]</c>). Devuelve verdadero si el
    /// valor era distinto.
    /// </summary>
    protected bool SetProperty<T>(ref T campo, T valor, string[]? tambien = null, [CallerMemberName] string? nombre = null)
    {
        if (EqualityComparer<T>.Default.Equals(campo, valor)) return false;
        campo = valor;
        OnPropertyChanged(nombre);
        if (tambien is not null)
            foreach (var derivada in tambien) OnPropertyChanged(derivada);
        return true;
    }

    protected void OnPropertyChanged([CallerMemberName] string? nombre = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nombre));

    /// <summary>Avisa de varias propiedades derivadas de una vez.</summary>
 