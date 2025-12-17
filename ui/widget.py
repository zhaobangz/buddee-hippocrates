"""UI widget: Siri-inspired visual + audio capture helper.

This module provides a lightweight `Widget` that can:
- capture periodic screenshots (uses Pillow ImageGrab on macOS/Windows)
- capture short audio snippets (if `sounddevice` + `numpy` are installed)

Design notes and safety:
- Capturing the screen or microphone requires explicit user consent and
  appropriate OS permissions (macOS requires Screen Recording and Microphone
  permission in System Settings). The widget will raise RuntimeError if the
  underlying capture backend is unavailable.
- Audio capture is optional and only enabled when sounddevice is installed.

Usage:
	from ui.widget import Widget

	def on_image(img):
		print('image captured', img.size)

	def on_audio(data, sr):
		print('audio captured', data.shape, sr)

	w = Widget(image_callback=on_image, audio_callback=on_audio)
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
from typing import TYPE_CHECKING, Callable, Optional

import tkinter as tk
from tkinter import ttk

try:
	from PIL import ImageGrab
	from PIL import ImageTk
except Exception:  # Pillow may not be installed
	ImageGrab = None  # type: ignore
	ImageTk = None   # type: ignore
# type only so type checkers see photo image but runtime works when mageTk is None
if TYPE_CHECKING:
	from PIL.ImageTk import PhotoImage as PILPhotoImage 

try:
	import sounddevice as sd
	import numpy as np
except Exception:  # sounddevice or numpy may not be installed
	sd = None  # type: ignore
	np = None  # type: ignore


try:
	import pytesseract
except ImportError:
	pytesseract = None  # type: ignore


class Widget:
	"""A small widget that can 'see' (screenshots), 'hear' (audio), and 'read' (OCR).

	This class runs background threads for screenshot and audio capture and
	calls user-supplied callbacks with captured data.

	Callbacks:
		image_callback(image: PIL.Image.Image) -> None
		audio_callback(data: numpy.ndarray, samplerate: int) -> None
		ocr_callback(text: str) -> None
	"""

	def __init__(
		self,
		image_callback: Optional[Callable] = None,
		audio_callback: Optional[Callable] = None,
		ocr_callback: Optional[Callable] = None,
		image_interval: float = 1.0,
		audio_interval: float = 2.0,
		audio_duration: float = 1.0,
	) -> None:
		self.image_callback = image_callback
		self.audio_callback = audio_callback
		self.ocr_callback = ocr_callback
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

		image_capture_requested = self.image_callback is not None or self.ocr_callback is not None
		if image_capture_requested:
			if ImageGrab is None:
				raise RuntimeError("Image/OCR capture requested but Pillow is not available.")
			if self.ocr_callback and pytesseract is None:
				raise RuntimeError(
					"OCR requested but pytesseract is not available. "
					"Please install it (`pip install pytesseract`) and the Tesseract engine."
				)

			self._image_thread = threading.Thread(target=self._image_loop, daemon=True)
			self._image_thread.start()

		if self.audio_callback is not None:
			if sd is None or np is None:
				raise RuntimeError(
					"Audio capture requested but sounddevice/numpy is not available."
				)
			self._audio_thread = threading.Thread(
				target=self._audio_loop, daemon=True
			)
			self._audio_thread.start()

	def stop(self) -> None:
		"""Stop background capture threads and wait for them to finish."""
		self._running = False
		if self._image_thread is not None:
			self._image_thread.join(timeout=2.0)
		if self._audio_thread is not None:
			self._audio_thread.join(timeout=2.0)

	def _image_loop(self) -> None:
		"""Background loop to take screenshots and call callbacks."""
		while self._running:
			try:
				img = ImageGrab.grab()
				if self.image_callback:
					try:
						self.image_callback(img)
					except Exception:
						pass  # swallow callback errors
				
				if self.ocr_callback:
					try:
						text = pytesseract.image_to_string(img)
						if text:
							self.ocr_callback(text)
					except Exception:
						pass # swallow callback errors

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
	"""A simple GUI window demonstrating the Widget's capabilities.
    
	Shows a live screen preview, audio level, and OCR text in a window
	with start/stop controls.
	"""
    
	def __init__(self):
		super().__init__()
        
		self.title("Widget Demo")
		self.geometry("800x750") # increased height for OCR output
        
		# Main content
		self.content = ttk.Frame(self)
		self.content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
		# Preview area (shows latest screenshot)
		self.preview = ttk.Label(self.content)
		self.preview.pack(fill=tk.BOTH, expand=True)
        
		# OCR output area
		ocr_frame = ttk.Frame(self.content)
		ocr_frame.pack(fill=tk.BOTH, expand=True, pady=10)
		ttk.Label(ocr_frame, text="OCR Output:").pack(anchor=tk.W)
		self.ocr_output = tk.Text(ocr_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
		self.ocr_output.pack(fill=tk.BOTH, expand=True, pady=(5,0))

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
		self.ocr_status = ttk.Label(controls, text="OCR: Unknown")
		self.ocr_status.pack(side=tk.RIGHT, padx=5)
		self.image_status = ttk.Label(controls, text="Screen: Unknown")
		self.image_status.pack(side=tk.RIGHT, padx=5)
		self.audio_status = ttk.Label(controls, text="Audio: Unknown")
		self.audio_status.pack(side=tk.RIGHT, padx=5)
        
		self._last_preview: Optional[PILPhotoImage] = None
		self.widget: Optional[Widget] = None
    
	def _on_image(self, img):
		"""Called when Widget captures a new screenshot."""
		# Scale down to fit our window (preserve aspect ratio)
		w, h = img.size
		scale = min(700/w, 400/h) # Adjusted for new layout
		if scale < 1:
			w, h = int(w*scale), int(h*scale)
			img = img.resize((w, h))
        
		# Convert to tkinter-compatible image
		self._last_preview = ImageTk.PhotoImage(img)
		self.preview.configure(image=self._last_preview)
    
	def _on_audio(self, data, sr):
		"""Called when Widget captures an audio snippet."""
		if np is not None:
			# Show RMS level (0-100)
			rms = float(np.sqrt(np.mean(np.square(data))))
			level = min(100, int(rms * 200)) # scaled for visibility
			self.level_bar['value'] = level

	def _on_ocr(self, text: str):
		"""Called when Widget extracts text from the screen."""
		self.ocr_output.configure(state=tk.NORMAL)
		self.ocr_output.delete('1.0', tk.END)
		self.ocr_output.insert('1.0', text)
		self.ocr_output.configure(state=tk.DISABLED)
    
	def _start(self):
		"""Start capture with status updates."""
		self.widget = Widget(
			image_callback=self._on_image,
			audio_callback=self._on_audio,
			ocr_callback=self._on_ocr,
			image_interval=1.0,  # slow interval for OCR
			audio_interval=0.1,
			audio_duration=0.05
		)
        
		try:
			self.widget.start()
			self.start_btn.configure(state=tk.DISABLED)
			self.stop_btn.configure(state=tk.NORMAL)
            
			# Update status labels based on which captures started
			self.image_status.configure(text="Screen: Running")
			self.audio_status.configure(text="Audio: Running")
			self.ocr_status.configure(text="OCR: Running")
                
		except Exception as e:
			self.widget = None
			import tkinter.messagebox as mb
			mb.showerror(
				"Error",
				f"Failed to start capture: {e}\n\n"
				"Check that you have granted necessary permissions (Screen, Mic)\n"
				"and that optional dependencies are installed (see README)."
			)
			self._stop() # Reset UI
    
	def _stop(self):
		"""Stop capture and reset UI state."""
		if self.widget:
			self.widget.stop()
			self.widget = None
        
		self.start_btn.configure(state=tk.NORMAL)
		self.stop_btn.configure(state=tk.DISABLED)
		self.image_status.configure(text="Screen: Stopped")
		self.audio_status.configure(text="Audio: Stopped")
		self.ocr_status.configure(text="OCR: Stopped")
		self.level_bar['value'] = 0
		self.ocr_output.configure(state=tk.NORMAL)
		self.ocr_output.delete('1.0', tk.END)
		self.ocr_output.configure(state=tk.DISABLED)

if __name__ == '__main__':
    # Run the GUI demo when the file is run directly
    app = GUI()
    app.mainloop()

