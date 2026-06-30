# start_local.ps1
# รันบอท PM2.5 + เปิด Cloudflare tunnel แล้วแสดง URL สำหรับตั้ง Webhook
# วิธีใช้: คลิกขวาที่ไฟล์ > Run with PowerShell  หรือพิมพ์  ./start_local.ps1
$proj = $PSScriptRoot
$py = Join-Path $proj ".venv\Scripts\python.exe"

$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) {
  foreach ($p in @("$env:ProgramFiles\cloudflared\cloudflared.exe", "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe")) {
    if (Test-Path $p) { $cf = $p; break }
  }
}
if (-not $cf) { Write-Host "ไม่พบ cloudflared — ติดตั้งด้วย:  winget install Cloudflare.cloudflared" -ForegroundColor Red; exit 1 }

Remove-Item (Join-Path $proj "cf.log") -ErrorAction SilentlyContinue
Start-Process -FilePath $py -ArgumentList "app.py" -WorkingDirectory $proj -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $proj "app.out.log") -RedirectStandardError (Join-Path $proj "app.err.log")
Start-Sleep -Seconds 3
Start-Process -FilePath $cf -ArgumentList "tunnel", "--url", "http://localhost:5000", "--logfile", (Join-Path $proj "cf.log"), "--loglevel", "info" -WindowStyle Hidden

$url = $null
for ($i = 0; $i -lt 45; $i++) {
  Start-Sleep -Seconds 1
  $log = Join-Path $proj "cf.log"
  if (Test-Path $log) {
    $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($m) { $url = $m.Matches[0].Value; break }
  }
}

Write-Host ""
if ($url) {
  Write-Host "บอทพร้อมแล้ว! นำ URL นี้ไปตั้งใน LINE Developers > Messaging API > Webhook URL:" -ForegroundColor Green
  Write-Host "    $url/callback" -ForegroundColor Yellow
  Write-Host "หมายเหตุ: URL นี้เป็นแบบชั่วคราว จะเปลี่ยนทุกครั้งที่รันสคริปต์ใหม่ ต้องอัปเดตใน LINE ใหม่ทุกครั้ง"
} else {
  Write-Host "ยังไม่ได้ URL — ลองเปิดไฟล์ cf.log เพื่อดูสาเหตุ" -ForegroundColor Red
}
