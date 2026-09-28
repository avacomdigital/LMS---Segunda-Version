using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// P4 · Cierre (PAN-008). El resumen consolidado de la sesión en tarjetas y un solo Primary:
/// volver a «Clase de hoy». Una clase cerrada no se reabre (sección H del Maestro).
/// </summary>
[QueryProperty(nameof(SesionId), "sesion")]
public partial class ClaseCierrePage : ContentPage
{
    public string SesionId { get; set; } = string.Empty;

    public ClaseCierrePage() => InitializeComponent();

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await CargarAsync();
    }

    private async Task CargarAsync()
    {
        AvisoHost.Clear();
        ResumenHost.Children.Clear();
        AccionesHost.Clear();
        var aula = Sesion.Aula;
        var sesion = string.IsNullOrWhiteSpace(SesionId) ? null : await aula.SesionAsync(SesionId);
        if (sesion is null)
        {
            AvisoHost.Add(Ds.Alerta_("No se pudo leer el resumen", aula.UltimoMotivo, Ds.PeligroSuave, Color.FromArgb("#8A1C1F")));
        }
        else
        {
            TituloLabel.Text = sesion.LeccionRotulo ?? sesion.CursoRotulo ?? "Clase libre";
            SubtituloLabel.Text = string.Join(" · ", new[] { sesion.CursoRotulo, sesion.ProfesorRotulo, $"código {sesion.CodigoUnion}" }.Where(x => !string.IsNullOrWhiteSpace(x)));
            var r = sesion.Resumen;
            if (r is null)
            {
                AvisoHost.Add(Ds.Alerta_("La clase aún no tiene resumen", $"Estado: {sesion.Estado}.", Ds.AlertaSuave, Ds.Tinta));
            }
            else
            {
                Tarjeta("Participantes", r.Participantes.ToString(), $"máximo {r.ConectadosMaximo} a la vez", Ds.CatClaseEnVivo);
                Tarjeta("Proyecciones", r.Selectores.ToString(), "cambios de selector", Ds.Info);
                Tarjeta("Actividades", r.Actividades.ToString(), r.Distribuciones == r.Actividades ? "lanzadas al grupo" : $"{r.Distribuciones} distribuciones en total", Ds.CatQuiz);
                Tarjeta("Avisos", r.Avisos.ToString(), "enviados al grupo", Ds.CatLectura);
                Tarjeta("Duración", r.DuracionTexto, r.OrigenCierre == "profesor" ? "cerrada por el profesor" : $"cierre: {r.OrigenCierre}", Ds.TintaSuave);
                Tarjeta("Pendientes", r.Pendientes.ToString(), r.Pendientes == 0 ? "ningún intento abierto" : "intentos abiertos al cierre", r.Pendientes == 0 ? Ds.Exito : Ds.Alerta);
            }
        }
        AccionesHost.Add(Ds.Boton("Volver a Clase de hoy", Ds.Rango.Primary, async (_, _) => await Shell.Current.GoToAsync("../../.."), 64, 320));
        AccionesHost.Add(Ds.Boton("Menú principal", Ds.Rango.Quiet, async (_, _) => await Shell.Current.GoToAsync("../../../.."), 64, 320));
    }

    private void Tarjeta(string titulo, string valor, string detalle, Color color)
    {
        var pila = new VerticalStackLayout { Spacing = 4, WidthRequest = 250 };
        pila.Add(Ds.Pildora(titulo, color));
        pila.Add(new Label { Text = valor, FontSize = 44, FontAttributes = FontAttributes.Bold, TextColor = Ds.Tinta });
        pila.Add(Ds.Secundario(detalle, 14));
        var tarjeta = Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18));
        tarjeta.Margin = new Thickness(8);
        ResumenHost.Children.Add(tarjeta);
    }
}
