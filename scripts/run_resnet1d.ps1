$env:PYTHONUNBUFFERED = "1"
Set-Location "D:\A1\ecg-lab-v2"

$pairs = @(
    @("ptbxl", "chapman", "data/ptbxl_processed", "data/chapman_processed_v2"),
    @("ptbxl", "cpsc", "data/ptbxl_processed", "data/cpsc_processed"),
    @("chapman", "ptbxl", "data/chapman_processed_v2", "data/ptbxl_processed"),
    @("chapman", "cpsc", "data/chapman_processed_v2", "data/cpsc_processed"),
    @("cpsc", "ptbxl", "data/cpsc_processed", "data/ptbxl_processed"),
    @("cpsc", "chapman", "data/cpsc_processed", "data/chapman_processed_v2")
)

$methods = @("ts", "platt", "isotonic", "vector", "matrix", "dirichlet", "em_prior", "bbse_prior")
$logFile = "logs\resnet1d_transfer.log"

foreach ($p in $pairs) {
    $src = $p[0]; $tgt = $p[1]; $sd = $p[2]; $td = $p[3]
    Add-Content $logFile "`n============================================================"
    Add-Content $logFile "resnet1d transfer: $src -> $tgt"
    Add-Content $logFile "============================================================"

    $cmd = "python scripts/eval_transfer.py --source $src --source-dir $sd --target $tgt --target-dir $td --arch resnet1d --seeds 42 43 --d-model 64 --methods $methods --bootstrap 200 --bci-method percentile --gpu-inference"
    $output = Invoke-Expression $cmd 2>&1
    $output | Out-File -FilePath $logFile -Append -Encoding UTF8
}

Add-Content $logFile "`nresnet1d 全量 transfer 实验完成。"
