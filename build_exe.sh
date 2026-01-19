#!/bin/bash
# Bash script to build EXE files (Linux/Mac - for cross-compilation or testing)
# Usage: ./build_exe.sh [--core] [--tui] [--all]

CORE=false
TUI=false
ALL=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --core)
            CORE=true
            ALL=false
            shift
            ;;
        --tui)
            TUI=true
            ALL=false
            shift
            ;;
        --all)
            ALL=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "Building EXE files..."
echo ""

# Check if PyInstaller is installed
if ! python -m pip show pyinstaller &>/dev/null; then
    echo "Installing PyInstaller..."
    python -m pip install pyinstaller
fi

# Create dist directory if it doesn't exist
mkdir -p dist

# Build core service
if [ "$CORE" = true ] || [ "$ALL" = true ]; then
    echo "Building core service (irswitchd)..."
    pyinstaller --onefile \
        --name irswitchd \
        --collect-all irswitch \
        --distpath dist \
        --workpath build \
        --clean \
        src/irswitch/main.py
    
    if [ $? -eq 0 ]; then
        echo "✓ Core service built: dist/irswitchd"
    else
        echo "✗ Failed to build core service"
        exit 1
    fi
fi

# Build TUI
if [ "$TUI" = true ] || [ "$ALL" = true ]; then
    echo "Building TUI (irswitch-tui)..."
    pyinstaller --onefile \
        --name irswitch-tui \
        --collect-all irswitch_tui \
        --collect-all textual \
        --distpath dist \
        --workpath build \
        --clean \
        src/irswitch_tui/main.py
    
    if [ $? -eq 0 ]; then
        echo "✓ TUI built: dist/irswitch-tui"
    else
        echo "✗ Failed to build TUI"
        exit 1
    fi
fi

echo ""
echo "Build complete! Files are in dist/"
echo ""
echo "Usage:"
echo "  dist/irswitchd --config config/config.ini"
echo "  dist/irswitch-tui --url http://127.0.0.1:17321"
