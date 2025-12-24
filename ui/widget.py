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
	# Provide an alternative: a Siri-like sidebar demo
	import argparse

	parser = argparse.ArgumentParser(description='Widget demos')
	parser.add_argument('--sidebar', action='store_true', help='Run Siri-style sidebar demo')
	args = parser.parse_args()

	if args.sidebar:
		class Sidebar(tk.Tk):
			"""A frameless, translucent sidebar inspired by macOS Siri sidebar.

			This is a lightweight approximation using Tkinter. It creates a
			frameless window docked to the right edge of the screen with a
			rounded background, a central microphone button, and a simple
			animated waveform effect.
			"""

			def __init__(self, width: int = 360, height: int = 520, padding: int = 16):
				super().__init__()
				self.width = width
				self.height = height
				self.padding = padding

				# Frameless, topmost window
				self.overrideredirect(True)
				try:
					self.wm_attributes('-topmost', True)
					# translucency (overall window alpha)
					self.wm_attributes('-alpha', 0.96)
					# macOS: allow transparent background color key
					self.wm_attributes('-transparent', True)
				except Exception:
					# Some attributes may not be available on all platforms
					pass

				sw = self.winfo_screenwidth()
				sh = self.winfo_screenheight()
				# Dock near right edge, centered vertically
				x = sw - self.width - 24
				y = max(24, (sh - self.height) // 2)
				self.geometry(f'{self.width}x{self.height}+{x}+{y}')

				# Root frame with padding
				self.config(bg='')
				self.canvas = tk.Canvas(self, width=self.width, height=self.height, highlightthickness=0)
				self.canvas.pack(fill=tk.BOTH, expand=True)

				# Draw rounded rectangle background
				radius = 20
				bg_color = '#0f1724'  # dark bluish
				self._draw_rounded_rect(0, 0, self.width, self.height, radius, fill=bg_color, outline='#21303d')

				# Add small drag area and close button
				self.canvas.create_text(self.width - 28, 18, text='✕', fill='#9aa8b3', font=('Helvetica', 12), tags='close')
				self.canvas.tag_bind('close', '<Button-1>', lambda e: self.hide())

				# Title / label
				self.canvas.create_text(self.padding + 12, 20, anchor='w', text='Buddi', fill='#e6eef6', font=('Times New Roman', 14, 'bold'))

				# Microphone button in center
				self.mic_size = 96
				cx = self.width // 2
				cy = self.height // 2 - 20
				self.mic_center = (cx, cy)
				self._mic_bg = self.canvas.create_oval(
					cx - self.mic_size//2, cy - self.mic_size//2,
					cx + self.mic_size//2, cy + self.mic_size//2,
					fill='#13232b', outline='#2b5363', width=2
				)

				# mic icon (simple text glyph)
				self.canvas.create_text(cx, cy, text='🎤', font=('Helvetica', 28), fill='#9fe7ff')

				# Animated waveform rings (canvas ovals)
				self.rings = []
				for i in range(3):
					ring = self.canvas.create_oval(0,0,0,0, outline='#3fb2d6', width=2, state='hidden')
					self.rings.append(ring)

				# Quick action buttons below mic
				btn_y = cy + self.mic_size//2 + 28
				self._add_quick_button(cx - 80, btn_y, 'Notes')
				self._add_quick_button(cx + 80, btn_y, 'Search')

				# Bindings
				self.canvas.tag_bind(self._mic_bg, '<Button-1>', lambda e: self._toggle_listen())
				self._listening = False
				self._anim_after = None

				# Make draggable by dragging the title area
				self._drag_data = {'x': 0, 'y': 0}
				self.canvas.bind('<ButtonPress-1>', self._on_press)
				self.canvas.bind('<B1-Motion>', self._on_drag)

			def _draw_rounded_rect(self, x1, y1, x2, y2, r=25, **kwargs):
				points = [x1+r, y1,
						  x1+r, y1,
						  x2-r, y1,
						  x2-r, y1,
						  x2, y1,
						  x2, y1+r,
						  x2, y1+r,
						  x2, y2-r,
						  x2, y2-r,
						  x2, y2,
						  x2-r, y2,
						  x2-r, y2,
						  x1+r, y2,
						  x1+r, y2,
						  x1, y2,
						  x1, y2-r,
						  x1, y2-r,
						  x1, y1+r,
						  x1, y1+r,
						  x1, y1]
				return self.canvas.create_polygon(points, smooth=True, **kwargs)

			def _add_quick_button(self, cx, cy, label):
				w, h = 100, 34
				x1, y1 = cx - w//2, cy - h//2
				rect = self.canvas.create_rectangle(x1, y1, x1+w, y1+h, fill='#13323b', outline='#2b4750')
				text = self.canvas.create_text(cx, cy, text=label, fill='#cfeef9', font=('Helvetica', 11))
				# simple hover effect
				for tag in (rect, text):
					self.canvas.tag_bind(tag, '<Enter>', lambda e, r=rect: self.canvas.itemconfigure(r, fill='#16454f'))
					self.canvas.tag_bind(tag, '<Leave>', lambda e, r=rect: self.canvas.itemconfigure(r, fill='#13323b'))

			def _on_press(self, event):
				self._drag_data['x'] = event.x
				self._drag_data['y'] = event.y

			def _on_drag(self, event):
				dx = event.x - self._drag_data['x']
				dy = event.y - self._drag_data['y']
				geom = self.geometry()
				# parse geometry WxH+X+Y
				try:
					parts = geom.split('+')
					base = parts[0]
					x = int(parts[1]) + dx
					y = int(parts[2]) + dy
					self.geometry(f"{base}+{x}+{y}")
				except Exception:
					pass

			def _toggle_listen(self):
				self._listening = not self._listening
				if self._listening:
					self._start_rings()
				else:
					self._stop_rings()

			def _start_rings(self):
				self._ring_steps = [0, 8, 16]
				for r in self.rings:
					self.canvas.itemconfigure(r, state='normal')
				self._animate_rings()

			def _animate_rings(self):
				# animate expanding rings
				cx, cy = self.mic_center
				maxr = self.mic_size
				for i, ring in enumerate(self.rings):
					step = (self._ring_steps[i] + 2) % (maxr + 20)
					self._ring_steps[i] = step
					r = 30 + step
					self.canvas.coords(ring, cx - r, cy - r, cx + r, cy + r)
					alpha = max(0, 1.0 - (r / (maxr + 40)))
					color = self._blend_color('#3fb2d6', '#0f1724', alpha)
					try:
						self.canvas.itemconfigure(ring, outline=color)
					except Exception:
						pass

				if self._listening:
					self._anim_after = self.after(70, self._animate_rings)

			def _stop_rings(self):
				if self._anim_after:
					self.after_cancel(self._anim_after)
					self._anim_after = None
				for r in self.rings:
					self.canvas.itemconfigure(r, state='hidden')

			def _blend_color(self, fg: str, bg: str, alpha: float) -> str:
				# Simple hex color blend fg over bg with alpha
				try:
					fg = fg.lstrip('#')
					bg = bg.lstrip('#')
					fr = int(fg[0:2], 16)
					fg_ = int(fg[2:4], 16)
					fb = int(fg[4:6], 16)
					br = int(bg[0:2], 16)
					bg_ = int(bg[2:4], 16)
					bb = int(bg[4:6], 16)
					r = int(fr * alpha + br * (1 - alpha))
					g = int(fg_ * alpha + bg_ * (1 - alpha))
					b = int(fb * alpha + bb * (1 - alpha))
					return f'#{r:02x}{g:02x}{b:02x}'
				except Exception:
					return fg

			def show(self):
				# simple slide-in animation from right
				sw = self.winfo_screenwidth()
				target_x = sw - self.width - 24
				geom = self.geometry()
				parts = geom.split('+')
				base = parts[0]
				try:
					cur_x = int(parts[1])
					y = int(parts[2])
				except Exception:
					cur_x = sw
					y = int((self.winfo_screenheight() - self.height) // 2)

				def step():
					nonlocal cur_x
					if cur_x > target_x:
						cur_x = max(target_x, cur_x - 40)
						self.geometry(f"{base}+{cur_x}+{y}")
						self.after(10, step)

				step()

			def hide(self):
				# slide-out then destroy
				sw = self.winfo_screenwidth()
				geom = self.geometry()
				parts = geom.split('+')
				base = parts[0]
				try:
					cur_x = int(parts[1])
					y = int(parts[2])
				except Exception:
					cur_x = sw - self.width
					y = int((self.winfo_screenheight() - self.height) // 2)

				def step():
					nonlocal cur_x
					if cur_x < sw:
						cur_x = min(sw + 10, cur_x + 40)
						self.geometry(f"{base}+{cur_x}+{y}")
						self.after(10, step)
					else:
						try:
							self.destroy()
						except Exception:
							pass

				step()

		app = Sidebar()
		# Try to start the agent perception if an agent exists
		perception_started = False
		try:
			import core.agent as core_agent
			if hasattr(core_agent, 'agent'):
				try:
					core_agent.agent.start_perception()
					perception_started = True
				except Exception:
					perception_started = False
		except Exception:
			perception_started = False

		app.show()
		try:
			app.mainloop()
		finally:
			# Stop perception if we started it
			if perception_started:
				try:
					import core.agent as core_agent
					if hasattr(core_agent, 'agent'):
						core_agent.agent.stop_perception()
				except Exception:
					pass
	else:
		app = GUI()
		app.mainloop()

