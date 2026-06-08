#!/usr/bin/env bash

# Bash script to run all code quality checks for both Python and JS

# Exit immediately if a command exits with a non-zero status
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0;3m' # No Color

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}                   GIS App Quality Tooling Suite                      ${NC}"
echo -e "${BLUE}======================================================================${NC}"

# Ensure we are in the project root
cd "$(dirname "$0")/.."

# ----------------------------------------------------------------------
# 1. Python Quality Check
# ----------------------------------------------------------------------
echo -e "\n${BLUE}[1/5] Running Ruff (Linter & Formatter)...${NC}"
if command -v ruff &> /dev/null; then
    ruff check src_new/
    ruff format --check src_new/
    echo -e "${GREEN}✓ Ruff passed!${NC}"
else
    echo -e "${RED}✗ Ruff is not installed. Run 'pip install ruff' or 'conda install ruff'.${NC}"
fi

echo -e "\n${BLUE}[2/5] Running Vulture (Dead Code Analysis)...${NC}"
if command -v vulture &> /dev/null; then
    vulture
    echo -e "${GREEN}✓ Vulture passed!${NC}"
else
    echo -e "${RED}✗ Vulture is not installed. Run 'pip install vulture'.${NC}"
fi

echo -e "\n${BLUE}[3/5] Running Pyright (Static Type Checker)...${NC}"
if command -v pyright &> /dev/null; then
    pyright
    echo -e "${GREEN}✓ Pyright passed!${NC}"
else
    echo -e "${RED}✗ Pyright is not installed. Run 'npm install -g pyright' or 'pip install pyright'.${NC}"
fi

echo -e "\n${BLUE}[4/5] Running Deptry (Dependency Check)...${NC}"
if command -v deptry &> /dev/null; then
    deptry .
    echo -e "${GREEN}✓ Deptry passed!${NC}"
else
    echo -e "${RED}✗ Deptry is not installed. Run 'pip install deptry'.${NC}"
fi

# ----------------------------------------------------------------------
# 2. JS / Frontend Quality Check
# ----------------------------------------------------------------------
echo -e "\n${BLUE}[5/5] Running JS Quality Checks (ESLint + Knip)...${NC}"

if command -v npx &> /dev/null; then
    echo -e "Running ESLint..."
    npx eslint "src_new/**/*.js" --quiet || echo -e "${RED}⚠️ ESLint warnings/errors detected.${NC}"
    
    echo -e "Running Knip (Unused exports & files)...${NC}"
    npx knip || echo -e "${RED}⚠️ Knip warnings/errors detected.${NC}"
else
    echo -e "${RED}✗ Node.js/npx not found. Skipping JS (ESLint/Knip) checks.${NC}"
fi

echo -e "\n${GREEN}Quality checks completed!${NC}"
