# central place for configs
import requests
import os

# general settings 

Assitant_name = "Buddi"
Use_VOICE  = False #toggle speech mode 
MEMORY_ENALED = True # toggle memory module

# when setting an api key choose deepseek or openai 
api_key = os.getenv("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")
url = f"https://api.example.com/data?param=value&apiKey={api_key}"
response = requests.get(url)

# evaluate the pros and cons ogf both of them and choose that one thta best fits your need 
# settings.py - Define your work domains
WORK_DOMAINS = {
    "coding": ["debugging", "code review", "algorithm design", "documentation"],
    "writing": ["emails", "reports", "documentation", "presentations"],
    "research": ["web search", "data analysis", "summarization"],
    "planning": ["task management", "scheduling", "priority setting"],
    "communication": ["email drafting", "meeting notes", "follow-ups"]
}

