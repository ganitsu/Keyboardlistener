import os
import sys
import time
import signal
import threading
import subprocess


# --- AUDIO BACKEND SELECTION ---
os.environ["SDL_AUDIODRIVER"] = "pulse"   # Correct driver name for SDL

# --- STDERR UNDERRUN MONITOR ---
def intercept_underruns(threshold=15, window=30, service="keyboardlistener.service"):
    r_fd, w_fd = os.pipe()
    os.dup2(w_fd, 2)  # Redirect stderr

    def monitor():
        underruns = 0
        start = time.time()

        with os.fdopen(r_fd, 'r') as pipe:
            for line in pipe:
                if "underrun occurred" in line:
                    underruns += 1

                if time.time() - start > window:
                    if underruns >= threshold:
                        print(f"[ALERT] {underruns} underruns in {window}s → restarting service")
                        os.system(f"systemctl restart {service}")
                        os._exit(1)

                    underruns = 0
                    start = time.time()

    threading.Thread(target=monitor, daemon=True).start()

# intercept_underruns()


# --- IMPORTS AFTER AUDIO FIXED ---
from evdev import InputDevice, categorize, ecodes, list_devices
from evdev.ecodes import EV_KEY, KEY
import requests
import pygame
import random
import numpy as np
from AudioHandler import MidiPlayer

proc = None

# --- CLEAN EXIT ---
def handle_exit(signum, frame):
    print("Exiting…")
    pygame.quit()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)


# --- INITIALIZE SOUND SYSTEM ---
pygame.mixer.init()

sound = pygame.mixer.Sound("burp.wav")

player = MidiPlayer(autoplay_keys=None)

claps = pygame.mixer.Sound("claps.wav")
raw = pygame.sndarray.array(claps)
amp = np.clip(raw * 3, -32768, 32767).astype(np.int16)
claps_loud = pygame.sndarray.make_sound(amp)




# --- PITCH SHIFT ---
def change_pitch(sound, factor):
    raw = pygame.sndarray.array(sound)
    new_len = int(raw.shape[0] / factor)

    resampled = np.interp(
        np.linspace(0, raw.shape[0], new_len, endpoint=False),
        np.arange(raw.shape[0]),
        raw[:, 0] if raw.ndim > 1 else raw
    ).astype(np.int16)

    if raw.ndim > 1:
        resampled = np.column_stack((resampled, resampled))

    return pygame.sndarray.make_sound(resampled)


pitch_factors = [x / 10 for x in range(9, 16)]
pitched = [change_pitch(sound, f) for f in pitch_factors]


# --- KEY HANDLER ---
pressed_keys = set()

def touched_any(key, event_type):
    global proc

    # Pass specific keys to MIDI player
    #Not now

    if key == "kpenter" and event_type == "down":
        threading.Thread(target=lambda:
            requests.get("http://127.0.0.0:2060/dev0/togglePower"),
            daemon=True
        ).start()
        pitched[-1].play()
        return

    if key == "kpdot" and event_type == "down":
        claps_loud.play()
        return
    
    if key == "kp0" and event_type == "down":
        subprocess.run(["/mnt/main/Keyboardlistener/env/bin/python", "/mnt/main/audioBridge/mic_control.py", "start"])
        pitched[-1].play()
        return
    
    if key == "kp1" and event_type == "down":
        subprocess.run(["/mnt/main/Keyboardlistener/env/bin/python", "/mnt/main/audioBridge/mic_control.py", "stop"])
        pitched[-1].play()
        return
    
    if key == "kp2" and event_type == "down":
        env = os.environ.copy()
        env["DISPLAY"] = ":0"
        env["PULSE_RUNTIME_PATH"] = "/run/user/1000/pulse"
        env["PULSE_SERVER"] = "unix:/run/user/1000/pulse/native"
        env["HOME"] = "/home/nitsuga"

        if proc and proc.poll() is None:
            print("Terminating existing MathToLatex process…")
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                print("Force killing MathToLatex process…")
                proc.kill()
    

        proc = subprocess.Popen(
            ["/mnt/main/MathToLatex/venv/bin/python", "/mnt/main/MathToLatex/main.py"],
            cwd="/mnt/main/MathToLatex",
            env=env
        )
        pitched[-1].play()
        return

    # Select random pitched sound
    if event_type == "down":
        s = random.choice(pitched[len(pitched)//2:])
    else:
        s = random.choice(pitched[:len(pitched)//2])

    s.set_volume(0.2)
    s.play()
    print(f"Key: {key}, event: {event_type}")


def call_touched_function(key, event_type):
    touched_any(key, event_type)
    func = globals().get(f"touched_{key}")
    if func:
        func(event_type)


# --- MAIN LOOP ---
print("Listening for keys…")

while True:
    # Find the keyboard device
    def find_keyboard():
        for path in list_devices():
            dev = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps and ecodes.KEY_A in caps[ecodes.EV_KEY]:
                return dev
        raise RuntimeError("No keyboard device found")

    dev = find_keyboard()
    print(f"Using keyboard: {dev.name} at {dev.path}")

    for event in dev.read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        data = categorize(event)
    
        # get key name
        key_name = ecodes.KEY[event.code]
        if isinstance(key_name, list):
            key_name = key_name[0]
        key_name = key_name.replace("KEY_", "").lower()

        # skip numlock noise
        if key_name in ("numlock", "num_lock"):
            continue

        if data.keystate == data.key_down:
            if key_name not in pressed_keys:
                pressed_keys.add(key_name)
                call_touched_function(key_name, "down")
        elif data.keystate == data.key_up:
            if key_name in pressed_keys:
                pressed_keys.discard(key_name)
                call_touched_function(key_name, "up")
