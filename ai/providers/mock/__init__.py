"""
MockProvider responder package (WK81 Round D-1).

The 4 mock LLM responders extracted from ai/providers/mock_provider.py via the
proven pure-move pattern: each function takes the MockProvider instance as
`provider`, and MockProvider keeps a 1-line delegating wrapper. MockProvider
itself stays in ai/providers/mock_provider.py as the facade (the provider
registry imports it from there).

Modules:
- autonomous.py      -> mock_autonomous_decision(provider, user_prompt)
- direct_prompt.py   -> mock_direct_prompt(provider, user_prompt)
- legacy_decision.py -> make_decision(provider, ...)
- conversation.py    -> mock_conversation_response(provider, system_prompt, user_prompt)
"""
