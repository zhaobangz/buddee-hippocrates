import pyttsx3
import threading 
from core.config import Config

engine = pyttsx3.init()

class SpeechOutput:

    def __init__(self):
        self.engine = pyttsx3.init()
        self._setup_voice()
        self.is_speaking = False
        self.speech_queue = []
        self.thread = None

    def _setup_voice(self):
        """Configure the text to speech engine"""

        try:
            #get available voices
            voices = self.engine.getProperty('voices')
            #prefer the female voice if available
            for voice in voices:
                if "female" in voice.name.lower() or 'zira' in voice.name.lower():
                    self.engine.setProperty('voice', voice.id)
                    break 
                else:
                    self.engine.setProperty('voice', voices[0].id) #default to the first voice
                    
                #set the speech properties
                self.engine.setProperty('rate', 180) #speaking speed
                self.engine.setProperty('volume', 1) #volume range = 0.0 to 1.0
        except Exception as e:
            print(f"Error Setting Up Voice: {e}")

    def send_speech_output(self,text):
        """convert text to speech (non-blocking)"""
        if not text or not Config.USE_VOICE:
            return
        
        print(f"{Config.ASSISTANT_NAME}: {text}")

        #add to queue and start speaking threafd if not already running 
        self.speech_queue.append(text)
        if not self.is_speaking:
            self._start_speaking_thread()

    def _start_speaking_thread(self):
        """start a thread to process the speech queue"""

        if self.thread and self.thread.is_alive():
            return
        
        self.thread = threading.Thread(target = self._process_speech_queue)
        self.thread.daemon = True 
        self.thread.start()

    def _process_speech_queue(self):
        """Process the speech queue in a separate thread"""
        self.is_speaking = True 

        try:
            while self.speech_queue:
                text = self.speech_queue.pop(0)
                self.engine.say(text)
                self.engine.runAndWait()

        finally:
            self.is_speaking = False 

        def stop(self):
            """stop any outgoing speech"""
            try:
                self.engine.stop()
                self.speech_queue.clear()
            except:
                pass

speech_output = SpeechOutput()




        