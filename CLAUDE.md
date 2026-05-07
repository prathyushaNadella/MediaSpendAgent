# MediaSpendAgent

## Self-Learning Protocol

1. **Review LESSONS.md at session start** — Read it before making any changes. Never repeat a documented mistake.
2. **Update LESSONS.md after every bug fix or correction** — Document the bug, root cause, and the rule that prevents it. Be specific. Include file names.
3. **Ruthlessly iterate** — If a lesson is vague, sharpen it. If a pattern keeps recurring, escalate it to a CLAUDE.md rule. Delete lessons that are no longer relevant.
4. **Verify before done** — Never assume code works. Read the full flow. Check route names against navigators. Check UI works with AND without backend. Ask: "Would a staff engineer approve this?"
5. **No assumptions** — Don't guess file contents, route names, API shapes, or state. Read first, then change.

## Overview

An interactive AI-powered agent that computes incremental ROAS (iROAS) from Amazon Marketing Cloud (AMC) data and provides budget optimization recommendations to marketing managers.

**Full architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md)

## Tech Stack

- **Language**: Python 3.11+
- **LLM**: Claude API (Anthropic SDK) — conversational interface with tool use
- **Data**: pandas for analysis, AMC API for data ingestion
- **Cache**: SQLite for local API response caching
- **Interface**: CLI (Phase 1), Streamlit Web UI (Phase 2)
- **Testing**: pytest
- **Linting**: ruff
- **Validation**: pydantic

## Project Structure

```
MediaSpendAgent/
├── CLAUDE.md              # Dev rules and project context (this file)
├── ARCHITECTURE.md        # System design and component details
├── LESSONS.md             # Bug log — updated every session
├── README.md
├── pyproject.toml
├── src/
│   └── media_spend_agent/
│       ├── __init__.py
│       ├── main.py              # CLI entrypoint
│       ├── agent.py             # Claude-powered conversational agent
│       ├── amc/
│       │   ├── __init__.py
│       │   ├── client.py        # AMC API client (OAuth, query execution)
│       │   ├── spend.py         # Spend data fetching
│       │   └── conversions.py   # Conversion data fetching
│       ├── analytics/
│       │   ├── __init__.py
│       │   ├── iroas.py         # iROAS computation
│       │   ├── baseline.py      # Baseline estimation
│       │   └── recommendations.py  # Budget reallocation logic
│       └── config.py            # Settings & credentials (pydantic)
├── tests/
│   ├── test_iroas.py
│   ├── test_baseline.py
│   └── test_recommendations.py
└── .env.example
```

## Key Formula

```
iROAS = (actual_revenue - baseline_revenue) / spend
```

- Baseline: average daily organic revenue estimated from low/zero-spend periods
- Applied per campaign, per ad type, at daily granularity

## Recommendation Thresholds

| iROAS | Action | Meaning |
|-------|--------|---------|
| < 1.0 | CUT | Destroying value — spend exceeds incremental revenue |
| 1.0–2.0 | MAINTAIN | Marginal — monitor closely |
| ≥ 2.0 | SCALE | Strong return — candidate for budget increase |

Budget reallocation: shift from CUT → SCALE, capped at 30% increase per campaign.

## Coding Rules

- Type hints on all function signatures
- No classes unless state management requires it; prefer functions
- AMC API logic stays isolated in `amc/` — never import analytics into amc or vice versa
- Analytics functions must be pure: data in, results out, no side effects
- Use pydantic for config and all data validation
- Never commit `.env` or credentials — `.gitignore` enforced

## Development

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run
python -m media_spend_agent

# Test
pytest

# Lint
ruff check src/ tests/
```

## Environment Variables

```
ANTHROPIC_API_KEY=         # Claude API key
AMC_CLIENT_ID=             # Amazon Advertising API client ID
AMC_CLIENT_SECRET=         # Amazon Advertising API client secret
AMC_REFRESH_TOKEN=         # OAuth refresh token
AMC_INSTANCE_ID=           # AMC instance identifier
AMC_ADVERTISER_ID=         # Advertiser ID
```

## Phases

### Phase 1 (Current): CLI + Core Analytics
- AMC API integration (spend + conversions)
- iROAS computation with simple baseline
- Budget recommendations
- Claude-powered CLI chat interface

### Phase 2: Web UI + Enhancements
- Streamlit dashboard with charts
- Historical trend visualization
- Multi-channel support (Google Ads, Meta)
- Advanced incrementality (geo-based or MMM)

## Pre-Change Checklist

Before modifying any file, verify:
- [ ] Read LESSONS.md for relevant past bugs
- [ ] Read the file you're about to change (no assumptions)
- [ ] Confirm API shapes by reading client code, not guessing
- [ ] After changes: run `pytest` and `ruff check src/ tests/`
- [ ] Update LESSONS.md if a bug was fixed
