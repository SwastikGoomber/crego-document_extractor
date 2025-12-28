import logging
import os
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None
import ollama
import time
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
# Suppress noisy HTTP logs from httpx/ollama
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        """
        Priority 1: Gemma (via Ollama) - Primary/Default
        Priority 2: Gemini 2.5 Flash Lite (via Google AI Studio API) - Backup
        """
        self.primary_model = "gemma3:1b"  # Primary: Local Ollama model
        self.backup_model = "gemini-2.5-flash-lite"  # Backup: Google AI Studio
        self.google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        

        if self.google_api_key and genai:
            try:
                self.gemini_client = genai.Client(api_key=self.google_api_key)
                logger.info(f"LLM Service initialized with Primary: {self.primary_model} (Ollama), Backup: {self.backup_model} (Google AI Studio)")
            except Exception as e:
                logger.warning(f"Failed to initialize Google AI Studio client: {e}. Will use Ollama only.")
                self.gemini_client = None
        else:
            if not genai:
                logger.debug("google.genai package not found. Will use Ollama only.")
            if not self.google_api_key:
                logger.debug("GOOGLE_API_KEY or GEMINI_API_KEY not found. Will use Ollama only.")
            self.gemini_client = None
            logger.info(f"LLM Service initialized with Primary: {self.primary_model} (Ollama)")

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """
        Generates text using the best available model.
        """
        try:
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            
            response = ollama.chat(model=self.primary_model, messages=messages)
            return response['message']['content']
        except Exception as e:
            logger.warning(f"Ollama generation failed: {str(e)}")
        
        if self.gemini_client and types:
            try:
                time.sleep(1)
                
                contents = []
                
                if system_instruction:
                    full_prompt = f"System context: {system_instruction}\n\nTask: {prompt}"
                else:
                    full_prompt = prompt
                
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=full_prompt)]
                ))
                
                config = types.GenerateContentConfig(
                    temperature=0.2,
                    top_p=0.95,
                    max_output_tokens=100
                )
                
                response = self.gemini_client.models.generate_content(
                    model=self.backup_model,
                    contents=contents,
                    config=config
                )
                return response.text
            except Exception as e:
                logger.error(f"Gemini generation failed: {str(e)}")
        
        return "Error: Could not generate response from any model."

if __name__ == "__main__":
    llm = LLMService()
    print(llm.generate("Say hello in JSON format."))

