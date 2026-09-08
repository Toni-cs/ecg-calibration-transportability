$ErrorActionPreference = "Stop"
Set-Location "D:\A1\ecg-lab-v2"
$py = "C:\python\python.exe"
$args = @("scripts/train.py", "--dataset", "cpsc", "--data_dir", "data/cpsc_processed",
          "--arch", "inceptiontime", "--num_classes", "4", "--epochs", "50",
          "--batch_size", "16", "--d_model", "64", "--seed", "44",
          "--save_dir", "checkpoints/cpsc_base_seed44")
$logFile = "D:\A1\ecg-lab-v2\train_cpsc_seed44.log"
$errFile = "D:\A1\ecg-lab-v2\train_cpsc_seed44.err"

try {
    $proc = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory "D:\A1\ecg-lab-v2" -RedirectStandardOutput $logFile -RedirectStandardError $errFile -PassThru -WindowStyle Hidden
    "SUCCESS PID=$($proc.Id)" | Out-File -FilePath "D:\A1\ecg-lab-v2\seed44_start_result.txt" -Encoding ascii
    $proc.Id | Out-File -FilePath "D:\A1\ecg-lab-v2\seed44_pid.txt" -Encoding ascii
} catch {
    "FAILED: $_" | Out-File -FilePath "D:\A1\ecg-lab-v2\seed44_start_result.txt" -Encoding ascii
}