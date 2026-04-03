import subprocess
import os
import sys
import time
import socket

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def kill_port(port):
    try:
        # Find all PIDs using port (including Established and Listening)
        # We use findstr /R to match exactly :port followed by space or end of string
        cmd = f'netstat -ano | findstr /R ":{port} "'
        output = subprocess.check_output(cmd, shell=True).decode()
        pids = set()
        for line in output.strip().split('\n'):
            parts = line.strip().split()
            if len(parts) >= 5:
                pids.add(parts[-1])
        
        for pid in pids:
            if pid == "0": continue
            print(f"Cleaning up process on port {port} (PID: {pid})...")
            subprocess.run(['taskkill', '/F', '/PID', pid, '/T'], check=False, capture_output=True)
    except subprocess.CalledProcessError:
        # Port not in use, this is fine
        pass
    except Exception as e:
        print(f"Note: Cleanup on port {port} skipped: {e}")

def start_app():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")
    
    # Kill existing processes on ports 8000 and 5173
    kill_port(8000)
    kill_port(5173)
    
    # Path to backend venv python
    venv_python = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        # Try generic python if venv not found (though it should be there)
        venv_python = sys.executable

    print("--- Starting Homeschooling App ---")
    ip = get_ip()
    print(f"Local Network IP: {ip}")
    
    # 1. Start Backend
    print("Launching Backend (FastAPI)...")
    backend_proc = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=backend_dir
    )
    
    # 2. Start Frontend
    print("Launching Frontend (Vite)...")
    # Use shell=True for npm on Windows
    frontend_proc = subprocess.Popen(
        ["npm.cmd", "run", "dev"],
        cwd=frontend_dir,
        shell=True
    )
    
    print(f"\n🚀 App is being served!")
    print(f"Local:   http://localhost:5173")
    print(f"Network: http://{ip}:5173")
    print("\nPress Ctrl+C in this window to stop both servers.")
    
    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print("Backend process exited unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("Frontend process exited unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\nStopping servers...")
    finally:
        backend_proc.terminate()
        frontend_proc.terminate()
        print("Done.")

if __name__ == "__main__":
    start_app()
