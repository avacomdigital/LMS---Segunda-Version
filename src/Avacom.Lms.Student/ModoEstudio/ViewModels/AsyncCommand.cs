using System.Windows.Input;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student.ModoEstudio.ViewModels;

/// <summary>
/// Un comando asíncrono para los botones de la pantalla: no se puede lanzar dos veces a la vez (un doble toque no descarga dos veces ni
/// abre dos lecciones), no bloquea la interfaz y ninguna excepción sale de aquí: se anota en el archivo de fallos y la pantalla sigue.
/// </summary>
public sealed class AsyncCommand<T> : ICommand
{
    private readonly Func<T?, Task> _ejecutar;
    private readonly Func<T?, bool>? _puede;
    private int _ocupado;

    public AsyncCommand(Func<T?, Task> ejecutar, Func<T?, bool>? puede = null)
    {
        _ejecutar = ejecutar;
        _puede = puede;
    }

    public event EventHandler? CanExecuteChanged;

    public bool IsRunning => Volatile.Read(ref _ocupado) == 1;

    public bool CanExecute(object? parameter) => !IsRunning && (_puede?.Invoke(Convertir(parameter)) ?? true);

    public async void Execute(object? parameter)
    {
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return;
        RaiseCanExecuteChanged();
        try { await _ejecutar(Convertir(parameter)); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "ModoEstudio.Comando", ex); }
        finally
        {
            Volatile.Write(ref _ocupado, 0);
            RaiseCanExecuteChanged();
        }
    }

    public void RaiseCanExecuteChanged() => MainThread.BeginInvokeOnMainThread(() => CanExecuteChanged?.Invoke(this, EventArgs.Empty));

    private static T? Convertir(object? parametro)
    {
        if (parametro is T t) return t;
        if (parametro is string texto && typeof(T).IsEnum && Enum.TryParse(typeof(T), texto, true, out var valor)) return (T)valor!;
        return default;
    }
}

/// <summary>El comando asíncrono sin parámetro.</summary>
public sealed class AsyncCommand : ICommand
{
    private readonly AsyncCommand<object> _interno;

    public AsyncCommand(Func<Task> ejecutar, Func<bool>? puede = null) =>
        _interno = new AsyncCommand<object>(_ => ejecutar(), puede is null ? null : _ => puede());

    public event EventHandler? CanExecuteChanged
    {
        add => _interno.CanExecuteChanged += value;
        remove => _interno.CanExecuteChanged -= value;
    }

    public bool CanExecute(object? parameter) => _interno.CanExecute(parameter);
    public void Execute(object? parameter) => _interno.Execute(parameter);
    public void RaiseCanExecuteChanged() => _interno.RaiseCanExecuteChanged();
}
