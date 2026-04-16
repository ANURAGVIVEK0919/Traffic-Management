Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "🚦 LAUNCHING MASTER TRAFFIC DEMONSTRATION" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "This script perfectly automates the 10 core constraints:"
Write-Host "1. Initial 10s Cycle Rotations for all lanes"
Write-Host "2. Dynamic Green Time Upscaling (Adjust Early)"
Write-Host "3. Yellow Phase Hard Locks (Commit Late)"
Write-Host "4. Instant Ambulance Preemption & Seamless Recovery"

# Start Backend
Write-Host "`n[1/3] Booting Python Backend API..." -ForegroundColor DarkGray
Start-Process powershell -ArgumentList "-NoExit -Command `"python -m uvicorn backend.main:app --reload --port 8000`"" -WindowStyle Minimized

# Start Frontend
Write-Host "[2/3] Booting React Simulator..." -ForegroundColor DarkGray
Start-Process powershell -ArgumentList "-NoExit -Command `"cd frontend; npm start`"" -WindowStyle Minimized

Write-Host "Waiting 7 seconds for servers to map..." -ForegroundColor Yellow
Start-Sleep -Seconds 7

# Open Browser explicitly loading master scenario
Write-Host "[3/3] Firing up Master Timeline Sequence!" -ForegroundColor Green
Start-Process "http://localhost:5173/simulation?demo=true&scenario=master"
