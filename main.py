import os
import sys
import time
import signal
import threading

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
import keyboard
import requests
import pygame
import random
import numpy as np
from AudioHandler import MidiPlayer


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

    # Pass specific keys to MIDI player
    if key in ("enter", "a", "+", "-", "backspace"):
        player.pressed(key, event_type)
        return

    if key == "0" and event_type == "down":
        threading.Thread(target=lambda:
            requests.get("http://127.0.0.0:2060/dev0/togglePower"),
            daemon=True
        ).start()
        pitched[-1].play()
        return

    if key == "÷" and event_type == "down":
        claps_loud.play()
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
    event = keyboard.read_event()

    # skip numlock noise
    if event.name.lower() in ("num lock", "numlock"):
        continue

    if event.event_type == keyboard.KEY_DOWN:
        if event.name not in pressed_keys:
            pressed_keys.add(event.name)
            call_touched_function(event.name, "down")

    elif event.event_type == keyboard.KEY_UP:
        if event.name in pressed_keys:
            pressed_keys.discard(event.name)
            call_touched_function(event.name, "up")
