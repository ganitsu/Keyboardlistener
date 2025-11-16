import time
import mido
import fluidsynth
import random
import threading

class MidiPlayer:
    def __init__(self, song_files=None, soundfont="GeneralUser-GS.sf2", autoplay_keys=None):

        if song_files is None:
            song_files = ["Beat.mid", "Beat3.mid", "Batman.mid", "Shreksophone.mid"]

        self.song_files = song_files
        self.song_index = 0
        self.mid = mido.MidiFile(self.song_files[self.song_index])
        self.playlist_iter = iter(self.mid.play())
        self.playlist_lock = threading.Lock()

        # --- FIXED FOR PULSEAUDIO ---
        self.fs.setting("audio.period-size", 256)
        self.fs.setting("synth.gain", 3.0)

        self.fs.start(driver="pulseaudio")
        self.sfid = self.fs.sfload(soundfont)
        self.fs.program_select(0, self.sfid, 0, 0)

        # Your logic preserved
        self._autoplaying = False
        self._autoplay_thread = None
        self.min_press_time = 1.5
        self.min_factor = 0.7
        self.max_factor = 1.3
        self.autoplay_keys = None if autoplay_keys is None else set(autoplay_keys)
        self._autoplay_pressed = set()
        self._longpress_timers = {}
        self._cancelled_longpress = set()
