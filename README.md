# investing-agent
Agent to assist with investing decisions

**Quick Start**

Start Ollama LLM: `ollama serve llama3:latest`

Just start: `python -m src.run_monitor`

---

### Project Summary: Smart Market Monitor AI Agent (MVP)

I am building a small, monetizable AI agent to gain hands-on experience with autonomous agents. The MVP is a market monitoring and alerting tool, not a trading or recommendation system.

### Goal
Detect and summarize material market-moving events for a narrow set of companies or keywords and deliver high-signal alerts quickly, without providing buy/sell advice.

### What the agent does

- Monitors a single, reliable public data source (initially SEC EDGAR filings, e.g., 8-K, 10-Q, 10-K, Form 4).
- Fetches new filings on a schedule (cron).
- Pre-filters noise using simple rules (duplicates, boilerplate, minimum length).
- Uses an LLM to:
    - Summarize the filing in ≤5 bullets
    - Classify the type of event (earnings, legal, M&A, guidance, insider activity, etc.)
    - Assign an impact level (None / Low / Medium / High) with reasoning
    - Applies deterministic alert rules (e.g., alert only if impact ≥ Medium).
    - Sends concise alerts via email only (no dashboard).
- What it explicitly does NOT do
    - No trade execution
    - No buy/sell recommendations
    - No valuation or financial advice
    - No real-time price prediction
    - No dashboards or backtesting in MVP

### Data philosophy

This is a change-detection and summarization problem, not a valuation engine. Price, P/E, dividends, etc. are intentionally excluded from MVP to reduce complexity, cost, and compliance risk. Optional future enhancement: descriptive price context only (e.g., % move).

### LLM strategy

- Prefer local open-source LLMs (e.g., Llama 3 8B via Ollama) to avoid API costs.
- Force structured JSON output for determinism.
- Optional future hybrid: paid API for long or complex filings.

### Agent architecture
Cron → Fetch Data → Pre-Filter → LLM Analysis → Rule-Based Decision → Email Notification
State stored minimally (last processed filing, user preferences, alert history).

### Tech Stack

- Language: Python 3.11
- Data Source: SEC EDGAR 
    - API: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
    - Primary Endpoint: https://data.sec.gov/submissions/CIK{CIK}.json
- LLM Layer: Ollama + Llama 3 8B Instruct
    - Runs locally
    - Good summarization + classification
    - No token costs
    - JSON output enforcement via prompting
- Scheduling: Cron (every 30-60 minutes)
- Notifications: SMTP

---

### Just for me rn

- just redownloaded model

Links

- https://docs.ollama.com/
- https://www.sec.gov/
- https://sam.gov/
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces