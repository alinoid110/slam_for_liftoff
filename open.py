import os
import cv2
import numpy as np
from mss import MSS as MSS_class
import signal
import sys
from datetime import datetime
import threading
from queue import Queue
from pynput import keyboard
import time
from evdev import InputDevice, ecodes, list_devices
import shutil
# Output directory for recorded sessions
OUTPUT_FOLDER = "recordings"
# Video recording frame rate
VIDEO_FPS = 60
# Path to camera configuration file for Liftoff simulator
LIFTOFF_YAML_SOURCE = "/home/marksuv/ORB_SLAM3/Examples/Monocular/Liftoff.yaml"
# Set of input device axes to monitor and log
INTERESTED_AXES = {
    ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_Z,
    ecodes.ABS_RX, ecodes.ABS_RY, ecodes.ABS_RZ,
    ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y,
    ecodes.ABS_RUDDER,
}
# Suppress Qt font warnings
os.environ['QT_LOGGING_RULES'] = "qt.qpa.fonts.warning=false"

def signal_handler(sig, frame):
    print("\nTermination signal received. Shutting down...")
    sys.exit(0)

def save_frame_worker(frame_queue, frames_folder, csv_file, timestamps_file):
    with open(csv_file, 'w') as f_csv, open(timestamps_file, 'w') as f_ts:
        f_csv.write("#timestamp [ns],filename\n")
        while True:
            item = frame_queue.get()
            if item is None:
                break
            frame, ts_ns, filename = item
            img_path = os.path.join(frames_folder, filename)
            # Save frame as PNG image
            cv2.imwrite(img_path, frame)
            # Write entry to CSV metadata file
            f_csv.write(f"{ts_ns},{filename}\n")
            f_csv.flush()
            # Write timestamp to timestamps file
            f_ts.write(f"{ts_ns}\n")
            f_ts.flush()
            frame_queue.task_done()

def input_logger(input_queue, log_file):
    with open(log_file, 'w') as f:
        f.write("timestamp,ABS_X,ABS_Y,ABS_Z,ABS_RX,ABS_RY,ABS_RZ,ABS_HAT0X,ABS_HAT0Y,ABS_RUDDER\n")
        # Initialize current state for all monitored axes
        current = {code: 0 for code in INTERESTED_AXES}
        while True:
            item = input_queue.get()
            if item is None:
                break
            ts, event_type, code, value = item
            
            # Update axis state on absolute value change
            if event_type == ecodes.EV_ABS and code in INTERESTED_AXES:
                current[code] = value
            # Write complete state snapshot on synchronization event
            if event_type == ecodes.EV_SYN:
                line = ts
                for c in [ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_Z, ecodes.ABS_RX,
                         ecodes.ABS_RY, ecodes.ABS_RZ, ecodes.ABS_HAT0X, 
                         ecodes.ABS_HAT0Y, ecodes.ABS_RUDDER]:
                    line += f",{current.get(c, 0)}"
                f.write(line + "\n")
            input_queue.task_done()

def read_device(dev, input_queue):
    try:
        for event in dev.read_loop():
            if event.type in (ecodes.EV_ABS, ecodes.EV_SYN):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                input_queue.put((ts, event.type, event.code, event.value))
    except Exception:
        pass

def monitor_inputs(input_queue):
    devices = [InputDevice(path) for path in list_devices()]
    print("Input devices detected:")
    for dev in devices:
        if dev.capabilities().get(ecodes.EV_ABS):
            print(f"  {dev.name}")
            t = threading.Thread(target=read_device, args=(dev, input_queue), daemon=True)
            t.start()

def record_screen_video():
    global recording_started
    recording_started = False
    signal.signal(signal.SIGINT, signal_handler)
    # Create output directory if it does not exist
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    # Generate session identifier based on current timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_folder = os.path.join(OUTPUT_FOLDER, timestamp)
    # Create EuRoC-compatible directory structure
    frames_folder = os.path.join(session_folder, "mav0", "cam0", "data")
    auxiliary_folder = os.path.join(session_folder, "auxiliary")
    os.makedirs(frames_folder, exist_ok=True)
    os.makedirs(auxiliary_folder, exist_ok=True)
    # Define output file paths
    video_filename = os.path.join(auxiliary_folder, f"{timestamp}.mp4")
    input_txt_file = os.path.join(auxiliary_folder, f"{timestamp}_inputs.txt")
    csv_file = os.path.join(session_folder, "mav0", "cam0", "data.csv")
    timestamps_file = os.path.join(session_folder, "timestamps.txt")
    # Copy camera configuration file
    liftoff_yaml_dest = os.path.join(session_folder, "mav0", "cam0", "Liftoff.yaml")
    if os.path.exists(LIFTOFF_YAML_SOURCE):
        shutil.copy(LIFTOFF_YAML_SOURCE, liftoff_yaml_dest)
        print(f"Camera configuration file copied: Liftoff.yaml")
    else:
        print(f"Warning: Camera configuration file not found at: {LIFTOFF_YAML_SOURCE}")
    print("Screen capture ready")
    print(f"Session folder: {session_folder}")
    print("Press 'S' to START recording")
    print("Press 'Q' to EXIT")
    def on_press(key):
        """Handle keyboard input for recording control."""
        global recording_started
        try:
            if key.char.lower() == 's' and not recording_started:
                print("\nRecording started!")
                recording_started = True
            elif key.char.lower() == 'q':
                os._exit(0)
        except AttributeError:
            pass
    # Start keyboard listener for recording control
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    # Initialize queues for inter-thread communication
    frame_queue = Queue(maxsize=800)
    input_queue = Queue(maxsize=3000)
    with MSS_class() as sct:
        monitor = sct.monitors[1]
        width, height = monitor["width"], monitor["height"]
        cv2.namedWindow('Screen Capture', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Screen Capture', 960, 540)
        # Wait for user to initiate recording
        while not recording_started:
            screenshot = sct.grab(monitor)
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
            preview = cv2.resize(frame, (960, 540))
            cv2.putText(preview, "Press 'S' to START recording", (20, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 3)
            cv2.imshow('Screen Capture', preview)
            cv2.waitKey(1)
            time.sleep(0.01)
        # Transition to recording mode
        print("Recording initiated...")
        # Start background worker threads
        save_thread = threading.Thread(
            target=save_frame_worker, 
            args=(frame_queue, frames_folder, csv_file, timestamps_file), 
            daemon=True
        )
        input_thread = threading.Thread(target=input_logger, args=(input_queue, input_txt_file), daemon=True)
        save_thread.start()
        input_thread.start()
        monitor_inputs(input_queue)
        # Initialize video writer
        writer = cv2.VideoWriter(video_filename, cv2.VideoWriter_fourcc(*'mp4v'), VIDEO_FPS, (width, height))
        frame_count = 0
        start_time = datetime.now()
        try:
            # Main capture loop
            while True:
                screenshot = sct.grab(monitor)
                frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
                writer.write(frame)
                frame_count += 1
                # Generate nanosecond timestamp for frame identification
                ts_ns = time.time_ns()
                filename = f"{ts_ns}.png"
                frame_queue.put((frame.copy(), ts_ns, filename))
                # Display statistics every 200 frames
                if frame_count % 200 == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    fps = frame_count / elapsed if elapsed > 0 else 0
                    print(f"Frames: {frame_count:6d} | Time: {elapsed:5.1f}s | FPS: {fps:5.1f}")
                # Update preview window every 3rd frame
                if frame_count % 3 == 0:
                    preview = cv2.resize(frame, (960, 540))
                    cv2.putText(preview, "RECORDING", (20, 50),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 255), 3)
                    cv2.imshow('Screen Capture', preview)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        finally:
            # Clean up resources
            writer.release()
            cv2.destroyAllWindows()
            frame_queue.put(None)
            input_queue.put(None)
            save_thread.join(timeout=10)
            input_thread.join(timeout=5)
            listener.stop()
            total_time = (datetime.now() - start_time).total_seconds()
            avg_fps = frame_count / total_time if total_time > 0 else 0

if __name__ == "__main__":
    record_screen_video()
