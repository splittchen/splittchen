#!/usr/bin/env pwsh
# Multi-Architecture Build script for Splittchen Docker image
# Builds for multiple platforms: linux/amd64, linux/arm64, linux/arm/v7
#
# Usage:
#   ./build-multiarch.ps1                           # Build and push latest
#   ./build-multiarch.ps1 -Tag "v1.2.3"            # Build with version
#   ./build-multiarch.ps1 -Version "1.2.3"         # Build with semantic versioning (creates multiple tags)
#   ./build-multiarch.ps1 -Platforms "linux/amd64,linux/arm64"  # Specify platforms
#   ./build-multiarch.ps1 -LocalOnly               # Build for local platform only (no push)
#
# Requirements:
#   - Docker Buildx (included in Docker Desktop)
#   - For push: authenticated with registry (docker login)
#
# NOTE: Default registry is set for the maintainer's builds.
#       For your own builds, either:
#       1. Change the Registry parameter below to your registry
#       2. Or use: ./build-multiarch.ps1 -Registry "ghcr.io/yourusername"

param(
    [string]$Registry = "ghcr.io/splittchen",  # Maintainer's registry - change for your builds
    [string]$Tag = "latest",
    [string]$Version = "",
    [string]$Platforms = "linux/amd64,linux/arm64,linux/arm/v7",
    [switch]$LocalOnly = $false,
    [switch]$NoPush = $false
)

# Color output helpers
function Write-Info($message) { Write-Host "ℹ️  $message" -ForegroundColor Cyan }
function Write-Success($message) { Write-Host "✅ $message" -ForegroundColor Green }
function Write-Warning($message) { Write-Host "⚠️  $message" -ForegroundColor Yellow }
function Write-Error($message) { Write-Host "❌ $message" -ForegroundColor Red }

# Check if Docker is available
Write-Info "Checking Docker availability..."
$dockerVersion = docker version --format '{{.Server.Version}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker is not running or not installed"
    exit 1
}
Write-Success "Docker version: $dockerVersion"

# Check if Buildx is available
Write-Info "Checking Docker Buildx availability..."
$buildxVersion = docker buildx version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker Buildx is not available. Please install Docker Desktop or enable Buildx."
    exit 1
}
Write-Success "Buildx available: $buildxVersion"

# Create or use existing builder
$builderName = "splittchen-builder"
Write-Info "Setting up multi-architecture builder..."

$existingBuilder = docker buildx ls | Select-String $builderName
if (-not $existingBuilder) {
    Write-Info "Creating new builder: $builderName"
    docker buildx create --name $builderName --use --bootstrap
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create builder"
        exit 1
    }
    Write-Success "Builder created: $builderName"
} else {
    Write-Info "Using existing builder: $builderName"
    docker buildx use $builderName
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to use builder"
        exit 1
    }
}

# Inspect builder to show supported platforms
Write-Info "Builder capabilities:"
docker buildx inspect --bootstrap | Select-String "Platforms:"

# Determine tags to create
$Tags = @()
if ($Version) {
    # Semantic versioning - create multiple tags
    $v = $Version.TrimStart('v')
    $parts = $v.Split('.')
    if ($parts.Length -ne 3) {
        Write-Error "Version must be in format X.Y.Z (e.g., 1.2.3)"
        exit 1
    }
    $major, $minor, $patch = $parts
    
    $Tags += "v$v"           # v1.2.3
    $Tags += "v$major.$minor" # v1.2  
    $Tags += "v$major"       # v1
    $Tags += "latest"        # latest
    
    Write-Info "Creating tags for version $v`: $($Tags -join ', ')"
} else {
    $Tags += $Tag
}

# Build tag arguments for docker buildx
$tagArgs = @()
foreach ($tag in $Tags) {
    $registryTag = "$Registry/splittchen:$tag"
    $tagArgs += "--tag"
    $tagArgs += $registryTag
}

# Determine build mode
if ($LocalOnly) {
    Write-Warning "Local-only build: Building for current platform only"
    $Platforms = ""
    $loadArg = "--load"
    $pushArg = ""
} elseif ($NoPush) {
    Write-Warning "Build without push: Image will not be pushed to registry"
    $loadArg = ""
    $pushArg = ""
} else {
    Write-Info "Multi-arch build: Building for platforms: $Platforms"
    $loadArg = ""
    $pushArg = "--push"
}

# Build the command
$buildCmd = @(
    "buildx", "build"
)

if ($Platforms) {
    $buildCmd += "--platform", $Platforms
}

$buildCmd += $tagArgs

if ($loadArg) {
    $buildCmd += $loadArg
}

if ($pushArg) {
    $buildCmd += $pushArg
}

$buildCmd += "--file", "Dockerfile"
$buildCmd += "."

# Display build information
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Splittchen Multi-Architecture Build" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Registry:   $Registry" -ForegroundColor White
Write-Host "Tags:       $($Tags -join ', ')" -ForegroundColor White
if ($Platforms) {
    Write-Host "Platforms:  $Platforms" -ForegroundColor White
} else {
    Write-Host "Platforms:  Current platform only (local build)" -ForegroundColor White
}
Write-Host "Push:       $(if ($pushArg) { 'Yes' } else { 'No' })" -ForegroundColor White
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Confirm for push operations
if ($pushArg -and -not $LocalOnly) {
    Write-Warning "This will build and push images to the registry."
    $confirmation = Read-Host "Continue? (y/N)"
    if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
        Write-Info "Build cancelled by user"
        exit 0
    }
}

# Execute build
Write-Host ""
Write-Info "Starting build..."
Write-Host "Command: docker $($buildCmd -join ' ')" -ForegroundColor DarkGray
Write-Host ""

& docker $buildCmd

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed with exit code $LASTEXITCODE"
    exit 1
}

# Success message
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Success "Build completed successfully!"
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""

if ($pushArg) {
    Write-Success "Images pushed to registry:"
    foreach ($tag in $Tags) {
        Write-Host "  📦 $Registry/splittchen:$tag" -ForegroundColor White
    }
    Write-Host ""
    Write-Info "To pull the image:"
    Write-Host "  docker pull $Registry/splittchen:$($Tags[0])" -ForegroundColor White
} elseif ($LocalOnly) {
    Write-Success "Local image built:"
    Write-Host "  📦 $Registry/splittchen:$($Tags[0])" -ForegroundColor White
    Write-Host ""
    Write-Info "To run the image:"
    Write-Host "  docker run -p 5000:5000 $Registry/splittchen:$($Tags[0])" -ForegroundColor White
} else {
    Write-Warning "Images built but not pushed (use without -NoPush to push)"
}

Write-Host ""
Write-Info "To view build history:"
Write-Host "  docker buildx imagetools inspect $Registry/splittchen:$($Tags[0])" -ForegroundColor White
Write-Host ""
