# Screen Capture Tool - Build Script with Icon
# This script creates an executable file with a custom icon

import subprocess
import sys
import os

def install_pyinstaller():
    """Install PyInstaller if not already installed"""
    print("Installing PyInstaller...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✓ PyInstaller installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("✗ Failed to install PyInstaller")
        return False

def create_icon():
    """Create icon using the icon generator script"""
    print("\nCreating application icon...")
    
    icon_file = os.path.join(os.path.dirname(__file__), 'screen_capture_icon.ico')
    
    # Check if icon already exists
    if os.path.exists(icon_file):
        print(f"✓ Icon already exists: {icon_file}")
        return icon_file
    
    # Create icon
    try:
        subprocess.check_call([sys.executable, "create_icon.py"])
        if os.path.exists(icon_file):
            return icon_file
        else:
            print("⚠ Icon creation completed but file not found")
            return None
    except subprocess.CalledProcessError as e:
        print(f"⚠ Could not create icon: {e}")
        print("Building without custom icon...")
        return None

def create_executable(icon_path=None):
    """Create executable using PyInstaller"""
    print("\nCreating executable file...")
    
    # Base PyInstaller command
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",  # Single executable file
        "--windowed",  # No console window
        "--name=ScreenCaptureTool",  # Name of the executable
        "--clean",  # Clean build cache
    ]
    
    # Add icon if available
    if icon_path and os.path.exists(icon_path):
        cmd.append(f"--icon={icon_path}")
        print(f"Using icon: {icon_path}")
    else:
        print("Building without custom icon")
    
    # Add the Python script
    cmd.append("screen_capture_tool.py")
    
    try:
        subprocess.check_call(cmd)
        print("\n" + "=" * 60)
        print("✓ Executable created successfully!")
        print("=" * 60)
        print("Location: dist\\ScreenCaptureTool.exe")
        print("\nYou can now run the executable by double-clicking it.")
        if icon_path:
            print("The executable includes your custom camera icon!")
        print("=" * 60)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Failed to create executable: {e}")
        return False

def main():
    print("=" * 60)
    print("Screen Capture Tool - Executable Builder (With Icon)")
    print("=" * 60)
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print("✓ PyInstaller is already installed")
    except ImportError:
        print("PyInstaller not found")
        if not install_pyinstaller():
            return
    
    # Create icon
    icon_path = create_icon()
    
    # Create executable
    if create_executable(icon_path):
        print("\nBuild completed successfully!")
        if icon_path:
            print(f"Icon file: {icon_path}")
    else:
        print("\nBuild failed. Please check the error messages above.")

if __name__ == "__main__":
    main()
