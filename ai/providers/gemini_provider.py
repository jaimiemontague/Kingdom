"""
Google Gemini provider implementation.
"""
from .base import BaseLLMProvider
from config import GEMINI_API_KEY


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider."""
    
    def __init__(self, model: str = "gemini-pro"):
        self.model_name = model
        self.model = None
        self._init_client()
    
    def _init_client(self):
        """Initialize the Gemini client."""
        if not GEMINI_API_KEY:
            print("Warning: GEMINI_API_KEY not set")
            return
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel(self.model_name)
        except ImportError:
            print("Warning: google-generativeai package not installed")
        except Exception as e:
            print(f"Warning: Failed to initialize Gemini client: {e}")
    
    @property
    def name(self) -> str:
        return "gemini"
    
    def is_available(self) -> bool:
        return self.model is not None and GEMINI_API_KEY
    
    def complete(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        timeout: float = 5.0
    ) -> str:
        """Send completion request to Gemini."""
        if not self.is_available():
            raise RuntimeError("Gemini client not available")
        
        try:
            # Gemini combines system and user prompts
            full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
            
            response = self.model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 200,
                }
            )
            
            return response.text
            
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")

