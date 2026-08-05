$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$projectRoot = $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot ".build-python311"
$runtimePython = Join-Path $runtimeRoot "python.exe"
$venvRoot = Join-Path $projectRoot ".build-venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$pythonInstaller = Join-Path $projectRoot "installers\python-3.11.8-amd64.exe"
$pillowWheel = Join-Path $projectRoot "installers\pillow-12.3.0-cp311-cp311-win_amd64.whl"
$ffmpegWheel = Join-Path $projectRoot "installers\imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl"
$specFile = Join-Path $projectRoot "FlipbookGenerator.spec"
$buildRoot = Join-Path $projectRoot "build"
$distRoot = Join-Path $projectRoot "dist"
$expectedExe = Join-Path $distRoot "FlipbookGenerator.exe"

function Assert-ProjectChild([string]$Path) {
    $root = [System.IO.Path]::GetFullPath($projectRoot).TrimEnd('\') + '\'
    $target = [System.IO.Path]::GetFullPath($Path)
    if (-not $target.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside the project: $target"
    }
}

foreach ($requiredFile in @($pythonInstaller, $pillowWheel, $ffmpegWheel, $specFile)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required build file is missing: $requiredFile"
    }
}

if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
    Write-Host "Installing the project-local Python 3.11.8 runtime..."
    Assert-ProjectChild $runtimeRoot
    $arguments = @(
        "/quiet",
        "InstallAllUsers=0",
        "TargetDir=`"$runtimeRoot`"",
        "PrependPath=0",
        "Include_launcher=0",
        "Include_pip=1",
        "Include_test=0"
    )
    $process = Start-Process -FilePath $pythonInstaller -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
        throw "Python 3.11.8 installation failed with exit code $($process.ExitCode)."
    }
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Host "Creating the isolated build environment..."
    & $runtimePython -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the Python virtual environment." }
}

Write-Host "Installing bundled runtime dependencies..."
& $venvPython -m pip install --disable-pip-version-check --no-index $pillowWheel $ffmpegWheel
if ($LASTEXITCODE -ne 0) { throw "Failed to install Pillow or imageio-ffmpeg." }

& $venvPython -c "import PyInstaller; raise SystemExit(0 if PyInstaller.__version__ == '6.16.0' else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..."
    & $venvPython -m pip install --disable-pip-version-check "PyInstaller==6.16.0"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Normal TLS verification failed; retrying through the official PyPI hosts..."
        & $venvPython -m pip install --disable-pip-version-check `
            --trusted-host pypi.org --trusted-host files.pythonhosted.org `
            "PyInstaller==6.16.0"
    }
    if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller. Check the network connection." }
} else {
    Write-Host "Using the existing PyInstaller 6.16.0 installation."
}

foreach ($target in @($buildRoot, $distRoot)) {
    Assert-ProjectChild $target
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

Write-Host "Building the single-file EXE. This may take several minutes..."
Push-Location $projectRoot
try {
    & $venvPython -m PyInstaller --noconfirm --clean $specFile
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $expectedExe -PathType Leaf)) {
    throw "The build completed without the expected output: $expectedExe"
}

$exe = Get-Item -LiteralPath $expectedExe
Write-Host ""
Write-Host "Build complete: $($exe.FullName)"
Write-Host ("File size: {0:N1} MB" -f ($exe.Length / 1MB))
