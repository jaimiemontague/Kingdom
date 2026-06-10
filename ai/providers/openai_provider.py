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
            # WK136: gpt-5 family is a reasoning model line. Two consequences:
            # 1. Reasoning tokens count against max_completion_tokens — a small
            #    budget (600) gets entirely eaten by reasoning and the content
            #    comes back EMPTY (finish_reason=length), which the brain maps
            #    to the canned "I am thinking, Sovereign..." fallback. Give a
            #    generous budget so real text survives.
            # 2. reasoning_effort="minimal" (gpt-5+; SDK >= ~1.58 passes it
            #    through) cuts reasoning latency dramatically — right for short
            #    in-character chat. Ladder: minimal -> low -> none, in case the
            #    deployed SDK/model rejects a value or the parameter itself.
            # Note: temperature is deliberately never passed — gpt-5 models
            # reject non-default values.
            if self.model.lower().startswith("gpt-5"):
                attempts = (
                    {"max_completion_tokens": 2000, "reasoning_effort": "minimal"},
                    {"max_completion_tokens": 2000, "reasoning_effort": "low"},
                    {"max_completion_tokens": 2000},
                    {"max_tokens": 200},
                )
            else:
                # Older models: max_completion_tokens first, legacy max_tokens fallback.
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
                except TypeError as e:
                    # Very old SDK without the reasoning_effort named param.
                    if "reasoning_effort" in str(e) and "reasoning_effort" in token_kwargs:
                        last_error = e
                        continue
                    raise
                except Exception as e:
                    msg = str(e)
                    if (
                        "max_tokens" in msg
                        or "max_completion_tokens" in msg
                        or "reasoning_effort" in msg
                        or "unsupported_parameter" in msg
                        or "unsupported_value" in msg
                    ):
                        last_error = e
                        continue
                    raise
            raise RuntimeError(last_error or "Unknown OpenAI token parameter error")

        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")

