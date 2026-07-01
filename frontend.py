import tkinter as tk
import requests
import json
from threading import Thread
BASE_URL = "http://0.0.0.0:8000"

class DroneController:
    def __init__(self, root):
        self.root = root
        self.root.title("Drone Controller")
        self.root.geometry("450x600")
        self.root.resizable(False, False)
        # Current values of all axes
        self.controls = {"throttle": 0, "yaw": 0, "pitch": 0, "roll": 0}
        # References to sliders for updating the display
        self.sliders = {}
        self.value_labels = {}
        # Debounce for sending
        self.pending_send = None
        self.send_delay_ms = 50  # Delay before sending
        # Connection flag
        self.connected = False
        self.create_widgets()
        
        # Start connection check in the background
        Thread(target=self.check_connection, daemon=True).start()

    def create_widgets(self):
        # Title
        title_label = tk.Label(self.root, text="Drone Controller", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        # Connection indicator
        self.connection_label = tk.Label(self.root, text="Connecting...", font=("Arial", 10))
        self.connection_label.pack(pady=5)
        # ARM/DISARM buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)
        
        self.arm_btn = tk.Button(btn_frame, text="ARM", bg="red", fg="white", 
                                 font=("Arial", 12, "bold"), width=10,
                                 command=lambda: self.post("/arm/"))
        self.arm_btn.pack(side=tk.LEFT, padx=5)
        
        self.disarm_btn = tk.Button(btn_frame, text="DISARM", bg="orange", 
                                    font=("Arial", 12, "bold"), width=10,
                                    command=lambda: self.post("/disarm/"))
        self.disarm_btn.pack(side=tk.LEFT, padx=5)
        # Separator
        tk.Frame(self.root, height=2, bg="gray").pack(fill=tk.X, padx=20, pady=10)
        # Sliders for sticks
        slider_frame = tk.Frame(self.root)
        slider_frame.pack(fill=tk.X, padx=20, pady=5)

        for name in ["Throttle", "Yaw", "Pitch", "Roll"]:
            # Container for slider and value
            row_frame = tk.Frame(slider_frame)
            row_frame.pack(fill=tk.X, pady=5)
            
            # Axis name
            tk.Label(row_frame, text=f"{name}:", font=("Arial", 10), width=10, anchor="w").pack(side=tk.LEFT)
            
            # Slider
            slider = tk.Scale(row_frame, from_=-255, to=255, orient=tk.HORIZONTAL,
                             length=250, showvalue=False,
                             command=lambda v, n=name: self.on_slider_change(n, v))
            slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            self.sliders[name.lower()] = slider
            
            # Display of current value
            value_label = tk.Label(row_frame, text="0", font=("Arial", 10, "bold"), width=5)
            value_label.pack(side=tk.LEFT, padx=5)
            self.value_labels[name.lower()] = value_label
            
        # Separator
        tk.Frame(self.root, height=2, bg="gray").pack(fill=tk.X, padx=20, pady=10)
        # Action buttons
        action_frame = tk.Frame(self.root)
        action_frame.pack(pady=10)
        tk.Button(action_frame, text="Hover", font=("Arial", 11), width=12,
                 command=lambda: self.post("/hover/")).pack(side=tk.LEFT, padx=5)
        
        tk.Button(action_frame, text="Neutral", font=("Arial", 11), width=12,
                 command=lambda: self.post("/neutral/")).pack(side=tk.LEFT, padx=5)
        
        tk.Button(action_frame, text="Center All", font=("Arial", 11), width=12,
                 command=self.center_all).pack(side=tk.LEFT, padx=5)

        # Status bar
        self.status_label = tk.Label(self.root, text="Ready", font=("Arial", 9), 
                                    fg="gray", anchor="w")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

    def on_slider_change(self, name, value):
        """Slider change handler with debounce"""
        value = int(value)
        axis_name = name.lower()
        # Update value in controls
        self.controls[axis_name] = value
        # Update value display
        self.value_labels[axis_name].config(text=str(value))
        # Cancel previous delayed call
        if self.pending_send:
            self.root.after_cancel(self.pending_send)
        # Start new delayed call
        self.pending_send = self.root.after(self.send_delay_ms, self.send_control)

    def send_control(self):
        """Send current controller state to the server"""
        if not self.connected:
            self.status_label.config(text="No connection to server", fg="red")
            return
        try:
            # Send ALL axis values
            response = requests.post(
                f"{BASE_URL}/controller/", 
                json=self.controls, 
                timeout=1.0  # Increased timeout
            )
            if response.status_code == 200:
                self.status_label.config(
                    text=f"Sent: T={self.controls['throttle']}, Y={self.controls['yaw']}, "
                         f"P={self.controls['pitch']}, R={self.controls['roll']}",
                    fg="green"
                )
            else:
                self.status_label.config(text=f"Server error: {response.status_code}", fg="orange")
        except requests.exceptions.Timeout:
            self.status_label.config(text="Request timeout", fg="orange")
        except requests.exceptions.ConnectionError:
            self.connected = False
            self.connection_label.config(text="Disconnected", fg="red")
            self.status_label.config(text="Lost connection to server", fg="red")
        except Exception as e:
            self.status_label.config(text=f"Error: {str(e)}", fg="red")

    def post(self, endpoint):
        """Send POST request to the specified endpoint"""
        if not self.connected:
            self.status_label.config(text="No connection to server", fg="red")
            return
        try:
            response = requests.post(f"{BASE_URL}{endpoint}", timeout=2.0)
            
            if response.status_code == 200:
                data = response.json()
                action_name = endpoint.strip('/').upper()
                self.status_label.config(text=f"{action_name} executed", fg="green")
                
                # If this is DISARM, reset all values
                if endpoint == "/disarm/":
                    self.center_all()
            else:
                self.status_label.config(text=f"Error: {response.status_code}", fg="orange")
        except requests.exceptions.Timeout:
            self.status_label.config(text="Request timeout", fg="orange")
        except requests.exceptions.ConnectionError:
            self.connected = False
            self.connection_label.config(text="Disconnected", fg="red")
            self.status_label.config(text="Lost connection to server", fg="red")
        except Exception as e:
            self.status_label.config(text=f"Error: {str(e)}", fg="red")

    def center_all(self):
        """Reset all axes to center position"""
        for axis_name in self.controls:
            self.controls[axis_name] = 0
            self.sliders[axis_name].set(0)
            self.value_labels[axis_name].config(text="0")
        
        # Send immediately, without debounce
        self.send_control()
        self.status_label.config(text="All axes centered", fg="blue")

    def check_connection(self):
        """Check connection to the server in a background thread"""
        while True:
            try:
                response = requests.get(f"{BASE_URL}/status/", timeout=2.0)
                if response.status_code == 200:
                    if not self.connected:
                        self.connected = True
                        self.root.after(0, lambda: self.connection_label.config(
                            text="Connected", fg="green"))
                        self.root.after(0, lambda: self.status_label.config(
                            text="Connection restored", fg="green"))
            except:
                if self.connected:
                    self.connected = False
                    self.root.after(0, lambda: self.connection_label.config(
                        text="Disconnected", fg="red"))
                    self.root.after(0, lambda: self.status_label.config(
                        text="Lost connection to server", fg="red"))
            # Check connection every 3 seconds
            import time
            time.sleep(3)
            
if __name__ == "__main__":
    root = tk.Tk()
    app = DroneController(root)
    root.mainloop()
