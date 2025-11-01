# keeps history of interactions with the user and the assistant
# provides context to the llm for better responses
# could implement different memory strategies ( e.g. short term, long term, etc)
# could also handle saving/loading memory from disk if needed

#simple history for now (just text log for now)

import json
import os

class Memory:
    def __init__(self,max_history=10, persist_file ="memory.json"):
        self.history = []
        self.max_history = max_history
        self.persist_file = persist_file
        self.load_memory()

    def remember(self, ui, response):
        self.history.append({"user": ui, "assistant": response})

        #keep only the most recent interactions between the user and the llm 
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        self.save_memory()


    def recall(self, num_interactions=5):
        return self.history[-num_interactions:] if self.history else []
    
    def save_memory(self):
        try:
            with open(self.persist_file, 'w') as f:
                json.dump(self.history, f)
        except Exception as e:
            print(f"Error Saving Memory to Disk: {e}")

    def load_memory(self):
        if os.path.exists(self.persist_file):
            try:
                with open(self.persist_file, 'r') as f:
                          self.history = json.load(f)
            except Exception as e:
                print(f"Error Loading Memory: {e}")
                self.history = []

memory = Memory()
    