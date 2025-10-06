# Splittchen Multi-Arch Build Makefile
# PowerShell-based build automation for Windows
# 
# Usage: 
#   .\make.ps1 <target>
#
# Targets:
#   build-local       - Build for local platform only (fast)
#   build-multiarch   - Build multi-arch images
#   build-push        - Build and push multi-arch images
#   build-version     - Build and push with version (requires VERSION env var)
#   test-build        - Test build without push
#   clean             - Clean up builders and cache
#   inspect           - Inspect multi-arch image
#   help              - Show this help

param(
    [Parameter(Position=0)]
    [string]$Target = "help",
    
    [Parameter()]
    [string]$Version = $env:VERSION,
    
    [Parameter()]
    [string]$Registry = $env:REGISTRY
)

# Default values
if (-not $Registry) {
    $Registry = "ghcr.io/splittchen"
}

function Show-Help {
    Write-Host @"
Splittchen Multi-Arch Build Helper
===================================

Available targets:

  build-local       Build for current platform only (fastest, for local testing)
  build-multiarch   Build multi-arch images (amd64, arm64, arm/v7)
  build-push        Build and push multi-arch images to registry
  build-version     Build and push with semantic versioning
  test-build        Test build multi-arch without pushing
  clean             Clean up Docker builders and build cache
  inspect           Inspect the multi-arch manifest
  help              Show this help message

Environment Variables:

  VERSION           Version number for build-version (e.g., 1.2.3)
  REGISTRY          Container registry (default: ghcr.io/splittchen)

Examples:

  # Local development build
  .\make.ps1 build-local

  # Build and push latest
  .\make.ps1 build-push

  # Build specific version
  `$env:VERSION="1.2.3"; .\make.ps1 build-version

  # Custom registry
  `$env:REGISTRY="ghcr.io/myuser"; .\make.ps1 build-push

  # Test multi-arch build
  .\make.ps1 test-build

"@ -ForegroundColor Cyan
}

function Build-Local {
    Write-Host "Building for local platform..." -ForegroundColor Green
    & .\build-multiarch.ps1 -LocalOnly -Registry $Registry
}

function Build-MultiArch {
    Write-Host "Building multi-arch images (no push)..." -ForegroundColor Green
    & .\build-multiarch.ps1 -NoPush -Registry $Registry
}

function Build-Push {
    Write-Host "Building and pushing multi-arch images..." -ForegroundColor Green
    & .\build-multiarch.ps1 -Registry $Registry
}

function Build-Version {
    if (-not $Version) {
        Write-Host "ERROR: VERSION environment variable not set" -ForegroundColor Red
        Write-Host "Usage: `$env:VERSION='1.2.3'; .\make.ps1 build-version" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Building version $Version..." -ForegroundColor Green
    & .\build-multiarch.ps1 -Version $Version -Registry $Registry
}

function Test-Build {
    Write-Host "Testing multi-arch build..." -ForegroundColor Green
    & .\build-multiarch.ps1 -NoPush -Registry $Registry
}

function Clean-Builders {
    Write-Host "Cleaning up Docker builders and cache..." -ForegroundColor Yellow
    
    $builderName = "splittchen-builder"
    $existingBuilder = docker buildx ls | Select-String $builderName
    
    if ($existingBuilder) {
        Write-Host "Removing builder: $builderName" -ForegroundColor Yellow
        docker buildx rm $builderName
    }
    
    Write-Host "Pruning build cache..." -ForegroundColor Yellow
    docker buildx prune -af
    
    Write-Host "✅ Cleanup complete" -ForegroundColor Green
}

function Inspect-Image {
    $image = "$Registry/splittchen:latest"
    Write-Host "Inspecting image: $image" -ForegroundColor Cyan
    docker buildx imagetools inspect $image
}

# Execute target
switch ($Target.ToLower()) {
    "build-local" {
        Build-Local
    }
    "build-multiarch" {
        Build-MultiArch
    }
    "build-push" {
        Build-Push
    }
    "build-version" {
        Build-Version
    }
    "test-build" {
        Test-Build
    }
    "clean" {
        Clean-Builders
    }
    "inspect" {
        Inspect-Image
    }
    "help" {
        Show-Help
    }
    default {
        Write-Host "Unknown target: $Target" -ForegroundColor Red
        Write-Host ""
        Show-Help
        exit 1
    }
}
