import keyboard
import requests
import pygame
import random
import numpy as np
from AudioHandler import MidiPlayer
import threading


pressed_keys = set()

pygame.mixer.init()
sound = pygame.mixer.Sound("burp.wav")
player = MidiPlayer(autoplay_keys=None)  # None means all keys will be used for autoplay


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


pitch_factors = [x/10 for x in range(9, 13)]
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
    
    ps = random.choice(pitched_sounds)
    ps.play()

# Podés definir más funciones touched_xxx() aquí.




def call_touched_function(key, event_type):
    touched_any(key, event_type)
    func_name = f"touched_{key}"
    func = globals().get(func_name)
    if func:
        func(event_type)
    else:
        print(f'Función "{func_name}" no existe')

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
