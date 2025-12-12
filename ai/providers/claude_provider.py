"""
Anthropic Claude provider implementation.
"""
from .base import BaseLLMProvider
from config import ANTHROPIC_API_KEY


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider."""
    
    def __init__(self, model: str = "claude-3-haiku-20240307"):
        self.model = model
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize the Anthropic client."""
        if not ANTHROPIC_API_KEY:
            print("Warning: ANTHROPIC_API_KEY not set")
            return
        
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        except ImportError:
            print("Warning: anthropic package not installed")
        except Exception as e:
            print(f"Warning: Failed to initialize Anthropic client: {e}")
    
    @property
    def name(self) -> str:
        return "claude"
    
    def is_available(self) -> bool:
        return self.client is not None and ANTHROPIC_API_KEY
    
    def complete(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        timeout: float = 5.0
    ) -> str:
        """Send completion request to Claude."""
        if not self.is_available():
            raise RuntimeError("Claude client not available")
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            return response.content[0].text
            
        except Exception as e:
            raise RuntimeError(f"Claude API error: {e}")

