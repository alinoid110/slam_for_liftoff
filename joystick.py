from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, conint, Field
import uinput
import asyncio
app = FastAPI(title="Drone Virtual Joystick", version="2.3")
# CONSTANTS AND CONFIGURATION
# Axis value range for primary control axes
AXIS_MIN = -255
AXIS_MAX = 255
# ARM mechanism configuration (mimicking physical controller behavior)
ARM_AXIS_MIN = 0
ARM_AXIS_MAX = 2047
ARM_AXIS = uinput.ABS_RUDDER
ARM_BUTTON = uinput.BTN_EAST

# DATA MODELS
class DroneControl(BaseModel):
    throttle: conint(ge=AXIS_MIN, le=AXIS_MAX) = Field(0, description="Throttle axis (left stick vertical)")
    yaw: conint(ge=AXIS_MIN, le=AXIS_MAX) = Field(0, description="Yaw axis (left stick horizontal)")
    pitch: conint(ge=AXIS_MIN, le=AXIS_MAX) = Field(0, description="Pitch axis (right stick vertical)")
    roll: conint(ge=AXIS_MIN, le=AXIS_MAX) = Field(0, description="Roll axis (right stick horizontal)")

class ButtonAction(BaseModel):
    button: str
    pressed: bool = True
# Define device capabilities: absolute axes and buttons
events = (
    # Primary control axes (standard for flight simulators)
    uinput.ABS_X + (AXIS_MIN, AXIS_MAX, 0, 0),    # Roll axis
    uinput.ABS_Y + (AXIS_MIN, AXIS_MAX, 0, 0),    # Pitch axis
    uinput.ABS_Z + (AXIS_MIN, AXIS_MAX, 0, 0),    # Throttle axis
    uinput.ABS_RX + (AXIS_MIN, AXIS_MAX, 0, 0),   # Yaw axis (primary)
    uinput.ABS_RY + (AXIS_MIN, AXIS_MAX, 0, 0),   # Reserved axis
    uinput.ABS_RZ + (AXIS_MIN, AXIS_MAX, 0, 0),   # Yaw axis (duplicate for compatibility)
    # ARM mechanism axis
    uinput.ABS_RUDDER + (ARM_AXIS_MIN, ARM_AXIS_MAX, 0, 0),
    # Digital buttons
    uinput.BTN_NORTH,
    uinput.BTN_EAST,    # ARM button
    uinput.BTN_SOUTH,
    uinput.BTN_WEST,
    uinput.BTN_START,
    uinput.BTN_SELECT,
    uinput.BTN_TL,
    uinput.BTN_TR,
    uinput.BTN_THUMBL,
    uinput.BTN_THUMBR,
)
# Initialize virtual device with specified capabilities
device = uinput.Device(events, name="Betafpv LiteRadio 2 SE Virtual")

# Mapping from string identifiers to uinput button codes
BUTTON_MAP = {
    "arm": uinput.BTN_EAST,
    "switch_a": uinput.BTN_EAST,
    "switch_b": uinput.BTN_NORTH,
    "switch_c": uinput.BTN_SOUTH,
    "switch_d": uinput.BTN_WEST,
    "start": uinput.BTN_START,
    "select": uinput.BTN_SELECT,
    "l_bumper": uinput.BTN_TL,
    "r_bumper": uinput.BTN_TR,
    "thumb_l": uinput.BTN_THUMBL,
    "thumb_r": uinput.BTN_THUMBR,
}

# HELPER FUNCTIONS
def _send_axes(throttle: int, yaw: int, pitch: int, roll: int):

    device.emit(uinput.ABS_Z, throttle, syn=False)    # Throttle
    device.emit(uinput.ABS_RX, yaw, syn=False)        # Yaw (primary)
    device.emit(uinput.ABS_RZ, yaw, syn=False)        # Yaw (duplicate)
    device.emit(uinput.ABS_X, roll, syn=False)        # Roll
    device.emit(uinput.ABS_Y, pitch, syn=True)        # Pitch (with sync)

def _send_arm_state(armed: bool):
    if armed:
        device.emit(ARM_AXIS, ARM_AXIS_MAX, syn=False)
        device.emit(ARM_BUTTON, 1, syn=True)
    else:
        device.emit(ARM_AXIS, ARM_AXIS_MIN, syn=False)
        device.emit(ARM_BUTTON, 0, syn=True)

def _safe_start_state():
    _send_axes(throttle=0, yaw=0, pitch=0, roll=0)
    _send_arm_state(False)

# Initialize device to safe state upon module load
_safe_start_state()
# REST API ENDPOINTS
@app.post("/controller/")
async def set_drone_control(ctrl: DroneControl):
    try:
        _send_axes(
            throttle=ctrl.throttle,
            yaw=ctrl.yaw,
            pitch=ctrl.pitch,
            roll=ctrl.roll,
        )
        return {"ok": True, **ctrl.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/button/")
async def press_button(action: ButtonAction):
    try:
        name = action.button.lower()
        if name not in BUTTON_MAP:
            raise HTTPException(status_code=400, detail={
                "error": "Unknown button identifier",
                "available": list(BUTTON_MAP.keys())
            })
        if name in ("arm", "switch_a"):
            _send_arm_state(action.pressed)
        else:
            code = BUTTON_MAP[name]
            device.emit(code, 1 if action.pressed else 0, syn=True)
        return {"ok": True, "button": name, "pressed": action.pressed}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/arm/")
async def arm():
    try:
        _send_arm_state(True)
        return {"ok": True, "state": "ARMED"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/disarm/")
async def disarm():
    try:
        _send_arm_state(False)
        _send_axes(0, 0, 0, 0)
        return {"ok": True, "state": "DISARMED"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/hover/")
async def hover():
    try:
        _send_axes(throttle=130, yaw=0, pitch=0, roll=0)
        return {"ok": True, "message": "Hover", "throttle": 130}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/neutral/")
async def neutral():
    try:
        _send_axes(0, 0, 0, 0)
        return {"ok": True, "message": "Axes centered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/")
async def status():
    return {
        "ok": True,
        "device": "Betafpv LiteRadio 2 SE Virtual",
        "mode": "Mode 2",
        "note": "Yaw axis duplicated on ABS_RX and ABS_RZ for compatibility",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
