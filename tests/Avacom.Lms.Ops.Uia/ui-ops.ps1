# Manejo de AVACOM OPS Master por UI Automation, sin ratón ni foco: lista controles, invoca botones por su nombre, escribe en entradas por
# ValuePattern, marca un PIN tocando las teclas del teclado propio (AutomationId tecla-N) y captura sólo el área de contenido de la ventana con PrintWindow.
# Uso: powershell -File ui-ops.ps1 -ProcId 1234 -Accion list|text|invoke|set|pin|shot|esperar|tecla|buscar|contar|doble|existe -Nombre "..." -Valor "..." -Salida x.png [-Espera ms]
#   invoke  busca un botón cuyo nombre sea exactamente -Nombre; si no lo hay, uno que lo contenga, e invoca UNA sola vez.
#   tecla   un toque sobre el control con ese AutomationId.
#   doble   dos toques SEGUIDOS sobre un control (AutomationId o nombre exacto): lo que hace un doble toque en la pantalla táctil. Sólo para pruebas de doble activación.
#   existe  mira SIN esperar si hay un control con ese AutomationId o nombre exacto (sale con 0, o con 3 si no hay): la comprobación barata de «¿en qué pantalla estoy?».
#   contar  cuántos elementos tiene el árbol de UI Automation de OPS ahora y cuánto tardó en recorrerse.
#   esperar sondea el texto visible hasta que aparezca -Valor (máx. -Espera ms, 15000 por defecto); sale con 3 si no aparece.
# Salidas: 0 bien · 1 sin ventana · 2 no hay el control · 3 no apareció / no existe · 4 INVOCACIÓN DUDOSA.
#
# Invocación dudosa (salida 4). Si Invoke() lanza una excepción (el hilo de interfaz de OPS tardó y UI Automation se rindió) el toque PUDO llegar igual: se queda pedido en OPS y se
# ejecuta cuando le toca. Repetirlo a ciegas —lo que hacía este guion— activaba dos veces «Menú principal» y sacaba también el menú: OPS volvía al acceso con el proceso vivo y sin 401.
# Aquí un toque se hace UNA vez, y quien llama mira la pantalla antes de volver a tocar. Buscar el control otra vez mientras no aparece sí es seguro (todavía no se tocó nada).
#
# Lecturas baratas: cada elemento se lee con una CacheRequest (nombre, tipo, AutomationId y habilitado en una sola llamada entre procesos) en lugar de cuatro llamadas por elemento,
# que eran las que cargaban el hilo de interfaz de OPS y alargaban los recorridos hasta segundos.
param(
    [int]$ProcId,
    [string]$Accion = "list",
    [string]$Nombre = "",
    [string]$Valor = "",
    [string]$Salida = "",
    [int]$Espera = 0
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class Win { [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT r);
[DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hwnd, out RECT r);
[DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hwnd, ref POINT p);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
public delegate bool Cb(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, Cb cb, IntPtr l);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder sb, int n);
public static IntPtr Contenido(IntPtr padre) {
    IntPtr hallado = IntPtr.Zero;
    EnumChildWindows(padre, (h, x) => { var sb = new System.Text.StringBuilder(256); GetClassName(h, sb, 256);
        if (sb.ToString() == "Microsoft.UI.Content.DesktopChildSiteBridge") { hallado = h; return false; } return true; }, IntPtr.Zero);
    return hallado; } }
"@

# La raíz es el contenido XAML (la ventana hija DesktopChildSiteBridge), no la ventana principal: si quien usa el equipo cambia de escritorio virtual,
# la ventana de prueba queda «cloaked», deja de colgar del escritorio en el árbol de UIA y desde la principal sólo se ven los botones del título.
# Por el manejador de la hija el árbol del contenido sigue entero.
function Ventana {
    for ($i = 0; $i -lt 20; $i++) {
        $proc = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
        if ($null -eq $proc) { return $null }
        if ($proc.MainWindowHandle -ne [IntPtr]::Zero) {
            $hijo = [Win]::Contenido($proc.MainWindowHandle)
            if ($hijo -ne [IntPtr]::Zero) { return @($proc.MainWindowHandle, [System.Windows.Automation.AutomationElement]::FromHandle($hijo)) }
        }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

$par = Ventana
if ($null -eq $par) { Write-Output "SIN VENTANA para pid $ProcId"; exit 1 }
$hwnd = [IntPtr]$par[0]
$win = $par[1]

# Las propiedades que se leen de cada elemento, traídas de una vez.
$script:Cache = New-Object System.Windows.Automation.CacheRequest
foreach ($p in @([System.Windows.Automation.AutomationElement]::NameProperty, [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                 [System.Windows.Automation.AutomationElement]::AutomationIdProperty, [System.Windows.Automation.AutomationElement]::IsEnabledProperty)) { $script:Cache.Add($p) }
$script:Cache.TreeScope = [System.Windows.Automation.TreeScope]::Element

function Todos($raiz) {
    $activa = $script:Cache.Activate()
    try { return $raiz.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition) }
    finally { $activa.Dispose() }
}

function PorId([string]$id) {
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
    $activa = $script:Cache.Activate()
    try { return $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond) }
    finally { $activa.Dispose() }
}

function Textos {
    $salida = New-Object System.Collections.Generic.List[string]
    foreach ($e in Todos $win) {
        if ($e.Cached.ControlType.ProgrammaticName -eq "ControlType.Text" -and $e.Cached.Name -ne "") { $salida.Add($e.Cached.Name) }
    }
    return $salida
}

function Boton([string]$nombre) {
    $parecido = $null
    foreach ($e in Todos $win) {
        if ($e.Cached.ControlType.ProgrammaticName -ne "ControlType.Button") { continue }
        $n = $e.Cached.Name.Trim()
        if ($n -eq $nombre.Trim()) { return $e }
        if ($null -eq $parecido -and $n -like ("*" + $nombre.Trim() + "*")) { $parecido = $e }
    }
    return $parecido
}

function Invocar($elemento) {
    $p = $elemento.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $p.Invoke()
}

# Un toque, UNA vez. Si Invoke() lanza, el toque pudo llegar igual: se dice y se sale con 4 (ver la nota de arriba); nunca se repite aquí.
function Tocar($elemento, [string]$que) {
    try { Invocar $elemento }
    catch {
        Write-Output ("DUDOSA '" + $que + "': " + $_.Exception.GetType().Name + " [" + ("{0:x8}" -f $_.Exception.HResult) + "] " + $_.Exception.Message)
        exit 4
    }
}

switch ($Accion) {
    "list" {
        foreach ($e in Todos $win) {
            $t = $e.Cached.ControlType.ProgrammaticName -replace "ControlType\.", ""
            if ($t -in @("Button","Edit","Text","CheckBox","Hyperlink") -and ($e.Cached.Name -ne "" -or $t -eq "Edit")) {
                Write-Output ("{0}`t{1}`t{2}`t{3}" -f $t, $e.Cached.Name, $e.Cached.AutomationId, $e.Cached.IsEnabled)
            }
        }
    }
    "text" { Textos | ForEach-Object { Write-Output $_ } }
    "contar" {
        $reloj = [Diagnostics.Stopwatch]::StartNew()
        $n = @(Todos $win).Count
        Write-Output ("ELEMENTOS {0} en {1} ms" -f $n, $reloj.ElapsedMilliseconds)
    }
    "buscar" {
        # Cualquier elemento (no sólo textos) cuyo nombre contenga -Valor: p. ej. los puntos del PIN, «1 de 6 números marcados».
        foreach ($e in Todos $win) { if ($e.Cached.Name -like ("*" + $Valor + "*")) { Write-Output ("VISTO '" + $e.Cached.Name + "'"); exit 0 } }
        Write-Output "NO HAY '$Valor'"; exit 3
    }
    "existe" {
        $e = PorId $Nombre
        if ($null -eq $e) { foreach ($c in Todos $win) { if ($c.Cached.Name.Trim() -eq $Nombre.Trim()) { $e = $c; break } } }
        if ($null -eq $e) { Write-Output "NO EXISTE '$Nombre'"; exit 3 }
        Write-Output "EXISTE '$Nombre'"
    }
    "tecla" {
        # Un solo toque sobre un control por su AutomationId (tecla-5, tecla-borrar, dashboard-licencia…).
        $t = PorId $Nombre
        if ($null -eq $t) { Write-Output "NO HAY TECLA '$Nombre'"; exit 2 }
        Tocar $t $Nombre
        Write-Output "TOCADA '$Nombre'"
    }
    "doble" {
        # Dos toques seguidos, sin pausa: el doble toque de la pantalla táctil (o el reintento de una prueba). Busca por AutomationId y, si no, por nombre de botón.
        $t = PorId $Nombre
        if ($null -eq $t) { $t = Boton $Nombre }
        if ($null -eq $t) { Write-Output "NO HAY CONTROL '$Nombre'"; exit 2 }
        Tocar $t $Nombre
        Tocar $t $Nombre
        Write-Output "DOBLE '$Nombre'"
    }
    "esperar" {
        $limite = if ($Espera -gt 0) { $Espera } else { 15000 }
        $reloj = [Diagnostics.Stopwatch]::StartNew()
        while ($reloj.ElapsedMilliseconds -lt $limite) {
            foreach ($t in Textos) { if ($t -like ("*" + $Valor + "*")) { Write-Output "VISTO '$t'"; exit 0 } }
            Start-Sleep -Milliseconds 400
        }
        Write-Output "NO APARECIO '$Valor'"; exit 3
    }
    "invoke" {
        # Los botones se reconstruyen al repintar: mientras no aparezca (o no esté habilitado) se busca otra vez, y eso es seguro porque todavía no se tocó nada.
        # Pero Invoke() se hace UNA sola vez (ver «Invocación dudosa»).
        $b = $null
        for ($intento = 0; $intento -lt 8 -and $null -eq $b; $intento++) {
            $c = Boton $Nombre
            if ($null -ne $c -and $c.Cached.IsEnabled) { $b = $c } else { Start-Sleep -Milliseconds 600 }
        }
        if ($null -eq $b) { Write-Output "NO HAY BOTON '$Nombre'"; exit 2 }
        Tocar $b $Nombre
        Write-Output "INVOCADO '$Nombre'"
    }
    "set" {
        $hallado = $null
        foreach ($e in Todos $win) {
            if ($e.Cached.ControlType.ProgrammaticName -eq "ControlType.Edit" -and ($e.Cached.Name -eq $Nombre -or $e.Cached.AutomationId -eq $Nombre)) { $hallado = $e; break }
        }
        if ($null -eq $hallado) {
            foreach ($e in Todos $win) {
                if ($e.Cached.ControlType.ProgrammaticName -eq "ControlType.Edit" -and $e.Cached.Name -like ("*" + $Nombre + "*")) { $hallado = $e; break }
            }
        }
        if ($null -eq $hallado) { Write-Output "NO HAY ENTRADA '$Nombre'"; exit 2 }
        $p = $hallado.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $p.SetValue($Valor); Write-Output "ESCRITO en '$Nombre'"
    }
    "pin" {
        # Toca las teclas del TecladoPinView (AutomationId tecla-0…tecla-9). El PIN no se escribe en la salida.
        # Una tecla se toca UNA vez (un dígito de más cambiaría el PIN): si la tecla todavía no está o no está habilitada se busca otra vez; si Invoke() lanza, sale con 4.
        foreach ($c in $Valor.ToCharArray()) {
            $tecla = $null
            for ($intento = 0; $intento -lt 8 -and $null -eq $tecla; $intento++) {
                $candidata = PorId "tecla-$c"
                if ($null -ne $candidata -and $candidata.Cached.IsEnabled) { $tecla = $candidata } else { Start-Sleep -Milliseconds 400 }
            }
            if ($null -eq $tecla) { Write-Output "NO HAY TECLA"; exit 2 }
            Tocar $tecla "tecla-$c"
            # El teclado descarta un segundo toque de la MISMA tecla dentro de 180 ms (rebote): entre dígitos se espera más que eso.
            Start-Sleep -Milliseconds 260
        }
        Write-Output ("PIN MARCADO (" + $Valor.Length + " digitos)")
    }
    "shot" {
        # Sólo el área de contenido (sin la barra de título), que es el encuadre sobre el que se juzga la regla de tercios.
        $r = New-Object Win+RECT
        [Win]::GetWindowRect($hwnd, [ref]$r) | Out-Null
        $w = $r.R - $r.L; $h = $r.B - $r.T
        $bmp = New-Object System.Drawing.Bitmap $w, $h
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $hdc = $g.GetHdc()
        [Win]::PrintWindow($hwnd, $hdc, 2) | Out-Null
        $g.ReleaseHdc($hdc); $g.Dispose()
        $c = New-Object Win+RECT
        [Win]::GetClientRect($hwnd, [ref]$c) | Out-Null
        $o = New-Object Win+POINT
        [Win]::ClientToScreen($hwnd, [ref]$o) | Out-Null
        # WinUI pinta su barra de título DENTRO del área cliente: se recorta (32 px) para quedarse con la página.
        $x = [Math]::Max(0, $o.X - $r.L); $y = [Math]::Max(0, $o.Y - $r.T) + 32
        $cw = [Math]::Min($c.R, $w - $x); $ch = [Math]::Min($c.B - 32, $h - $y)
        $recorte = $bmp.Clone((New-Object System.Drawing.Rectangle $x, $y, $cw, $ch), $bmp.PixelFormat)
        $recorte.Save($Salida, [System.Drawing.Imaging.ImageFormat]::Png)
        $recorte.Dispose(); $bmp.Dispose()
        Write-Output "CAPTURA $Salida ${cw}x${ch}"
    }
}
