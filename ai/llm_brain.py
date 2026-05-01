"""
LLM Brain - coordinates LLM decision making for heroes.
Uses async calls to prevent blocking the game loop.
"""
import json
import threading
import queue
from typing import Optional
from ai.context_builder import ContextBuilder
from ai.decision_moments import decision_moment_from_prompt_dict
from ai.decision_output_validator import validate_autonomous_decision
from ai.direct_prompt_validator import validate_direct_prompt_output
from ai.prompt_packs import (
    AUTONOMOUS_SYSTEM_PROMPT,
    build_autonomous_user_prompt,
    build_direct_prompt_messages,
)
from ai.prompt_templates import (
    SYSTEM_PROMPT,
    VALID_ACTIONS,
    TOOL_ACTIONS,
    OBEY_DEFY_VALUES,
    build_decision_prompt,
    get_fallback_decision,
)
from config import LLM_PROVIDER, LLM_TIMEOUT, CONVERSATION_TIMEOUT

# WK18: Optional event bus for dev tools — capture LLM prompts/responses (game.events is safe to import here).
try:
    from game.events import GameEventType
except ImportError:
    GameEventType = None


class LLMBrain:
    """
    Manages LLM decision requests and responses.
    Uses a separate thread for API calls to avoid blocking.
    """
    
    def __init__(self, provider_name: str = None):
        self.provider_name = provider_name or LLM_PROVIDER
        self.provider = self._create_provider()
        
        # Request queue: (hero_key, context) or (hero_key, payload, mode) for conversation
        self.request_queue = queue.Queue()
        
        # Response storage: hero_key -> decision
        self.responses = {}
        # Conversation responses: hero_key -> raw text (wk14)
        self.conversation_responses = {}
        self.response_lock = threading.Lock()
        
        # Background worker thread
        self.worker_thread = None
        self.running = False
        
        # WK18: Optional event bus for AI monitoring dev tools (set by engine/main).
        self._event_bus = None
        
        # Start the worker
        self.start()
    
    def set_event_bus(self, event_bus) -> None:
        """Set EventBus for emitting LLM prompt/response events (called by engine/main)."""
        self._event_bus = event_bus
    
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
        """Background worker that processes LLM requests (decision or conversation)."""
        while self.running:
            hero_key = None
            mode = None
            context = None
            try:
                item = self.request_queue.get(timeout=0.5)
                if len(item) == 2:
                    hero_key, context = item
                    mode = "decision"
                else:
                    hero_key, payload, mode = item
                    context = payload

                if mode == "conversation":
                    text = self._process_conversation(hero_key, context)
                    with self.response_lock:
                        self.conversation_responses[hero_key] = text
                else:
                    decision = self._process_request(hero_key, context)
                    with self.response_lock:
                        self.responses[hero_key] = decision
            except queue.Empty:
                continue
            except Exception as e:
                print(f"LLM worker error: {e}")
                if hero_key and mode == "conversation":
                    hc = {}
                    pm = ""
                    if isinstance(context, dict):
                        hc = context.get("hero_context") or {}
                        pm = str(context.get("player_message") or "")
                    with self.response_lock:
                        self.conversation_responses[hero_key] = validate_direct_prompt_output(
                            {
                                "spoken_response": "I'm at a loss for words right now.",
                                "interpreted_intent": "no_action_chat_only",
                                "tool_action": None,
                            },
                            hc,
                            pm,
                        )
    
    def _process_request(self, hero_key, context: dict) -> dict:
        """Process a single LLM request."""
        try:
            aut = context.get("wk50_autonomous")
            if isinstance(aut, dict):
                return self._process_autonomous_decision_request(hero_key, context, aut)
            # Build the prompt
            summary = ContextBuilder.build_summary(context)
            prompt = build_decision_prompt(context, summary)
            
            # WK18: Emit for dev tools overlay (non-blocking; bus queues and flushes on main thread).
            if self._event_bus and GameEventType is not None:
                self._event_bus.emit({
                    "type": GameEventType.LLM_PROMPT_SENT.value,
                    "hero_key": hero_key,
                    "system_prompt": SYSTEM_PROMPT,
                    "user_prompt": prompt,
                    "mode": "decision",
                })
            
            # Call the LLM
            response_text = self.provider.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                timeout=LLM_TIMEOUT
            )
            
            if self._event_bus and GameEventType is not None:
                self._event_bus.emit({
                    "type": GameEventType.LLM_RESPONSE_RECEIVED.value,
                    "hero_key": hero_key,
                    "response_text": response_text or "",
                    "mode": "decision",
                })
            
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

    def _process_autonomous_decision_request(
        self, hero_key: str, context: dict, aut: dict
    ) -> dict:
        """WK50 Phase 2A: autonomous moment prompt + per-moment action validation."""
        moment = decision_moment_from_prompt_dict(aut.get("moment") or {})
        if moment is None:
            return get_fallback_decision(context)
        try:
            user_prompt = build_autonomous_user_prompt(aut)
            if self._event_bus and GameEventType is not None:
                self._event_bus.emit(
                    {
                        "type": GameEventType.LLM_PROMPT_SENT.value,
                        "hero_key": hero_key,
                        "system_prompt": AUTONOMOUS_SYSTEM_PROMPT,
                        "user_prompt": user_prompt,
                        "mode": "decision",
                    }
                )
            response_text = self.provider.complete(
                system_prompt=AUTONOMOUS_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                timeout=LLM_TIMEOUT,
            )
            if self._event_bus and GameEventType is not None:
                self._event_bus.emit(
                    {
                        "type": GameEventType.LLM_RESPONSE_RECEIVED.value,
                        "hero_key": hero_key,
                        "response_text": response_text or "",
                        "mode": "decision",
                    }
                )
            parsed = self._parse_response(response_text or "")
            if parsed:
                validated = validate_autonomous_decision(parsed, moment)
                if validated:
                    return validated
            return get_fallback_decision(context)
        except Exception as e:
            print(f"LLM autonomous request failed for {hero_key}: {e}")
            return get_fallback_decision(context)

    def _parse_response(self, response_text: str) -> Optional[dict]:
        """Parse the LLM response into a decision dict (WK18: includes obey_defy and tool_action)."""
        try:
            text = response_text.strip()
            start = text.find('{')
            end = text.rfind('}') + 1

            if start >= 0 and end > start:
                json_str = text[start:end]
                decision = json.loads(json_str)

                action = decision.get("action", None)
                if isinstance(action, str):
                    action = action.strip()
                # Accept tool_action as action fallback when valid
                tool_action = decision.get("tool_action", "")
                if isinstance(tool_action, str):
                    tool_action = tool_action.strip()
                if not action and tool_action and tool_action in TOOL_ACTIONS:
                    action = tool_action
                if not action:
                    return None
                if action not in VALID_ACTIONS and action not in TOOL_ACTIONS:
                    return None

                target = decision.get("target", "")
                reasoning = decision.get("reasoning", "")
                obey_defy = decision.get("obey_defy", "")
                if isinstance(obey_defy, str):
                    obey_defy = obey_defy.strip()
                if obey_defy not in OBEY_DEFY_VALUES:
                    obey_defy = "Obey"

                out = {
                    "action": action,
                    "target": target if isinstance(target, str) else "",
                    "reasoning": reasoning if isinstance(reasoning, str) else "",
                    "obey_defy": obey_defy,
                    "tool_action": tool_action if tool_action in TOOL_ACTIONS else action,
                }
                return out
            return None
        except json.JSONDecodeError:
            return None
    
    def _process_conversation(self, hero_key, payload: dict) -> dict:
        """Process a conversation request; returns validated direct-prompt dict (WK50 Phase 2B)."""
        try:
            hero_context = payload.get("hero_context", {})
            conversation_history = payload.get("conversation_history", [])
            player_message = payload.get("player_message", "")
            system_prompt, user_prompt = build_direct_prompt_messages(
                hero_context, conversation_history, player_message
            )
            if self._event_bus and GameEventType is not None:
                self._event_bus.emit({
                    "type": GameEventType.LLM_PROMPT_SENT.value,
                    "hero_key": hero_key,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "mode": "conversation",
                })
            response_text = self.provider.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout=CONVERSATION_TIMEOUT,
            )
            if self._event_bus and GameEventType is not None:
                self._event_bus.emit({
                    "type": GameEventType.LLM_RESPONSE_RECEIVED.value,
                    "hero_key": hero_key,
                    "response_text": (response_text or "").strip(),
                    "mode": "conversation",
                })
            text = (response_text or "").strip()
            if not text:
                return validate_direct_prompt_output(
                    {
                        "spoken_response": "I am thinking, Sovereign... ask me again in a moment.",
                        "interpreted_intent": "no_action_chat_only",
                        "tool_action": None,
                    },
                    hero_context,
                    str(player_message or ""),
                )

            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                decision = json.loads(json_str)
                return validate_direct_prompt_output(
                    decision, hero_context, str(player_message or "")
                )

            return validate_direct_prompt_output(
                {
                    "spoken_response": text,
                    "interpreted_intent": "no_action_chat_only",
                    "tool_action": None,
                },
                hero_context,
                str(player_message or ""),
            )
        except Exception as e:
            print(f"Conversation request failed for {hero_key}: {e}")
            hc = payload.get("hero_context", {}) or {}
            pm = str(payload.get("player_message") or "")
            return validate_direct_prompt_output(
                {
                    "spoken_response": "I'm at a loss for words right now.",
                    "interpreted_intent": "no_action_chat_only",
                    "tool_action": None,
                },
                hc,
                pm,
            )

    def request_decision(self, hero_key, context: dict):
        """Queue a decision request for a hero."""
        self.request_queue.put((hero_key, context))

    def request_conversation(
        self,
        hero_key,
        hero_context: dict,
        conversation_history: list,
        player_message: str,
    ):
        """Queue a conversation request (wk14 Persona and Presence)."""
        payload = {
            "hero_context": hero_context,
            "conversation_history": conversation_history,
            "player_message": player_message,
        }
        self.request_queue.put((hero_key, payload, "conversation"))

    def get_conversation_response(self, hero_key) -> Optional[dict]:
        """Get and consume a conversation response for the hero, if ready."""
        with self.response_lock:
            return self.conversation_responses.pop(hero_key, None)
    
    def get_decision(self, hero_key) -> Optional[dict]:
        """Get a decision for a hero if one is ready."""
        with self.response_lock:
            return self.responses.pop(hero_key, None)
    
    def has_pending_decision(self, hero_key) -> bool:
        """Check if a decision is pending for a hero."""
        with self.response_lock:
            return hero_key in self.responses

