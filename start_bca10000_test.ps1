$ErrorActionPreference = "Stop"
Set-Location "D:\A1\ecg-lab-v2"
$py = "C:\python\python.exe"
# B=10000 percentile 快速测试：单对 cpsc->ptbxl, seed 42, --load-model
$args = @("scripts/eval_transfer.py",
          "--source", "cpsc", "--source-dir", "data/cpsc_processed",
          "--target", "ptbxl", "--target-dir", "data/ptbxl_processed",
          "--arch", "inceptiontime", "--seeds", "42", "--load-model",
          "--methods", "ts", "platt",
          "--bootstrap", "10000", "--bci-method", "percentile",
          "--gpu-inference",
          "--save-dir", "checkpoints/transfer")
$logFile = "D:\A1\ecg-lab-v2\bca10000_test.log"
$errFile = "D:\A1\ecg-lab-v2\bca10000_test.err"

try {
    $proc = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory "D:\A1\ecg-lab-v2" -RedirectStandardOutput $logFile -RedirectStandardError $errFile -PassThru -WindowStyle Hidden
    "SUCCESS PID=$($proc.Id)" | Out-File -FilePath "D:\A1\ecg-lab-v2\bca10000_test_start.txt" -Encoding ascii
    $proc.Id | Out-File -FilePath "D:\A1\ecg-lab-v2\bca10000_test_pid.txt" -Encoding ascii
} catch {
    "FAILED: $_" | Out-File -FilePath "D:\A1\ecg-lab-v2\bca10000_test_start.txt" -Encoding ascii
}