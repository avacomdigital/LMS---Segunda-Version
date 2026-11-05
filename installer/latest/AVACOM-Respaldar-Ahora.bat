@echo off
rem ===========================================================================
rem  AVACOM OPS Master - Respaldar ahora (MOD-016 Backup & Recovery)
rem
rem  UN SOLO ARCHIVO .bat, sin PowerShell. Usa curl.exe, que ya viene con
rem  Windows 10 y 11.
rem
rem  Uso: toca este archivo EN EL EQUIPO DONDE CORRE OPS MASTER (el nodo).
rem  Pide el documento y la clave de un usuario TECNICO de AVACOM (el permiso
rem  backup.run es solo del personal tecnico), crea un respaldo completo,
rem  deja la constancia en el escritorio y, AL FINAL, dice claramente:
rem    - si el respaldo SE HIZO, y en que archivo y carpeta quedo; o
rem    - si NO SE HIZO, y el motivo y la respuesta exacta del nodo.
rem
rem  Opcional:  AVACOM-Respaldar-Ahora.bat [puerto] [completo|incremental]
rem             (por defecto: el puerto de backend.env, o 8000, y completo)
rem
rem  Respeta los permisos: no abre la base ni salta la sesion. Cada respaldo
rem  queda en la bitacora a nombre de quien inicio sesion. No restaura, no
rem  exporta y no borra nada.
rem
rem  Codigos de salida: 0 hecho y verificado, 1 no se hizo, 2 hecho sin verificar.
rem ===========================================================================
setlocal EnableExtensions EnableDelayedExpansion
title AVACOM OPS Master - Respaldar ahora

set "RAIZ=%ProgramData%\AVACOM\OPS Master"
set "PUERTO=8000"
set "TIPO=completo"
set "MOTIVO="
set "HTTPERR="
set "ERRARCH="

rem --- puerto: lo que diga backend.env (el mismo que usa el servicio) ---
if exist "%RAIZ%\Config\backend.env" (
    for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b /c:"AVACOM_OPS_BACKEND_PORT=" "%RAIZ%\Config\backend.env"`) do set "PUERTO=%%b"
)
set "PUERTO=!PUERTO: =!"
if not "%~1"=="" set "PUERTO=%~1"
if /i "%~2"=="incremental" set "TIPO=incremental"
set "BASE=http://127.0.0.1:!PUERTO!"

echo.
echo   AVACOM OPS Master
echo   Respaldar ahora ^(Backup ^& Recovery^)
echo.

where curl.exe >nul 2>&1
if errorlevel 1 (
    set "MOTIVO=No se encontro curl.exe. Hace falta Windows 10 (1803 o mas) o Windows 11."
    goto :fallo
)

rem --- carpeta de trabajo propia; se borra al terminar ---
set "TRABAJO=%TEMP%\avacom-respaldo-%RANDOM%%RANDOM%"
mkdir "%TRABAJO%" >nul 2>&1
if not exist "%TRABAJO%" (
    set "MOTIVO=No se pudo crear una carpeta temporal en %TEMP%."
    goto :fallo
)

rem --- 1. el nodo responde ---
echo   [1/4] Buscando el nodo en !BASE! ...
curl.exe -s -S --max-time 15 -o "%TRABAJO%\salud.json" -w "%%{http_code}" "!BASE!/health/" > "%TRABAJO%\http.txt" 2>"%TRABAJO%\err.txt"
set "HTTP="
set /p HTTP=<"%TRABAJO%\http.txt"
if not "!HTTP!"=="200" (
    set "MOTIVO=El nodo no responde en !BASE!. Abre AVACOM OPS Master o revisa que el servicio AVACOMOPSBackend este iniciado. Si usa otro puerto: AVACOM-Respaldar-Ahora.bat <puerto>"
    set "HTTPERR=!HTTP!"
    set "ERRARCH=%TRABAJO%\err.txt"
    goto :fallo
)
echo         el nodo responde.

rem --- 2. iniciar sesion como tecnico ---
echo.
echo   [2/4] Inicia sesion con tu usuario tecnico de AVACOM.
echo         ^(Lo que escribas se ve en pantalla; se borra al continuar.^)
echo.
set "ID="
set "SEC="
set /p "ID=        Documento o codigo: "
set /p "SEC=        Clave: "
if "!ID!"=="" goto :sin_datos
if "!SEC!"=="" goto :sin_datos
set "_x=!ID!!SEC!"
set "_y=!_x:"=!"
if not "!_y!"=="!_x!" goto :comillas
set "_x="
set "_y="
set "ID=!ID:\=\\!"
set "SEC=!SEC:\=\\!"
cls
echo.
echo   AVACOM OPS Master - Respaldar ahora
echo.
echo   [2/4] Iniciando sesion como !ID! ...

>"%TRABAJO%\login.json" (echo {"identificador":"!ID!","secreto":"!SEC!","rol":"TECHNICIAN"})
set "SEC="
curl.exe -s -S --max-time 30 -o "%TRABAJO%\login.out" -w "%%{http_code}" -H "Content-Type: application/json" --data-binary "@%TRABAJO%\login.json" "!BASE!/api/acceso/sesiones/" > "%TRABAJO%\http.txt" 2>"%TRABAJO%\err.txt"
del /f /q "%TRABAJO%\login.json" >nul 2>&1
set "HTTP="
set /p HTTP=<"%TRABAJO%\http.txt"
if not "!HTTP!"=="200" if not "!HTTP!"=="201" (
    set "MOTIVO=No se pudo iniciar sesion. Revisa el documento y la clave, y que el usuario tenga el rol TECHNICIAN (solo el personal de AVACOM respalda)."
    set "HTTPERR=!HTTP!"
    call :leer_error "%TRABAJO%\login.out"
    goto :fallo
)
set "R="
set /p R=<"%TRABAJO%\login.out"
call :campo R TOKEN token
call :campo R SESION sesion_id
if "!TOKEN!"=="" (
    set "MOTIVO=El nodo acepto el acceso pero no devolvio la sesion."
    set "ERRARCH=%TRABAJO%\login.out"
    goto :fallo
)
echo         sesion abierta.

rem --- 3. respaldar ---
echo.
echo   [3/4] Creando el respaldo !TIPO! ... ^(puede tardar; no cierres esta ventana^)
>"%TRABAJO%\ahora.json" (echo {"tipo":"!TIPO!"})
curl.exe -s -S --max-time 1800 -o "%TRABAJO%\ahora.out" -w "%%{http_code}" -H "Authorization: Bearer !TOKEN!" -H "Content-Type: application/json" --data-binary "@%TRABAJO%\ahora.json" "!BASE!/api/respaldo/respaldos/ahora/" > "%TRABAJO%\http.txt" 2>"%TRABAJO%\err.txt"
set "HTTP="
set /p HTTP=<"%TRABAJO%\http.txt"
if not "!HTTP!"=="201" (
    set "MOTIVO=El nodo no creo el respaldo."
    set "HTTPERR=!HTTP!"
    call :leer_error "%TRABAJO%\ahora.out"
    goto :fallo
)
set "R="
set /p R=<"%TRABAJO%\ahora.out"
call :campo R RID respaldo_id
call :campo R RTIPO tipo
call :campo R RESTADO estado
call :campo R RBYTES bytes
call :campo R RDISPARO disparo
call :campo R RARCHIVO archivo
if "!RID!"=="" (
    set "MOTIVO=El nodo respondio 201 pero la respuesta no trae el respaldo."
    set "ERRARCH=%TRABAJO%\ahora.out"
    goto :fallo
)
if "!RESTADO!"=="fallido" set "MOTIVO=El nodo marco el respaldo como fallido."
if "!RESTADO!"=="incompleto" set "MOTIVO=El nodo marco el respaldo como incompleto."
if "!RESTADO!"=="en_curso" set "MOTIVO=El respaldo sigue en curso; no hay archivo terminado."
if defined MOTIVO (
    set "ERRARCH=%TRABAJO%\ahora.out"
    goto :fallo
)

rem --- 4. la constancia al escritorio ---
echo.
echo   [4/4] Guardando la constancia en el escritorio ...
set "CONSTANCIA=%USERPROFILE%\Desktop\constancia-de-respaldo-!RID:~0,8!.txt"
curl.exe -s -S --max-time 60 -o "!CONSTANCIA!" -w "%%{http_code}" -H "Authorization: Bearer !TOKEN!" "!BASE!/api/respaldo/respaldos/!RID!/constancia/?formato=txt" > "%TRABAJO%\http.txt" 2>"%TRABAJO%\err.txt"
set "HTTP="
set /p HTTP=<"%TRABAJO%\http.txt"
if not "!HTTP!"=="200" (
    echo         no se pudo bajar la constancia ^(HTTP !HTTP!^); el respaldo SI quedo hecho.
    del /f /q "!CONSTANCIA!" >nul 2>&1
    set "CONSTANCIA="
)

call :cerrar_sesion

rem --- donde quedo: la carpeta de respaldos del nodo + el nombre que dice la ficha ---
set "CARPETA=%RAIZ%\Respaldos"
set "ARCHIVO=!CARPETA!\!RARCHIVO!"
set "EXISTE="
set "TAM="
if defined RARCHIVO if exist "!ARCHIVO!" (
    set "EXISTE=1"
    for %%f in ("!ARCHIVO!") do set "TAM=%%~zf"
)

echo.
if "!RESTADO!"=="completo_verificado" (
    set "CODIGO=0"
    echo   ################################################################
    echo   #   RESPALDO HECHO Y VERIFICADO
    echo   ################################################################
) else (
    set "CODIGO=2"
    echo   ################################################################
    echo   #   RESPALDO HECHO, PERO SIN VERIFICAR  ^(!RESTADO!^)
    echo   ################################################################
)
echo.
echo   Donde quedo:
if defined EXISTE (
    echo     Archivo ..... !ARCHIVO!
    echo     Tamano ...... !TAM! bytes
) else (
    echo     Carpeta ..... !CARPETA!
    echo     Archivo ..... !RARCHIVO!
    echo     AVISO: el nodo dice que lo creo, pero no lo veo en esa ruta. Si el nodo
    echo     usa otra carpeta de datos, busca ese nombre dentro de ella.
)
if defined CONSTANCIA echo     Constancia .. !CONSTANCIA!
echo     Informes .... !CARPETA!\Informes
echo.
echo   Identificador: !RID!
echo   Tipo: !RTIPO!   Disparo: !RDISPARO!   Estado: !RESTADO!
echo.
if "!CODIGO!"=="0" (
    echo   Se comprobo que este respaldo se puede restaurar.
) else (
    echo   El nodo lo reintenta verificar cada 6 horas. Mira la constancia.
)
if defined CONSTANCIA start "" notepad.exe "!CONSTANCIA!"
goto :fin

rem ===========================================================================
:sin_datos
set "MOTIVO=Falta el documento o la clave."
goto :fallo

:comillas
set "MOTIVO=El documento o la clave llevan comillas, que este archivo no admite. Cambia la clave, o haz el respaldo por la API con el procedimiento de spec-driven\18-backup-recovery\04-operacion.md."
goto :fallo

:fallo
set "CODIGO=1"
call :cerrar_sesion
echo.
echo   ################################################################
echo   #   NO SE HIZO EL RESPALDO
echo   ################################################################
echo.
if defined MOTIVO echo   Que paso:   !MOTIVO!
if defined HTTPERR echo   Codigo HTTP: !HTTPERR!
if defined ERRARCH if exist "!ERRARCH!" (
    echo   Respuesta del nodo:
    echo.
    type "!ERRARCH!"
    echo.
)
echo.
echo   No se creo ningun respaldo nuevo. Lo que ya habia sigue intacto.
goto :fin

:fin
if defined TRABAJO rmdir /s /q "%TRABAJO%" >nul 2>&1
echo.
pause
exit /b %CODIGO%

rem --------------------------------------------------------------------------
rem :campo <variable con el JSON> <variable destino> <nombre del campo>
rem   Saca el valor de un campo de primer nivel de la respuesta (una linea).
rem --------------------------------------------------------------------------
:campo
set "_t=!%~1!"
set "_t=!_t:"=!"
set "_t=!_t:: =:!"
set "%~2="
if "!_t:*%~3:=!"=="!_t!" exit /b 0
set "_t=!_t:*%~3:=!"
for /f "tokens=1 delims=,}" %%z in ("!_t!") do set "%~2=%%z"
exit /b 0

rem --------------------------------------------------------------------------
rem :leer_error <archivo>  -> traduce el codigo del nodo al motivo y guarda la respuesta
rem --------------------------------------------------------------------------
:leer_error
set "ERRARCH=%~1"
set "_e="
set /p _e=<"%~1"
call :campo _e _cod codigo
if "!_cod!"=="sin_permiso"          set "MOTIVO=Este usuario no es personal de AVACOM (le falta el permiso backup.run)."
if "!_cod!"=="sesion_activa"        set "MOTIVO=Hay una clase abierta. Cierrala y vuelve a intentar."
if "!_cod!"=="respaldo_en_curso"    set "MOTIVO=Ya hay un respaldo o una restauracion en marcha. Espera a que termine."
if "!_cod!"=="espacio_insuficiente" set "MOTIVO=No hay espacio en el disco (hacen falta unas 2 veces la base + 64 MB)."
if "!_cod!"=="sin_respaldo_previo"  set "MOTIVO=Un incremental necesita un completo anterior. Usa: completo"
if "!_cod!"=="respaldo_fallido"     set "MOTIVO=El respaldo no termino; lo anterior sigue intacto."
if "!_cod!"=="credenciales_invalidas" set "MOTIVO=Documento o clave incorrectos."
if defined _cod set "MOTIVO=!MOTIVO! [codigo: !_cod!]"
exit /b 0

rem --------------------------------------------------------------------------
rem :cerrar_sesion  -> revoca la sesion que abrio este archivo
rem --------------------------------------------------------------------------
:cerrar_sesion
if defined TOKEN curl.exe -s --max-time 15 -o nul -X DELETE -H "Authorization: Bearer !TOKEN!" "!BASE!/api/acceso/sesiones/actual/" >nul 2>&1
set "TOKEN="
exit /b 0
