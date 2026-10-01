param([string]$target)

Write-Host "Opening target: $target"
$app = New-Object -ComObject Shell.Application
$app.Open($target)
