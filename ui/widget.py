"""UI widget: Siri-inspired visual + audio capture helper.

This module provides a lightweight `SiriWidget` that can:
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

	w = SiriWidget(image_callback=on_image, audio_callback=on_audio)
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

import tkinter as tk
from tkinter import ttk

try:
	from PIL import ImageGrab
	from PIL import ImageTk
except Exception:  # Pillow may not be installed
	ImageGrab = None  # type: ignore
	ImageTk = None   # type: ignore

try:
	import numpy as np
except Exception:  # sounddevice or numpy may not be installed
	sd = None  # type: ignore
	np = None  # type: ignore


class Widget:
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


class GUI(tk.Tk):
	"""A simple GUI window demonstrating the SpiriWidget capabilities.
    
	Shows live screen capture preview and audio levels in a window with
	start/stop controls.
	"""
    
	def __init__(self):
		super().__init__()
        
		self.title("Widget Demo")
		self.geometry("800x600")
        
		# Main content
		self.content = ttk.Frame(self)
		self.content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
		# Preview area (shows latest screenshot)
		self.preview = ttk.Label(self.content)
		self.preview.pack(fill=tk.BOTH, expand=True)
        
		# Audio meter frame
		meter_frame = ttk.Frame(self.content)
		meter_frame.pack(fill=tk.X, pady=10)
        
		ttk.Label(meter_frame, text="Audio Level:").pack(side=tk.LEFT)
		self.level_bar = ttk.Progressbar(
			meter_frame, length=200, mode='determinate'
		)
		self.level_bar.pack(side=tk.LEFT, padx=5)
        
		# Controls frame
		controls = ttk.Frame(self.content)
		controls.pack(fill=tk.X, pady=10)
        
		self.start_btn = ttk.Button(
			controls, text="Start", command=self._start
		)
		self.start_btn.pack(side=tk.LEFT, padx=5)
        
		self.stop_btn = ttk.Button(
			controls, text="Stop", command=self._stop, state=tk.DISABLED
		)
		self.stop_btn.pack(side=tk.LEFT, padx=5)
        
		# Status labels
		self.image_status = ttk.Label(controls, text="Screen: Unknown")
		self.image_status.pack(side=tk.RIGHT, padx=5)
		self.audio_status = ttk.Label(controls, text="Audio: Unknown")
		self.audio_status.pack(side=tk.RIGHT, padx=5)
        
		self._last_preview: Optional[ImageTk.PhotoImage] = None
		self.widget: Optional[SpiriWidget] = None
    
	def _on_image(self, img):
		"""Called when SpiriWidget captures a new screenshot."""
		# Scale down to fit our window (preserve aspect ratio)
		w, h = img.size
		scale = min(700/w, 500/h)
		if scale < 1:
			w, h = int(w*scale), int(h*scale)
			img = img.resize((w, h))
        
		# Convert to tkinter-compatible image
		self._last_preview = ImageTk.PhotoImage(img)
		self.preview.configure(image=self._last_preview)
    
	def _on_audio(self, data, sr):
		"""Called when SpiriWidget captures an audio snippet."""
		if np is not None:
			# Show RMS level (0-100)
			rms = float(np.sqrt(np.mean(np.square(data))))
			level = min(100, rms * 100)
			self.level_bar['value'] = level
    
	def _start(self):
		"""Start capture with status updates."""
		self.widget = Widget(
			image_callback=self._on_image,
			audio_callback=self._on_audio,
			image_interval=0.1,  # faster updates for demo
			audio_interval=0.1,
			audio_duration=0.05
		)
        
		try:
			self.widget.start()
			self.start_btn.configure(state=tk.DISABLED)
			self.stop_btn.configure(state=tk.NORMAL)
            
			# Update status labels based on which captures started
			if self.widget._image_thread is not None:
				self.image_status.configure(text="Screen: Running")
			else:
				self.image_status.configure(text="Screen: Failed")
            
			if self.widget._audio_thread is not None:
				self.audio_status.configure(text="Audio: Running")
			else:
				self.audio_status.configure(text="Audio: Failed")
                
		except Exception as e:
			self.widget = None
			import tkinter.messagebox as mb
			mb.showerror(
				"Error",
				f"Failed to start capture: {e}\n\n"
				"Check that you have granted:\n"
				"- Screen Recording permission\n"
				"- Microphone permission\n"
				"in System Settings → Privacy & Security"
			)
    
	def _stop(self):
		"""Stop capture and reset UI state."""
		if self.widget:
			self.widget.stop()
			self.widget = None
        
		self.start_btn.configure(state=tk.NORMAL)
		self.stop_btn.configure(state=tk.DISABLED)
		self.image_status.configure(text="Screen: Stopped")
		self.audio_status.configure(text="Audio: Stopped")
		self.level_bar['value'] = 0

if __name__ == '__main__':
    # Run the GUI demo when the file is run directly
    app = GUI()
    app.mainloop()

