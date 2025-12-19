"""
Kingdom Sim - A Majesty-inspired game with LLM-controlled heroes.

Usage:
    python main.py [--provider <provider_name>]
    
Providers:
    openai  - OpenAI GPT (requires OPENAI_API_KEY)
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


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Kingdom Sim - A Majesty-inspired game with LLM-controlled heroes"
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="mock",
        choices=["openai", "claude", "gemini", "grok", "mock"],
        help="LLM provider to use for hero decisions (default: mock)"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM integration, use only basic AI"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    print("=" * 50)
    print("  Kingdom Sim - LLM-Powered Fantasy Kingdom")
    print("=" * 50)
    print()
    
    # Create the game engine
    print("Initializing game engine...")
    game = GameEngine()
    
    # Set up AI
    if args.no_llm:
        print("Running with basic AI only (no LLM)")
        ai_controller = BasicAI(llm_brain=None)
    else:
        print(f"Setting up LLM brain with provider: {args.provider}")
        try:
            llm_brain = LLMBrain(provider_name=args.provider)
            ai_controller = BasicAI(llm_brain=llm_brain)
            print(f"LLM brain initialized successfully")
        except Exception as e:
            print(f"Warning: Failed to initialize LLM brain: {e}")
            print("Falling back to basic AI only")
            ai_controller = BasicAI(llm_brain=None)
    
    game.ai_controller = ai_controller
    
    print()
    print("Controls:")
    print("  1         - Build Warrior Guild ($150)")
    print("  2         - Build Marketplace ($100)")
    print("  3         - Build Ranger Guild ($175)")
    print("  4         - Build Rogue Guild ($160)")
    print("  5         - Build Wizard Guild ($220)")
    print("  6         - Build Blacksmith ($200)")
    print("  7         - Build Inn ($150)")
    print("  8         - Build Trading Post ($250)")
    print("  T         - Build Temple Agrela ($400)")
    print("  G         - Build Gnome Hovel ($300)")
    print("  E         - Build Elven Bungalow ($350)")
    print("  V         - Build Dwarven Settlement ($300)")
    print("  U         - Build Guardhouse ($200)")
    print("  Y         - Build Ballista Tower ($300)")
    print("  O         - Build Wizard Tower ($500)")
    print("  F         - Build Fairgrounds ($400)")
    print("  I         - Build Library ($350)")
    print("  R         - Build Royal Gardens ($250)")
    print("  H         - Hire Hero ($50)")
    print("  B         - Place Bounty ($50)")
    print("  Click     - Select hero/building")
    print("  P         - Use potion (selected hero)")
    print("  Esc       - Pause")
    print("  Space     - Center on Castle (reset zoom)")
    print("  WASD / Mouse Edge - Scroll camera")
    print("  Mouse Wheel / +/- - Zoom")
    print()
    print("Starting game...")
    print()
    
    # Run the game
    game.run()
    
    print("Thanks for playing!")


if __name__ == "__main__":
    main()

