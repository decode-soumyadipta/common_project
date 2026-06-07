#!/usr/bin/env bash
# =============================================================================
# Environment Setup Script
# =============================================================================
# Creates conda environment, installs dependencies, and builds Rust modules.
# Requirements: 13.8, 20.6, 20.7
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=========================================="
echo "Geospatial Microservices Environment Setup"
echo "=========================================="
echo "Project Root: $PROJECT_ROOT"
echo "=========================================="

# Check for conda
if ! command -v conda &> /dev/null; then
    echo "ERROR: conda command not found"
    echo ""
    echo "Installation Instructions:"
    echo "1. Install Miniconda or Anaconda from https://docs.conda.io/en/latest/miniconda.html"
    echo "2. Initialize conda: conda init bash"
    echo "3. Restart your shell"
    echo "4. Run this script again"
    exit 1
fi

# Check for environment.yml
ENV_YML="$PROJECT_ROOT/environment.yml"
if [[ ! -f "$ENV_YML" ]]; then
    echo "ERROR: environment.yml not found at $ENV_YML"
    exit 1
fi

# Extract environment name from environment.yml
CONDA_ENV_NAME=$(grep "^name:" "$ENV_YML" | awk '{print $2}')
if [[ -z "$CONDA_ENV_NAME" ]]; then
    echo "ERROR: Could not extract environment name from environment.yml"
    exit 1
fi

echo ""
echo "Step 1: Creating Conda Environment"
echo "=========================================="
echo "Environment name: $CONDA_ENV_NAME"
echo ""

# Check if environment already exists
if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
    echo "WARNING: Conda environment '$CONDA_ENV_NAME' already exists"
    read -p "Do you want to remove and recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing existing environment..."
        conda env remove -n "$CONDA_ENV_NAME" -y
    else
        echo "Skipping environment creation. Using existing environment."
        ENV_EXISTS=true
    fi
fi

if [[ "${ENV_EXISTS:-false}" != "true" ]]; then
    echo "Creating conda environment from environment.yml..."
    cd "$PROJECT_ROOT"
    conda env create -f environment.yml
    echo "✓ Conda environment created successfully"
fi

# Activate the environment
echo ""
echo "Step 2: Activating Environment"
echo "=========================================="
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV_NAME"
echo "✓ Environment activated: $CONDA_ENV_NAME"

# Install additional dependencies if requirements.txt exists
REQUIREMENTS_TXT="$PROJECT_ROOT/requirements.txt"
if [[ -f "$REQUIREMENTS_TXT" ]]; then
    echo ""
    echo "Step 3: Installing Additional Dependencies"
    echo "=========================================="
    pip install -r "$REQUIREMENTS_TXT"
    echo "✓ Additional dependencies installed"
fi

# Build Rust modules
BUILD_RUST_SCRIPT="$SCRIPT_DIR/build_rust.sh"
if [[ -f "$BUILD_RUST_SCRIPT" ]]; then
    echo ""
    echo "Step 4: Building Rust Accelerators"
    echo "=========================================="
    
    # Check for Rust
    if ! command -v cargo &> /dev/null; then
        echo "WARNING: Rust/cargo not found"
        echo ""
        echo "Rust accelerators will not be built. The system will use Python fallbacks."
        echo ""
        echo "To install Rust:"
        echo "1. Visit https://rustup.rs/"
        echo "2. Run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        echo "3. Restart your shell"
        echo "4. Run this script again"
    else
        bash "$BUILD_RUST_SCRIPT"
        echo "✓ Rust modules built successfully"
    fi
else
    echo ""
    echo "Step 4: Building Rust Accelerators"
    echo "=========================================="
    echo "WARNING: build_rust.sh not found at $BUILD_RUST_SCRIPT"
    echo "Skipping Rust build. Python fallbacks will be used."
fi

# Create .env if it doesn't exist
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/.env.example"
if [[ ! -f "$ENV_FILE" ]] && [[ -f "$ENV_EXAMPLE" ]]; then
    echo ""
    echo "Step 5: Creating .env Configuration"
    echo "=========================================="
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "✓ Created .env from .env.example"
    echo ""
    echo "IMPORTANT: Please edit $ENV_FILE and configure the required variables"
fi

# Create necessary directories
echo ""
echo "Step 6: Creating Required Directories"
echo "=========================================="
mkdir -p "$PROJECT_ROOT/data"
mkdir -p "$PROJECT_ROOT/logs"
echo "✓ Created data/ and logs/ directories"

echo ""
echo "=========================================="
echo "Environment Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Activate the environment:"
echo "   conda activate $CONDA_ENV_NAME"
echo ""
echo "2. Configure your deployment:"
echo "   Edit $ENV_FILE"
echo ""
echo "3. Start services:"
echo "   Server 1: bash $SCRIPT_DIR/deploy_server1.sh"
echo "   Server 2: bash $SCRIPT_DIR/deploy_server2.sh"
echo ""
echo "4. Start clients:"
echo "   Ingestion: bash $SCRIPT_DIR/start_ingestion_client.sh"
echo "   Search: bash $SCRIPT_DIR/start_search_client.sh"
echo ""
echo "=========================================="
