#!/usr/bin/env python3
"""
Buddi Agent - Web Interface Launcher
Starts both backend and frontend servers in separate threads
"""

# Unused import removed
import sys
import subprocess
# Unused import removed
import time
import signal
from pathlib import Path


# Configuration
BACKEND_PORT = 8000
FRONTEND_PORT = 3000
BACKEND_HOST = "0.0.0.0"

# Global process references
backend_process = None
frontend_process = None
class Colors:
    GREEN = '\033[0;32m'
    BLUE = '\033[0;34m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'  # No Color

def print_status(message, status="info"):
    """Print status message with color"""
    if status == "success":
        print(f"{Colors.GREEN}✓ {message}{Colors.NC}")
    elif status == "error":
        print(f"{Colors.RED}❌ {message}{Colors.NC}")
    elif status == "info":
        print(f"{Colors.BLUE}ℹ {message}{Colors.NC}")
    elif status == "warning":
        print(f"{Colors.YELLOW}⚠ {message}{Colors.NC}")

def check_dependencies():
    """Check if required packages are installed"""
    try:
        pass
        return True
    except ImportError:
        return False

def install_dependencies():
    """Install required packages"""
    print_status("Installing required packages...", "info")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn[standard]"],
            check=True
        )
        print_status("Dependencies installed", "success")
        return True
    except subprocess.CalledProcessError:
        print_status("Failed to install dependencies", "error")
        return False

def start_backend():
    """Start the FastAPI backend"""
    print_status("Starting backend (FastAPI)...", "info")
    
    try:
        # Check if port is already in use
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", BACKEND_PORT))
        sock.close()
        
        if result == 0:
            print_status(f"Port {BACKEND_PORT} is already in use", "error")
            return None
        
        process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "backend.api:app",
                "--host", BACKEND_HOST,
                "--port", str(BACKEND_PORT),
                "--reload"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        time.sleep(2)  # Give server time to start
        
        if process.poll() is None:  # Process is still running
            print_status(f"Backend running on http://localhost:{BACKEND_PORT}", "success")
            return process
        else:
            stdout, stderr = process.communicate()
            print_status(f"Backend failed to start: {stderr}", "error")
            return None
            
    except Exception as e:
        print_status(f"Error starting backend: {e}", "error")
        return None

def start_frontend():
    """Start the web frontend server"""
    print_status("Starting frontend (HTTP Server)...", "info")
    
    try:
        # Change to web directory
        web_dir = Path(__file__).parent / "web"
        
        if not web_dir.exists():
            print_status(f"Web directory not found: {web_dir}", "error")
            return None
        
        # Check if port is already in use
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", FRONTEND_PORT))
        sock.close()
        
        if result == 0:
            print_status(f"Port {FRONTEND_PORT} is already in use", "error")
            return None
        
        process = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(FRONTEND_PORT)],
            cwd=str(web_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        time.sleep(1)  # Give server time to start
        
        if process.poll() is None:  # Process is still running
            print_status(f"Frontend running on http://localhost:{FRONTEND_PORT}", "success")
            return process
        else:
            stdout, stderr = process.communicate()
            print_status(f"Frontend failed to start: {stderr}", "error")
            return None
            
    except Exception as e:
        print_status(f"Error starting frontend: {e}", "error")
        return None

def cleanup(signum, frame):
    """Handle shutdown"""
    print("\n")
    print_status("Shutting down...", "warning")
    # Unused globals removed
    
    if backend_process:
        try:
            backend_process.terminate()
            backend_process.wait(timeout=5)
            print_status("Backend stopped", "success")
        except:
            backend_process.kill()
    
    if frontend_process:
        try:
            frontend_process.terminate()
            frontend_process.wait(timeout=5)
            print_status("Frontend stopped", "success")
        except:
            frontend_process.kill()
    
    sys.exit(0)

def main():
    """Main launcher function"""
    global backend_process, frontend_process
    backend_process = None
    frontend_process = None
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    print("=" * 50)
    print("   Buddi Agent - Web Interface")
    print("=" * 50)
    print()
    
    # Check dependencies
    if not check_dependencies():
        print_status("Required packages not found", "warning")
        if not install_dependencies():
            print_status("Cannot start without dependencies", "error")
            return 1
    
    print()
    
    # Start backend
    backend_process = start_backend()
    if not backend_process:
        return 1
    
    # Start frontend
    frontend_process = start_frontend()
    if not frontend_process:
        backend_process.terminate()
        return 1
    
    print()
    print("=" * 50)
    print(f"{Colors.GREEN}✓ Both servers are running!{Colors.NC}")
    print("=" * 50)
    print()
    print(f"{Colors.BLUE}Backend API:{Colors.NC}")
    print(f"  URL:  http://localhost:{BACKEND_PORT}")
    print(f"  Docs: http://localhost:{BACKEND_PORT}/docs")
    print()
    print(f"{Colors.BLUE}Frontend Web UI:{Colors.NC}")
    print(f"  URL: http://localhost:{FRONTEND_PORT}")
    print()
    print(f"{Colors.YELLOW}Press Ctrl+C to stop all servers{Colors.NC}")
    print()
    
    # Keep running
    try:
        while True:
            time.sleep(1)
            
            # Check if processes are still running
            if backend_process.poll() is not None:
                print_status("Backend process crashed!", "error")
                break
            if frontend_process.poll() is not None:
                print_status("Frontend process crashed!", "error")
                break
                
    except KeyboardInterrupt:
        pass
    finally:
        cleanup(None, None)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
