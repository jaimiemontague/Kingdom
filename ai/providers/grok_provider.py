"""
xAI Grok provider implementation.
Uses OpenAI-compatible API.
"""
from .base import BaseLLMProvider
from config import GROK_API_KEY


class GrokProvider(BaseLLMProvider):
    """xAI Grok provider (OpenAI-compatible API)."""
    
    def __init__(self, model: str = "grok-beta"):
        self.model = model
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize the Grok client using OpenAI SDK."""
        if not GROK_API_KEY:
            print("Warning: GROK_API_KEY not set")
            return
        
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=GROK_API_KEY,
                base_url="https://api.x.ai/v1"
            )
        except ImportError:
            print("Warning: openai package not installed (required for Grok)")
        except Exception as e:
            print(f"Warning: Failed to initialize Grok client: {e}")
    
    @property
    def name(self) -> str:
        return "grok"
    
    def is_available(self) -> bool:
        return self.client is not None and GROK_API_KEY
    
    def complete(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        timeout: float = 5.0
    ) -> str:
        """Send completion request to Grok."""
        if not self.is_available():
            raise RuntimeError("Grok client not available")
        
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
            raise RuntimeError(f"Grok API error: {e}")

