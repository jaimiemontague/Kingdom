# Root scripts archived (WK40 Stage 5, Task 5-A)

These files lived in the repository root and were one-off PM utilities, extractors, LLM smoke scripts, or agent-response helpers. They were moved here in **2026-04** to keep the project root clean. Nothing in `game/`, `ai/`, `tools/` (except this folder), or `tests/` imported them.

To run a script manually, use from repo root:

```powershell
python tools/archive/root_wk40_stage5/<filename>.py
```

| File | Former purpose (approx.) |
|------|---------------------------|
| `pm_*.py` | Sprint / PM hub maintenance one-offs |
| `extract_*.py` | Log or plan extraction utilities |
| `get_agent_responses.py` | Agent response helper |
| `test_llm.py` | OpenAI API smoke (requires `OPENAI_API_KEY`) |

GLB debug scratch files (`scratch_debug_glb*.py`) were **deleted** (no references); re-create from git history if needed.
