$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$packageRoot = $PSScriptRoot
$offlinePython = Join-Path $packageRoot "installers\python-3.11.8-amd64.exe"
$offlinePillow = Join-Path $packageRoot "installers\pillow-12.3.0-cp311-cp311-win_amd64.whl"
$downloadedInstaller = Join-Path $env:TEMP "flipbook-python-latest-amd64.exe"

function Get-Python3Command {
    $commands = @()
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $commands += ,@($pyLauncher.Source, "-3")
    }

    $searchRoots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        (Join-Path $env:ProgramFiles "Python*")
    )
    foreach ($root in $searchRoots) {
        Get-ChildItem -Path $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            ForEach-Object { $commands += ,@($_.FullName) }
    }

    foreach ($command in $commands) {
        try {
            $executable = $command[0]
            $prefixArguments = @($command | Select-Object -Skip 1)
            $versionText = & $executable @prefixArguments --version 2>&1
            if ($LASTEXITCODE -eq 0 -and "$versionText" -match '^Python 3\.') {
                return ,$command
            }
        } catch {}
    }
    return $null
}

function Get-Python311Command {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $versionText = & $launcher.Source -3.11 --version 2>&1
            if ($LASTEXITCODE -eq 0 -and "$versionText" -match '^Python 3\.11\.') {
                return ,@($launcher.Source, "-3.11")
            }
        } catch {}
    }

    $localPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path -LiteralPath $localPython) { return ,@($localPython) }
    return $null
}

function Install-LatestPython {
    Write-Host "正在查詢 Python 官方最新版..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $index = Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/"
    $versions = [regex]::Matches($index.Content, 'href="(3\.\d+\.\d+)/"') |
        ForEach-Object { [version]$_.Groups[1].Value } |
        Sort-Object -Descending -Unique

    foreach ($version in $versions) {
        $installerUrl = "https://www.python.org/ftp/python/$version/python-$version-amd64.exe"
        try {
            Write-Host "正在下載 Python $version..."
            Invoke-WebRequest -UseBasicParsing -Uri $installerUrl -OutFile $downloadedInstaller
            $process = Start-Process -FilePath $downloadedInstaller -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1" -Wait -PassThru
            if ($process.ExitCode -ne 0) { throw "Python 安裝程式結束碼：$($process.ExitCode)" }
            return
        } catch {
            Remove-Item -LiteralPath $downloadedInstaller -Force -ErrorAction SilentlyContinue
        }
    }
    throw "無法從 Python 官網下載或安裝最新版 Python。"
}

function Install-OfflineFallback {
    Write-Host "`n線上安裝未完成，改用內附的離線安裝檔。" -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath $offlinePython)) { throw "找不到 $offlinePython" }
    if (-not (Test-Path -LiteralPath $offlinePillow)) { throw "找不到 $offlinePillow" }

    $process = Start-Process -FilePath $offlinePython -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1" -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "離線 Python 安裝失敗，結束碼：$($process.ExitCode)" }

    $python = Get-Python311Command
    if (-not $python) { throw "Python 3.11.8 安裝完成，但找不到 Python 3 執行檔。" }
    $executable = $python[0]
    $prefixArguments = @($python | Select-Object -Skip 1)
    & $executable @prefixArguments -m pip install --no-index --force-reinstall $offlinePillow
    if ($LASTEXITCODE -ne 0) { throw "離線 Pillow 安裝失敗。" }
}

try {
    try {
        Install-LatestPython
        $python = Get-Python3Command
        if (-not $python) { throw "Python 安裝完成，但找不到 Python 3 執行檔。" }
        Write-Host "正在安裝最新版 Pillow..."
        $executable = $python[0]
        $prefixArguments = @($python | Select-Object -Skip 1)
        & $executable @prefixArguments -m pip install --upgrade Pillow
        if ($LASTEXITCODE -ne 0) { throw "最新版 Pillow 安裝失敗。" }
    } catch {
        Write-Warning $_
        Install-OfflineFallback
    }

    $python = Get-Python3Command
    $executable = $python[0]
    $prefixArguments = @($python | Select-Object -Skip 1)
    & $executable @prefixArguments -c "import sys, PIL; print('Python ' + sys.version.split()[0]); print('Pillow ' + PIL.__version__)"
    if ($LASTEXITCODE -ne 0) { throw "安裝後驗證失敗。" }
    $installedPython = & $executable @prefixArguments -c "import sys; print(sys.executable)"
    if ($LASTEXITCODE -ne 0 -or -not $installedPython) { throw "無法記錄 Python 執行檔位置。" }
    Set-Content -LiteralPath (Join-Path $packageRoot ".flipbook-python-path") -Value "$installedPython" -Encoding Unicode
    exit 0
} catch {
    Write-Host "`n錯誤：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Remove-Item -LiteralPath $downloadedInstaller -Force -ErrorAction SilentlyContinue
}
