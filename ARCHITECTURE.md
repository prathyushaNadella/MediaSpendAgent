# Architecture — MediaSpendAgent

## System Overview

An interactive AI agent that computes incremental ROAS from Amazon Marketing Cloud data and delivers budget optimization recommendations to marketing managers via natural language.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        User Interface                            │
│  Phase 1: CLI (Rich terminal)    Phase 2: Streamlit Web UI       │
└──────────────────────┬───────────────────────────────────────────┘
                       │ natural language query
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Conversational Agent                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐      │
│  │  Claude API (Anthropic SDK)                            │      │
│  │  - Intent classification                               │      │
│  │  - Tool use: calls analytics functions as tools        │      │
│  │  - Response formatting with recommendations            │      │
│  └────────────────────────────────────────────────────────┘      │
└──────────────────────┬───────────────────────────────────────────┘
                       │ structured function calls
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Analytics Engine                               │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐      │
│  │  Baseline    │  │   iROAS      │  │  Recommendations  │      │
│  │  Estimation  │──▶  Calculator  │──▶  Engine            │      │
│  └──────┬───────┘  └──────────────┘  └───────────────────┘      │
│         │                                                        │
│  Methodology:                                                    │
│  - Organic baseline from low/zero-spend periods                  │
│  - iROAS = (total revenue - baseline revenue) / spend            │
│  - Recommendations based on iROAS thresholds + diminishing       │
│    returns heuristic                                             │
└──────────────────────┬───────────────────────────────────────────┘
                       │ data requests
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Data Layer                                  │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │  AMC Spend       │  │  AMC Conversions │  │  Local Cache  │   │
│  │  Client          │  │  Client          │  │  (SQLite)     │   │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────────┘   │
│           │                     │                                │
│           ▼                     ▼                                │
│  ┌──────────────────────────────────────────┐                    │
│  │  Data Joiner                             │                    │
│  │  - Join spend + conversions by date,     │                    │
│  │    campaign, ad type                     │                    │
│  │  - Fill gaps, validate integrity         │                    │
│  └──────────────────────────────────────────┘                    │
└──────────────────────┬───────────────────────────────────────────┘
                       │ API calls
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│              Amazon Marketing Cloud (AMC)                         │
│                                                                  │
│  - OAuth 2.0 via Amazon Advertising API                          │
│  - AMC SQL queries for spend + attributed conversions            │
│  - Daily granularity, by campaign and ad type                    │
└──────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. User Interface (`src/media_spend_agent/main.py`)

**Phase 1 — CLI**
- Rich terminal interface for interactive Q&A
- Supports multi-turn conversation with memory
- Displays tables and simple charts in terminal

**Phase 2 — Web UI**
- Streamlit app with chat panel + dashboard
- Trend charts, campaign comparison tables
- Exportable reports

### 2. Conversational Agent (`src/media_spend_agent/agent.py`)

Uses Claude API with tool use pattern:

```
User: "What's the iROAS for Sponsored Products last week?"
  │
  ▼
Claude classifies intent → calls get_iroas(campaign_type="SP", period="last_week")
  │
  ▼
Claude receives structured data → formats natural language response with table
```

**Tools exposed to Claude:**
| Tool | Purpose |
|------|---------|
| `get_iroas` | Compute iROAS for given filters (campaign, date range, ad type) |
| `get_spend_summary` | Return spend breakdown by campaign/ad type |
| `get_recommendations` | Generate budget reallocation suggestions |
| `get_trends` | Return daily iROAS trend for a period |

### 3. Analytics Engine (`src/media_spend_agent/analytics/`)

#### Baseline Estimation (`baseline.py`)
- Identifies low/zero-spend periods as organic revenue proxy
- Computes average daily organic revenue per campaign type
- Falls back to minimum-revenue-day heuristic when zero-spend days unavailable

#### iROAS Calculator (`iroas.py`)
```
Input:  daily spend + daily revenue per campaign
Output: iROAS per campaign, per ad type, and aggregate

iROAS = (actual_revenue - baseline_revenue) / spend

Where:
  baseline_revenue = avg_organic_daily_revenue × num_days
  actual_revenue   = sum of attributed revenue in period
  spend            = sum of ad spend in period
```

#### Recommendations Engine (`recommendations.py`)
- **Cut**: campaigns with iROAS < 1.0 (destroying value)
- **Maintain**: campaigns with 1.0 ≤ iROAS < 2.0 (marginal)
- **Scale**: campaigns with iROAS ≥ 2.0 (strong incremental return)
- **Reallocation**: shift budget from Cut → Scale campaigns
- Applies diminishing returns cap: don't recommend >30% budget increase per campaign

### 4. Data Layer (`src/media_spend_agent/amc/`)

#### AMC Client (`client.py`)
- OAuth 2.0 token management (refresh flow)
- AMC workflow creation and execution
- Query result polling and retrieval

#### Spend Client (`spend.py`)
- AMC SQL: daily spend by campaign ID, campaign name, ad type
- Date range filtering
- Returns pandas DataFrame

#### Conversions Client (`conversions.py`)
- AMC SQL: daily attributed conversions + revenue by campaign
- Matches spend granularity (daily, by campaign)
- Returns pandas DataFrame

#### Local Cache (SQLite)
- Caches API responses to avoid redundant AMC queries
- TTL-based expiry (default: 6 hours)
- Stores raw DataFrames as parquet blobs

## Data Model

```
spend_daily:
  date         DATE
  campaign_id  STRING
  campaign_name STRING
  ad_type      STRING    # SP, SB, SD, DSP
  spend        FLOAT

conversions_daily:
  date         DATE
  campaign_id  STRING
  campaign_name STRING
  ad_type      STRING
  conversions  INT
  revenue      FLOAT

joined_daily (computed):
  date, campaign_id, campaign_name, ad_type, spend, conversions, revenue

iroas_result (computed):
  campaign_id, campaign_name, ad_type, period_start, period_end,
  total_spend, total_revenue, baseline_revenue, incremental_revenue,
  iroas, recommendation (CUT | MAINTAIN | SCALE)
```

## Authentication Flow

```
1. User provides AMC credentials in .env
2. Client uses client_id + client_secret + refresh_token
3. OAuth 2.0 token exchange → access_token (1hr TTL)
4. Auto-refresh on 401 response
5. Access token cached in memory (never persisted)
```

## Error Handling Strategy

| Layer | Strategy |
|-------|----------|
| AMC API | Retry with exponential backoff (3 attempts), surface clear error to user |
| Data join | Warn on missing days, proceed with available data, note gaps in response |
| Analytics | Validate inputs (non-negative spend, date ranges), raise descriptive errors |
| Agent | Claude catches tool errors, explains issue to user in plain language |

## Security

- Credentials stored in `.env`, never committed (`.gitignore`)
- Access tokens held in memory only
- No PII processed — only campaign-level aggregate data
- AMC data stays local (no external transmission beyond Claude API calls for conversation)

## Future Extensions

- **Multi-channel**: Add Google Ads, Meta API clients alongside AMC
- **Advanced incrementality**: Geo-based experiments, MMM with PyMC-Marketing
- **Scheduled reports**: Daily/weekly iROAS email digests
- **Web UI**: Streamlit dashboard with interactive charts
- **Export**: CSV/PDF report generation
