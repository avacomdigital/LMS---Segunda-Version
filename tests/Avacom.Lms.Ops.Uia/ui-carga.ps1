# Clientes de UI Automation que CARGAN a OPS en un solo proceso de PowerShell (sin lanzar uno por acción), para medir su estabilidad (tests/Avacom.Lms.Ops.Uia/estabilidad_ops.py):
#   -Modo vueltas   Ir y volver de «Licencia» -Vueltas veces: toca «Licencia» del menú, espera la pantalla, toca «Menú principal» y espera el menú. Cada toque se hace UNA vez (una
#                   excepción de Invoke() queda anotada, nunca se repite) y las esperas buscan por AutomationId (licencia-titulo, dashboard-licencia): una lectura barata.
#                   -Asentar <ms>: tras cada toque, esa pausa ANTES de volver a preguntarle nada a OPS (deja que la pantalla termine de cambiar).
#                   -Completo: espera con el recorrido de todo el árbol (como el arnés de antes) en lugar de buscar por AutomationId.
#   -Modo leer      Un lector que SÓLO lee, durante -Segundos: recorre todos los descendientes leyendo nombre, tipo, AutomationId y habilitado, sin invocar nada. Varios lectores a la vez
#                   (y uno que invoca) reproducen la carga que tumbó a OPS (APPCRASH 0xc0000005 en Microsoft.UI.Xaml.dll) y sirven para comparar las pausas.
# Anota en -Registro (JSONL) cada vuelta (duración de cada paso, excepciones de UIA, contadores de OPS) y, si OPS muere, «MUERTO». Sale con 0 si terminó, 5 si OPS murió, 6 si una espera falló.
param(
    [int]$ProcId,
    [string]$Modo = "vueltas",
    [int]$Vueltas = 100,
    [int]$Segundos = 300,
    [string]$Registro = "",
    [int]$Asentar = 0,
    [int]$Pausa = 0,
    [switch]$Completo,
    [string]$Quien = "u"
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class WinCarga { public delegate bool Cb(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, Cb cb, IntPtr l);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder sb, int n);
[DllImport("user32.dll")] public static extern uint GetGuiResources(IntPtr proceso, uint tipo);
public static IntPtr Contenido(IntPtr padre) { IntPtr hallado = IntPtr.Zero;
    EnumChildWindows(padre, (h, x) => { var sb = new System.Text.StringBuilder(256); GetClassName(h, sb, 256); if (sb.ToString() == "Microsoft.UI.Content.DesktopChildSiteBridge") { hallado = h; return false; } return true; }, IntPtr.Zero);
    return hallado; } }
"@
$t0 = [Diagnostics.Stopwatch]::StartNew()

function Log($o) {
    $o["t"] = [math]::Round($t0.Elapsed.TotalSeconds, 1); $o["quien"] = $Quien
    $l = ($o | ConvertTo-Json -Compress -Depth 5)
    if ($Registro -ne "") { Add-Content -Path $Registro -Value $l -Encoding UTF8 }
    Write-Output $l
}
function Contadores {
    $p = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    if ($null -eq $p) { return @{ vivo = $false } }
    return @{ vivo = $true; ws = [math]::Round($p.WorkingSet64 / 1MB, 1); priv = [math]::Round($p.PrivateMemorySize64 / 1MB, 1); handles = $p.HandleCount; hilos = $p.Threads.Count
              gdi = [WinCarga]::GetGuiResources($p.Handle, 0); user = [WinCarga]::GetGuiResources($p.Handle, 1) }
}
function Raiz {
    $p = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    if ($null -eq $p -or $p.MainWindowHandle -eq [IntPtr]::Zero) { return $null }
    $hijo = [WinCarga]::Contenido($p.MainWindowHandle)
    if ($hijo -eq [IntPtr]::Zero) { return $null }
    return [System.Windows.Automation.AutomationElement]::FromHandle($hijo)
}

$cache = New-Object System.Windows.Automation.CacheRequest
foreach ($p in @([System.Windows.Automation.AutomationElement]::NameProperty, [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                 [System.Windows.Automation.AutomationElement]::AutomationIdProperty, [System.Windows.Automation.AutomationElement]::IsEnabledProperty)) { $cache.Add($p) }
$cache.TreeScope = [System.Windows.Automation.TreeScope]::Element

function Todos($win) {
    $a = $cache.Activate()
    try { return $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition) } finally { $a.Dispose() }
}
function PorId($win, [string]$id) {
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
    $a = $cache.Activate()
    try { return $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond) } finally { $a.Dispose() }
}
function HayId($win, [string]$id) { return $null -ne (PorId $win $id) }
function HayTexto($win, [string]$texto) {
    foreach ($e in Todos $win) { if ($e.Cached.ControlType.ProgrammaticName -eq "ControlType.Text" -and $e.Cached.Name -like ("*" + $texto + "*")) { return $true } }
    return $false
}
function HayBoton($win, [string]$nombre) {
    foreach ($e in Todos $win) { if ($e.Cached.ControlType.ProgrammaticName -eq "ControlType.Button" -and $e.Cached.Name.Trim() -eq $nombre) { return $true } }
    return $false
}
# Un toque, UNA vez. Devuelve $null si salió bien o el texto de la excepción (el toque pudo llegar igual: no se repite).
function Tocar($elemento) {
    try { $elemento.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); return $null }
    catch { return $_.Exception.GetType().Name + " [" + ("{0:x8}" -f $_.Exception.HResult) + "] " + $_.Exception.Message }
}
function Esperar([scriptblock]$condicion, [int]$ms) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.ElapsedMilliseconds -lt $ms) {
        if (& $condicion) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

if ($Modo -eq "leer") {
    $recorridos = 0; $elementos = 0; $excs = 0; $ultima = ""
    Log @{ ev = "inicio"; modo = "leer"; pid = $ProcId }
    while ($t0.Elapsed.TotalSeconds -lt $Segundos) {
        if ($null -eq (Get-Process -Id $ProcId -ErrorAction SilentlyContinue)) { Log @{ ev = "MUERTO"; recorridos = $recorridos; elementos = $elementos; excepciones = $excs; ultima = $ultima }; exit 5 }
        try {
            $win = Raiz
            if ($null -eq $win) { Start-Sleep -Milliseconds 200; continue }
            foreach ($e in (Todos $win)) { $null = $e.Cached.Name; $elementos++ }
            $recorridos++
            if ($recorridos % 20 -eq 0) { Log @{ ev = "progreso"; recorridos = $recorridos; elementos = $elementos; excepciones = $excs } }
        } catch { $excs++; $ultima = $_.Exception.GetType().Name + " " + $_.Exception.Message.Substring(0, [math]::Min(60, $_.Exception.Message.Length)) }
        if ($Pausa -gt 0) { Start-Sleep -Milliseconds $Pausa }
    }
    Log @{ ev = "fin"; recorridos = $recorridos; elementos = $elementos; excepciones = $excs; ultima = $ultima }
    exit 0
}

# ---- Modo vueltas
Log @{ ev = "inicio"; modo = "vueltas"; pid = $ProcId; asentar = $Asentar; completo = [bool]$Completo; c = (Contadores) }
for ($v = 1; $v -le $Vueltas; $v++) {
    if ($null -eq (Get-Process -Id $ProcId -ErrorAction SilentlyContinue)) { Log @{ ev = "MUERTO"; vuelta = $v }; exit 5 }
    $win = Raiz
    if ($null -eq $win) { Log @{ ev = "SIN VENTANA"; vuelta = $v }; exit 6 }
    $lap = [Diagnostics.Stopwatch]::StartNew(); $s = [Diagnostics.Stopwatch]::StartNew()
    $paso = @{}; $excepciones = @()

    $boton = PorId $win "dashboard-licencia"
    $e1 = $null; if ($null -ne $boton) { $e1 = Tocar $boton; if ($e1) { $excepciones += "licencia: $e1" } }
    $paso["tocar"] = @($s.ElapsedMilliseconds, ($null -ne $boton))
    if ($Asentar -gt 0) { Start-Sleep -Milliseconds $Asentar }

    $s.Restart()
    $ok2 = if ($Completo) { Esperar { HayTexto $win "Licencia de este equipo" } 25000 } else { Esperar { HayId $win "licencia-titulo" } 25000 }
    $paso["pantalla"] = @($s.ElapsedMilliseconds, $ok2)
    if (-not $ok2) { Log @{ ev = "FALLA"; vuelta = $v; paso = "pantalla"; pasos = $paso; exc = $excepciones; c = (Contadores) }; exit 6 }

    $s.Restart()
    $atras = PorId $win "licencia-volver"
    $e3 = $null; if ($null -ne $atras) { $e3 = Tocar $atras; if ($e3) { $excepciones += "volver: $e3" } }
    $paso["volver"] = @($s.ElapsedMilliseconds, ($null -ne $atras))
    if ($Asentar -gt 0) { Start-Sleep -Milliseconds $Asentar }

    $s.Restart()
    $ok4 = if ($Completo) { Esperar { HayBoton $win "Licencia" } 25000 } else { Esperar { HayId $win "dashboard-licencia" } 25000 }
    $paso["menú"] = @($s.ElapsedMilliseconds, $ok4)
    Log @{ ev = "vuelta"; n = $v; s = [math]::Round($lap.Elapsed.TotalSeconds, 1); pasos = $paso; exc = $excepciones; c = (Contadores) }
    if (-not $ok4) { Log @{ ev = "FALLA"; vuelta = $v; paso = "menú" }; exit 6 }
    if ($Pausa -gt 0) { Start-Sleep -Milliseconds $Pausa }
}
Log @{ ev = "fin"; c = (Contadores) }
exit 0
