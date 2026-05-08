# Lessons Learned

Rules and patterns discovered through bugs, fixes, and corrections. Read this before making any changes.

## Format

Each lesson follows this structure:
- **Bug**: What went wrong
- **Root Cause**: Why it happened
- **Rule**: The rule that prevents it from recurring
- **Files**: Which files are affected

---

## Agent produces no reasoning — only formats tool output

- **Bug**: Agent called tools but the final response just formatted the raw JSON; no business reasoning, no campaign comparison, no prioritization.
- **Root Cause**: Two problems:
  1. The while loop's last API call (when `stop_reason == "end_turn"`) still passes `tools=TOOLS`. Claude sees it can call more tools and takes the lazy path — shallow formatting instead of deep analysis.
  2. System prompt didn't explicitly instruct Claude to synthesize after seeing tool results.
- **Rule**: After the tool-execution loop exits, make a dedicated reasoning-only API call **without `tools=`**. This forces Claude to synthesize rather than format. Name the two phases explicitly in code: "Phase 1: data-gathering loop" and "Phase 2: reasoning pass".
- **Files**: `src/media_spend_agent/agent.py` — `chat()` method structure and `SYSTEM_PROMPT`.
