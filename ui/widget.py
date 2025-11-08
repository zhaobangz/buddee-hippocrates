"""UI widget: Siri-inspired visual + audio capture helper.

This module provides a lightweight `SpiriWidget` that can:
- capture periodic screenshots (uses Pillow ImageGrab on macOS/Windows)
- capture short audio snippets (if `sounddevice` + `numpy` are installed)

Design notes and safety:
- Capturing the screen or microphone requires explicit user consent and
  appropriate OS permissions (macOS requires Screen Recording and Microphone
  permission in System Settings). The widget will raise RuntimeError if the
  underlying capture backend is unavailable.
- Audio capture is optional and only enabled when sounddevice is installed.

Usage:
	from ui.widget import SiriWidget

	def on_image(img):
		print('image captured', img.size)

	def on_audio(data, sr):
		print('audio captured', data.shape, sr)

	w = SpiriWidget(image_callback=on_image, audio_callback=on_audio)
	w.start()
	# ... later
	w.stop()

This file intentionally keeps dependencies optional to avoid forcing heavy
installs. Add packages to requirements.txt if you want full audio/screenshot
support (pillow, sounddevice, numpy).
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

try:
	from PIL import ImageGrab
except Exception:  # Pillow may not be installed
	ImageGrab = None  # type: ignore

try:
	import sounddevice as sd
	import numpy as np
except Exception:  # sounddevice or numpy may not be installed
	sd = None  # type: ignore
	np = None  # type: ignore


class SpiriWidget:
	"""A small widget that can 'see' (screenshots) and 'hear' (audio snippets).

	This class runs background threads for screenshot and audio capture and
	calls user-supplied callbacks with captured data.

	Callbacks:
		image_callback(image: PIL.Image.Image) -> None
		audio_callback(data: numpy.ndarray, samplerate: int) -> None
	"""

	def __init__(
		self,
		image_callback: Optional[Callable] = None,
		audio_callback: Optional[Callable] = None,
		image_interval: float = 1.0,
		audio_interval: float = 2.0,
		audio_duration: float = 1.0,
	) -> None:
		self.image_callback = image_callback
		self.audio_callback = audio_callback
		self.image_interval = float(image_interval)
		self.audio_interval = float(audio_interval)
		self.audio_duration = float(audio_duration)

		self._running = False
		self._image_thread: Optional[threading.Thread] = None
		self._audio_thread: Optional[threading.Thread] = None

	def start(self) -> None:
		"""Start background capture threads."""
		if self._running:
			return
		self._running = True

		if ImageGrab is not None and self.image_callback is not None:
			self._image_thread = threading.Thread(
				target=self._image_loop, daemon=True
			)
			self._image_thread.start()
		elif self.image_callback is not None:
			raise RuntimeError(
				"Image capture requested but Pillow/ImageGrab is not available."
			)

		if sd is not None and np is not None and self.audio_callback is not None:
			self._audio_thread = threading.Thread(
				target=self._audio_loop, daemon=True
			)
			self._audio_thread.start()
		elif self.audio_callback is not None:
			raise RuntimeError(
				"Audio capture requested but sounddevice/numpy is not available."
			)

	def stop(self) -> None:
		"""Stop background capture threads and wait for them to finish."""
		self._running = False
		if self._image_thread is not None:
			self._image_thread.join(timeout=2.0)
		if self._audio_thread is not None:
			self._audio_thread.join(timeout=2.0)

	def _image_loop(self) -> None:
		"""Background loop to take screenshots and call the image_callback."""
		while self._running:
			try:
				img = ImageGrab.grab()
				if self.image_callback:
					# callback should handle PIL.Image.Image
					try:
						self.image_callback(img)
					except Exception:
						# swallow callback errors to keep loop running
						pass
			except Exception:
				# Could be permission error on macOS or other issue; stop loop
				break
			time.sleep(self.image_interval)

	def _audio_loop(self) -> None:
		"""Background loop to record short audio snippets and call audio_callback."""
		samplerate = int(sd.query_devices(kind='input')['default_samplerate'])
		samplerate = int(samplerate)
		while self._running:
			try:
				# record blocks for audio_duration seconds
				frames = int(self.audio_duration * samplerate)
				data = sd.rec(frames, samplerate=samplerate, channels=1, dtype='float32')
				sd.wait()
				if self.audio_callback:
					try:
						self.audio_callback(np.copy(data.squeeze()), samplerate)
					except Exception:
						pass
			except Exception:
				# problems with audio device or permissions; stop loop
				break
			time.sleep(self.audio_interval)


if __name__ == '__main__':
	# Quick demo: print sizes and shapes when running directly.
	def _on_image(img):
		print('captured image', img.size)

	def _on_audio(data, sr):
		print('captured audio', getattr(data, 'shape', None), 'sr=', sr)

	w = SpiriWidget(image_callback=_on_image, audio_callback=_on_audio)
	try:
		print('Starting SpiriWidget demo. Press Ctrl-C to stop.')
		w.start()
		while True:
			time.sleep(1.0)
	except KeyboardInterrupt:
		print('Stopping...')
		w.stop()

