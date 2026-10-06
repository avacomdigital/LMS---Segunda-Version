# Manejo de AVACOM OPS Master por UI Automation, sin ratón ni foco: lista controles, invoca botones por su nombre, escribe en entradas por
# ValuePattern, marca un PIN tocando las teclas del teclado propio (AutomationId tecla-N) y captura sólo el área de contenido de la ventana con PrintWindow.
# Uso: powershell -File ui-ops.ps1 -ProcId 1234 -Accion list|text|invoke|set|pin|shot|esperar -Nombre "..." -Valor "..." -Salida x.png [-Espera ms]
#   invoke  busca un botón cuyo nombre sea exactamente -Nombre; si no lo hay, uno que lo contenga.
#   esperar sondea el texto visible hasta que aparezca -Valor (máx. -Espera ms, 15000 por defecto); sale con 3 si no aparece.
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

function Todos($raiz) { return $raiz.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition) }

function Textos {
    $salida = New-Object System.Collections.Generic.List[string]
    foreach ($e in Todos $win) {
        if ($e.Current.ControlType.ProgrammaticName -eq "ControlType.Text" -and $e.Current.Name -ne "") { $salida.Add($e.Current.Name) }
    }
    return $salida
}

function Boton([string]$nombre) {
    $parecido = $null
    foreach ($e in Todos $win) {
        if ($e.Current.ControlType.ProgrammaticName -ne "ControlType.Button") { continue }
        $n = $e.Current.Name.Trim()
        if ($n -eq $nombre.Trim()) { return $e }
        if ($null -eq $parecido -and $n -like ("*" + $nombre.Trim() + "*")) { $parecido = $e }
    }
    return $parecido
}

function Invocar($elemento) {
    $p = $elemento.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $p.Invoke()
}

switch ($Accion) {
    "list" {
        foreach ($e in Todos $win) {
            $t = $e.Current.ControlType.ProgrammaticName -replace "ControlType\.", ""
            if ($t -in @("Button","Edit","Text","CheckBox","Hyperlink") -and ($e.Current.Name -ne "" -or $t -eq "Edit")) {
                Write-Output ("{0}`t{1}`t{2}`t{3}" -f $t, $e.Current.Name, $e.Current.AutomationId, $e.Current.IsEnabled)
            }
        }
    }
    "text" { Textos | ForEach-Object { Write-Output $_ } }
    "buscar" {
        # Cualquier elemento (no sólo textos) cuyo nombre contenga -Valor: p. ej. los puntos del PIN, «1 de 6 números marcados».
        foreach ($e in Todos $win) { if ($e.Current.Name -like ("*" + $Valor + "*")) { Write-Output ("VISTO '" + $e.Current.Name + "'"); exit 0 } }
        Write-Output "NO HAY '$Valor'"; exit 3
    }
    "tecla" {
        # Un solo toque sobre una tecla del teclado del PIN por su AutomationId (tecla-5, tecla-borrar…).
        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $Nombre)
        $t = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
        if ($null -eq $t) { Write-Output "NO HAY TECLA '$Nombre'"; exit 2 }
        Invocar $t; Write-Output "TOCADA '$Nombre'"
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
        # Los botones se reconstruyen al repintar: el elemento puede quedar obsoleto entre buscarlo e invocarlo, así que se reintenta.
        $hecho = $false
        for ($intento = 0; $intento -lt 8 -and -not $hecho; $intento++) {
            $b = Boton $Nombre
            if ($null -ne $b -and $b.Current.IsEnabled) {
                try { Invocar $b; $hecho = $true } catch { Start-Sleep -Milliseconds 400 }
            } else { Start-Sleep -Milliseconds 600 }
        }
        if (-not $hecho) { Write-Output "NO HAY BOTON '$Nombre'"; exit 2 }
        Write-Output "INVOCADO '$Nombre'"
    }
    "set" {
        $hallado = $null
        foreach ($e in Todos $win) {
            if ($e.Current.ControlType.ProgrammaticName -eq "ControlType.Edit" -and ($e.Current.Name -eq $Nombre -or $e.Current.AutomationId -eq $Nombre)) { $hallado = $e; break }
        }
        if ($null -eq $hallado) {
            foreach ($e in Todos $win) {
                if ($e.Current.ControlType.ProgrammaticName -eq "ControlType.Edit" -and $e.Current.Name -like ("*" + $Nombre + "*")) { $hallado = $e; break }
            }
        }
        if ($null -eq $hallado) { Write-Output "NO HAY ENTRADA '$Nombre'"; exit 2 }
        $p = $hallado.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $p.SetValue($Valor); Write-Output "ESCRITO en '$Nombre'"
    }
    "pin" {
        # Toca las teclas del TecladoPinView (AutomationId tecla-0…tecla-9). El PIN no se escribe en la salida.
        foreach ($c in $Valor.ToCharArray()) {
            $hecho = $false
            for ($intento = 0; $intento -lt 8 -and -not $hecho; $intento++) {
                $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, "tecla-$c")
                $tecla = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
                if ($null -ne $tecla -and $tecla.Current.IsEnabled) { try { Invocar $tecla; $hecho = $true } catch { Start-Sleep -Milliseconds 300 } }
                else { Start-Sleep -Milliseconds 400 }
            }
            if (-not $hecho) { Write-Output "NO HAY TECLA"; exit 2 }
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
