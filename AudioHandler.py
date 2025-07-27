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
		self.fs = fluidsynth.Synth()
		self.fs.setting("audio.period-size", 256)
		self.fs.setting("synth.gain", 0.2) # Default is 0.2, max is 10.0
  
		# for ch in range(16):
		#     self.fs.cc(ch, 7, 110)
		self.fs.start()
		self.sfid = self.fs.sfload(soundfont)
		self.fs.program_select(0, self.sfid, 0, 0)
		self._autoplaying = False
		self._autoplay_thread = None
		self.min_press_time = 1.5
		self.min_factor = 0.7  # global min factor for manual note duration
		self.max_factor = 1.3  # global max factor for manual note duration
		self.autoplay_keys = None if autoplay_keys is None else set(autoplay_keys)
		self._autoplay_pressed = set()  # keys currently held for autoplay
		self._longpress_timers = {}
		self._cancelled_longpress = set()  # keys released before timer fires

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
				base_time = 0.5  # mido.tick2second(elapsed_ticks, self.mid.ticks_per_beat, tempo)
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
		while True:
			if not self._autoplaying:
				break
			with self.playlist_lock:
				try:
					msg = next(self.playlist_iter)
				except StopIteration:
					self.next_song()
					continue
			if msg.type == 'note_on' and msg.velocity > 0:
				if msg.channel != 9:
					self.fs.noteon(msg.channel, msg.note, msg.velocity)
			elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
				self.fs.noteoff(msg.channel, msg.note)
			elif msg.type == 'program_change':
				self.fs.program_select(msg.channel, self.sfid, 0, msg.program)
		# When autoplay stops, turn off all notes
		self.stop_all_notes()

	def pressed(self, key, event_type):
		# event_type is a string: 'down' or 'up' (from keyboard.read_event())
		# Any key triggers manual note, only autoplay_keys can start/stop autoplay
		print(f"[DEBUG] Key pressed: {key}, event_type: {event_type}")
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
		if event_type == 'down':
			print(f"[DEBUG] Key down: {key}")
			# Clean up any stale cancelled state for this key
			if key in self._cancelled_longpress:
				print(f"[DEBUG] Removing {key} from _cancelled_longpress on key down")
				self._cancelled_longpress.discard(key)
			allow_autoplay = True if self.autoplay_keys is None else (key in self.autoplay_keys)
			print(f"[DEBUG] allow_autoplay: {allow_autoplay}, _autoplaying: {self._autoplaying}, _autoplay_pressed: {self._autoplay_pressed}, _cancelled_longpress: {self._cancelled_longpress}")
			# Always play manual note unless already in autoplay
			if key not in self._autoplay_pressed:
				self.touch()
			# Always start long-press timer for autoplay keys
			if allow_autoplay:
				def start_autoplay_if_still_pressed(k=key):
					if k in self._cancelled_longpress:
						print(f"[DEBUG] Timer fired for key: {k} but was cancelled (removing)")
						self._cancelled_longpress.discard(k)
						return
					print(f"[DEBUG] Timer fired for key: {k}")
					self._autoplay_pressed.add(k)
					if not self._autoplaying:
						print(f"[DEBUG] Starting autoplay thread for key: {k}")
						self._autoplaying = True
						self._autoplay_thread = threading.Thread(target=self.autoplay_worker, daemon=True)
						self._autoplay_thread.start()
				if key not in self._autoplay_pressed and key not in self._longpress_timers:
					print(f"[DEBUG] Starting longpress timer for key: {key}")
					timer = threading.Timer(self.min_press_time, start_autoplay_if_still_pressed)
					self._longpress_timers[key] = timer
					timer.start()
		elif event_type == 'up':
			print(f"[DEBUG] Key up: {key}")
			if key in self._longpress_timers:
				print(f"[DEBUG] Cancelling longpress timer for key: {key}")
				self._longpress_timers[key].cancel()
				del self._longpress_timers[key]
				self._cancelled_longpress.add(key)
				print(f"[DEBUG] Added {key} to _cancelled_longpress on key up")
			if key in self._autoplay_pressed:
				print(f"[DEBUG] Removing key from _autoplay_pressed: {key}")
				self._autoplay_pressed.remove(key)
			print(f"[DEBUG] _autoplay_pressed after key up: {self._autoplay_pressed}, _cancelled_longpress: {self._cancelled_longpress}")
			# Stop autoplay if all keys are released
			if not self._autoplay_pressed and self._autoplaying:
				print(f"[DEBUG] Stopping autoplay (all keys released)")
				self._autoplaying = False
				# Wait for thread to finish and clear reference
				if self._autoplay_thread is not None:
					self._autoplay_thread.join(timeout=1)
					self._autoplay_thread = None


# if __name__ == "__main__":
#     import keyboard
#     player = MidiPlayer()
#     print("Testing MidiPlayer: Press 'k' to play, hold for autoplay, 'esc' to exit.")
		# print(f"[DEBUG] Autoplay worker started")
		# while True:
		# 	if not self._autoplaying:
		# 		print(f"[DEBUG] Autoplay worker exiting (self._autoplaying is False)")
		# 		break
		# 	with self.playlist_lock:
		# 		try:
		# 			msg = next(self.playlist_iter)
		# 		except StopIteration:
		# 			print(f"[DEBUG] End of song, loading next song")
		# 			self.next_song()
		# 			continue
		# 	print(f"[DEBUG] Autoplay event: {msg}")
		# 	if msg.type == 'note_on' and msg.velocity > 0:
		# 		if msg.channel != 9:
		# 			print(f"[DEBUG] Autoplay note_on: {msg.note} ch {msg.channel} vel {msg.velocity}")
		# 			self.fs.noteon(msg.channel, msg.note, msg.velocity)
		# 	elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
		# 		print(f"[DEBUG] Autoplay note_off: {msg.note} ch {msg.channel}")
		# 		self.fs.noteoff(msg.channel, msg.note)
		# 	elif msg.type == 'program_change':
		# 		print(f"[DEBUG] Autoplay program_change: {msg.program} ch {msg.channel}")
		# 		self.fs.program_select(msg.channel, self.sfid, 0, msg.program)
		# print(f"[DEBUG] Autoplay worker stopped, turning off all notes")
		# self.stop_all_notes()
