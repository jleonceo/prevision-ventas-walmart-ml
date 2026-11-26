<#
Envoltorio del lote diario de la previsión del caso 69 (método despliegue, programacion.md). Es lo único que llamaría el
Programador de tareas de Windows: crear y activar esa tarea lo decide el responsable del caso (puerta 6), este fichero no la crea.

Lo que hace, en este orden:
  1. toma la carpeta del caso de su propia ubicación (la carpeta de encima de produccion/), así que no depende de la
     carpeta desde la que se lanza; con -Raiz se le puede pasar otra, para un ensayo;
  2. lee produccion/configuracion.json en UTF-8 y comprueba que trae su apartado lote_diario, el intérprete del entorno
     del caso (lote_diario.python, sin el nombre de la persona escrito: %CONDA_PREFIX%) y la carpeta de sus registros;
  3. lanza produccion/lote_diario.py con ese intérprete, -W error y PYTHONUTF8=1, pasándole los demás argumentos
     (--repetir, --origen AAAA-MM-DD, --fecha AAAA-MM-DD);
  4. guarda en <registros_del_envoltorio>/lote_diario_AAAAMMDD_HHMMSS.log todo lo que imprime el script, errores
     incluidos, con la hora de inicio y fin y el código de salida: la tarea programada no lo guarda;
  5. sale con el código del lote: 0 si la previsión del día quedó guardada, 1 si paró y 2 si hubo un fallo técnico. Si
     el envoltorio no puede ni lanzarlo (sin configuración o sin intérprete), sale con 1 y lo dice.

Uso: powershell.exe -NoProfile -File produccion\lote_diario.ps1 [-Raiz CARPETA] [--repetir] [--origen AAAA-MM-DD]
#>
param([string]$Raiz = "")

# ══ 1. La carpeta del caso y la configuración ═══════════════════════════════════
$ErrorActionPreference = "Stop"
# Lo que imprime el envoltorio sale en UTF-8, como el registro, también cuando otro programa lo recoge
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$inicio = Get-Date
if (-not $Raiz) { $Raiz = Split-Path -Parent $PSScriptRoot }
$Raiz = (Resolve-Path -LiteralPath $Raiz).Path
$rutaConfiguracion = Join-Path $Raiz "produccion\configuracion.json"
if (-not (Test-Path -LiteralPath $rutaConfiguracion)) {
    Write-Output "PARA · envoltorio: no existe la configuración $rutaConfiguracion"
    exit 1
}
$configuracion = Get-Content -LiteralPath $rutaConfiguracion -Raw -Encoding UTF8 | ConvertFrom-Json
$lote = $configuracion.lote_diario
if ($null -eq $lote -or -not $lote.python -or -not $lote.registros_del_envoltorio) {
    Write-Output "PARA · envoltorio: la configuración no trae lote_diario con python y registros_del_envoltorio"
    exit 1
}

# Una ruta de la configuración: variables de entorno expandidas, barras normalizadas y, si es relativa, desde el caso
function Resolve-RutaDelCaso([string]$ruta) {
    $r = [Environment]::ExpandEnvironmentVariables($ruta) -replace '/', '\'
    if ([System.IO.Path]::IsPathRooted($r)) { return $r }
    return (Join-Path $Raiz $r)
}

$python = Resolve-RutaDelCaso $lote.python
if (-not (Test-Path -LiteralPath $python)) {
    Write-Output "PARA · envoltorio: no existe el intérprete de la configuración ($python)"
    exit 1
}
$carpetaRegistros = Resolve-RutaDelCaso $lote.registros_del_envoltorio
New-Item -ItemType Directory -Force -Path $carpetaRegistros | Out-Null
$registro = Join-Path $carpetaRegistros ("lote_diario_{0}.log" -f $inicio.ToString("yyyyMMdd_HHmmss"))

# ══ 2. Lanzar el lote y guardar lo que imprime ══════════════════════════════════
$script = Join-Path $PSScriptRoot "lote_diario.py"
$argumentos = @("-W", "error", "`"$script`"", "--raiz", "`"$Raiz`"") + @($args | ForEach-Object { "`"$_`"" })
$env:PYTHONUTF8 = "1"
$salida = "$registro.salida"
$errores = "$registro.errores"
try {
    $proceso = Start-Process -FilePath $python -ArgumentList ($argumentos -join " ") -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $salida -RedirectStandardError $errores
    $codigo = $proceso.ExitCode
} catch {
    $codigo = 2
    Set-Content -LiteralPath $errores -Value "el envoltorio no pudo lanzar el lote: $($_.Exception.Message)" -Encoding UTF8
}
$fin = Get-Date
$lineas = @("inicio: $($inicio.ToString('s'))", "caso: $Raiz", "intérprete: $python",
            "orden: $python $($argumentos -join ' ')", "── lo que imprime el lote ──")
if (Test-Path -LiteralPath $salida) { $lineas += Get-Content -LiteralPath $salida -Encoding UTF8 }
$lineas += "── errores ──"
if (Test-Path -LiteralPath $errores) { $lineas += Get-Content -LiteralPath $errores -Encoding UTF8 }
$lineas += @("fin: $($fin.ToString('s'))", "segundos: $([math]::Round(($fin - $inicio).TotalSeconds, 1))",
             "código de salida: $codigo")
Set-Content -LiteralPath $registro -Value $lineas -Encoding UTF8
Remove-Item -LiteralPath $salida, $errores -ErrorAction SilentlyContinue
$lineas | ForEach-Object { Write-Output $_ }
Write-Output "registro del envoltorio: $registro"
exit $codigo
