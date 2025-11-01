from core.llm_manager import LLMManager
from core.config import Config
from core.memory import Memory 

class FileManager:
    def __init__(self):
        self.llm_manager = LLMManager()
        self.config = Config()

    def create_file(self, file_name, content):
        """Create a new file"""
        with open(file_name, 'w') as f:
            f.write(content)