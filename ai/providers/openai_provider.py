"""
OpenAI GPT provider implementation.
"""
from .base import BaseLLMProvider
from config import OPENAI_API_KEY


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider."""
    
    def __init__(self, model: str = "gpt-3.5-turbo"):
        self.model = model
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize the OpenAI client."""
        if not OPENAI_API_KEY:
            print("Warning: OPENAI_API_KEY not set")
            return
        
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=OPENAI_API_KEY)
        except ImportError:
            print("Warning: openai package not installed")
        except Exception as e:
            print(f"Warning: Failed to initialize OpenAI client: {e}")
    
    @property
    def name(self) -> str:
        return "openai"
    
    def is_available(self) -> bool:
        return self.client is not None and OPENAI_API_KEY
    
    def complete(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        timeout: float = 5.0
    ) -> str:
        """Send completion request to OpenAI."""
        if not self.is_available():
            raise RuntimeError("OpenAI client not available")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=200,
                timeout=timeout
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")

