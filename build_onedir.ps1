param(
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'

$project = $PSScriptRoot
$buildRoot = Join-Path $project 'build'
$toolsDir = Join-Path $buildRoot 'packaging-tools'
$tempDir = Join-Path $buildRoot 'tmp'

New-Item -ItemType Directory -Force -Path $toolsDir, $tempDir | Out-Null

$saved = @{}

foreach ($key in @('PYTHONPATH', 'PYINSTALLER_CONFIG_DIR', 'TEMP', 'TMP', 'MPLCONFIGDIR')) {
    $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}

try {
    # Verify Python is available
    & $Python --version
    if ($LASTEXITCODE -ne 0) {
        throw "Python executable not found: $Python"
    }

    $env:PYTHONPATH = $toolsDir
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $buildRoot 'pyinstaller-cache'
    $env:MPLCONFIGDIR = Join-Path $buildRoot 'matplotlib'
    $env:TEMP = $tempDir
    $env:TMP = $tempDir

    if (-not (Test-Path (Join-Path $toolsDir 'PyInstaller\__main__.py'))) {
        & $Python -m pip install `
            --disable-pip-version-check `
            --no-cache-dir `
            --target $toolsDir `
            'pyinstaller>=6,<7'

        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to install local packaging tools.'
        }
    }

    & $Python -m PyInstaller `
        --noconfirm `
        --onedir `
        --console `
        --name LosslessLens `
        --distpath (Join-Path $project 'dist') `
        --workpath (Join-Path $buildRoot 'onedir') `
        --specpath $buildRoot `
        --paths $project `
        --add-data "${project}\web:web" `
        --collect-data plotly `
        --collect-submodules uvicorn `
        --exclude-module matplotlib `
        --exclude-module IPython `
        --exclude-module tkinter `
        (Join-Path $project 'web_app.py')

    if ($LASTEXITCODE -ne 0) {
        throw 'PyInstaller build failed.'
    }

    Write-Host "Built: $(Join-Path $project 'dist\LosslessLens\LosslessLens.exe')"
}
finally {
    foreach ($key in $saved.Keys) {
        [Environment]::SetEnvironmentVariable(
            $key,
            $saved[$key],
            'Process'
        )
    }
}