$pdfs = Get-ChildItem 'D:\A1\ecg-lab-v2\paper\figures\*.pdf' | Select-Object -ExpandProperty Name
$content = Get-Content 'D:\A1\ecg-lab-v2\paper\main_bspc.tex' -Raw
$refs = [regex]::Matches($content, 'includegraphics.*\{figures/([^}]+)\}') | ForEach-Object { $_.Groups[1].Value }
Write-Output ("PDFs count: " + $pdfs.Count)
Write-Output ("Refs count: " + $refs.Count)
$unreferenced = $pdfs | Where-Object { $_ -notin $refs }
Write-Output "Unreferenced PDFs:"
$unreferenced
Write-Output "---"
$missing = $refs | Where-Object { $_ -notin $pdfs }
Write-Output "Referenced but missing PDFs:"
$missing
