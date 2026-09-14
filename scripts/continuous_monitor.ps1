chcp 65001
$monitorLog = "D:\A1\ecg-lab-v2\results\monitor_log.txt"
$interval = 300  # 5分钟

function Write-MonitorLog {
    param([string]$msg)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $msg"
    Add-Content -Path $monitorLog -Value $line -Encoding UTF8
    Write-Output $line
}

Write-MonitorLog "持续监测启动 (间隔${interval}秒)"

while ($true) {
    $now = Get-Date
    
    # 检查E4进程
    $e4proc = Get-Process -Id 20636 -ErrorAction SilentlyContinue
    $e4alive = $null -ne $e4proc
    
    # 读取E4日志
    $logContent = Get-Content "D:\A1\ecg-lab-v2\results\e4_run.log" -ErrorAction SilentlyContinue
    $tGlobalDone = ($logContent | Where-Object { $_ -match 'T_global.*status=ok' }).Count
    $shiftDone = ($logContent | Where-Object { $_ -match '偏移敏感度' }).Count
    
    # GPU状态
    $gpu = nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader 2>$null
    
    # 检查后续实验是否已启动
    $e6Exists = Test-Path "D:\A1\ecg-lab-v2\results\binned_temperature_exploratory.csv"
    $e1bExists = Test-Path "D:\A1\ecg-lab-v2\results\loco_validation_results.csv"
    $e5Exists = Test-Path "D:\A1\ecg-lab-v2\results\inceptiontime_lite_transfer.csv"
    
    # 检查auto_chain日志
    $chainLog = Get-Content "D:\A1\ecg-lab-v2\results\auto_chain.log" -ErrorAction SilentlyContinue
    $chainLast = if ($chainLog) { $chainLog[-1] } else { "(无)" }
    
    # 检查E4输出
    $e4outExists = Test-Path "D:\A1\ecg-lab-v2\results\temperature_distribution_analysis.csv"
    
    $status = "E4: T_global=$tGlobalDone/62 shift=$shiftDone/62 alive=$e4alive GPU=$gpu"
    if ($e4outExists) { $status += " E4输出已生成!" }
    if ($e6Exists) { $status += " E6完成!" }
    if ($e1bExists) { $status += " E1b完成!" }
    if ($e5Exists) { $status += " E5完成!" }
    
    Write-MonitorLog $status
    
    # 如果E4进程消失，检查是否正常完成
    if (-not $e4alive) {
        if ($e4outExists) {
            Write-MonitorLog "E4已正常完成！输出文件已生成。"
            Write-MonitorLog "自动串联应开始启动E6..."
        } else {
            Write-MonitorLog "警告: E4进程消失但输出文件未生成！可能崩溃。"
            # 检查错误日志
            $errContent = Get-Content "D:\A1\ecg-lab-v2\results\e4_err.log" -ErrorAction SilentlyContinue
            if ($errContent -and $errContent.Count -gt 0) {
                Write-MonitorLog "错误日志最后5行:"
                $errContent | Select-Object -Last 5 | ForEach-Object { Write-MonitorLog "  $_" }
            }
        }
    }
    
    # 检查所有Python进程
    $pyProcs = Get-Process python -ErrorAction SilentlyContinue
    if ($pyProcs) {
        $procInfo = ($pyProcs | ForEach-Object { "PID=$($_.Id)" }) -join " "
        Write-MonitorLog "Python进程: $procInfo"
    }
    
    Start-Sleep -Seconds $interval
}
