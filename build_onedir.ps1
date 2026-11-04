param(
    [string]$Python = 'python',
    [switch]$Zip
)

$ErrorActionPreference = 'Stop'

$project = $PSScriptRoot
$buildRoot = Join-Path $project 'build'
$toolsDir = Join-Path $buildRoot 'packaging-tools'
$tempDir = Join-Path $buildRoot 'tmp'
$stagingDist = Join-Path $buildRoot 'dist'
$stagedPackage = Join-Path $stagingDist 'LosslessLens'
$outputDir = [IO.Path]::GetFullPath((Join-Path $project 'dist\LosslessLens'))

New-Item -ItemType Directory -Force -Path $toolsDir, $tempDir | Out-Null

$saved = @{}

foreach ($key in @('PATH', 'PYTHONPATH', 'PYINSTALLER_CONFIG_DIR', 'TEMP', 'TMP', 'MPLCONFIGDIR')) {
    $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}

try {
    # Verify Python is available
    & $Python --version
    if ($LASTEXITCODE -ne 0) {
        throw "Python executable not found: $Python"
    }

    # PyInstaller can succeed with missing imports and produce an unusable exe.
    $pythonPrefix = & $Python -c 'import sys, ssl; import fastapi, uvicorn, numpy, scipy.signal, soundfile, plotly; print(sys.base_prefix)'
    if ($LASTEXITCODE -ne 0) {
        throw 'Selected Python cannot import the required Web dependencies. Install requirements-web.txt in that interpreter, or select the project environment with -Python.'
    }

    # Selecting python.exe does not activate its Conda DLL search paths. Keep
    # native dependencies aligned with that interpreter, even from a base shell.
    $env:PATH = @((Join-Path $pythonPrefix 'Library\bin'),
                 (Join-Path $pythonPrefix 'DLLs'), $pythonPrefix, $env:PATH) -join [IO.Path]::PathSeparator
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

    # The Web entry point serves Plotly JS and does not use dataframe or Qt
    # integrations. Do not collect these optional stacks from a full Conda base.
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --console `
        --name LosslessLens `
        --distpath $stagingDist `
        --workpath (Join-Path $buildRoot 'onedir') `
        --specpath $buildRoot `
        --paths $project `
        --add-data "${project}\web:web" `
        --collect-data plotly `
        --collect-submodules uvicorn `
        --exclude-module matplotlib `
        --exclude-module IPython `
        --exclude-module tkinter `
        --exclude-module pandas `
        --exclude-module dask `
        --exclude-module qtpy `
        --exclude-module PyQt5 `
        --exclude-module PyQt6 `
        --exclude-module PySide2 `
        --exclude-module PySide6 `
        (Join-Path $project 'web_app.py')

    if ($LASTEXITCODE -ne 0) {
        throw 'PyInstaller build failed.'
    }

    # --help imports the application (including ssl) without starting a server.
    & (Join-Path $stagedPackage 'LosslessLens.exe') --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Packaged executable failed its startup check; see the traceback above.'
    }

    # Keep the final directory itself: a terminal may have it as its cwd.
    # Only replace its contents after the staged executable passes startup.
    $distRoot = [IO.Path]::GetFullPath((Join-Path $project 'dist')) + [IO.Path]::DirectorySeparatorChar
    if (-not $outputDir.StartsWith($distRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Output directory is outside the project dist directory: $outputDir"
    }
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $outputDir -Force) {
        $targetPath = [IO.Path]::GetFullPath($item.FullName)
        if (-not $targetPath.StartsWith($outputDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove a path outside the output directory: $targetPath"
        }
        Remove-Item -LiteralPath $targetPath -Recurse -Force
    }
    Get-ChildItem -LiteralPath $stagedPackage -Force | Copy-Item -Destination $outputDir -Recurse -Force
    Copy-Item -Path (Join-Path $project 'packaging\*') -Destination $outputDir -Force
    if ($Zip) {
        $zipPath = Join-Path $project 'dist\LosslessLens-windows-x64.zip'
        if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
        Compress-Archive -Path $outputDir -DestinationPath $zipPath
        Write-Host "Release zip: $zipPath"
    }
    Write-Host "Built and startup-checked: $(Join-Path $outputDir 'LosslessLens.exe')"
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
