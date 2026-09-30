using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

// Vista 1 · las asignaciones de la profesora, con sus totales. Un toque en una tarjeta abre «quién completó».
public partial class EstudioPage
{
    private string _filtroLista = "activa";   // activa · cerrada · todas

    private async Task MostrarListaAsync()
    {
        Entrar(Vista.Lista);
        var nueva = EstudioUi.Accion("Asignar una lección", Ds.Rango.Primary, async () => await MostrarNuevaAsync(), 250, "estudio-nueva");
        PonerCabecera("MODO DE ESTUDIO", "Lecciones asignadas para estudiar",
            "Asigna una lección a un grupo o a algunos alumnos y mira en vivo quién la completó. Los alumnos entran a «Modo de estudio» en su tableta, eligen su nombre (sin código) y estudian.",
            nueva.Vista, AccionActualizar().Vista, AccionMenu().Vista);
        Vaciar(true);
        ContenidoHost.Add(Cargando("Buscando tus asignaciones…"));
        await CargarListaAsync(_generacion, true);
    }

    private async Task CargarListaAsync(int generacion, bool forzar)
    {
        var api = Api;
        var lista = await api.AsignacionesDocenteAsync(Actor, null, _filtroLista == "todas" ? null : _filtroLista);
        if (generacion != _generacion || _vista != Vista.Lista) return;
        if (lista is null)
        {
            var error = api.UltimoError;
            var firmaError = $"{_filtroLista}|error|{error?.Estado}|{error?.Codigo}";
            if (!forzar && firmaError == _firma) return;
            _firma = firmaError;
            Repintar(() =>
            {
                Vaciar(false);
                ContenidoHost.Add(Filtros());
                ContenidoHost.Add(EstudioUi.Aviso(error?.Codigo == "no_instalado" ? "El nodo aún no está instalado" : "No se pudieron leer las asignaciones",
                    EstudioTexto.Error(error, api.UltimoMotivo), Ds.PeligroSuave, EstudioUi.TintaPeligro));
            });
            return;
        }

        var firma = _filtroLista + "|" + JsonSerializer.Serialize(lista.Asignaciones);
        if (!forzar && firma == _firma) return;
        _firma = firma;
        Repintar(() =>
        {
            Vaciar(false);
            ContenidoHost.Add(Filtros());
            if (lista.Asignaciones.Count == 0)
            {
                ContenidoHost.Add(ListaVacia());
                return;
            }
            foreach (var a in lista.Asignaciones.OrderBy(a => a.Cerrada).ThenByDescending(a => a.CreadaEn))
                ContenidoHost.Add(TarjetaDeAsignacion(a));
        });
    }

    private View Filtros()
    {
        var fila = EstudioUi.Envolver();
        void Uno(string rotulo, string valor)
        {
            fila.Add(EstudioUi.Chip(rotulo, _filtroLista == valor, async () =>
            {
                if (_filtroLista == valor) return;
                _filtroLista = valor;
                _firma = string.Empty;
                await RefrescarAsync(true);
            }, $"estudio-filtro-{valor}"));
        }
        Uno("Abiertas", "activa");
        Uno("Cerradas", "cerrada");
        Uno("Todas", "todas");
        return fila;
    }

    private View ListaVacia()
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(Ds.Titulo(_filtroLista == "cerrada" ? "No hay asignaciones cerradas" : "Todavía no has asignado ninguna lección", 22));
        pila.Add(Ds.Secundario(_filtroLista == "cerrada"
            ? "Cuando cierres una asignación, quedará aquí con lo que cada alumno alcanzó."
            : "Elige un grupo (o unos alumnos), una lección del curso y, si quieres, una fecha límite. Los alumnos la verán en «Modo de estudio»: eligen su nombre y no necesitan ningún código.", 16));
        if (_filtroLista != "cerrada")
        {
            var primera = EstudioUi.Accion("Asignar mi primera lección", Ds.Rango.Primary, async () => await MostrarNuevaAsync(), 300, "estudio-primera");
            primera.Vista.HorizontalOptions = LayoutOptions.Start;
            primera.Vista.Margin = new Thickness(0, 8, 0, 0);
            pila.Add(primera.Vista);
        }
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28), Colors.White);
    }

    private View TarjetaDeAsignacion(AsignacionDocente a)
    {
        var ahora = RelojNodo.AhoraMs;
        var sinTerminar = a.Pendientes + a.EnCurso;
        var vencida = !a.Cerrada && a.FechaLimite is { } limite && limite < ahora;
        var izquierda = new VerticalStackLayout { Spacing = 7 };

        var cabeza = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
        cabeza.Add(new Label { Text = a.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap }, 0, 0);
        cabeza.Add(Ds.Pildora(a.Cerrada ? "CERRADA" : "ABIERTA", a.Cerrada ? EstudioUi.PistaBarra : Ds.ExitoSuave, a.Cerrada ? Ds.TintaSuave : Color.FromArgb("#0B5D3B"), 12), 1, 0);
        izquierda.Add(cabeza);

        var meta = string.Join(" · ", new[] { a.Asignatura, a.Unidad, a.GrupoRotulo ?? (a.Alcance == "seleccion" ? "Alumnos elegidos" : null) }
            .Where(x => !string.IsNullOrWhiteSpace(x)));
        if (meta.Length > 0) izquierda.Add(Ds.Secundario(meta, 15));

        izquierda.Add(new Label
        {
            Text = EstudioTexto.Entrega(a.FechaLimite) + (vencida ? " · ya pasó" : string.Empty),
            FontFamily = Ds.FuenteRegular, FontSize = 15,
            TextColor = vencida && sinTerminar > 0 ? EstudioUi.TintaPeligro : Ds.TintaMedia,
        });

        var total = Math.Max(a.DestinatariosTotal, 0);
        var avance = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14, Margin = new Thickness(0, 6, 0, 0) };
        avance.Add(EstudioUi.Barra(total == 0 ? 0 : (double)a.Completaron / total), 0, 0);
        avance.Add(new Label
        {
            Text = total == 0 ? "Todavía no hay alumnos" : $"{a.Completaron} de {total} completaron",
            FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center,
        }, 1, 0);
        izquierda.Add(avance);

        var cuentas = EstudioUi.Envolver();
        cuentas.Margin = new Thickness(0, 6, 0, -8);
        void Cuenta(int n, string texto, Color fondo, Color tinta)
        {
            if (n <= 0) return;
            var pildora = Ds.Pildora(texto, fondo, tinta, 13);
            pildora.Margin = new Thickness(0, 0, 8, 8);
            cuentas.Add(pildora);
        }
        Cuenta(a.Completaron, EstudioTexto.Plural(a.Completaron, "completó", "completaron"), Ds.ExitoSuave, Color.FromArgb("#017A48"));
        Cuenta(a.EnCurso, $"{a.EnCurso} en curso", Color.FromArgb("#E5F5FB"), Color.FromArgb("#02739E"));
        Cuenta(a.Pendientes, EstudioTexto.Plural(a.Pendientes, "sin empezar", "sin empezar"), Color.FromArgb("#FFF7D6"), Color.FromArgb("#806600"));
        Cuenta(a.FueraDePlazo, $"{a.FueraDePlazo} fuera de plazo", Ds.PeligroSuave, EstudioUi.TintaPeligro);
        Cuenta(a.PendientesDecision, EstudioTexto.Plural(a.PendientesDecision, "envío por decidir", "envíos por decidir"), Ds.VioletaSuave, Color.FromArgb("#7A1560"));
        if (cuentas.Children.Count > 0) izquierda.Add(cuentas);

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 18 };
        fila.Add(izquierda, 0, 0);
        fila.Add(new Label { Text = "Ver quién completó  ›", FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.TintaMedia, VerticalOptions = LayoutOptions.Center }, 1, 0);

        var id = a.Id;
        return EstudioUi.TarjetaElegible(fila, false, async () => await MostrarDetalleAsync(id, null),
            $"{a.Titulo}. {EstudioTexto.Entrega(a.FechaLimite)}. {a.Completaron} de {total} completaron.", $"asignacion-{id}");
    }
}
