# decides what to do with the input (use llm vs tool)

from core.llm_manager import LLMManager
from core.memory import Memory
from core.config import Config
from tools import browser, system, search
import speech_recognition as sr
import pyttsx3

class Agent: 
    def __init__(self):
        self.memory = Memory() if Config.Memory_Enabled else None
        self.llm_manager = LLMManager(self.memory)
        self.recognizer = sr.Recognizer() if Config.USE_VOICE else None 
        self.tts_engine = pyttsx3.init() if Config.USE_VOICE else None 

        if Config.USE_VOICE and self.tts_engine:
            #set voice properties 
            voices = self.tts_engine.getProperty('voices')
            self.tts_engine.setProperty('voice', voices[0].id) #use of the first avaiable voice 
            self.tts_engine.setProperty('rate', 150) # speed percent

    def listen(self):
        """Listen for voice input"""
        if not self.recognizer:
            return None
        
        with sr.Microphone() as source:
            print("f{Config.ASSISTANT_NAME} is listening... ")
            self.recognizer.adjust_for_ambient_noise(source)

            try:
                audio = self.recognizer.listen(source, timeout = 5)
                text = self.recognizer.recognize_google(audio)
                print(f"You said:{text}")
                return text
            except sr.UnknownValueError:
                return "Sorry, I did not catch that."
            except sr.RequestError:
                return "Sorry, my speech service is down."
            except sr.WaitTimeoutError:
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

        intent = self.detect_intent(ui)
        
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
            self.memory.remember(ui, response)
            return response

agent =Agent()