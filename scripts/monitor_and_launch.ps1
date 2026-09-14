# E1a completion monitor + E4/E6 auto-launcher
$projectRoot = "D:\A1\ecg-lab-v2"
$e1aPid = 30668
$logFile = "$projectRoot\results\monitor_e1a_completion.log"

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -FilePath $logFile -Append -Encoding UTF8
    Write-Host "$ts $msg"
}

Write-Log "Monitor started. Waiting for E1a (PID $e1aPid) to complete..."

# Wait for E1a to finish
$maxWait = 8 * 3600  # 8 hours max
$waited = 0
while ($waited -lt $maxWait) {
    $proc = Get-Process -Id $e1aPid -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Log "E1a (PID $e1aPid) has exited!"
        break
    }
    Start-Sleep -Seconds 60
    $waited += 60
    if ($waited % 600 -eq 0) {
        # Every 10 minutes, log status
        $progressLine = Get-Content "$projectRoot\results\e1a_full_v5.log" -Tail 50 | Select-String "\[progress\]" | Select-Object -Last 1
        Write-Log "Still waiting... E1a running. Last progress: $progressLine"
    }
}

if ($waited -ge $maxWait) {
    Write-Log "Timeout after 8 hours. E1a may still be running."
    exit 1
}

# Check E1a output
$e1aCsv = "$projectRoot\results\l2_shift_full_390cells.csv"
if (Test-Path $e1aCsv) {
    Write-Log "E1a output CSV found: $e1aCsv"
} else {
    Write-Log "WARNING: E1a output CSV not found at $e1aCsv"
}

# Count completed checkpoints
$pythonCmd = "python -X utf8 -c `"import json,pathlib; base=pathlib.Path('checkpoints/transfer'); files=list(base.glob('**/l2_shift_results.json')); correct=sum(1 for f in files if any(isinstance(v,dict) and v.get('__seed_strategy__')=='md5_v1' for v in json.loads(f.read_text(encoding='utf-8')).values())); print(f'{correct}/60')`""
$completed = & python -X utf8 -c "import json,pathlib; base=pathlib.Path('checkpoints/transfer'); files=list(base.glob('**/l2_shift_results.json')); correct=sum(1 for f in files if any(isinstance(v,dict) and v.get('__seed_strategy__')=='md5_v1' for v in json.loads(f.read_text(encoding='utf-8')).values())); print(f'{correct}/60')" 2>&1
Write-Log "Completed checkpoints with md5_v1: $completed"

# Launch E4
Write-Log "Launching E4 (temperature analysis)..."
$e4Log = "$projectRoot\results\e4_run.log"
$e4Proc = Start-Process -FilePath "python" -ArgumentList "-X utf8 scripts/run_e4_temperature_analysis.py" -WorkingDirectory $projectRoot -RedirectStandardOutput $e4Log -RedirectStandardError "$projectRoot\results\e4_err.log" -PassThru -NoNewWindow
Write-Log "E4 started with PID $($e4Proc.Id)"

# Wait for E4 to finish
$e4Proc.WaitForExit()
Write-Log "E4 finished with exit code $($e4Proc.ExitCode)"

# Check E4 output
$e4Csv = "$projectRoot\results\e4_temperature_analysis.csv"
if (Test-Path $e4Csv) {
    Write-Log "E4 output CSV found: $e4Csv"
} else {
    Write-Log "WARNING: E4 output CSV not found"
}

# Launch E6
Write-Log "Launching E6 (reliability diagrams)..."
$e6Log = "$projectRoot\results\e6_run.log"
$e6Proc = Start-Process -FilePath "python" -ArgumentList "-X utf8 scripts/run_e6_reliability_diagrams.py" -WorkingDirectory $projectRoot -RedirectStandardOutput $e6Log -RedirectStandardError "$projectRoot\results\e6_err.log" -PassThru -NoNewWindow
Write-Log "E6 started with PID $($e6Proc.Id)"

# Wait for E6 to finish
$e6Proc.WaitForExit()
Write-Log "E6 finished with exit code $($e6Proc.ExitCode)"

Write-Log "E4 and E6 both complete. Ready for E1b and E5."
