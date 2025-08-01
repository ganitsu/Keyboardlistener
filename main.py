import keyboard
import requests
import pygame
import random
import numpy as np
from AudioHandler import MidiPlayer
import threading
import signal
import sys


def handle_exit(signum, frame):
    print("Exiting on signal", signum)
    pygame.quit()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)  # Optional: handle Ctrl+C too


pressed_keys = set()

pygame.mixer.init()
sound = pygame.mixer.Sound("burp.wav")
player = MidiPlayer(autoplay_keys=None)  # None means all keys will be used for autoplay

claps = pygame.mixer.Sound("claps.wav")
claps.set_volume(3.0)

def change_pitch(sound, factor):
    # Extraer datos crudos del sonido
    raw = pygame.sndarray.array(sound)
    # Resamplear el array para cambiar pitch
    new_length = int(raw.shape[0] / factor)
    resampled = np.interp(
        np.linspace(0, raw.shape[0], new_length, endpoint=False),
        np.arange(raw.shape[0]),
        raw[:, 0] if raw.ndim > 1 else raw
    ).astype(np.int16)

    # Expandir a 2D si era estéreo
    if raw.ndim > 1:
        resampled = np.column_stack((resampled, resampled))

    return pygame.sndarray.make_sound(resampled)


pitch_factors = [x/10 for x in range(9, 16)]
pitched_sounds = [change_pitch(sound, f) for f in pitch_factors]



def touched_any(key, event_type):
    
    if key in ["enter", "a", "+", "-", "backspace"]:
        player.pressed(key, event_type)
        return
    
    if key == "0" and event_type == "down":
        def do_request():
            requests.get("http://192.168.5.10:2060/dev0/togglePower")
        threading.Thread(target=do_request, daemon=True).start()
        ps = pitched_sounds[-1]
        ps.play()
        return
    
    if key == "÷" and event_type == "down":
        claps.play()
        return
    
    if event_type == "down":
        #Use the upper half of the pitched sounds, acounting for the ammount of pitched sounds
        ps = random.choice(pitched_sounds[len(pitched_sounds)//2:])
    else:
        #Use the lower half of the pitched sounds, acounting for the ammount of pitched sounds
        ps = random.choice(pitched_sounds[:len(pitched_sounds)//2])
    #Set the volume of the sound.
    ps.set_volume(0.2)
    ps.play()
    print(f"Key pressed: {key}, event_type: {event_type}")

# Podés definir más funciones touched_xxx() aquí.




def call_touched_function(key, event_type):
    touched_any(key, event_type)
    func_name = f"touched_{key}"
    func = globals().get(func_name)
    if func:
        func(event_type)
    else:
        pass
        #print(f'Función "{func_name}" no existe')

print("Escuchando teclas (Ctrl+C para salir)...")

while True:
    event = keyboard.read_event()

    # Ignorar num lock (puede ser 'num lock' o 'numlock' según sistema)
    if event.name.lower() in ['num lock', 'numlock']:
        continue

    if event.event_type == keyboard.KEY_DOWN:
        if event.name not in pressed_keys:
            pressed_keys.add(event.name)
            call_touched_function(event.name, event.event_type)

    elif event.event_type == keyboard.KEY_UP:
        if event.name in pressed_keys:
            pressed_keys.discard(event.name)
            call_touched_function(event.name, event.event_type)
