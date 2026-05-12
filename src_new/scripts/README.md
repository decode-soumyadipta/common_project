# Deployment and Startup Scripts

This directory contains all deployment and startup scripts for the Geospatial Microservices system.

## Overview

The scripts are organized into three categories:

1. **Service Startup Scripts** - Start individual backend services
2. **Client Startup Scripts** - Start desktop applications
3. **Deployment Scripts** - Deploy services to servers
4. **Setup Scripts** - Environment setup and configuration

## Prerequisites

Before running any scripts, ensure you have:

1. **Conda** installed (Miniconda or Anaconda)
2. **Environment configured** - Run `setup_environment.sh` first
3. **.env file** - Copy `.env.example` to `.env` and configure

## Quick Start

### Initial Setup

```bash
# 1. Run the environment setup script
bash src_new/scripts/setup_environment.sh

# 2. Configure your .env file
cp .env.example .env
# Edit .env with your configuration

# 3. Activate the conda environment
conda activate offline-3d-gis
```

### Starting Services

#### Option 1: Deploy to Two Servers (Production)

**Server 1** (Ingestion + Tile Serving):
```bash
bash src_new/scripts/deploy_server1.sh
```

**Server 2** (Query Processing):
```bash
bash src_new/scripts/deploy_server2.sh
```

#### Option 2: Start Services Individually (Development)

```bash
# Start Ingestion Service (port 8001)
bash src_new/scripts/start_ingestion_service.sh

# Start Tile Service (port 8002)
bash src_new/scripts/start_tile_service.sh

# Start Query Service (port 8003)
bash src_new/scripts/start_query_service.sh
```

### Starting Desktop Clients

```bash
# Start Ingestion Client (for data managers)
bash src_new/scripts/start_ingestion_client.sh

# Start Search Client (for analysts)
bash src_new/scripts/start_search_client.sh
```

## Script Reference

### setup_environment.sh

**Purpose**: Creates conda environment, installs dependencies, and builds Rust modules.

**Usage**:
```bash
bash src_new/scripts/setup_environment.sh
```

**What it does**:
- Creates the `offline-3d-gis` conda environment from `environment.yml`
- Installs Python dependencies
- Builds Rust accelerators (if Rust is installed)
- Creates `.env` from `.env.example` (if needed)
- Creates required directories (`data/`, `logs/`)

**Requirements**: conda, environment.yml

---

### start_ingestion_service.sh

**Purpose**: Starts the Ingestion Service (FastAPI) on Server 1.

**Usage**:
```bash
bash src_new/scripts/start_ingestion_service.sh
```

**Required Environment Variables**:
- `API_HOST` - Host interface to bind to
- `INGESTION_SERVICE_PORT` - Port number (default: 8001)
- `DATA_ROOT` - Root directory for geospatial data
- `DATABASE_URL` - Database connection string

**What it does**:
- Sources `.env` file
- Activates conda environment
- Validates required environment variables
- Sets GDAL environment variables
- Starts uvicorn server with the Ingestion Service

**Requirements**: 13.1, 13.8, 20.6, 20.7

---

### start_tile_service.sh

**Purpose**: Starts the Tile Service (TiTiler) on Server 1.

**Usage**:
```bash
bash src_new/scripts/start_tile_service.sh
```

**Required Environment Variables**:
- `API_HOST` - Host interface to bind to
- `TILE_SERVICE_PORT` - Port number (default: 8002)
- `DATA_ROOT` - Root directory for geospatial data

**What it does**:
- Sources `.env` file
- Validates required environment variables
- Sets GDAL environment variables
- Starts uvicorn server with the Tile Service

**Requirements**: 13.2, 13.8, 20.6, 20.7

---

### start_query_service.sh

**Purpose**: Starts the Query Service (FastAPI) on Server 2.

**Usage**:
```bash
bash src_new/scripts/start_query_service.sh
```

**Required Environment Variables**:
- `API_HOST` - Host interface to bind to
- `QUERY_SERVICE_PORT` - Port number (default: 8003)
- `DATABASE_URL` - Database connection string

**What it does**:
- Sources `.env` file
- Validates required environment variables
- Starts uvicorn server with the Query Service

**Requirements**: 13.3, 13.8, 20.6, 20.7

---

### start_ingestion_client.sh

**Purpose**: Starts the Desktop Ingestion Client (PySide6 application).

**Usage**:
```bash
bash src_new/scripts/start_ingestion_client.sh
```

**Required Environment Variables**:
- `INGESTION_SERVICE_URL` - URL of the Ingestion Service
- `TILE_SERVICE_URL` - URL of the Tile Service

**What it does**:
- Sources `.env` file
- Validates required environment variables
- Starts the desktop ingestion client

**Requirements**: 13.4, 13.8, 20.6, 20.7

---

### start_search_client.sh

**Purpose**: Starts the Desktop Search Client (PySide6 + CesiumJS application).

**Usage**:
```bash
bash src_new/scripts/start_search_client.sh
```

**Required Environment Variables**:
- `QUERY_SERVICE_URL` - URL of the Query Service
- `TILE_SERVICE_URL` - URL of the Tile Service
- `CESIUM_BASE_URL` - Base URL for CesiumJS assets

**What it does**:
- Sources `.env` file
- Validates required environment variables
- Starts the desktop search client

**Requirements**: 13.5, 13.8, 20.6, 20.7

---

### deploy_server1.sh

**Purpose**: Deploys both Ingestion Service and Tile Service on Server 1.

**Usage**:
```bash
bash src_new/scripts/deploy_server1.sh
```

**What it does**:
- Starts Ingestion Service in background
- Starts Tile Service in background
- Logs PIDs to `logs/server1.pids`
- Redirects service logs to `logs/ingestion_service.log` and `logs/tile_service.log`
- Exits with non-zero status if either service fails to start
- Provides cleanup on failure

**Stopping Services**:
```bash
# Using PIDs directly
kill <INGESTION_PID> <TILE_PID>

# Using PID file
while IFS=: read service pid; do kill $pid; done < logs/server1.pids
```

**Requirements**: 13.6, 13.8

---

### deploy_server2.sh

**Purpose**: Deploys the Query Service on Server 2.

**Usage**:
```bash
bash src_new/scripts/deploy_server2.sh
```

**What it does**:
- Starts Query Service in foreground
- Exits with non-zero status if service fails to start

**Requirements**: 13.7, 13.8

---

### build_rust.sh

**Purpose**: Builds Rust accelerator modules for performance-critical operations.

**Usage**:
```bash
bash src_new/scripts/build_rust.sh
```

**What it does**:
- Compiles Rust modules using PyO3
- Creates Python-importable `.so`/`.pyd` files
- Falls back to Python implementations if Rust is unavailable

**Requirements**: Rust toolchain (cargo), PyO3

---

## Error Handling

All scripts include comprehensive error handling:

1. **Missing .env file** - Clear instructions to create from `.env.example`
2. **Missing environment variables** - Lists all missing variables
3. **Missing conda environment** - Instructions to run `setup_environment.sh`
4. **Service startup failures** - Logs error details and exits with non-zero status
5. **Missing dependencies** - Installation instructions for conda, Rust, etc.

## Logging

Service logs are written to the `logs/` directory:

- `logs/ingestion_service.log` - Ingestion Service output
- `logs/tile_service.log` - Tile Service output
- `logs/server1.pids` - PIDs of Server 1 services

## Environment Variables

All scripts source environment variables from `.env` in the project root. See `.env.example` for a complete list of available variables.

### Critical Variables

| Variable | Description | Used By |
|----------|-------------|---------|
| `API_HOST` | Host interface for services | All services |
| `INGESTION_SERVICE_PORT` | Ingestion Service port | Ingestion Service |
| `TILE_SERVICE_PORT` | Tile Service port | Tile Service |
| `QUERY_SERVICE_PORT` | Query Service port | Query Service |
| `DATA_ROOT` | Geospatial data directory | Ingestion, Tile Services |
| `DATABASE_URL` | Database connection string | Ingestion, Query Services |
| `INGESTION_SERVICE_URL` | Ingestion Service URL | Ingestion Client |
| `QUERY_SERVICE_URL` | Query Service URL | Search Client |
| `TILE_SERVICE_URL` | Tile Service URL | Both Clients |
| `CESIUM_BASE_URL` | CesiumJS assets URL | Search Client |

## Deployment Topologies

### Same-Machine Development

All services and clients run on the same machine:

```bash
# Terminal 1: Start all services
bash src_new/scripts/start_ingestion_service.sh &
bash src_new/scripts/start_tile_service.sh &
bash src_new/scripts/start_query_service.sh &

# Terminal 2: Start clients as needed
bash src_new/scripts/start_ingestion_client.sh
bash src_new/scripts/start_search_client.sh
```

### Two-Server Production

**Server 1** (Ingestion + Tile Serving):
```bash
bash src_new/scripts/deploy_server1.sh
```

**Server 2** (Query Processing):
```bash
bash src_new/scripts/deploy_server2.sh
```

**Client Workstations**:
```bash
# Data manager workstation
bash src_new/scripts/start_ingestion_client.sh

# Analyst workstation
bash src_new/scripts/start_search_client.sh
```

## Troubleshooting

### Service Won't Start

1. Check the log file in `logs/` directory
2. Verify all required environment variables are set in `.env`
3. Ensure the conda environment is activated
4. Check that ports are not already in use

### Import Errors

1. Ensure you're running scripts from the project root
2. Verify the conda environment is activated
3. Check that all dependencies are installed

### Rust Build Failures

1. Rust accelerators are optional - the system will use Python fallbacks
2. Install Rust from https://rustup.rs/ if you want performance optimizations
3. Re-run `setup_environment.sh` after installing Rust

### Database Connection Errors

1. Verify `DATABASE_URL` in `.env` is correct
2. For PostGIS, ensure PostgreSQL is running and accessible
3. For SQLite, ensure the database file path is writable

## See Also

- [DEPLOYMENT.md](../docs/DEPLOYMENT.md) - Detailed deployment guide
- [CONFIGURATION.md](../docs/CONFIGURATION.md) - Configuration reference
- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) - System architecture overview
