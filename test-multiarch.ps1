# Multi-Arch Build Test Script
# Validates the multi-arch build setup without pushing to registry

param(
    [switch]$Quick = $false
)

Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Splittchen Multi-Arch Build Validation" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Test 1: Check Docker
Write-Host "Test 1: Checking Docker availability..." -ForegroundColor Yellow
$dockerVersion = docker version --format '{{.Server.Version}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ FAIL: Docker is not available" -ForegroundColor Red
    exit 1
}
Write-Host "✅ PASS: Docker version $dockerVersion" -ForegroundColor Green
Write-Host ""

# Test 2: Check Buildx
Write-Host "Test 2: Checking Docker Buildx..." -ForegroundColor Yellow
$buildxVersion = docker buildx version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ FAIL: Docker Buildx is not available" -ForegroundColor Red
    exit 1
}
Write-Host "✅ PASS: Buildx available" -ForegroundColor Green
Write-Host ""

# Test 3: Check scripts exist
Write-Host "Test 3: Checking build scripts..." -ForegroundColor Yellow
$scripts = @(
    "build-multiarch.ps1",
    "make.ps1",
    "build.ps1"
)
foreach ($script in $scripts) {
    if (Test-Path $script) {
        Write-Host "✅ Found: $script" -ForegroundColor Green
    } else {
        Write-Host "❌ Missing: $script" -ForegroundColor Red
        exit 1
    }
}
Write-Host ""

# Test 4: Check documentation
Write-Host "Test 4: Checking documentation..." -ForegroundColor Yellow
$docs = @(
    "MULTIARCH.md",
    "MULTIARCH-QUICKREF.md"
)
foreach ($doc in $docs) {
    if (Test-Path $doc) {
        Write-Host "✅ Found: $doc" -ForegroundColor Green
    } else {
        Write-Host "❌ Missing: $doc" -ForegroundColor Red
        exit 1
    }
}
Write-Host ""

# Test 5: Check GitHub Actions workflow
Write-Host "Test 5: Checking GitHub Actions workflow..." -ForegroundColor Yellow
$workflow = ".github/workflows/docker-multiarch.yml"
if (Test-Path $workflow) {
    Write-Host "✅ Found: $workflow" -ForegroundColor Green
} else {
    Write-Host "❌ Missing: $workflow" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Test 6: Check Dockerfile
Write-Host "Test 6: Validating Dockerfile..." -ForegroundColor Yellow
if (Test-Path "Dockerfile") {
    Write-Host "✅ Dockerfile exists" -ForegroundColor Green
} else {
    Write-Host "❌ Dockerfile missing" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Test 7: Test make.ps1 help
Write-Host "Test 7: Testing make.ps1 help..." -ForegroundColor Yellow
$helpOutput = & .\make.ps1 help 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ make.ps1 help works" -ForegroundColor Green
} else {
    Write-Host "❌ make.ps1 help failed" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Test 8: Build test (optional, only if not Quick)
if (-not $Quick) {
    Write-Host "Test 8: Running local build test..." -ForegroundColor Yellow
    Write-Host "Building for current platform only (this may take a few minutes)..." -ForegroundColor Cyan
    
    & .\build-multiarch.ps1 -LocalOnly -Tag "test-build" -Registry "splittchen-test"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Build test passed" -ForegroundColor Green
        
        # Clean up test image
        Write-Host "Cleaning up test image..." -ForegroundColor Yellow
        docker rmi splittchen-test/splittchen:test-build 2>$null
    } else {
        Write-Host "❌ Build test failed" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
} else {
    Write-Host "Test 8: Build test skipped (use without -Quick to run)" -ForegroundColor Gray
    Write-Host ""
}

# Summary
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ All validation tests passed!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "Multi-arch build setup is ready to use!" -ForegroundColor Cyan
Write-Host ""
Write-Host "Quick commands:" -ForegroundColor White
Write-Host "  .\make.ps1 help         - Show all available commands" -ForegroundColor Gray
Write-Host "  .\make.ps1 build-local  - Fast local build" -ForegroundColor Gray
Write-Host "  .\make.ps1 test-build   - Test multi-arch build" -ForegroundColor Gray
Write-Host ""
Write-Host "Documentation:" -ForegroundColor White
Write-Host "  MULTIARCH.md            - Complete documentation" -ForegroundColor Gray
Write-Host "  MULTIARCH-QUICK-REF.md  - Quick reference card" -ForegroundColor Gray
Write-Host ""
