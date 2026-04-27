"""
Kingdom Sim - A Majesty-inspired game with LLM-controlled heroes.

Usage:
    python main.py [--provider <provider_name>]
    
Providers:
    openai  - OpenAI GPT (reads OPENAI_API_KEY/OPENAI_MODEL from .env)
    claude  - Anthropic Claude (requires ANTHROPIC_API_KEY)  
    gemini  - Google Gemini (requires GEMINI_API_KEY)
    grok    - xAI Grok (requires GROK_API_KEY)
    mock    - Mock provider for testing (no API key needed)
"""
import sys
import argparse
from game.engine import GameEngine
from ai.basic_ai import BasicAI
from ai.llm_brain import LLMBrain
from config import LLM_PROVIDER


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Kingdom Sim - A Majesty-inspired game with LLM-controlled heroes"
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=LLM_PROVIDER,
        choices=["openai", "claude", "gemini", "grok", "mock"],
        help=f"LLM provider (default from .env: {LLM_PROVIDER})"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM integration, use only basic AI"
    )
    parser.add_argument(
        "--early-nudge",
        type=str,
        default=None,
        choices=["auto", "off", "force"],
        help="Early pacing nudge mode (Build B). Overrides config EARLY_PACING_NUDGE_MODE if set."
    )
    parser.add_argument(
        "--renderer",
        type=str,
        default="ursina",
        choices=["pygame", "ursina"],
        help="Rendering frontend (default: ursina / 3D; use pygame for 2D)",
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    print("=" * 50)
    print("  Kingdom Sim - LLM-Powered Fantasy Kingdom")
    print("=" * 50)
    print()
    
    # Set up AI Factory for Ursina to spawn internally if needed
    def create_ai():
        if args.no_llm:
            return BasicAI(llm_brain=None)
        else:
            try:
                llm_brain = LLMBrain(provider_name=args.provider)
                return BasicAI(llm_brain=llm_brain)
            except Exception as e:
                return BasicAI(llm_brain=None)

    if args.renderer == "ursina":
        print("Launching Ursina 3D Viewer (MVP mode)...")
        from game.graphics.ursina_app import UrsinaApp
        viewer = UrsinaApp(ai_controller_factory=create_ai)
        
        # In Ursina, we must set up the event bus for the AI specifically since 
        # the engine is buried inside the UrsinaApp.
        ai_ctrl = viewer.engine.ai_controller
        llm = getattr(ai_ctrl, "llm_brain", None)
        if llm and hasattr(llm, "set_event_bus"):
            llm.set_event_bus(viewer.engine.event_bus)
            
        viewer.run()
        
    else:
        # Create the game engine
        print("Initializing game engine...")
        from game.pygame_input_manager import PygameInputManager
        input_manager = PygameInputManager()
        game = GameEngine(early_nudge_mode=args.early_nudge, input_manager=input_manager)
        
        # Set up AI
        game.ai_controller = create_ai()
        
        # Wire event bus to LLM brain
        llm_brain = getattr(game.ai_controller, "llm_brain", None)
        if llm_brain is not None and hasattr(llm_brain, "set_event_bus") and hasattr(game, "event_bus"):
            llm_brain.set_event_bus(game.event_bus)
        
        # Run the standard Pygame loop
        game.run()
    
    print("Thanks for playing!")


if __name__ == "__main__":
    main()

