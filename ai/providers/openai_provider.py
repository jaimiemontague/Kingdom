"""
OpenAI GPT provider implementation.
"""
from .base import BaseLLMProvider
from config import OPENAI_API_KEY, OPENAI_MODEL


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider."""
    
    def __init__(self, model: str | None = None):
        self.model = model or OPENAI_MODEL
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
        return self.client is not None and bool(OPENAI_API_KEY)
    
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
            base_kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "timeout": timeout,
            }
            # gpt-5 family expects max_completion_tokens, while older models
            # may still accept max_tokens. Try modern first, then fallback.
            attempts = (
                {"max_completion_tokens": 600},
                {"max_tokens": 200},
            )
            last_error = None
            for token_kwargs in attempts:
                try:
                    response = self.client.chat.completions.create(
                        **base_kwargs,
                        **token_kwargs,
                    )
                    return (response.choices[0].message.content or "").strip()
                except Exception as e:
                    msg = str(e)
                    if "max_tokens" in msg or "max_completion_tokens" in msg or "unsupported_parameter" in msg:
                        last_error = e
                        continue
                    raise
            raise RuntimeError(last_error or "Unknown OpenAI token parameter error")
            
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")

