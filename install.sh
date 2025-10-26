#!/bin/bash
# Local Transparency - Installation Script
# This script automates the installation of all required dependencies

set -e  # Exit on any error

echo "========================================"
echo "Local Transparency - Installation Script"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check PostgreSQL
echo "Step 1: Checking PostgreSQL..."
if command -v psql &> /dev/null; then
    POSTGRES_VERSION=$(psql --version | awk '{print $3}')
    echo -e "${GREEN}✓${NC} PostgreSQL $POSTGRES_VERSION found"
else
    echo -e "${YELLOW}⚠${NC} PostgreSQL not found"
    echo ""
    echo "PostgreSQL is required for Local Transparency."
    echo "Installation instructions:"
    echo ""
    echo "  macOS (Homebrew):"
    echo "    brew install postgresql@18"
    echo "    brew services start postgresql@18"
    echo ""
    echo "  Linux (Ubuntu/Debian):"
    echo "    sudo apt install postgresql postgresql-contrib"
    echo ""
    echo "For complete setup guide, see: DATABASE_SETUP.md"
    echo ""
    read -p "Do you want to continue without PostgreSQL? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check Python version
echo ""
echo "Step 2: Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 7 ]; then
        echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION found"
    else
        echo -e "${RED}✗${NC} Python 3.7+ required, found $PYTHON_VERSION"
        exit 1
    fi
else
    echo -e "${RED}✗${NC} Python 3 not found"
    echo "Please install Python 3.7+ from:"
    echo "  macOS: brew install python3"
    echo "  Linux: sudo apt install python3 python3-pip"
    exit 1
fi

# Check pip
echo ""
echo "Step 3: Checking pip..."
if command -v pip3 &> /dev/null; then
    echo -e "${GREEN}✓${NC} pip3 found"
else
    echo -e "${RED}✗${NC} pip3 not found"
    echo "Please install pip3"
    exit 1
fi

# Install Python dependencies
echo ""
echo "Step 4: Installing Python dependencies..."
echo "This may take a few minutes..."
echo "Installing: playwright, httpx, psycopg2-binary (PostgreSQL adapter), mitmproxy"
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Python packages installed successfully"
    
    # Verify psycopg2-binary installation
    echo ""
    echo "Verifying PostgreSQL adapter..."
    python3 -c "import psycopg2; print('${GREEN}✓${NC} psycopg2-binary installed')" 2>/dev/null || \
        echo -e "${YELLOW}⚠${NC} psycopg2-binary may not be installed correctly"
else
    echo -e "${RED}✗${NC} Failed to install Python packages"
    exit 1
fi

# Install Chromium browser
echo ""
echo "Step 5: Installing Chromium browser..."
echo "This will download ~300MB..."
playwright install chromium

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Chromium browser installed successfully"
else
    echo -e "${RED}✗${NC} Failed to install Chromium browser"
    exit 1
fi

# Test installation
echo ""
echo "Step 6: Testing installation..."
python3 google_ads_transparency_scraper.py --help > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Installation test passed"
else
    echo -e "${RED}✗${NC} Installation test failed"
    exit 1
fi

# Success summary
echo ""
echo "========================================"
echo -e "${GREEN}✓ Installation Complete!${NC}"
echo "========================================"
echo ""
echo "Installed components:"
echo "  • Python packages (playwright, httpx, psycopg2-binary)"
echo "  • Chromium browser"
echo ""

# Check PostgreSQL status
if command -v psql &> /dev/null; then
    echo -e "${GREEN}✓${NC} PostgreSQL is installed"
    echo ""
    echo -e "${BLUE}Next step: Set up PostgreSQL database${NC}"
    echo "  See DATABASE_SETUP.md for complete instructions"
    echo ""
    echo "Quick setup:"
    echo "  psql postgres"
    echo "  CREATE DATABASE local_transparency;"
    echo "  CREATE USER transparency_user WITH PASSWORD 'your_password';"
    echo "  GRANT ALL PRIVILEGES ON DATABASE local_transparency TO transparency_user;"
else
    echo -e "${YELLOW}⚠${NC} PostgreSQL is not installed"
    echo ""
    echo "To install PostgreSQL:"
    echo "  macOS: brew install postgresql@18"
    echo "  Linux: sudo apt install postgresql postgresql-contrib"
    echo ""
    echo "See DATABASE_SETUP.md for complete instructions"
fi

echo ""
echo "Optional: Install mitmproxy for traffic measurement"
echo "  pip3 install mitmproxy"
echo ""
echo "Quick start:"
echo "  python3 google_ads_transparency_scraper.py --help"
echo "  python3 stress_test_scraper.py --help"
echo ""
echo "Documentation:"
echo "  • START_HERE.md - Getting started guide"
echo "  • DATABASE_SETUP.md - PostgreSQL setup"
echo "  • README.md - Complete documentation"
echo ""

