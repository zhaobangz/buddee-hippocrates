import speech_recognition as sr  # type: ignore
from core.config import Config  # type: ignore


class SpeechInput:

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300 #adjust for sensitivity issues if needed 
        self.recognizer.dynamic_energy_threshod = True
        self.recognizer.pause_threhold = 0.8 #time to wait for the speech to end



    def get_speech_input(self, timeout = 5, phrase_time_limit = 10):
        """
        CAPTURE SPEECH IPUT FROM THE MICROPHONE

        ARGUMENTS:
        TIMEOUT(INT): SECONDS TO WAIT FOR SPEED TO START
        PHRASE_TIME_LIMIT(INT): MAX SECONDS FOR A PHRASE 
        
        RETURNS

        STR: RECOGNIZED TEXT OR NONE IF NO SPEECH IS DETECTED 

        """
        try:
            with sr.Microphone() as source:
                print(f"{Config.ASSISTANT_NAME} is listening...")
                #adjust for ambient noise
                self.recognizer.adjust_for_Ambient_noise(source, duration=0.5)

                #listen for audio input 
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit
                )

            # Recognize speech using Google's speech recognition
            text = self.recognizer.recognize_google(audio)
            print(f"You said: {text}")
            return text.lower()
            
        except sr.WaitTimeoutError:
            # No speech detected within timeout
            return None
        except sr.UnknownValueError:
            print("Sorry, I didn't understand that.")
            return None
        except sr.RequestError as e:
            print(f"Speech recognition service error: {e}")
            return "Speech recognition service is unavailable."
        except Exception as e:
            print(f"Error in speech input: {e}")
            return None

# Create a global instance
speech_input = SpeechInput()


            

