# decides what to do with the input (use llm vs tool)

from core.llm_manager import LLMManager
from core.memory import Memory
from core.config import Config
from tools import browser, system, search
import os
from typing import Optional

# File manager will be imported lazily where used to avoid heavy imports at startup

try:
    import tools as sr
except Exception:
    sr = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None


class Agent:
    def __init__(self):
        # Memory (persistent) if enabled
        self.memory = Memory(max_history=Config.MAX_MEMORY_HISTORY, persist_file=Config.MEMORY_PERSIST_FILE) if Config.MEMORY_ENABLED else None

        # LLM manager—pass memory so the manager can include context
        self.llm_manager = LLMManager(self.memory)

        # Optional voice stack
        self.recognizer = sr.Recognizer() if (Config.USE_VOICE and sr is not None) else None
        self.tts_engine = pyttsx3.init() if (Config.USE_VOICE and pyttsx3 is not None) else None

        if Config.USE_VOICE and self.tts_engine:
            try:
                voices = self.tts_engine.getProperty('voices')
                if voices:
                    self.tts_engine.setProperty('voice', voices[0].id)
                self.tts_engine.setProperty('rate', 150)
            except Exception:
                pass

        # pending organize operation awaiting user confirmation
        self._pending_organize = None

    def listen(self):
        """Listen for voice input"""
        if not self.recognizer:
            return None

        try:
            with sr.Microphone() as source:
                print(f"{Config.ASSISTANT_NAME} is listening...")
                self.recognizer.adjust_for_ambient_noise(source)
                try:
                    audio = self.recognizer.listen(source, timeout=5)
                    text = self.recognizer.recognize_google(audio)
                    print(f"You said: {text}")
                    return text
                except sr.UnknownValueError:
                    return "Sorry, I did not catch that."
                except sr.RequestError:
                    return "Sorry, my speech service is down."
                except sr.WaitTimeoutError:
                    return None
        except Exception:
            return None
            
    def speak(self, text):
        """convert text to speech"""
        if self.tts_engine:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()

    def detect_intent(self, ui):
        """Use LLM to classify user intent"""
        prompt = f"""
        Analyze this user input and classify its intent: "{ui}"
        
        Possible intents:
        - open_website: User wants to open a website or application
        - web_search: User wants to search for information online
        - system_command: User wants to control the system (shutdown, restart, etc.)
        - general_query: User has a general question or request
        
        Respond with ONLY the intent name. If unsure, respond with "general_query".
    
        Possible intents:
        - open_website: User wants to open a website or web application
        - web_search: User wants to search the web for information
        - system_command: User wants to control the system (shutdown, etc.)
        - general_query: User has a general question or request
        
        Respond with ONLY the intent name.
        """
        
        intent = self.llm_manager.ask_llm(prompt).strip().lower()
        return intent


    def handle(self, ui):
        """process user input and return the appropriate response"""
        if not ui or ui.strip() == "":
            return "I didn't hear anythging. Please Repeat it?"

        # If we have a pending organize operation, treat 'yes'/'no' replies as confirmation
        if self._pending_organize is not None:
            lower = ui.strip().lower()
            if lower in ('yes', 'y', 'confirm', 'ok', 'sure'):
                pending = self._pending_organize
                self._pending_organize = None
                try:
                    fm = pending['fm']
                    strategy = pending['strategy']
                    target = pending['target']
                    if strategy == 'extension':
                        actions = fm.organize_by_extension(target, dry_run=False)
                    elif strategy == 'date':
                        actions = fm.organize_by_date(target, dry_run=False)
                    else:
                        actions = fm.organize_by_category(target, dry_run=False)
                    return f"Organized {len(actions)} files in {target} using strategy '{strategy}'."
                except Exception as e:
                    return f"Failed to organize files: {e}"
            else:
                self._pending_organize = None
                return "Okay — I won't organize files."

        intent = self.detect_intent(ui)
        # quick heuristic: if user asks to organize files, handle locally
        lower = ui.lower()
        if any(k in lower for k in ("organize", "sort", "tidy up", "clean up")):
            # determine target folder
            target: Optional[str] = None
            for name in ("downloads", "desktop", "documents", "pictures", "music", "videos"):
                if name in lower:
                    target = os.path.expanduser(f"~/{name.capitalize()}") if name != 'downloads' else os.path.expanduser('~/Downloads')
                    break
            # allow explicit path
            if target is None:
                import re
                m = re.search(r'(/[^\s]+)', ui)
                if m:
                    target = os.path.expanduser(m.group(1))

            # choose strategy
            strategy = 'category'
            if 'by date' in lower or 'by month' in lower or 'by year' in lower:
                strategy = 'date'
            elif 'by extension' in lower or 'by ext' in lower or 'by file type' in lower:
                strategy = 'extension'
            elif 'by type' in lower or 'by category' in lower:
                strategy = 'category'

            try:
                from tools.file_manager import FileManager
                fm = FileManager()
                if not target:
                    return "Which folder would you like me to organize? (e.g. Downloads, Desktop, or a full path)"

                # perform a dry-run first and ask for confirmation
                if strategy == 'extension':
                    actions = fm.organize_by_extension(target, dry_run=True)
                elif strategy == 'date':
                    actions = fm.organize_by_date(target, dry_run=True)
                else:
                    actions = fm.organize_by_category(target, dry_run=True)

                count = len(actions)
                # store pending operation for confirmation
                self._pending_organize = {'fm': fm, 'target': target, 'strategy': strategy, 'actions': actions}
                return f"I found {count} files to organize in {target} using strategy '{strategy}'. Shall I proceed? (yes/no)"
            except Exception as e:
                return f"Failed to plan organization: {e}"
        
        if "open_website" in intent:
            # Extract URL from input or use default
            if "http" in ui:
                # Extract URL from input
                import re
                url_match = re.search(r'https?://[^\s]+', ui)
                if url_match:
                    url = url_match.group(0)
                else:
                    url = "https://www.google.com"
            else:
                url = "https://www.google.com"
            return browser.open_website(url)
            
        elif "web_search" in intent:
            # Extract search query
            query = ui.replace("search", "").replace("for", "").strip()
            return search.web_search(query)
            
        elif "system_command" in intent:
            if "shutdown" in ui:
                return system.shutdown()
            # Add other system commands here
            
        else:  # general_query or unknown
            response = self.llm_manager.ask_llm(ui)
            try:
                if self.memory:
                    self.memory.remember(ui, response)
            except Exception:
                pass
            return response

    # Perception helpers (optional)
    def start_perception(self):
        """Start screen/audio perception if enabled in Config.

        This will create a `ui.widget.Widget` instance (if available) that
        can run background capture threads. We keep it optional to avoid
        importing GUI/audio libs when not needed.
        """
        if not (Config.ENABLE_SCREEN_CAPTURE or Config.ENABLE_AUDIO):
            return None

        try:
            from ui.widget import Widget
        except Exception:
            return None

        self._perception_widget = Widget(
            image_callback=(self._on_image if Config.ENABLE_SCREEN_CAPTURE else None),
            audio_callback=(self._on_audio if Config.ENABLE_AUDIO else None),
            ocr_callback=(self._on_ocr if Config.ENABLE_OCR else None),
            image_interval=1.0,
            audio_interval=1.0,
            audio_duration=0.5,
        )
        try:
            self._perception_widget.start()
            return self._perception_widget
        except Exception:
            return None

    def stop_perception(self):
        try:
            if getattr(self, '_perception_widget', None):
                self._perception_widget.stop()
                self._perception_widget = None
        except Exception:
            pass

    def _on_image(self, img):
        # optional hook: store small preview into memory or pass to LLM
        try:
            if self.memory:
                self.memory.remember('screenshot', f'<image {img.size}>')
        except Exception:
            pass

    def _on_audio(self, data, sr):
        try:
            if self.memory:
                self.memory.remember('audio_snippet', f'<audio {len(data)} samples>')
        except Exception:
            pass

    def _on_ocr(self, text: str):
        try:
            if self.memory:
                self.memory.remember('ocr', text)
        except Exception:
            pass

agent = Agent()