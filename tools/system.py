# tools/system.py
import os
import platform

def shutdown():
    """Shutdown the computer"""
    try:
        if platform.system() == "Windows":
            os.system("shutdown /s /t 1")
        else:
            os.system("shutdown -h now")
        return "Shutting down..."
    except Exception as e:
        return f"Failed to shutdown: {str(e)}"

def get_system_info():
    """Get system information"""
    return f"System: {platform.system()} {platform.release()}"