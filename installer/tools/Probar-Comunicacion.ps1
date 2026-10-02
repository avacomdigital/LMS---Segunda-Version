<#
.SYNOPSIS
    Diagnóstico de la comunicación entre AVACOM OPS Master y AVACOM Biblioteca.

.DESCRIPTION
    Recorre la cadena completa, eslabón por eslabón, y cuando algo falla dice
    dónde se rompe y qué hacer:

        AVACOM OPS Master (interfaz)
            │  HTTP  127.0.0.1:8000
            ▼
        Servicio AVACOMOPSBackend  →  Daphne (ASGI)  →  Django / DRF + WebSocket
            │  loopback, puerto efímero, cabecera X-Avacom-Token
            ▼
        AVACOM Contenido  (127.0.0.1:{apiPort de link.json})

    La gracia del diagnóstico está en separar dos fallos que se ven igual desde
    la pantalla del profesor —«no aparecen los cursos»— y tienen causas
    distintas:

      · la Biblioteca no está publicando su API, o
      · la Biblioteca sí está, pero el backend no la alcanza.

    Para distinguirlos, el script habla con la Biblioteca por su cuenta, con la
    token de link.json, y compara lo que ve él con lo que dice el
    backend en /health/.

    También lee los registros del backend y clasifica los errores de Python,
    con atención especial a los que ocurren dentro de las peticiones de Daphne: son los
    que rompen una petición suelta y no dejan rastro en la pantalla.

    NO MODIFICA NADA. Solo lee y consulta. No reinicia servicios, no cambia
    configuración y no escribe en el expediente de los estudiantes.

.PARAMETER Puerto
    Puerto de la API local. Por defecto se lee de la configuración del nodo y,
    si no está, se usa 8000.

.PARAMETER Informe
    Dónde escribir el informe. Por defecto, el escritorio.

.PARAMETER Abrir
    Abre el informe al terminar. Útil en el equipo del aula, que es táctil.

.PARAMETER HorasDeLog
    Cuántas horas atrás mirar en los registros. Por defecto 24.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Probar-Comunicacion.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Probar-Comunicacion.ps1 -Abrir

.NOTES
    Códigos de salida:  0 todo bien · 1 hay algo que bloquea · 2 sólo avisos
#>
[CmdletBinding()]
param(
    [int]    $Puerto = 0,
    [string] $Informe = '',
    [switch] $Abrir,
    [int]    $HorasDeLog = 24,
    # Para analizar registros copiados de otro equipo: se apunta aqui la
    # carpeta Logs traida del nodo y el apartado 10 la lee en su lugar.
    [string] $CarpetaDeLogs = '',
    # Deja en el escritorio un .zip con el informe, las respuestas crudas de la
    # Biblioteca y del backend, y los registros. Es lo que hay que enviar para
    # que alguien pueda diagnosticar sin tocar el equipo.
    [switch] $Paquete
)

Set-StrictMode -Version Latest
# A propósito NO se usa 'Stop': un diagnóstico que se cae en la primera
# comprobación que falla no sirve para nada. Cada bloque maneja su error.
$ErrorActionPreference = 'Continue'

$VersionDiagnostico = '2.2.0'
$RaizDatos = Join-Path $env:ProgramData 'AVACOM\OPS Master'
$RutaEnlace = Join-Path $env:ProgramData 'AVACOM\content\link.json'
$NombreServicio = 'AVACOMOPSBackend'

# Respuestas crudas que se guardan en el paquete de evidencias.
$Evidencias = New-Object System.Collections.Generic.List[object]
# El token es la credencial de la biblioteca: nunca sale del equipo.
$FichaParaOcultar = ''

# ---------------------------------------------------------------- utilidades

$Hallazgos = New-Object System.Collections.Generic.List[object]
$Renglones = New-Object System.Collections.Generic.List[string]

function Escribir {
    param([string] $Texto = '', [string] $Color = 'Gray')
    $Renglones.Add($Texto)
    Write-Host $Texto -ForegroundColor $Color
}

function Seccion {
    param([string] $Titulo)
    Escribir ''
    Escribir ('=' * 74) 'DarkGray'
    Escribir "  $Titulo" 'Cyan'
    Escribir ('=' * 74) 'DarkGray'
}

<#
    Anota un hallazgo. La gravedad decide el color, el orden del resumen final
    y el código de salida.

      OK      · el eslabón funciona
      INFO    · dato de contexto, no hay nada que hacer
      AVISO   · funciona, pero hay algo que conviene mirar
      BLOQUEA · esto es lo que impide que la comunicación funcione
#>
function Anotar {
    param(
        [ValidateSet('OK', 'INFO', 'AVISO', 'BLOQUEA')] [string] $Gravedad,
        [string] $Titulo,
        [string] $Detalle = '',
        [string] $Accion = ''
    )

    $Hallazgos.Add([pscustomobject]@{
        Gravedad = $Gravedad
        Titulo   = $Titulo
        Detalle  = $Detalle
        Accion   = $Accion
    })

    $marca = switch ($Gravedad) {
        'OK'      { '  [ok]     ' }
        'INFO'    { '  [info]   ' }
        'AVISO'   { '  [aviso]  ' }
        'BLOQUEA' { '  [FALLA]  ' }
    }
    $color = switch ($Gravedad) {
        'OK'      { 'Green' }
        'INFO'    { 'Gray' }
        'AVISO'   { 'Yellow' }
        'BLOQUEA' { 'Red' }
    }
    Escribir "$marca$Titulo" $color
    if ($Detalle) {
        foreach ($linea in ($Detalle -split "`n")) { Escribir "            $linea" 'DarkGray' }
    }
}

<#
    Lee una propiedad de un objeto venido de ConvertFrom-Json.

    Con StrictMode, tocar una propiedad que no existe en un PSCustomObject es un
    error que aborta el script. Como el backend puede degradar y devolver
    respuestas con menos campos, todo acceso a JSON pasa por aquí.
#>
function Prop {
    param($Objeto, [string] $Nombre, $PorDefecto = $null)
    if ($null -eq $Objeto) { return $PorDefecto }
    if ($Objeto -isnot [psobject]) { return $PorDefecto }
    $propiedad = $Objeto.PSObject.Properties[$Nombre]
    if ($null -eq $propiedad) { return $PorDefecto }
    if ($null -eq $propiedad.Value) { return $PorDefecto }
    return $propiedad.Value
}

<#
    Petición HTTP que NO lanza por un código de estado.

    Invoke-WebRequest trata un 503 como excepción, y en este diagnóstico un 503
    es justamente la respuesta más interesante: hay que poder leer su cuerpo,
    porque el backend explica ahí el motivo y la sugerencia. Por eso se usa
    HttpWebRequest y se lee el cuerpo también en el camino de error.
#>
function Invoke-Peticion {
    param(
        [string]    $Url,
        [string]    $Metodo = 'GET',
        [hashtable] $Cabeceras = $null,
        [int]       $SegundosDeEspera = 10
    )

    $resultado = [pscustomobject]@{
        Url          = $Url
        Estado       = 0
        Cuerpo       = ''
        Json         = $null
        Error        = ''
        Milisegundos = 0
    }
    $reloj = [System.Diagnostics.Stopwatch]::StartNew()
    $respuesta = $null
    try {
        $peticion = [System.Net.HttpWebRequest]::Create($Url)
        $peticion.Method = $Metodo
        $peticion.Timeout = $SegundosDeEspera * 1000
        $peticion.ReadWriteTimeout = $SegundosDeEspera * 1000
        $peticion.AllowAutoRedirect = $false
        $peticion.UserAgent = "AVACOM-Diagnostico/$VersionDiagnostico"
        # Loopback: un proxy configurado en el equipo solo estorbaría.
        $peticion.Proxy = $null
        if ($Cabeceras) {
            foreach ($clave in $Cabeceras.Keys) { $peticion.Headers.Add($clave, $Cabeceras[$clave]) }
        }
        $respuesta = $peticion.GetResponse()
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) {
            $respuesta = $_.Exception.Response
        } else {
            $resultado.Error = $_.Exception.Message
        }
    } catch {
        $resultado.Error = $_.Exception.Message
    }

    if ($respuesta) {
        try {
            $resultado.Estado = [int]$respuesta.StatusCode
            $flujo = $respuesta.GetResponseStream()
            if ($flujo) {
                $lector = New-Object System.IO.StreamReader($flujo, [System.Text.Encoding]::UTF8)
                $resultado.Cuerpo = $lector.ReadToEnd()
                $lector.Dispose()
            }
        } catch {
            $resultado.Error = $_.Exception.Message
        } finally {
            try { $respuesta.Close() } catch { }
        }
    }

    $reloj.Stop()
    $resultado.Milisegundos = [int]$reloj.ElapsedMilliseconds

    if ($resultado.Cuerpo) {
        try { $resultado.Json = $resultado.Cuerpo | ConvertFrom-Json } catch { }
    }
    return $resultado
}

<#
    Quita la ficha de cualquier texto que vaya a salir del equipo.

    La ficha es la credencial con la que el backend habla con la Biblioteca.
    Un informe que se manda por correo no puede llevarla.
#>
function Ocultar {
    param([string] $Texto)
    if (-not $Texto) { return '' }
    if ($FichaParaOcultar) { return $Texto.Replace($FichaParaOcultar, '<ficha oculta>') }
    return $Texto
}

function Guardar-Evidencia {
    param([string] $Nombre, [string] $Contenido, [int] $Estado = 0, [string] $Url = '')
    $Evidencias.Add([pscustomobject]@{
        Nombre    = $Nombre
        Contenido = "# $Url`n# HTTP $Estado`n`n$Contenido"
    })
}

function Recortar {
    param([string] $Texto, [int] $Largo = 300)
    if (-not $Texto) { return '' }
    # Algunas rutas devuelven material, no JSON: sin esto, un audio o una imagen
    # llenaría el informe de basura binaria.
    $imprimible = [regex]::Replace($Texto, '[^ -~ -￿]', '.')
    $limpio = ($imprimible -replace '\s+', ' ').Trim()
    if ($limpio.Length -le $Largo) { return $limpio }
    return $limpio.Substring(0, $Largo) + '...'
}

# ============================================================================
Escribir ''
Escribir "  AVACOM OPS Master · diagnóstico de comunicación con AVACOM Biblioteca" 'White'
Escribir "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')   equipo: $env:COMPUTERNAME   usuario: $env:USERNAME" 'DarkGray'
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Escribir '  (sin permisos de administrador: algunos datos del servicio no se podrán leer)' 'DarkYellow'
}

# ============================================================ 1. Instalación
Seccion '1 · Instalación en este equipo'

$RaizInstalacion = ''
try {
    $clave = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B6D1F0A4-3C57-4E2B-9A18-7F5C2E8D4A31}_is1'
    if (Test-Path $clave) {
        $entrada = Get-ItemProperty $clave
        $RaizInstalacion = [string](Prop $entrada 'InstallLocation' '')
        Anotar 'OK' "AVACOM OPS Master $(Prop $entrada 'DisplayVersion' '(sin versión)') instalado" $RaizInstalacion
    }
} catch { }

if (-not $RaizInstalacion) {
    # Sin entrada de desinstalación: puede ser una compilación de desarrollo.
    # El servicio sabe dónde está su ejecutable, y eso basta.
    try {
        $wmi = Get-CimInstance Win32_Service -Filter "Name='$NombreServicio'" -ErrorAction Stop
        $imagen = [string](Prop $wmi 'PathName' '')
        if ($imagen -match '"([^"]+)"') {
            $RaizInstalacion = Split-Path (Split-Path $Matches[1] -Parent) -Parent
            Anotar 'INFO' 'No hay entrada de desinstalación; la ruta se deduce del servicio' $RaizInstalacion
        }
    } catch { }
}

if (-not $RaizInstalacion) {
    Anotar 'AVISO' 'No se encontró una instalación de AVACOM OPS Master' `
        'Puede ser una compilación de desarrollo ejecutada a mano.' `
        'Las comprobaciones de la API siguen siendo válidas; las de archivos instalados se omiten.'
} elseif (Test-Path (Join-Path $RaizInstalacion 'manifiesto.json')) {
    try {
        $manifiesto = Get-Content (Join-Path $RaizInstalacion 'manifiesto.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        Anotar 'INFO' "Paquete: versión $(Prop $manifiesto 'version' '?') · revisión $(Prop $manifiesto 'revision' '?')" `
            ("Python $(Prop $manifiesto 'runtime_python' '?') · servidor $(Prop $manifiesto 'servidor_wsgi' '?') · escucha $(Prop $manifiesto 'escucha' '?')")
    } catch {
        Anotar 'AVISO' 'El manifiesto del paquete no se pudo leer' $_.Exception.Message
    }
}

# ====================================================== 2. Configuración
Seccion '2 · Configuración de este nodo'

$ArchivoConfig = Join-Path $RaizDatos 'Config\backend.env'
$Config = @{}
if (Test-Path $ArchivoConfig) {
    try {
        foreach ($linea in (Get-Content $ArchivoConfig -Encoding UTF8)) {
            $texto = $linea.Trim()
            if (-not $texto -or $texto.StartsWith('#')) { continue }
            $corte = $texto.IndexOf('=')
            if ($corte -gt 0) { $Config[$texto.Substring(0, $corte).Trim()] = $texto.Substring($corte + 1).Trim() }
        }
        # La clave del nodo no se imprime ni se escribe en el informe.
        $visibles = $Config.Keys | Where-Object { $_ -ne 'AVACOM_LMS_SECRET' } | Sort-Object
        Anotar 'OK' 'Configuración del nodo leída' (($visibles | ForEach-Object { "$_=$($Config[$_])" }) -join "`n")
        if (-not $Config.ContainsKey('AVACOM_LMS_SECRET')) {
            Anotar 'AVISO' 'La configuración no define AVACOM_LMS_SECRET' '' `
                'Vuelve a ejecutar el instalador para regenerar la configuración del nodo.'
        }
    } catch {
        Anotar 'AVISO' 'La configuración del nodo no se pudo leer' $_.Exception.Message
    }
} else {
    Anotar 'AVISO' 'No hay configuración del nodo' "Se esperaba $ArchivoConfig" `
        'Si el producto se instaló con el asistente, esto debería existir. Reinstala para regenerarla.'
}

if ($Puerto -le 0) {
    if ($Config.ContainsKey('AVACOM_OPS_BACKEND_PORT')) {
        $valor = 0
        if ([int]::TryParse($Config['AVACOM_OPS_BACKEND_PORT'], [ref]$valor) -and $valor -gt 0) { $Puerto = $valor }
    }
}
if ($Puerto -le 0) { $Puerto = 8000 }
$Base = "http://127.0.0.1:$Puerto"
Escribir "            API local: $Base" 'DarkGray'

# La causa raíz más frecuente de «la Biblioteca está pero no se ve»: alguien
# dejó apuntando el backend a la nota del host de pruebas del repositorio.
$EnlaceForzado = ''
if ($Config.ContainsKey('AVACOM_CONTENIDO_ENLACE') -and $Config['AVACOM_CONTENIDO_ENLACE']) {
    $EnlaceForzado = $Config['AVACOM_CONTENIDO_ENLACE']
}
try {
    $deMaquina = [Environment]::GetEnvironmentVariable('AVACOM_CONTENIDO_ENLACE', 'Machine')
    if ($deMaquina) { $EnlaceForzado = $deMaquina }
} catch { }

if ($EnlaceForzado) {
    $RutaEnlace = $EnlaceForzado
    Anotar 'BLOQUEA' 'El backend está mirando una nota de enlace forzada, no la de AVACOM Biblioteca' `
        ("AVACOM_CONTENIDO_ENLACE = $EnlaceForzado`n" +
         "Esa variable sólo existe para probar la integración con el host de pruebas del repositorio.") `
        ("Quita la línea AVACOM_CONTENIDO_ENLACE de $ArchivoConfig (y la variable de entorno de máquina si está), " +
         "y reinicia el servicio $NombreServicio. Sin ella el backend busca la nota donde la Biblioteca la publica de verdad.")
} else {
    Anotar 'OK' 'El backend busca la nota de enlace donde la publica AVACOM Biblioteca' $RutaEnlace
}

if ($Config.ContainsKey('AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG')) {
    $espera = 0.0
    if ([double]::TryParse($Config['AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG'], [ref]$espera) -and $espera -lt 2) {
        Anotar 'AVISO' "El tiempo de espera hacia la Biblioteca es muy corto ($espera s)" `
            'Con la Biblioteca ocupada, el backend dará 503 de forma intermitente.' `
            "Sube AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG a 3 en $ArchivoConfig y reinicia el servicio."
    }
}

# ========================================================== 3. El servicio
Seccion "3 · Servicio $NombreServicio"

$ServicioCorriendo = $false
$ServicioExiste = $false
try {
    $servicio = Get-Service -Name $NombreServicio -ErrorAction Stop
    $ServicioExiste = $true
    $ServicioCorriendo = ($servicio.Status -eq 'Running')

    $arranque = '(desconocido)'
    $cuenta = '(desconocida)'
    try {
        $wmi = Get-CimInstance Win32_Service -Filter "Name='$NombreServicio'" -ErrorAction Stop
        $arranque = [string](Prop $wmi 'StartMode' '(desconocido)')
        $cuenta = [string](Prop $wmi 'StartName' '(desconocida)')
    } catch { }

    if ($ServicioCorriendo) {
        Anotar 'OK' "El servicio está en marcha" "Inicio: $arranque · Cuenta: $cuenta"
    } else {
        Anotar 'BLOQUEA' "El servicio está $($servicio.Status)" "Inicio: $arranque · Cuenta: $cuenta" `
            ("Sin el servicio no hay API local y AVACOM OPS Master no puede ver ningún curso. " +
             "Arráncalo desde Servicios de Windows, o con: sc start $NombreServicio")
    }
    if ($arranque -notmatch 'Auto') {
        Anotar 'AVISO' "El servicio no arranca solo con Windows (inicio: $arranque)" `
            'El nodo debe atender a las tabletas desde que se enciende, sin esperar a que alguien abra la interfaz.' `
            "Ponlo en Automático: sc config $NombreServicio start= auto"
    }
} catch {
    Anotar 'BLOQUEA' "El servicio $NombreServicio no está registrado en este equipo" '' `
        ('Si AVACOM OPS Master se instaló con el asistente, el servicio debería existir. ' +
         'Reinstala el producto, o arranca el backend a mano para comprobar.')
}

# Procesos de Python del runtime instalado.
$ProcesosPython = @()
try {
    $ProcesosPython = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop)
} catch { }

$DelBackend = @($ProcesosPython | Where-Object { [string](Prop $_ 'CommandLine' '') -match 'avacom_ops_backend\.py' })
$Runserver = @($ProcesosPython | Where-Object { [string](Prop $_ 'CommandLine' '') -match 'manage\.py.*runserver' })

if (@($DelBackend).Count -gt 0) {
    Anotar 'OK' "El backend está ejecutándose ($(@($DelBackend).Count) proceso)" `
        (($DelBackend | ForEach-Object { "pid $(Prop $_ 'ProcessId' '?')" }) -join ', ')
} elseif ($ServicioCorriendo) {
    Anotar 'AVISO' 'El servicio dice estar en marcha pero no se ve su proceso de Python' `
        'Puede estar arrancando, o reiniciándose en bucle.' `
        'Mira el apartado de registros más abajo.'
}

if (@($Runserver).Count -gt 0) {
    $detalleRunserver = ($Runserver | ForEach-Object {
        "pid $(Prop $_ 'ProcessId' '?'): $(Recortar ([string](Prop $_ 'CommandLine' '')) 160)"
    }) -join "`n"

    if ($ServicioExiste) {
        # Con el servicio registrado, un runserver es un conflicto real: se
        # pelean por el puerto y por el mismo archivo SQLite.
        Anotar 'BLOQUEA' 'Hay un servidor de desarrollo (manage.py runserver) compitiendo con el servicio' `
            $detalleRunserver `
            ('Dos procesos sirviendo el mismo SQLite es la causa clásica de «database is locked», y si el ' +
             'runserver ocupó el puerto primero, el servicio no puede escuchar. Cierra esa ventana.')
    } else {
        # Sin servicio: es un equipo de desarrollo sirviendo a mano. Funciona,
        # pero no es como debe quedar un nodo de aula.
        Anotar 'AVISO' 'El backend se está sirviendo a mano con manage.py runserver' `
            $detalleRunserver `
            ('Es un servidor de desarrollo: un solo hilo por petición y sin arranque automático. En un nodo ' +
             'de aula debe correr como el servicio que instala el asistente.')
    }
}

# ============================================================ 4. El puerto
Seccion "4 · Puerto $Puerto"

$Escuchando = @()
$PudoConsultarPuerto = $false
try {
    $Escuchando = @(Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction Stop)
    $PudoConsultarPuerto = $true
} catch {
    # El cmdlet puede no existir o estar restringido. No se concluye nada de
    # su ausencia: la prueba que importa es si /health/ contesta (apartado 5).
    Anotar 'INFO' "No se pudo consultar quién escucha en el puerto $Puerto" $_.Exception.Message `
        'El apartado 5 comprueba lo que de verdad importa: si la API contesta.'
}

if ($PudoConsultarPuerto -and @($Escuchando).Count -eq 0) {
    Anotar 'BLOQUEA' "Nadie escucha en el puerto $Puerto" '' `
        "Sin esto, AVACOM OPS Master no tiene con quién hablar. Arranca el servicio $NombreServicio."
} elseif (@($Escuchando).Count -gt 0) {
    $detalle = foreach ($conexion in $Escuchando) {
        $duenoPid = [int](Prop $conexion 'OwningProcess' 0)
        $nombre = '(desconocido)'
        try { $nombre = (Get-Process -Id $duenoPid -ErrorAction Stop).ProcessName } catch { }
        "$(Prop $conexion 'LocalAddress' '?'):$Puerto  ← $nombre (pid $duenoPid)"
    }
    Anotar 'OK' "Algo escucha en el puerto $Puerto" ($detalle -join "`n")

    # 0.0.0.0 es lo que esperan las tabletas. Si sólo escucha en loopback,
    # OPS Master funciona pero el aula no.
    $enTodas = @($Escuchando | Where-Object { [string](Prop $_ 'LocalAddress' '') -eq '0.0.0.0' })
    if (@($enTodas).Count -eq 0) {
        Anotar 'AVISO' "El backend no escucha en 0.0.0.0" `
            'Las tabletas llegan por la IP de este equipo; en loopback sólo lo alcanza esta máquina.' `
            "Comprueba AVACOM_OPS_BACKEND_HOST=0.0.0.0 en $ArchivoConfig y reinicia el servicio."
    }
}

# ============================================================ 5. El backend
Seccion '5 · La API local responde'

$Salud = Invoke-Peticion "$Base/health/"
Guardar-Evidencia 'lms-health.json' $Salud.Cuerpo $Salud.Estado $Salud.Url
$BackendVivo = $false
$EstadoBiblioteca = $null

if ($Salud.Estado -eq 0) {
    Anotar 'BLOQUEA' 'La API local no contesta' `
        ("$($Salud.Url)`n$($Salud.Error)") `
        "Arranca el servicio $NombreServicio y vuelve a ejecutar este diagnóstico."
} elseif ($Salud.Estado -ne 200) {
    Anotar 'BLOQUEA' "La API local contestó $($Salud.Estado) en /health/" (Recortar $Salud.Cuerpo) `
        'Mira los registros del backend más abajo: casi siempre hay un error de Python detrás.'
} else {
    $componente = [string](Prop $Salud.Json 'componente' '')
    if ($componente -ne 'avacom-lms-backend') {
        Anotar 'BLOQUEA' "El puerto $Puerto lo atiende otro programa" `
            "Contestó 200 pero se identifica como '$componente', no como avacom-lms-backend." `
            'Cierra ese programa: AVACOM OPS Master necesita ese puerto para su API local.'
    } else {
        $BackendVivo = $true
        Anotar 'OK' "El backend contesta en $($Salud.Milisegundos) ms" `
            "administra_cursos=$(Prop $Salud.Json 'administra_cursos' '?') · dueño de los cursos: $(Prop $Salud.Json 'dueno_de_los_cursos' '?')"
        $EstadoBiblioteca = Prop $Salud.Json 'biblioteca' $null
    }
}

if ($BackendVivo) {
    # La frontera del artículo 14: administrar cursos debe estar cerrado.
    $frontera = Invoke-Peticion "$Base/api/courses/"
    if ($frontera.Estado -eq 409) {
        Anotar 'OK' 'La frontera de administración está cerrada (409)' `
            (Recortar $frontera.Cuerpo 160)
    } elseif ($frontera.Estado -eq 0) {
        Anotar 'AVISO' 'No se pudo comprobar la frontera de administración' $frontera.Error
    } else {
        Anotar 'AVISO' "La frontera de administración contestó $($frontera.Estado), se esperaba 409" `
            (Recortar $frontera.Cuerpo 160) `
            'Los cursos son de AVACOM Biblioteca; el backend no debería aceptar administrarlos.'
    }
}

# =================================================== 6. La nota de enlace
Seccion '6 · La nota de enlace de AVACOM Contenido (link.json)'

# AVACOM Contenido publica en link.json el puerto de su API (apiPort), el de su
# servidor de medios (mediaPort) y el token con el que se le habla
# (cabecera X-Avacom-Token). Cambian en cada arranque de la biblioteca.
# El backend la relee en cada peticion y este diagnostico tambien.
$PuertoBiblioteca = 0
$FichaBiblioteca = ''   # el token: la credencial de la biblioteca (se oculta en todo lo que sale del equipo)
$ProcesoNota = 0

if (-not (Test-Path $RutaEnlace)) {
    Anotar 'BLOQUEA' 'No hay nota de enlace: AVACOM Contenido no está publicando su API' `
        "Se esperaba en $RutaEnlace" `
        'Abre AVACOM Contenido: al arrancar escribe la nota con sus puertos y su token.'
} else {
    try {
        $archivo = Get-Item $RutaEnlace
        $edad = (Get-Date) - $archivo.LastWriteTime
        $nota = Get-Content $RutaEnlace -Raw -Encoding UTF8 | ConvertFrom-Json

        # El backend acepta varios nombres para cada campo; aquí se hace lo mismo.
        foreach ($nombre in @('apiPort', 'port', 'puerto')) {
            $v = Prop $nota $nombre 0
            if ($v) { $PuertoBiblioteca = [int]$v; break }
        }
        $puertoMedios = 0
        $v = Prop $nota 'mediaPort' 0
        if ($v) { $puertoMedios = [int]$v }
        foreach ($nombre in @('token')) {
            $v = Prop $nota $nombre ''
            if ($v) { $FichaBiblioteca = [string]$v; break }
        }
        foreach ($nombre in @('pid', 'processId', 'proceso')) {
            $v = Prop $nota $nombre 0
            if ($v) { $ProcesoNota = [int]$v; break }
        }
        $contrato = 0
        foreach ($nombre in @('contract', 'contrato')) {
            $v = Prop $nota $nombre 0
            if ($v) { $contrato = [int]$v; break }
        }

        $FichaParaOcultar = $FichaBiblioteca
        Guardar-Evidencia 'contenido-link.json' (Get-Content $RutaEnlace -Raw -Encoding UTF8) 0 $RutaEnlace

        Anotar 'OK' 'La nota de enlace existe' `
            ("Escrita hace $([int]$edad.TotalMinutes) min · contrato $(if ($contrato) { $contrato } else { '(no declarado)' }) · " +
             "apiPort $PuertoBiblioteca · mediaPort $puertoMedios · proceso $ProcesoNota · token " +
             $(if ($FichaBiblioteca) { "presente ($($FichaBiblioteca.Length) caracteres)" } else { 'AUSENTE' }))

        if (-not $PuertoBiblioteca -or -not $FichaBiblioteca) {
            Anotar 'BLOQUEA' 'La nota de enlace está incompleta' `
                'Faltan apiPort o token, y el backend la rechaza entera.' `
                'Cierra AVACOM Contenido por completo y vuelve a abrirlo.'
        }
        if ($contrato -gt 2) {
            Anotar 'BLOQUEA' "AVACOM Contenido habla el contrato $contrato y este LMS sólo entiende hasta el 2" '' `
                'Hay que actualizar AVACOM OPS Master a una versión que entienda ese contrato.'
        }

        # ¿La nota es de esta sesión de la biblioteca, o quedó de una anterior?
        if ($ProcesoNota) {
            $vivo = $null
            try { $vivo = Get-Process -Id $ProcesoNota -ErrorAction Stop } catch { }
            if ($vivo) {
                Anotar 'OK' "El proceso de la nota sigue vivo: $($vivo.ProcessName) (pid $ProcesoNota)"
            } else {
                Anotar 'BLOQUEA' "El proceso $ProcesoNota de la nota de enlace ya no existe" `
                    'La nota quedó de una sesión anterior de AVACOM Contenido: apunta a un puerto muerto.' `
                    'Abre AVACOM Contenido: al arrancar reescribe la nota con su puerto real.'
            }
        }

        # Que el servicio (que corre como SYSTEM) pueda leer el archivo.
        try {
            $acl = Get-Acl $RutaEnlace
            $puedeSistema = @($acl.Access | Where-Object {
                $_.IdentityReference -match 'SYSTEM|Administradores|Administrators|Todos|Everyone' -and
                $_.AccessControlType -eq 'Allow'
            })
            if (@($puedeSistema).Count -eq 0) {
                Anotar 'AVISO' 'La nota de enlace podría no ser legible por el servicio' `
                    "El servicio corre como SYSTEM y en los permisos de $RutaEnlace no aparece." `
                    'Si el backend dice que la biblioteca no está mientras este script sí la alcanza, esta es la causa.'
            }
        } catch { }
    } catch {
        Anotar 'BLOQUEA' 'La nota de enlace no se pudo leer' $_.Exception.Message `
            'Cierra AVACOM Contenido y vuelve a abrirlo para que la reescriba.'
    }
}

$appContenido = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^Avacom\.Contenido|^AVACOM Contenido|^Avacom\.Content' })
if (@($appContenido).Count -gt 0) {
    Anotar 'INFO' "AVACOM Contenido está abierto ($(@($appContenido).Count) proceso)" `
        (($appContenido | ForEach-Object { "$($_.ProcessName) pid $($_.Id)" }) -join ', ')
} else {
    Anotar 'AVISO' 'No se ve AVACOM Contenido abierto en este equipo' '' `
        ('Los cursos son suyos: sin él, AVACOM OPS Master funciona pero no tiene nada que mostrar. ' +
         'Si su API corre como servicio o con otro nombre de proceso, ignora este aviso.')
}

# ============================= 7. Hablar con AVACOM Contenido por nuestra cuenta
Seccion '7 · Contacto directo con AVACOM Contenido (API v2)'

$BibliotecaAlcanzable = $false
# -1 significa «no se pudo saber», que no es lo mismo que cero.
$CursosEnBiblioteca = -1
if (-not $PuertoBiblioteca -or -not $FichaBiblioteca) {
    Anotar 'INFO' 'No se puede probar el contacto directo sin apiPort y token' `
        'Resuelve primero lo del apartado anterior.'
} else {
    $directo = Invoke-Peticion "http://127.0.0.1:$PuertoBiblioteca/v2/health" `
        -Cabeceras @{ 'X-Avacom-Token' = $FichaBiblioteca } -SegundosDeEspera 6

    Guardar-Evidencia 'contenido-health.json' $directo.Cuerpo $directo.Estado $directo.Url

    if ($directo.Estado -eq 200) {
        $BibliotecaAlcanzable = $true
        $indice = [string](Prop $directo.Json 'index' '?')
        Anotar 'OK' "AVACOM Contenido contesta en 127.0.0.1:$PuertoBiblioteca ($($directo.Milisegundos) ms)" `
            ("contrato $(Prop $directo.Json 'contract' '?') · esquema $(Prop $directo.Json 'schema' '?') · " +
             "índice $indice · cursos instalados $(Prop $directo.Json 'installedCourses' '?')")

        if ($indice -eq 'rebuilding') {
            Anotar 'AVISO' 'El índice de AVACOM Contenido se está reconstruyendo' '' `
                'Espera unos minutos: mientras se reconstruye, la lista de cursos puede salir incompleta.'
        }

        <#
            La pregunta del aula es «¿por qué no salen los cursos?». Aquí se le
            pide la lista a la biblioteca directamente, con su mismo token. Si
            ella ya devuelve cero, no hay nada que el backend pueda entregar y
            buscar el fallo en el LMS es perder el tiempo.
        #>
        $directoCursos = Invoke-Peticion "http://127.0.0.1:$PuertoBiblioteca/v2/courses?page=1&pageSize=100" `
            -Cabeceras @{ 'X-Avacom-Token' = $FichaBiblioteca } -SegundosDeEspera 10
        Guardar-Evidencia 'contenido-cursos.json' $directoCursos.Cuerpo $directoCursos.Estado $directoCursos.Url

        if ($directoCursos.Estado -eq 200) {
            $lista = @(Prop $directoCursos.Json 'items' @())
            $total = [int](Prop $directoCursos.Json 'total' @($lista).Count)
            $CursosEnBiblioteca = $total

            if ($total -gt 0) {
                Anotar 'OK' "AVACOM Contenido ofrece $total curso(s)" `
                    (($lista | Select-Object -First 8 | ForEach-Object {
                        "$(Prop $_ 'id' (Prop $_ 'courseId' '?'))  ·  $(Prop $_ 'title' (Prop $_ 'titulo' '?'))"
                    }) -join "`n")
            } else {
                Anotar 'BLOQUEA' 'AVACOM Contenido no ofrece ningún curso' `
                    ('Contesta correctamente, pero su lista de cursos está vacía. El problema no es la ' +
                     'comunicación con el LMS: no hay nada que entregar.') `
                    'Abre AVACOM Contenido y comprueba que haya un paquete de curso instalado.'
            }
        } else {
            Anotar 'AVISO' "AVACOM Contenido contestó $($directoCursos.Estado) al pedirle sus cursos" `
                (Recortar $directoCursos.Cuerpo 300)
        }
    } elseif ($directo.Estado -eq 401 -or $directo.Estado -eq 403) {
        Anotar 'BLOQUEA' "AVACOM Contenido rechazó el token de la nota de enlace ($($directo.Estado))" `
            (Recortar $directo.Cuerpo 200) `
            ('La nota es vieja: la biblioteca cambia su token al reiniciarse. Ábrela de nuevo para que ' +
             'reescriba la nota.')
    } elseif ($directo.Estado -eq 0) {
        Anotar 'BLOQUEA' "Nada contesta en 127.0.0.1:$PuertoBiblioteca" $directo.Error `
            ('El puerto de la nota está muerto. Cierra AVACOM Contenido por completo y vuelve a abrirlo.')
    } else {
        Anotar 'AVISO' "AVACOM Contenido contestó $($directo.Estado) en /v2/health" (Recortar $directo.Cuerpo 200)
    }
}

# ======================== 8. Lo que dice el backend de sí mismo
Seccion '8 · Lo que ve el backend'

if (-not $BackendVivo) {
    Anotar 'INFO' 'Sin API local no hay nada que comparar' 'Resuelve primero el apartado 5.'
} else {
    # Modulo de acceso: sin organizacion el login responde 409 no_instalado.
    $acceso = Prop $Salud.Json 'acceso' $null
    if ($null -eq $acceso) {
        Anotar 'AVISO' 'El backend no informó del estado del módulo de acceso en /health/'
    } else {
        if ([bool](Prop $acceso 'instalado' $false)) {
            Anotar 'OK' 'El nodo tiene organización y administrador'
        } else {
            Anotar 'AVISO' 'El nodo aún no tiene organización ni administrador (el login responde 409 no_instalado)' '' `
                'Créalos una sola vez desde AVACOM OPS Master la primera vez que se abra, o con manage.py acceso_instalar.'
        }
        $derivadas = Prop $acceso 'claves_derivadas' $null
        if ($derivadas -eq $true) {
            Anotar 'INFO' 'Las claves de acceso son las derivadas de AVACOM_LMS_SECRET' `
                'Es lo normal en un nodo que viene de la versión 2.0.0 y ya tiene personas guardadas.' `
                'No las cambies mientras haya personas guardadas: dejarían de poder descifrarse.'
        } elseif ($derivadas -eq $false) {
            Anotar 'OK' 'Las claves de acceso son propias de este nodo (backend.env)'
        }
    }

    # /health/ describe la biblioteca con el contrato anterior (enlace.json);
    # el aula lee la API v2. Se muestra como referencia y no como veredicto.
    if ($null -ne $EstadoBiblioteca) {
        $motivo = [string](Prop $EstadoBiblioteca 'motivo' '')
        if (-not [bool](Prop $EstadoBiblioteca 'disponible' $false) -and $motivo) {
            Anotar 'INFO' '/health/ describe la biblioteca con el contrato anterior y la ve no disponible' $motivo `
                'No es un fallo si el apartado 7 alcanzó a AVACOM Contenido: el aula usa la API v2 (link.json).'
        }
    }

    # El canal en tiempo real: el mismo puerto, otro protocolo.
    try {
        Add-Type -AssemblyName System.Net.WebSockets -ErrorAction SilentlyContinue
        $ws = New-Object System.Net.WebSockets.ClientWebSocket
        $limite = New-Object System.Threading.CancellationTokenSource (8000)
        $ws.ConnectAsync([Uri]"ws://127.0.0.1:$Puerto/ws/aula/sesiones/diagnostico/?rol=docente", $limite.Token).GetAwaiter().GetResult()
        Anotar 'OK' 'El canal en tiempo real (WebSocket) acepta conexiones' "ws://127.0.0.1:$Puerto/ws/aula/sesiones/…"
        try { $ws.Abort() } catch { }
    } catch {
        Anotar 'BLOQUEA' 'El canal en tiempo real (WebSocket) no acepta conexiones' $_.Exception.Message `
            ('El backend debe correr con Daphne (avacom_lms.asgi). Si corre con otro servidor, o con un manage.py ' +
             'runserver antiguo, las tabletas no reciben actividad en vivo. Reinstala AVACOM OPS Master.')
    }
}

# ===================================== 9. Extremo a extremo: los cursos del aula
Seccion '9 · Los cursos que entrega el aula'

$CursosEnLms = -1
if (-not $BackendVivo) {
    Anotar 'INFO' 'Sin API local no se pueden probar los cursos'
} else {
    # Lo que usa la pantalla del profesor: /api/aula/cursos/ (fuente: la biblioteca v2).
    $cursos = Invoke-Peticion "$Base/api/aula/cursos/"
    Guardar-Evidencia 'lms-cursos.json' $cursos.Cuerpo $cursos.Estado $cursos.Url

    switch ($cursos.Estado) {
        200 {
            $lista = @()
            if ($cursos.Json -is [System.Array]) { $lista = @($cursos.Json) }
            else {
                foreach ($nombre in @('cursos', 'items', 'asignaturas')) {
                    $candidata = @(Prop $cursos.Json $nombre @())
                    if (@($candidata).Count -gt 0) { $lista = $candidata; break }
                }
            }
            $CursosEnLms = @($lista).Count
            Anotar 'OK' "El aula responde con $CursosEnLms elemento(s) de curso" `
                (Recortar $cursos.Cuerpo 300)

            if ($CursosEnBiblioteca -gt 0 -and $CursosEnLms -eq 0) {
                Anotar 'BLOQUEA' "AVACOM Contenido ofrece $CursosEnBiblioteca curso(s) y el aula entrega 0" `
                    'La comunicación funciona y el contenido existe: los cursos se pierden dentro del backend.' `
                    ('Envía el paquete de diagnóstico: lleva las dos respuestas crudas, que es lo que hace falta ' +
                     'para localizar el fallo.')
            } elseif ($CursosEnBiblioteca -gt 0 -and $CursosEnLms -gt 0) {
                Anotar 'OK' 'La cadena completa funciona: la biblioteca ofrece cursos y el aula los entrega' `
                    'Si la pantalla de AVACOM OPS Master sigue vacía, el fallo está en la interfaz, no en la comunicación.'
            }
        }
        503 {
            Anotar 'BLOQUEA' 'Los cursos no se pueden listar: la biblioteca no está disponible (503)' `
                (Recortar $cursos.Cuerpo 300) `
                'Es el mismo diagnóstico de los apartados 6 y 7.'
        }
        502 {
            Anotar 'BLOQUEA' 'AVACOM Contenido contestó con error al pedirle los cursos (502)' `
                (Recortar $cursos.Cuerpo 300) `
                'El fallo está dentro de AVACOM Contenido. Mira sus propios registros.'
        }
        0 {
            Anotar 'BLOQUEA' 'La petición de cursos no llegó a completarse' $cursos.Error
        }
        default {
            Anotar 'AVISO' "La lista de cursos del aula contestó $($cursos.Estado)" (Recortar $cursos.Cuerpo 300)
        }
    }
}

# ============================= 10. Errores de Python en los registros
Seccion '10 · Errores de Python en los registros del backend'

<#
    Clasificación de los errores que se ven de verdad en este backend.

    `Hilo = $true` marca los que ocurren dentro de una petición de Daphne. Son los
    peores de diagnosticar sin esto: revientan una petición suelta, el cliente
    ve un 500 o un cuelgue, el servicio sigue «en marcha» y en la pantalla del
    profesor no queda ninguna pista.
#>
$Clasificacion = @(
    @{ Patron = 'SQLite objects created in a thread can only be used in that same thread'
       Clase  = 'Hilo · SQLite usado desde otro hilo'; Hilo = $true
       Causa  = 'Una conexión SQLite se creó en una petición de Daphne y se usó en otro.'
       Accion = 'Es un fallo del backend, no de la instalación. Repórtalo con este registro.' }

    @{ Patron = 'database is locked'
       Clase  = 'Hilo · SQLite bloqueado por concurrencia'; Hilo = $true
       Causa  = 'Varios hilos (o dos procesos) escriben el expediente a la vez y SQLite agota su espera.'
       Accion = 'Comprueba que no haya un manage.py runserver abierto sobre la misma base. Si persiste, repórtalo con este registro.' }

    @{ Patron = 'SynchronousOnlyOperation'
       Clase  = 'Hilo · ORM llamado desde contexto asíncrono'; Hilo = $true
       Causa  = 'Se tocó la base de datos desde código asíncrono.'
       Accion = 'Fallo del backend. Repórtalo con este registro.' }

    @{ Patron = 'Exception inside application|Exception while serving'
       Clase  = 'Hilo · excepción sin manejar en una petición de Daphne'; Hilo = $true
       Causa  = 'Daphne atrapó un error que subió hasta el servidor: esa petición murió.'
       Accion = 'La línea siguiente del registro dice la excepción real. Mírala y repórtala.' }

    @{ Patron = 'There is no current event loop in thread'
       Clase  = 'Hilo · sin bucle de eventos'; Hilo = $true
       Causa  = 'Código asíncrono ejecutado en una petición de Daphne que no tiene bucle propio.'
       Accion = 'Fallo del backend. Repórtalo con este registro.' }

    @{ Patron = 'cannot schedule new futures after (interpreter )?shutdown'
       Clase  = 'Hilo · trabajo lanzado durante el apagado'; Hilo = $true
       Causa  = 'Llegó una petición mientras el servicio se estaba deteniendo.'
       Accion = 'Inofensivo si sólo aparece al parar o reiniciar el servicio.' }

    @{ Patron = 'RuntimeError:.*(lock|thread)'
       Clase  = 'Hilo · error de sincronización'; Hilo = $true
       Causa  = 'Problema con un candado o un hilo dentro del backend.'
       Accion = 'Fallo del backend. Repórtalo con este registro.' }

    @{ Patron = 'ModuleNotFoundError|ImportError'
       Clase  = 'Runtime incompleto'; Hilo = $false
       Causa  = 'Falta un módulo de Python en el runtime instalado.'
       Accion = 'La instalación quedó a medias. Reinstala AVACOM OPS Master.' }

    @{ Patron = 'PermissionError|Errno 13'
       Clase  = 'Permisos'; Hilo = $false
       Causa  = 'El backend no puede leer o escribir un archivo: base de datos, registro o nota de enlace.'
       Accion = 'Revisa los permisos de %ProgramData%\AVACOM\OPS Master. La cuenta del servicio debe poder escribir en Data y Logs.' }

    @{ Patron = 'unable to open database file'
       Clase  = 'Base de datos inaccesible'; Hilo = $false
       Causa  = 'La ruta de AVACOM_LMS_DB no existe o no es escribible por la cuenta del servicio.'
       Accion = 'Comprueba AVACOM_LMS_DB en la configuración del nodo y que exista la carpeta Data.' }

    @{ Patron = 'socket\.timeout|TimeoutError|timed out'
       Clase  = 'Tiempo de espera agotado hacia la Biblioteca'; Hilo = $false
       Causa  = 'La Biblioteca no contestó dentro del plazo (3 s por defecto).'
       Accion = 'Si se repite, sube AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG. Si es constante, la Biblioteca está atascada: reiníciala.' }

    @{ Patron = 'URLError|ConnectionRefusedError|Errno 10061'
       Clase  = 'Conexión rechazada por la Biblioteca'; Hilo = $false
       Causa  = 'El puerto de la nota de enlace no acepta conexiones: nota vieja o Biblioteca cerrada.'
       Accion = 'Abre AVACOM Biblioteca y entra en la pestaña «Contenido AVACOM» para que reescriba la nota.' }

    @{ Patron = 'JSONDecodeError'
       Clase  = 'Respuesta ilegible'; Hilo = $false
       Causa  = 'La nota de enlace o una respuesta de la Biblioteca no es JSON válido.'
       Accion = 'Cierra AVACOM Biblioteca y vuelve a abrirla para que reescriba la nota.' }

    @{ Patron = 'ConnectionResetError|BrokenPipeError|Errno 10054'
       Clase  = 'El cliente cortó la conexión'; Hilo = $false
       Causa  = 'Una tableta o la interfaz se desconectó a media descarga.'
       Accion = 'Normalmente inofensivo. Sólo preocupa si es constante: apunta a una red del aula inestable.' }

    @{ Patron = 'UnicodeDecodeError|UnicodeEncodeError'
       Clase  = 'Codificación de texto'; Hilo = $false
       Causa  = 'Un texto con acentos se leyó con la codificación equivocada.'
       Accion = 'Fallo del backend. Repórtalo con este registro.' }

    @{ Patron = 'MemoryError'
       Clase  = 'Memoria agotada'; Hilo = $false
       Causa  = 'El equipo se quedó sin memoria sirviendo material.'
       Accion = 'Cierra programas en este equipo. Si se repite, hace falta más memoria en el nodo.' }
)

$ArchivosDeLog = @()
$CarpetaLogs = if ($CarpetaDeLogs) { $CarpetaDeLogs } else { Join-Path $RaizDatos 'Logs' }
if ($CarpetaDeLogs) { Escribir "            Analizando registros traidos de: $CarpetaDeLogs" 'DarkGray' }
if (Test-Path $CarpetaLogs) {
    $ArchivosDeLog = @(Get-ChildItem $CarpetaLogs -File -Filter '*.log*' -ErrorAction SilentlyContinue)
}

if (@($ArchivosDeLog).Count -eq 0) {
    Anotar 'AVISO' 'No se encontraron registros del backend' "Se buscaron en $CarpetaLogs" `
        'Sin registros no se puede ver si hubo errores de Python. Puede que el servicio nunca haya arrancado.'
} else {
    $desde = (Get-Date).AddHours(-$HorasDeLog)
    $Tracebacks = New-Object System.Collections.Generic.List[object]
    $Reinicios = 0

    # Desde MOD-019 el backend escribe JSON Lines (backend-errores.log, backend-app.log...): cada error
    # es UNA línea con la traza dentro del campo «traza». Esos errores se leen primero y por su campo, y
    # el mismo error que Daphne escribió también como texto en servicio.log no se cuenta dos veces.
    $FirmasJson = New-Object 'System.Collections.Generic.HashSet[string]'
    $ArchivosDeLog = @($ArchivosDeLog | Sort-Object { if ($_.Name -like 'backend-*') { 0 } else { 1 } }, Name)

    foreach ($archivo in $ArchivosDeLog) {
        $lineas = @()
        try { $lineas = @(Get-Content $archivo.FullName -Encoding UTF8 -ErrorAction Stop) } catch { continue }
        $esJson = $archivo.Name -like 'backend-*'

        for ($i = 0; $i -lt @($lineas).Count; $i++) {
            $cruda = $lineas[$i]
            if ($cruda -match 'El backend termino con codigo') { $Reinicios++ }

            if ($esJson) {
                if (-not $cruda.StartsWith('{') -or $cruda -notmatch '"traza"\s*:\s*"') { continue }
                try {
                    $registroJson = $cruda | ConvertFrom-Json
                    $traza = [string](Prop $registroJson 'traza' '')
                    if (-not $traza.Trim()) { continue }
                    $momentoJson = [datetimeoffset]::Parse([string](Prop $registroJson 'ts' '')).LocalDateTime
                    if ($momentoJson -lt $desde) { continue }
                    $bloqueJson = @($traza -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 40)
                    $ultimaJson = $bloqueJson[$bloqueJson.Count - 1]
                    [void]$FirmasJson.Add("$ultimaJson|$($momentoJson.ToString('yyyyMMddHHmm'))")
                    $Tracebacks.Add([pscustomobject]@{
                        Archivo   = $archivo.Name
                        Fecha     = $momentoJson
                        Excepcion = $ultimaJson
                        Texto     = ($bloqueJson -join "`n")
                    })
                } catch { }
                continue
            }

            if ($cruda -notmatch 'Traceback \(most recent call last\)') { continue }

            # La línea del registro es «fecha  [backend] <texto de Python>».
            # Se quita ese prefijo para leer el traceback como lo escribió
            # Python, con su sangría intacta.
            $fecha = $null
            if ($cruda -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') {
                try { $fecha = [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm:ss', $null) } catch { }
            }
            if ($fecha -and $fecha -lt $desde) { continue }

            $bloque = New-Object System.Collections.Generic.List[string]
            for ($j = $i; $j -lt @($lineas).Count -and $bloque.Count -lt 40; $j++) {
                $texto = $lineas[$j] -replace '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}( [+\-]\d{2}:\d{2})?\s+(\[backend\] )?', ''
                $bloque.Add($texto)
                # El traceback termina en la línea de la excepción: la primera
                # sin sangrar después de la cabecera.
                if ($j -gt $i -and $texto -match '^\S' -and $texto -notmatch '^Traceback') { break }
            }

            # El mismo error ya contado desde el registro JSON del backend (misma excepción, mismo minuto).
            $repetido = $false
            if ($fecha) {
                foreach ($desfase in -1, 0, 1) {
                    if ($FirmasJson.Contains("$($bloque[$bloque.Count - 1])|$($fecha.AddMinutes($desfase).ToString('yyyyMMddHHmm'))")) { $repetido = $true; break }
                }
            }
            if (-not $repetido) {
                $Tracebacks.Add([pscustomobject]@{
                    Archivo   = $archivo.Name
                    Fecha     = $fecha
                    Excepcion = $bloque[$bloque.Count - 1]
                    Texto     = ($bloque -join "`n")
                })
            }
            $i = $j
        }
    }

    Escribir "            Revisados $(@($ArchivosDeLog).Count) archivo(s) de registro, últimas $HorasDeLog h" 'DarkGray'

    if ($Reinicios -gt 3) {
        Anotar 'BLOQUEA' "El backend se reinició $Reinicios veces" `
            'El servicio lo levanta con espera creciente, pero algo lo está tumbando.' `
            'La causa suele estar en el primer error de Python de la lista de abajo.'
    } elseif ($Reinicios -gt 0) {
        Anotar 'INFO' ("El backend se reinició " +
            $(if ($Reinicios -eq 1) { '1 vez' } else { "$Reinicios veces" }) + ' en el periodo revisado')
    }

    if ($Tracebacks.Count -eq 0) {
        Anotar 'OK' 'No hay ningún error de Python en los registros del periodo revisado'
    } else {
        # Se agrupa por la línea de la excepción: es la firma natural del fallo.
        $grupos = $Tracebacks | Group-Object -Property Excepcion | Sort-Object Count -Descending
        Anotar 'AVISO' "Hay $($Tracebacks.Count) error(es) de Python, en $(@($grupos).Count) forma(s) distinta(s)"

        $enHilos = 0
        foreach ($grupo in $grupos) {
            $muestra = $grupo.Group[0]
            $ultimo = ($grupo.Group | Sort-Object Fecha -Descending | Select-Object -First 1)

            $clase = 'Sin clasificar'
            $causa = 'No coincide con ningún patrón conocido de este backend.'
            $accion = 'Guarda este informe y repórtalo junto al registro completo.'
            $esDeHilo = $false
            foreach ($regla in $Clasificacion) {
                if ($muestra.Texto -match $regla.Patron) {
                    $clase = $regla.Clase
                    $causa = $regla.Causa
                    $accion = $regla.Accion
                    $esDeHilo = $regla.Hilo
                    break
                }
            }
            if ($esDeHilo) { $enHilos += $grupo.Count }

            $cuando = '(sin fecha)'
            if ($ultimo.Fecha) { $cuando = $ultimo.Fecha.ToString('yyyy-MM-dd HH:mm:ss') }

            Escribir ''
            $repeticiones = if ($grupo.Count -eq 1) { '1 vez' } else { "$($grupo.Count) veces" }
            Escribir "            ── $clase  ($repeticiones, la última $cuando, en $($ultimo.Archivo))" 'Yellow'
            Escribir "               $(Recortar $muestra.Excepcion 220)" 'White'
            Escribir "               Qué es:  $causa" 'DarkGray'
            Escribir "               Qué hacer: $accion" 'DarkGray'
        }

        if ($enHilos -gt 0) {
            Anotar 'BLOQUEA' "$enHilos de esos errores ocurrieron dentro de peticiones de Daphne" `
                ('Son los que no se ven: revientan una petición suelta, la interfaz muestra un cuelgue o un 500, ' +
                 'y el servicio sigue apareciendo «en marcha».') `
                'Revisa la acción indicada en cada grupo marcado como «Hilo ·» aquí arriba.'
        }
    }
}

# ================================================= 11. La interfaz y el aula
Seccion '11 · La interfaz y las tabletas'

try {
    $ops = @(Get-Process -Name 'Avacom.Lms.Ops' -ErrorAction Stop)
    $rutas = @($ops | ForEach-Object { try { $_.Path } catch { '(ruta no legible)' } } | Sort-Object -Unique)
    Anotar 'INFO' "AVACOM OPS Master está abierto ($(@($ops).Count) proceso)" ($rutas -join "`n")
    if ($RaizInstalacion -and -not (@($rutas | Where-Object { $_ -like "$RaizInstalacion*" }).Count)) {
        Anotar 'AVISO' 'La interfaz abierta no es la instalada' `
            "Instalada en $RaizInstalacion, pero se está ejecutando desde otra ruta." `
            'Una compilación de desarrollo puede apuntar a otra dirección de API. Cierra esa y abre la del icono del escritorio.'
    }
} catch {
    Anotar 'INFO' 'AVACOM OPS Master no está abierto ahora mismo' `
        'No hace falta para este diagnóstico: la API vive en el servicio, no en la interfaz.'
}

try {
    $regla = @(Get-NetFirewallRule -DisplayName 'AVACOM OPS Master Backend' -ErrorAction Stop)
    $activa = @($regla | Where-Object { $_.Enabled -eq 'True' })
    if (@($activa).Count -gt 0) {
        Anotar 'OK' 'La regla de firewall para las tabletas existe y está activa' `
            (($regla | ForEach-Object { "perfiles: $($_.Profile) · dirección: $($_.Direction) · acción: $($_.Action)" }) -join "`n")
    } else {
        Anotar 'AVISO' 'La regla de firewall existe pero está desactivada' '' `
            'Las tabletas no podrán alcanzar este equipo. Actívala en Windows Defender Firewall.'
    }
} catch {
    Anotar 'AVISO' 'No se encontró la regla de firewall «AVACOM OPS Master Backend»' `
        'Sin ella, este equipo funciona pero las tabletas no lo alcanzan por la red del aula.' `
        'La crea el instalador. Si el nodo sólo se usa desde su propia pantalla, no importa.'
}

$ips = @()
try {
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -ne 'WellKnown' } |
        Select-Object -ExpandProperty IPAddress)
} catch { }
if (@($ips).Count -gt 0) {
    Anotar 'INFO' 'Dirección de este equipo para las tabletas' `
        (($ips | ForEach-Object { "http://${_}:$Puerto" }) -join "`n")
}

# ==================================================================== Resumen
Seccion 'Resumen'

$Bloqueos = @($Hallazgos | Where-Object { $_.Gravedad -eq 'BLOQUEA' })
$Avisos = @($Hallazgos | Where-Object { $_.Gravedad -eq 'AVISO' })

if (@($Bloqueos).Count -eq 0 -and @($Avisos).Count -eq 0) {
    Escribir ''
    Escribir '  La comunicación entre AVACOM OPS Master y AVACOM Biblioteca funciona.' 'Green'
    $CodigoSalida = 0
} elseif (@($Bloqueos).Count -eq 0) {
    Escribir ''
    Escribir "  La comunicación funciona, con $(@($Avisos).Count) aviso(s) que conviene mirar:" 'Yellow'
    $numero = 0
    foreach ($aviso in $Avisos) {
        $numero++
        Escribir ''
        Escribir "  $numero. $($aviso.Titulo)" 'Yellow'
        if ($aviso.Accion) { Escribir "     → $($aviso.Accion)" 'Gray' }
    }
    $CodigoSalida = 2
} else {
    Escribir ''
    Escribir "  Hay $(@($Bloqueos).Count) problema(s) que impiden la comunicación:" 'Red'
    $numero = 0
    foreach ($bloqueo in $Bloqueos) {
        $numero++
        Escribir ''
        Escribir "  $numero. $($bloqueo.Titulo)" 'Red'
        if ($bloqueo.Detalle) {
            foreach ($linea in ($bloqueo.Detalle -split "`n")) { Escribir "     $linea" 'DarkGray' }
        }
        if ($bloqueo.Accion) { Escribir "     → $($bloqueo.Accion)" 'White' }
    }
    if (@($Avisos).Count -gt 0) {
        Escribir ''
        Escribir "  Y $(@($Avisos).Count) aviso(s) secundario(s):" 'Yellow'
        foreach ($aviso in $Avisos) { Escribir "    · $($aviso.Titulo)" 'DarkYellow' }
    }
    $CodigoSalida = 1
}

# ==================================================================== Informe
if (-not $Informe) {
    $escritorio = Join-Path $env:USERPROFILE 'Desktop'
    $carpeta = if (Test-Path $escritorio) { $escritorio } else { [IO.Path]::GetTempPath() }
    $Informe = Join-Path $carpeta ("AVACOM-diagnostico-{0}.txt" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
}

$TextoInforme = @($Renglones | ForEach-Object { Ocultar $_ })

try {
    $TextoInforme | Set-Content -Path $Informe -Encoding UTF8
    Write-Host ''
    Write-Host "  Informe guardado en: $Informe" -ForegroundColor Cyan
} catch {
    Write-Host "  No se pudo guardar el informe: $($_.Exception.Message)" -ForegroundColor Yellow
}

<#
    Paquete de evidencias.

    El informe dice qué pasa; el paquete permite comprobarlo desde fuera. Lleva
    las respuestas crudas de la Biblioteca y del backend —las dos listas de
    cursos, una al lado de la otra— y los registros del servicio.

    La ficha se sustituye antes de escribir nada: es la credencial con la que el
    backend habla con la Biblioteca y no puede salir del equipo.
#>
$RutaPaquete = ''
if ($Paquete) {
    try {
        $carpeta = [IO.Path]::ChangeExtension($Informe, $null).TrimEnd('.')
        if (Test-Path $carpeta) { Remove-Item -Recurse -Force $carpeta }
        New-Item -ItemType Directory -Force $carpeta | Out-Null

        $TextoInforme | Set-Content -Path (Join-Path $carpeta 'informe.txt') -Encoding UTF8

        $carpetaRespuestas = Join-Path $carpeta 'respuestas'
        New-Item -ItemType Directory -Force $carpetaRespuestas | Out-Null
        foreach ($evidencia in $Evidencias) {
            Ocultar $evidencia.Contenido |
                Set-Content -Path (Join-Path $carpetaRespuestas $evidencia.Nombre) -Encoding UTF8
        }

        # Los registros del backend: ahí están los errores de Python completos.
        if (Test-Path $CarpetaLogs) {
            $carpetaLogsPaquete = Join-Path $carpeta 'logs'
            New-Item -ItemType Directory -Force $carpetaLogsPaquete | Out-Null
            Get-ChildItem $CarpetaLogs -File -ErrorAction SilentlyContinue |
                Copy-Item -Destination $carpetaLogsPaquete -ErrorAction SilentlyContinue
        }

        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
        $RutaPaquete = "$carpeta.zip"
        if (Test-Path $RutaPaquete) { Remove-Item -Force $RutaPaquete }
        [System.IO.Compression.ZipFile]::CreateFromDirectory($carpeta, $RutaPaquete)
        Remove-Item -Recurse -Force $carpeta

        Write-Host ''
        Write-Host '  ----------------------------------------------------------------' -ForegroundColor Cyan
        Write-Host "  Paquete de diagnóstico: $RutaPaquete" -ForegroundColor Cyan
        Write-Host '  Envía ESE archivo. Lleva el informe, las respuestas de la' -ForegroundColor Gray
        Write-Host '  Biblioteca y del backend, y los registros del servicio.' -ForegroundColor Gray
        Write-Host '  La credencial de la Biblioteca no va dentro.' -ForegroundColor Gray
        Write-Host '  ----------------------------------------------------------------' -ForegroundColor Cyan
    } catch {
        Write-Host "  No se pudo crear el paquete: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

if ($Abrir) {
    try {
        Start-Process notepad.exe $Informe | Out-Null
        # Abre también la carpeta, para poder coger el .zip con un toque.
        if ($RutaPaquete) { Start-Process explorer.exe "/select,`"$RutaPaquete`"" | Out-Null }
    } catch { }
}

exit $CodigoSalida
