#!/bin/bash

echo "Installing diskface..."

# Function to try different installation methods
install_diskface() {
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Method 1: Try pipx (best for CLI tools - isolated environment)
    if command -v pipx &> /dev/null; then
        echo "Using pipx (recommended for CLI tools)..."
        if pipx install -e "$script_dir"; then
            echo "✅ Installed with pipx"
            return 0
        else
            echo "❌ pipx failed, trying other methods..."
        fi
    fi
    
    # Method 2: User install (doesn't require sudo, goes to ~/.local/bin)
    if command -v pip &> /dev/null; then
        PIP_CMD="pip"
    elif command -v pip3 &> /dev/null; then
        PIP_CMD="pip3"
    else
        echo "❌ Error: No pip found. Please install Python 3 and pip first."
        exit 1
    fi
    
    echo "Using: $PIP_CMD --user (user-local install)..."
    if $PIP_CMD install --user -e "$script_dir"; then
        echo "✅ Installed to user directory"
        
        # Check if ~/.local/bin is in PATH
        if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
            echo ""
            echo "⚠️  WARNING: ~/.local/bin is not in your PATH"
            echo "   Add this line to your ~/.bashrc or ~/.zshrc:"
            echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
            echo ""
            echo "   Or run this now:"
            echo "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
            echo "   source ~/.bashrc"
        fi
        return 0
    fi
    
    # Method 3: System-wide install (requires sudo)
    echo "❌ User install failed, trying system-wide install..."
    echo "🔐 This will require sudo privileges..."
    
    if sudo $PIP_CMD install -e "$script_dir"; then
        echo "✅ Installed system-wide"
        return 0
    else
        echo "❌ All installation methods failed!"
        exit 1
    fi
}

# Run the installation
install_diskface

echo ""
echo "🎉 Installation complete!"
echo ""
echo "You can now use diskface with these commands:"
echo ""
echo "  diskface                    # Run disk scan (default)"
echo "  diskface scan               # Same as above"
echo "  diskface exclude add /path  # Add exclusion pattern"
echo "  diskface exclude list       # List all exclusions"
echo "  diskface exclude remove 5   # Remove exclusion #5"
echo "  diskface settings           # Show all settings"
echo "  diskface files              # Toggle file scanning"
echo "  diskface directories        # Toggle directory scanning"
echo ""
echo "📁 Config is stored in: ~/.config/diskface/"
echo ""
echo "Test it now: diskface exclude list" 