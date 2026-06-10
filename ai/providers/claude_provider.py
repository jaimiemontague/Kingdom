"""
Anthropic Claude provider implementation.

WK134 provider audit:
- Model is no longer pinned to the deprecated ``claude-3-haiku-20240307``
  (retiring 2026-04-19). Resolution order: explicit ``model=`` arg >
  ``ANTHROPIC_MODEL`` env var (read at construction time, .env supported via
  config's load_dotenv) > ``DEFAULT_ANTHROPIC_MODEL``.
- Default is ``claude-sonnet-4-6`` — current Sonnet-class model: the best
  speed/cost balance for many short per-hero decision calls (Opus-class is
  overkill for a 200-token JSON decision; set ANTHROPIC_MODEL to override,
  e.g. ``claude-haiku-4-5`` for cheapest or ``claude-opus-4-8`` for smartest).
- ``timeout`` is now actually honored per request (it was previously accepted
  and ignored, leaving the SDK's long default timeout to stall the worker).
"""
import os

from .base import BaseLLMProvider
from config import ANTHROPIC_API_KEY

# Current Sonnet-class model (bare alias, no date suffix — Anthropic aliases
# track the latest snapshot). Override with the ANTHROPIC_MODEL env var.
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, model: str = None):
        self.model = model or os.getenv("ANTHROPIC_MODEL", "").strip() or DEFAULT_ANTHROPIC_MODEL
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
                ],
                timeout=float(timeout),
            )

            return response.content[0].text

        except Exception as e:
            raise RuntimeError(f"Claude API error: {e}")
