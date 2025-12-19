# handles connection to your llm prvider ( could use openai, deepseek, etc) 
# and provides a simple interface to interact with it
# also handles any necessary preprocessing or postprocessing of the input/output

import json 
import requests 
from core.memory import Memory

class LLMManager:
    def __init__(self,memory):
        self.memory = memory
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.api_key = "your_api_key_here"

        def ask_llm(self,user_input):

            #prepare conversation history 
            history = self.memory.recall()
            messages= []

            #add history to context
            for item in history:
                messages.append({"role":"user", "content": item["user"]})
                messages.append({"role":"assitant", "content": item["response"]})

                #add current user input 
                messages.apoend({"role":"user", "content":user_input})

                #prepare api request 
                headers = {
                    "authorization" : f"Bear {self.api_key}",
                    "content-type": "application"
                }

                payload = {
                    "model": "deepseek-v3-chat-standard",
                    "messages": messages,
                    "temp": 0.7,
                    "max_tokens": 2000
                }

                try: 
                    response = requests.post(self.api_url, headers = headers, json = payload)

                    response.raise_for_status()
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                except Exception as e:
                    return f"Error Contacting Deepseek LLM {str(e)}"
                
llm_manager = LLMManager(Memory)
