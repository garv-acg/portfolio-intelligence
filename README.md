# Daily Market Newsletter Agent

A local V1 of a concise, institutional-style market newsletter for portfolio monitoring. It is designed to summarize verified inputs, not give investment advice.

## 1. Setup

```bash
cd newsletter_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. Edit your portfolio

Open `portfolio.yml` and replace the sample tickers with your holdings.

## 3. Generate a newsletter

```bash
python main.py
```

The output will save to:

```text
output/latest_newsletter.html
output/latest_newsletter.txt
```

## 4. Run the dashboard

```bash
streamlit run app/dashboard/streamlit_app.py
```

## 5. Optional keys

- `OPENAI_API_KEY`: improves summarization and neutral formatting.
- `NEWSAPI_KEY`: adds broader article search.
- `RESEND_API_KEY`: enables email delivery.

Without keys, the app still runs using Yahoo Finance data and deterministic fallback summaries.
