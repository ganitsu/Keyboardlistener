import time
import mido
import fluidsynth
import random
import threading

class MidiPlayer:
    def __init__(self, song_files=None, soundfont="GeneralUser-GS.sf2", autoplay_keys=None):
        if song_files is None:
            song_files = ["Batman.mid"]
        self.song_files = song_files
        self.song_index = 0
        self.mid = mido.MidiFile(self.song_files[self.song_index])
        self.playlist_iter = iter(self.mid.play())
        self.playlist_lock = threading.Lock()
        self.fs = fluidsynth.FluidSynth(soundfont)
        # self.fs.set_gain(1.0)  # Default is 0.2, max is 10.0, try 1.0–2.0 for much louder
        for ch in range(16):
            self.fs.cc(ch, 7, 127)
        self.fs.program_select(0, 0)
        self._autoplaying = False
        self._autoplay_thread = None
        self.min_press_time = 1.5
        self.min_factor = 0.7  # global min factor for manual note duration
        self.max_factor = 1.3  # global max factor for manual note duration
        self.autoplay_keys = None if autoplay_keys is None else set(autoplay_keys)
        self._autoplay_pressed = set()  # keys currently held for autoplay

    def next_song(self):
        self.song_index = (self.song_index + 1) % len(self.song_files)
        self.mid = mido.MidiFile(self.song_files[self.song_index])
        self.playlist_iter = iter(self.mid.play())

    def touch(self):
        def play_note(msg_on, duration):
            self.fs.noteon(msg_on.channel, msg_on.note, msg_on.velocity)
            time.sleep(duration)
            self.fs.noteoff(msg_on.channel, msg_on.note)

        while True:
            with self.playlist_lock:
                try:
                    msg = next(self.playlist_iter)
                except StopIteration:
                    self.next_song()
                    continue
            if msg.type == 'note_on' and msg.velocity > 0:
                if msg.channel == 9:
                    continue
                # Find the corresponding note_off for this note
                elapsed_ticks = 0
                with self.playlist_lock:
                    for next_msg in self.playlist_iter:
                        elapsed_ticks += getattr(next_msg, 'time', 0)
                        if (next_msg.type == 'note_off' and next_msg.note == msg.note and next_msg.channel == msg.channel) or \
                           (next_msg.type == 'note_on' and next_msg.velocity == 0 and next_msg.note == msg.note and next_msg.channel == msg.channel):
                            break
                    else:
                        elapsed_ticks = int(0.5 * self.mid.ticks_per_beat)
                # Convert ticks to seconds
                tempo = 500000
                for track in self.mid.tracks:
                    for m in track:
                        if m.type == 'set_tempo':
                            tempo = m.tempo
                            break
                    else:
                        continue
                    break
                base_time = 0.5#mido.tick2second(elapsed_ticks, self.mid.ticks_per_beat, tempo)
                factor = random.uniform(self.min_factor, self.max_factor)
                duration = max(base_time * factor, 0.05)
                threading.Thread(target=play_note, args=(msg, duration), daemon=True).start()
                print(msg.note, msg.velocity, msg.channel, duration)
                break
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                self.fs.noteoff(msg.channel, msg.note)
                continue
            elif msg.type == 'program_change':
                self.fs.program_select(msg.channel, self.sfid, 0, msg.program)
                continue

    def stop_all_notes(self):
        # Turn off all notes on all channels (0-15, notes 0-127)
        for ch in range(16):
            for note in range(128):
                self.fs.noteoff(ch, note)

    def autoplay_worker(self):
        while self._autoplaying:
            with self.playlist_lock:
                try:
                    msg = next(self.playlist_iter)
                except StopIteration:
                    self.next_song()
                    continue
            if not self._autoplaying:
                break
            if msg.type == 'note_on':
                self.fs.noteon(msg.channel, msg.note, msg.velocity)
            elif msg.type == 'note_off':
                self.fs.noteoff(msg.channel, msg.note)
            elif msg.type == 'program_change':
                self.fs.program_select(msg.channel, self.sfid, 0, msg.program)
            if not self._autoplaying:
                break
        # When autoplay stops, turn off all notes
        self.stop_all_notes()

    def pressed(self, key, event_type):
        # event_type is a string: 'down' or 'up' (from keyboard.read_event())
        # Any key triggers manual note, only autoplay_keys can start/stop autoplay
        if not hasattr(self, '_autoplaying'):
            self._autoplaying = False
        if not hasattr(self, '_autoplay_thread'):
            self._autoplay_thread = None
        if not hasattr(self, 'min_press_time'):
            self.min_press_time = 1.5
        if not hasattr(self, 'fs'):
            return
        if not hasattr(self, '_longpress_timers'):
            self._longpress_timers = {}
        # Always play a note for any key down
        if event_type == 'down':
            self.touch()
            # Only start timer for autoplay keys
            allow_autoplay = True if self.autoplay_keys is None else (key in self.autoplay_keys)
            if allow_autoplay:
                def start_autoplay_if_still_pressed(k=key):
                    self._autoplay_pressed.add(k)
                    if not self._autoplaying:
                        self._autoplaying = True
                        self._autoplay_thread = threading.Thread(target=self.autoplay_worker, daemon=True)
                        self._autoplay_thread.start()
                timer = threading.Timer(self.min_press_time, start_autoplay_if_still_pressed)
                self._longpress_timers[key] = timer
                timer.start()
        elif event_type == 'up':
            # Cancel timer for this key if exists
            if key in self._longpress_timers:
                self._longpress_timers[key].cancel()
                del self._longpress_timers[key]
            # Remove from pressed set if present
            if key in self._autoplay_pressed:
                self._autoplay_pressed.remove(key)
            # Only stop autoplay if all autoplay keys are released
            if not self._autoplay_pressed and self._autoplaying:
                self._autoplaying = False


# if __name__ == "__main__":
#     import keyboard
#     player = MidiPlayer()
#     print("Testing MidiPlayer: Press 'k' to play, hold for autoplay, 'esc' to exit.")
#     while True:
#         if keyboard.is_pressed('esc'):
#             break
#         if keyboard.is_pressed('k'):
#             player.pressed('k', keyboard.KEY_DOWN)
#             while keyboard.is_pressed('k'):
#                 time.sleep(0.01)
#             player.pressed('k', keyboard.KEY_UP)
#         time.sleep(0.01)
        