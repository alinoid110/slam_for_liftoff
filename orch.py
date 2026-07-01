import os
import sys
import subprocess
import threading
import time
from datetime import datetime
import signal
# Paths to subsystem scripts
JOYSTICK_BACKEND = "/home/user/drone_scripts/joystick_backend.py"
JOYSTICK_FRONTEND = "/home/user/drone_scripts/frontend_tkinter.py"
SCREEN_CAPTURE = "/home/user/drone_scripts/screen_capture.py"
# ORB-SLAM3 installation paths
ORB_SLAM3_ROOT = "/home/user/ORB_SLAM3"
ORB_SLAM3_EXECUTABLE = os.path.join(ORB_SLAM3_ROOT, "Examples/Monocular/mono_euroc")
ORB_VOCABULARY = os.path.join(ORB_SLAM3_ROOT, "Vocabulary/ORBvoc.txt")
ORB_CONFIG = os.path.join(ORB_SLAM3_ROOT, "Examples/Monocular/Liftoff.yaml")
# Dataset storage location
RECORDINGS_FOLDER = "/home/user/Downloads/recordings"
processes = {}
shutdown_event = threading.Event()

def signal_handler(sig, frame):
    print("\nTermination signal received. Initiating graceful shutdown...")
    shutdown_event.set()
    cleanup_processes()
    sys.exit(0)

def cleanup_processes():
    print("Terminating managed processes...")
    for name, proc in processes.items():
        if proc.poll() is None:
            print(f"  Stopping {name} (PID: {proc.pid})")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

def get_latest_recording_folder():
    print(f"\n Searching for the latest recording in {RECORDINGS_FOLDER}...")
    if not os.path.exists(RECORDINGS_FOLDER):
        print(f"Error: Recording folder not found: {RECORDINGS_FOLDER}")
        return None
    # Filter directories by timestamp pattern
    folders = [
        f for f in os.listdir(RECORDINGS_FOLDER)
        if os.path.isdir(os.path.join(RECORDINGS_FOLDER, f)) and 
           f.startswith("20") and len(f) >= 15
    ]
    if not folders:
        print("Error: No recording directories found.")
        return None
    # Sort by name (timestamp prefix ensures chronological order)
    folders.sort(reverse=True)
    latest = folders[0]
    latest_path = os.path.join(RECORDINGS_FOLDER, latest)
    print(f"Latest recording identified: {latest}")
    print(f"  Path: {latest_path}")
    # Verify presence of required timestamps file
    timestamps_file = os.path.join(latest_path, "timestamps.txt")
    if not os.path.exists(timestamps_file):
        print(f"Warning: Required file not found: {timestamps_file}")
        alt_timestamps = os.path.join(latest_path, "mav0", "cam0", "data.csv")
        if os.path.exists(alt_timestamps):
            print(f"  Alternative file available: {alt_timestamps}")
        else:
            print("Error: timestamps.txt not found. ORB-SLAM3 execution will fail.")
            return None
    return latest_path

def run_orb_slam3(recording_path):
    if not recording_path:
        print("Error: Invalid recording path. ORB-SLAM3 execution aborted.")
        return
    timestamps_file = os.path.join(recording_path, "timestamps.txt")
    # Validate required files
    if not os.path.exists(ORB_SLAM3_EXECUTABLE):
        print(f"Error: ORB-SLAM3 executable not found: {ORB_SLAM3_EXECUTABLE}")
        return
    if not os.path.exists(ORB_VOCABULARY):
        print(f"Error: Vocabulary file not found: {ORB_VOCABULARY}")
        return
    if not os.path.exists(ORB_CONFIG):
        print(f"Error: Configuration file not found: {ORB_CONFIG}")
        return
    print(f"Executable:  {ORB_SLAM3_EXECUTABLE}")
    print(f"Vocabulary:  {ORB_VOCABULARY}")
    print(f"Config:      {ORB_CONFIG}")
    print(f"Dataset:     {recording_path}")
    print(f"Timestamps:  {timestamps_file}")
    print("=" * 80)
    cmd = [
        ORB_SLAM3_EXECUTABLE,
        ORB_VOCABULARY,
        ORB_CONFIG,
        recording_path,
        timestamps_file
    ]
    print(f"\nCommand:\n{' '.join(cmd)}\n")
    try:
        proc = subprocess.Popen(cmd, cwd=ORB_SLAM3_ROOT)
        processes["ORB-SLAM3"] = proc
        print("ORB-SLAM3 process initiated successfully.")
        print("  Press Ctrl+C to terminate ORB-SLAM3.\n")
        proc.wait()
        print("\n ORB-SLAM3 execution completed.")
        
    except FileNotFoundError as e:
        print(f"Error launching ORB-SLAM3: {e}")
    except Exception as e:
        print(f"Unexpected error during ORB-SLAM3 execution: {e}")

def run_joystick_backend():
    print("\n Launching virtual joystick backend...")
    if not os.path.exists(JOYSTICK_BACKEND):
        print(f"Warning: Backend script not found: {JOYSTICK_BACKEND}")
        print("  Skipping backend initialization.")
        return None
    try:
        proc = subprocess.Popen(
            [sys.executable, JOYSTICK_BACKEND],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes["Joystick Backend"] = proc
        # Allow time for server initialization
        time.sleep(2) 
        if proc.poll() is None:
            print("Backend service started successfully (http://0.0.0.0:8000)")
            return proc
        else:
            print("Error: Backend process terminated unexpectedly.")
            return None 
    except Exception as e:
        print(f"Error launching backend: {e}")
        return None

def run_joystick_frontend():
    print("\n Launching virtual joystick frontend...")
    if not os.path.exists(JOYSTICK_FRONTEND):
        print(f"Warning: Frontend script not found: {JOYSTICK_FRONTEND}")
        print("  Skipping frontend initialization.")
        return None
    try:
        proc = subprocess.Popen(
            [sys.executable, JOYSTICK_FRONTEND],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes["Joystick Frontend"] = proc   
        print("Frontend application started successfully.")
        return proc       
    except Exception as e:
        print(f"Error launching frontend: {e}")
        return None
        
def run_screen_capture():
    print("\n Launching screen capture subsystem...")   
    if not os.path.exists(SCREEN_CAPTURE):
        print(f"Error: Screen capture script not found: {SCREEN_CAPTURE}")
        return None 
    try:
        proc = subprocess.Popen(
            [sys.executable, SCREEN_CAPTURE],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        processes["Screen Capture"] = proc     
        print("Screen capture subsystem started successfully.")
        print("  Process output:")    
        # Monitor process output in real-time
        while True:
            if shutdown_event.is_set():
                break           
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break    
        return proc      
    except Exception as e:
        print(f"Error launching screen capture: {e}")
        return None

def main():
    print(f"Execution started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")   
    # Register signal handlers for graceful termination
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)    
    # Phase 1: Initialize control subsystem
    backend_proc = run_joystick_backend()
    time.sleep(1)   
    frontend_proc = run_joystick_frontend()
    time.sleep(1)  
    # Phase 2: Launch data acquisition (blocking)
    capture_proc = run_screen_capture()   
    print("\n Awaiting completion of data acquisition...")   
    if capture_proc:
        capture_proc.wait()    
    # Phase 3: Dataset processing
    print("PREPARING DATASET FOR ORB-SLAM3 PROCESSING")    
    latest_folder = get_latest_recording_folder()   
    if latest_folder:
        print("\n Initiating ORB-SLAM3 execution in 3 seconds...")
        time.sleep(3)
        run_orb_slam3(latest_folder)
    else:
        print("\n Warning: ORB-SLAM3 execution skipped due to missing dataset.") 
    # Phase 4: Cleanup
    print("\n" + "=" * 80)
    print("ORCHESTRATOR SHUTDOWN")
    print("=" * 80)
    cleanup_processes()
    print("All processes terminated successfully.")

if __name__ == "__main__":
    main()
