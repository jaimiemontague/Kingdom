"""
LLM Brain - coordinates LLM decision making for heroes.
Uses async calls to prevent blocking the game loop.
"""
import json
import threading
import queue
from typing import Optional
from ai.context_builder import ContextBuilder
from ai.prompt_templates import (
    SYSTEM_PROMPT, VALID_ACTIONS, build_decision_prompt, get_fallback_decision
)
from config import LLM_PROVIDER, LLM_TIMEOUT


class LLMBrain:
    """
    Manages LLM decision requests and responses.
    Uses a separate thread for API calls to avoid blocking.
    """
    
    def __init__(self, provider_name: str = None):
        self.provider_name = provider_name or LLM_PROVIDER
        self.provider = self._create_provider()
        
        # Request queue: (hero_key, context) where hero_key is a stable identifier (int/str)
        self.request_queue = queue.Queue()
        
        # Response storage: hero_key -> decision
        self.responses = {}
        self.response_lock = threading.Lock()
        
        # Background worker thread
        self.worker_thread = None
        self.running = False
        
        # Start the worker
        self.start()
    
    def _create_provider(self):
        """Create the appropriate LLM provider."""
        try:
            if self.provider_name == "openai":
                from ai.providers.openai_provider import OpenAIProvider
                return OpenAIProvider()
            elif self.provider_name == "claude":
                from ai.providers.claude_provider import ClaudeProvider
                return ClaudeProvider()
            elif self.provider_name == "gemini":
                from ai.providers.gemini_provider import GeminiProvider
                return GeminiProvider()
            elif self.provider_name == "grok":
                from ai.providers.grok_provider import GrokProvider
                return GrokProvider()
            elif self.provider_name == "mock":
                from ai.providers.mock_provider import MockProvider
                return MockProvider()
            else:
                print(f"Unknown provider: {self.provider_name}, using mock")
                from ai.providers.mock_provider import MockProvider
                return MockProvider()
        except Exception as e:
            print(f"Failed to create provider {self.provider_name}: {e}")
            print("Falling back to mock provider")
            from ai.providers.mock_provider import MockProvider
            return MockProvider()
    
    def start(self):
        """Start the background worker thread."""
        if self.running:
            return
        
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
    
    def stop(self):
        """Stop the background worker."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
    
    def _worker_loop(self):
        """Background worker that processes LLM requests."""
        while self.running:
            try:
                # Get request with timeout
                hero_name, context = self.request_queue.get(timeout=0.5)
                
                # Process the request
                decision = self._process_request(hero_name, context)
                
                # Store the response
                with self.response_lock:
                    self.responses[hero_name] = decision
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"LLM worker error: {e}")
    
    def _process_request(self, hero_key, context: dict) -> dict:
        """Process a single LLM request."""
        try:
            # Build the prompt
            summary = ContextBuilder.build_summary(context)
            prompt = build_decision_prompt(context, summary)
            
            # Call the LLM
            response_text = self.provider.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                timeout=LLM_TIMEOUT
            )
            
            # Parse the response
            decision = self._parse_response(response_text)
            
            if decision:
                return decision
            else:
                # Failed to parse, use fallback
                return get_fallback_decision(context)
                
        except Exception as e:
            print(f"LLM request failed for {hero_key}: {e}")
            return get_fallback_decision(context)
    
    def _parse_response(self, response_text: str) -> Optional[dict]:
        """Parse the LLM response into a decision dict."""
        try:
            # Try to extract JSON from the response
            text = response_text.strip()
            
            # Find JSON in the response
            start = text.find('{')
            end = text.rfind('}') + 1
            
            if start >= 0 and end > start:
                json_str = text[start:end]
                decision = json.loads(json_str)
                
                # Validate required fields
                action = decision.get("action", None)
                if isinstance(action, str):
                    action = action.strip()

                if action and action in VALID_ACTIONS:
                    target = decision.get("target", "")
                    reasoning = decision.get("reasoning", "")
                    return {
                        "action": action,
                        "target": target if isinstance(target, str) else "",
                        "reasoning": reasoning if isinstance(reasoning, str) else "",
                    }
            
            return None
            
        except json.JSONDecodeError:
            return None
    
    def request_decision(self, hero_key, context: dict):
        """Queue a decision request for a hero."""
        self.request_queue.put((hero_key, context))
    
    def get_decision(self, hero_key) -> Optional[dict]:
        """Get a decision for a hero if one is ready."""
        with self.response_lock:
            return self.responses.pop(hero_key, None)
    
    def has_pending_decision(self, hero_key) -> bool:
        """Check if a decision is pending for a hero."""
        with self.response_lock:
            return hero_key in self.responses

