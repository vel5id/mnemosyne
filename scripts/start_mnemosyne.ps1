# =============================================================================
# Mnemosyne Core V3.0 - Orchestration Script
# =============================================================================
# PowerShell скрипт для запуска всей системы Mnemosyne Core одной командой
# Включает: Graceful Shutdown, скрытые окна, управление жизненным циклом
# =============================================================================

[CmdletBinding()]
param()

# -----------------------------------------------------------------------------
# Конфигурация путей
# -----------------------------------------------------------------------------
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$WatcherExe = Join-Path $ProjectRoot "watcher.exe"
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvActivate = Join-Path $VenvPath "Scripts\Activate.ps1"
$PythonScript = Join-Path $ProjectRoot "main.py"

# -----------------------------------------------------------------------------
# Глобальные переменные для управления процессами
# -----------------------------------------------------------------------------
$global:WatcherProcess = $null
$global:BrainProcess = $null
$global:IsRunning = $true

# -----------------------------------------------------------------------------
# Цветовая схема для вывода
# -----------------------------------------------------------------------------
$Colors = @{
    Success    = "Green"
    Info       = "Cyan"
    Warning    = "Yellow"
    Error      = "Red"
    Highlight  = "Magenta"
    Dim        = "Gray"
}

# -----------------------------------------------------------------------------
# Функция цветного вывода
# -----------------------------------------------------------------------------
function Write-ColorOutput {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Message,
        
        [Parameter(Mandatory=$false)]
        [string]$Color = "White"
    )
    
    Write-Host $Message -ForegroundColor $Color
}

# -----------------------------------------------------------------------------
# Функция вывода заголовка раздела
# -----------------------------------------------------------------------------
function Write-SectionHeader {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Title
    )
    
    Write-Host ""
    Write-Host "═" * 60 -ForegroundColor $Colors.Highlight
    Write-Host "  $Title" -ForegroundColor $Colors.Highlight
    Write-Host "═" * 60 -ForegroundColor $Colors.Highlight
}

# -----------------------------------------------------------------------------
# Функция вывода статуса операции
# -----------------------------------------------------------------------------
function Write-Status {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Operation,
        
        [Parameter(Mandatory=$true)]
        [bool]$Success,
        
        [Parameter(Mandatory=$false)]
        [string]$Detail = ""
    )
    
    $symbol = if ($Success) { "✓" } else { "✗" }
    $color = if ($Success) { $Colors.Success } else { $Colors.Error }
    
    Write-Host ("  {0} {1}" -f $symbol, $Operation) -ForegroundColor $color
    
    if ($Detail) {
        Write-Host ("    → {0}" -f $Detail) -ForegroundColor $Colors.Dim
    }
}

# -----------------------------------------------------------------------------
# Проверка наличия виртуального окружения
# -----------------------------------------------------------------------------
function Test-VirtualEnvironment {
    Write-SectionHeader "Проверка виртуального окружения"
    
    if (-not (Test-Path $VenvPath)) {
        Write-Status "Виртуальное окружение (.venv) найдено" $false
        Write-ColorOutput "  Создайте виртуальное окружение:" $Colors.Warning
        Write-ColorOutput "    python -m venv .venv" $Colors.Dim
        Write-ColorOutput "    .venv\Scripts\Activate.ps1" $Colors.Dim
        Write-ColorOutput "    pip install -r requirements.txt" $Colors.Dim
        return $false
    }
    
    if (-not (Test-Path $VenvActivate)) {
        Write-Status "Скрипт активации найден" $false
        return $false
    }
    
    Write-Status "Виртуальное окружение найдено" $true $VenvPath
    return $true
}

# -----------------------------------------------------------------------------
# Проверка службы Ollama
# -----------------------------------------------------------------------------
function Test-OllamaService {
    Write-SectionHeader "Проверка службы Ollama"
    
    # Проверка по порту
    $portCheck = Test-NetConnection -ComputerName localhost -Port 11434 -InformationLevel Quiet -WarningAction SilentlyContinue
    
    if ($portCheck) {
        Write-Status "Ollama работает (порт 11434 открыт)" $true
        return $true
    }
    
    # Проверка по процессу
    $processCheck = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    
    if ($processCheck) {
        Write-Status "Ollama процесс найден" $true ("PID: $($processCheck.Id)")
        return $true
    }
    
    Write-Status "Ollama не запущен" $false
    Write-ColorOutput "  Внимание: Ollama требуется для LLM-инференса" $Colors.Warning
    Write-ColorOutput "  Запустите: ollama serve" $Colors.Dim
    
    $response = Read-Host "  Продолжить без Ollama? (y/N)"
    return $response -eq "y" -or $response -eq "Y"
}

# -----------------------------------------------------------------------------
# Проверка наличия watcher.exe
# -----------------------------------------------------------------------------
function Test-WatcherExecutable {
    Write-SectionHeader "Проверка исполняемых файлов"
    
    if (-not (Test-Path $WatcherExe)) {
        Write-Status "Watcher.exe найден" $false
        Write-ColorOutput "  Скомпилируйте Watcher:" $Colors.Warning
        Write-ColorOutput "    go build -o watcher.exe ./cmd/watcher" $Colors.Dim
        return $false
    }
    
    Write-Status "Watcher.exe найден" $true $WatcherExe
    return $true
}

# -----------------------------------------------------------------------------
# Запуск Tier 1: Watcher (Go)
# -----------------------------------------------------------------------------
function Start-Watcher {
    Write-SectionHeader "Запуск Tier 1: The Watcher"
    
    try {
        # Запуск в скрытом окне
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $WatcherExe
        $psi.WorkingDirectory = $ProjectRoot
        $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
        $psi.CreateNoWindow = $true
        $psi.UseShellExecute = $false
        
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $process.EnableRaisingEvents = $true
        
        # Регистрация события завершения процесса
        Register-ObjectEvent -InputObject $process -EventName Exited -Action {
            Write-ColorOutput "`n  [WATCHER] Процесс завершился с кодом: $($Sender.ExitCode)" $Colors.Warning
        } | Out-Null
        
        $process.Start() | Out-Null
        $global:WatcherProcess = $process
        
        Write-Status "Watcher запущен" $true ("PID: $($process.Id)")
        Write-ColorOutput "  → Работает в фоновом режиме (скрытое окно)" $Colors.Dim
        
        return $true
    }
    catch {
        Write-Status "Запуск Watcher не удался" $false $_.Exception.Message
        return $false
    }
}

# -----------------------------------------------------------------------------
# Запуск Tier 2: Brain (Python)
# -----------------------------------------------------------------------------
function Start-Brain {
    Write-SectionHeader "Запуск Tier 2: The Brain"
    
    try {
        # Активация виртуального окружения
        Write-ColorOutput "  Активация виртуального окружения..." $Colors.Info
        & $VenvActivate
        
        # Проверка Python
        $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
        if (-not (Test-Path $pythonPath)) {
            Write-Status "Python в venv найден" $false
            return $false
        }
        
        Write-Status "Python найден" $true $pythonPath
        
        # Запуск main.py
        Write-ColorOutput "  Запуск main.py..." $Colors.Info
        
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $pythonPath
        $psi.Arguments = $PythonScript
        $psi.WorkingDirectory = $ProjectRoot
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $false
        
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $process.EnableRaisingEvents = $true
        
        # Асинхронное чтение вывода
        $outputBuilder = New-Object System.Text.StringBuilder
        $errorBuilder = New-Object System.Text.StringBuilder
        
        $outputAction = {
            if (-not [String]::IsNullOrEmpty($EventArgs.Data)) {
                $Event.MessageData.AppendLine($EventArgs.Data)
            }
        }
        
        $outputEvent = Register-ObjectEvent -InputObject $process -EventName OutputDataReceived -Action $outputAction -MessageData $outputBuilder
        $errorEvent = Register-ObjectEvent -InputObject $process -EventName ErrorDataReceived -Action $outputAction -MessageData $errorBuilder
        
        $process.BeginOutputReadLine()
        $process.BeginErrorReadLine()
        
        $process.Start() | Out-Null
        $global:BrainProcess = $process
        
        Write-Status "Brain запущен" $true ("PID: $($process.Id)")
        Write-ColorOutput "  → Логи выводятся в текущем терминале" $Colors.Dim
        
        return $true
    }
    catch {
        Write-Status "Запуск Brain не удался" $false $_.Exception.Message
        return $false
    }
}

# -----------------------------------------------------------------------------
# Graceful Shutdown для Watcher
# -----------------------------------------------------------------------------
function Stop-WatcherGracefully {
    if ($null -eq $global:WatcherProcess -or $global:WatcherProcess.HasExited) {
        return
    }
    
    Write-ColorOutput "`n  Graceful Shutdown: Watcher..." $Colors.Info
    
    try {
        # Сначала SIGTERM (taskkill без /f)
        $pid = $global:WatcherProcess.Id
        $result = taskkill /PID $pid 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Status "Watcher завершил работу (SIGTERM)" $true
            
            # Ждем завершения до 5 секунд
            $timeout = 5000
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            
            while (-not $global:WatcherProcess.HasExited -and $stopwatch.ElapsedMilliseconds -lt $timeout) {
                Start-Sleep -Milliseconds 100
            }
            
            if ($global:WatcherProcess.HasExited) {
                Write-ColorOutput "    → Буфер сброшен на диск" $Colors.Success
            }
            else {
                # Принудительное завершение
                Write-ColorOutput "    → Принудительное завершение..." $Colors.Warning
                $global:WatcherProcess.Kill()
            }
        }
        else {
            Write-Status "Завершение Watcher не удалось" $false
            $global:WatcherProcess.Kill()
        }
    }
    catch {
        Write-ColorOutput "    Ошибка при завершении: $_" $Colors.Error
    }
}

# -----------------------------------------------------------------------------
# Graceful Shutdown для Brain
# -----------------------------------------------------------------------------
function Stop-BrainGracefully {
    if ($null -eq $global:BrainProcess -or $global:BrainProcess.HasExited) {
        return
    }
    
    Write-ColorOutput "  Graceful Shutdown: Brain..." $Colors.Info
    
    try {
        $global:BrainProcess.CloseMainWindow()
        
        # Ждем до 3 секунд
        $timeout = 3000
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        
        while (-not $global:BrainProcess.HasExited -and $stopwatch.ElapsedMilliseconds -lt $timeout) {
            Start-Sleep -Milliseconds 100
        }
        
        if ($global:BrainProcess.HasExited) {
            Write-Status "Brain завершил работу" $true
        }
        else {
            Write-ColorOutput "    → Принудительное завершение..." $Colors.Warning
            $global:BrainProcess.Kill()
        }
    }
    catch {
        Write-ColorOutput "    Ошибка при завершении: $_" $Colors.Error
    }
}

# -----------------------------------------------------------------------------
# Обработчик Ctrl+C
# -----------------------------------------------------------------------------
function Handle-CtrlC {
    Write-Host ""
    Write-SectionHeader "Получен сигнал остановки"
    $global:IsRunning = $false
}

# -----------------------------------------------------------------------------
# Главный цикл мониторинга
# -----------------------------------------------------------------------------
function Start-MonitoringLoop {
    Write-SectionHeader "Система Online"
    Write-ColorOutput "  Mnemosyne Core V3.0 активна" $Colors.Success
    Write-ColorOutput "  Нажмите Ctrl+C для graceful shutdown" $Colors.Dim
    Write-Host ""
    
    # Вывод логов Brain в реальном времени
    while ($global:IsRunning -and -not $global:BrainProcess.HasExited) {
        Start-Sleep -Milliseconds 100
    }
    
    if ($global:BrainProcess.HasExited) {
        Write-ColorOutput "`n  Процесс Brain завершился unexpectedly" $Colors.Warning
    }
}

# -----------------------------------------------------------------------------
# Точка входа
# -----------------------------------------------------------------------------
try {
    # Регистрация обработчика Ctrl+C
    [Console]::TreatControlCAsInput = $false
    $ctrlCEvent = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
        Stop-WatcherGracefully
        Stop-BrainGracefully
    }
    
    # Приветствие
    Write-Host ""
    Write-Host "╔" + "═" * 58 + "╗" -ForegroundColor $Colors.Highlight
    Write-Host "║" + " " * 58 + "║" -ForegroundColor $Colors.Highlight
    Write-Host "║" + "  Mnemosyne Core V3.0 - Orchestration Script".PadRight(58) + "║" -ForegroundColor $Colors.Highlight
    Write-Host "║" + "  Local Digital Twin for Personal Analytics".PadRight(58) + "║" -ForegroundColor $Colors.Dim
    Write-Host "║" + " " * 58 + "║" -ForegroundColor $Colors.Highlight
    Write-Host "╚" + "═" * 58 + "╝" -ForegroundColor $Colors.Highlight
    
    # Проверки окружения
    $envOk = $true
    
    if (-not (Test-WatcherExecutable)) {
        $envOk = $false
    }
    
    if (-not (Test-VirtualEnvironment)) {
        $envOk = $false
    }
    
    if (-not (Test-OllamaService)) {
        # Предупреждение, но не критическая ошибка
    }
    
    if (-not $envOk) {
        Write-ColorOutput "`n  Ошибка окружения. Исправьте проблемы и перезапустите." $Colors.Error
        exit 1
    }
    
    # Запуск компонентов
    if (-not (Start-Watcher)) {
        Write-ColorOutput "`n  Не удалось запустить Watcher. Завершение." $Colors.Error
        exit 1
    }
    
    if (-not (Start-Brain)) {
        Write-ColorOutput "`n  Не удалось запустить Brain. Завершение." $Colors.Error
        Stop-WatcherGracefully
        exit 1
    }
    
    # Мониторинг
    Start-MonitoringLoop
}
finally {
    # Graceful Shutdown
    Write-SectionHeader "Graceful Shutdown"
    
    Stop-BrainGracefully
    Stop-WatcherGracefully
    
    Write-Host ""
    Write-ColorOutput "  Mnemosyne Core V3.0 остановлена" $Colors.Success
    Write-Host ""
}
