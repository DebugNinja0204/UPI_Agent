# UPI Agent Demo Setup Script
# Run this script before your demo to ensure everything is ready

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "UPI Dispute Resolution Agent - Demo Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if we're in the right directory
if (-not (Test-Path "requirements.txt")) {
    Write-Host "❌ Error: requirements.txt not found!" -ForegroundColor Red
    Write-Host "Please run this script from the upi_agent directory" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Run: cd C:\Users\nisha\Desktop\upi_agent" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Found upi_agent directory" -ForegroundColor Green
Write-Host ""

# Step 1: Check Python
Write-Host "Step 1: Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python installed: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found! Please install Python 3.8+" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 2: Install dependencies
Write-Host "Step 2: Installing dependencies..." -ForegroundColor Yellow
Write-Host "(This may take 1-2 minutes)" -ForegroundColor Gray
pip install -r requirements.txt --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Dependencies installed successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 3: Clean old database
Write-Host "Step 3: Cleaning old database..." -ForegroundColor Yellow
if (Test-Path "instance") {
    Remove-Item -Path "instance\*.db" -Force -ErrorAction SilentlyContinue
    Write-Host "✅ Old database removed" -ForegroundColor Green
} else {
    Write-Host "✅ No old database to remove" -ForegroundColor Green
}
Write-Host ""

# Step 4: Seed database
Write-Host "Step 4: Seeding database with sample data..." -ForegroundColor Yellow
python seed_data.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Database seeded successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to seed database" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 5: Check ports
Write-Host "Step 5: Checking if required ports are available..." -ForegroundColor Yellow
$portsToCheck = @(5000, 5001, 5002)
$portsInUse = @()

foreach ($port in $portsToCheck) {
    $connection = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($connection) {
        $portsInUse += $port
        Write-Host "⚠️  Port $port is in use" -ForegroundColor Yellow
    } else {
        Write-Host "✅ Port $port is available" -ForegroundColor Green
    }
}

if ($portsInUse.Count -gt 0) {
    Write-Host ""
    Write-Host "⚠️  Warning: Some ports are in use!" -ForegroundColor Yellow
    Write-Host "You may need to stop these processes before starting the demo:" -ForegroundColor Yellow
    foreach ($port in $portsInUse) {
        Write-Host "  Port $port" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "To kill process on port (example for 5000):" -ForegroundColor Yellow
    Write-Host "  netstat -ano | findstr :5000" -ForegroundColor Gray
    Write-Host "  taskkill /PID <PID> /F" -ForegroundColor Gray
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ SETUP COMPLETE!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Your system is ready for demo!" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Open 4 PowerShell terminals" -ForegroundColor White
Write-Host "2. Run these commands in separate terminals:" -ForegroundColor White
Write-Host ""
Write-Host "   Terminal 1: python run.py" -ForegroundColor Cyan
Write-Host "   Terminal 2: python run_mock_bank.py" -ForegroundColor Cyan
Write-Host "   Terminal 3: python run_mock_merchant.py" -ForegroundColor Cyan
Write-Host "   Terminal 4: python run_agent.py daemon --delay 5" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Open dashboard: http://localhost:5000/dashboard" -ForegroundColor White
Write-Host ""
Write-Host "📄 See QUICK_DEMO_CARD.md for complete demo script" -ForegroundColor Yellow
Write-Host "📚 See TESTING_GUIDE.md for detailed testing scenarios" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
