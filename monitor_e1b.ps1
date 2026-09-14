# 后台监控脚本：等待 PID 20916 结束，然后写入完成标志
$pid_target = 20916
$flag = "D:\A1\ecg-lab-v2\results\e1b_done.flag"
$log = "D:\A1\ecg-lab-v2\results\e1b_loco_run.log"
$csv = "D:\A1\ecg-lab-v2\results\deployment_loco_validation.csv"
$json = "D:\A1\ecg-lab-v2\results\deployment_loco_validation.json"

# 等待进程结束（最多 6 小时）
for ($i=0; $i -lt 720; $i++) {
    Start-Sleep -Seconds 30
    $p = Get-Process -Id $pid_target -ErrorAction SilentlyContinue
    if (-not $p) {
        # 进程结束，收集信息
        $logInfo = Get-Item $log -ErrorAction SilentlyContinue
        $csvInfo = Get-Item $csv -ErrorAction SilentlyContinue
        $jsonInfo = Get-Item $json -ErrorAction SilentlyContinue
        $result = @{
            status = "exited"
            exit_time = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            log_len = if ($logInfo) { $logInfo.Length } else { 0 }
            log_mtime = if ($logInfo) { $logInfo.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }
            csv_len = if ($csvInfo) { $csvInfo.Length } else { 0 }
            csv_mtime = if ($csvInfo) { $csvInfo.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }
            json_len = if ($jsonInfo) { $jsonInfo.Length } else { 0 }
            json_mtime = if ($jsonInfo) { $jsonInfo.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }
        }
        $result | ConvertTo-Json | Out-File -FilePath $flag -Encoding UTF8
        break
    }
}
