#!/bin/bash

# Sunnat Collection POS System - Setup Script
# This script sets up the development environment

echo "========================================="
echo "Sunnat Collection POS System Setup"
echo "========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✓ Python $PYTHON_VERSION found"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env configuration file..."
    cp .env.example .env
    echo "✓ .env file created"
    echo "  Please edit .env with your configuration"
else
    echo ""
    echo "✓ .env file already exists"
fi

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p backups logs static/uploads static/receipts static/reports
echo "✓ Directories created"

# Initialize database
echo ""
echo "Initializing database..."
export FLASK_APP=run.py
flask init-db || python run.py init-db

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Run the application: python run.py"
echo "4. Open browser: http://localhost:5000"
echo "5. Login with: username=admin, password=admin123"
echo ""
echo "IMPORTANT: Change the admin password after first login!"
echo ""
