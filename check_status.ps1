chcp 65001
echo "========================================"
echo "  实验进度 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
echo "========================================"
echo ""
$bgFile = "C:\Users\Administrator\AppData\Local\Temp\tool_call_01750d86800349caaa14a7a6_output.log"
$bgContent = Get-Content $bgFile -ErrorAction SilentlyContinue
$progressLines = $bgContent | Where-Object { $_ -match '\[\d+/62\]' }
$tLines = $bgContent | Where-Object { $_ -match 'T_global' }
$completed = if ($tLines) { $tLines.Count } else { 0 }
Write-Output "E4: $completed/62 ($([math]::Round($completed/62*100,1))%)"
if ($progressLines) { Write-Output "  当前: $($progressLines[-1])" }
$proc = Get-Process -Id 20636 -ErrorAction SilentlyContinue
if ($proc) {
    $elapsed = (Get-Date) - $proc.StartTime
    if ($completed -gt 0) {
        $perCkpt = $elapsed.TotalMinutes / $completed
        $remainMin = (62 - $completed) * $perCkpt
        Write-Output "  预计完成: $((Get-Date).AddMinutes($remainMin).ToString('MM-dd HH:mm'))"
    }
}
echo ""
echo "后续队列:"
if (Test-Path "D:\A1\ecg-lab-v2\results\auto_chain.log") {
    Get-Content "D:\A1\ecg-lab-v2\results\auto_chain.log" -Tail 5
}
echo ""
echo "已完成: E1a✅ E2✅ E3✅"
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object { Write-Output "  PID=$($_.Id) CPU=$([math]::Round($_.CPU))s" }
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
