# Buy or Wait?

A small budgeting app for the moment you find something you want and wonder whether it can wait until payday.

Enter your balance, bills, salary and purchase price. The app compares paying today, splitting the cost and waiting, then shows a 90-day balance chart.

## Run locally

Requires Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

## What is included

- Natural-language and image extraction for product listings, bills, receipts and payment messages
- Manual budget entry and a minimum balance to keep aside
- Explicit next salary and rent dates
- Monthly income and rent schedules with calendar month-end handling
- Essential spending spread across each calendar month
- Full, partial, monthly instalment and delayed payment comparisons
- A payment schedule, earliest full-payment date and balance chart
- Decimal arithmetic for monetary calculations

Instalments are hypothetical user-entered offers, starting today with equal monthly payments plus any rounding adjustment in the last payment. Only select them if the seller offers those terms. Pending payments must not already be deducted from the starting balance.

## Current scope

This repository restores the standalone Streamlit demo from the earlier Buy or Wait hackathon project. The original CSV pipeline, dataset and evaluation scripts are not included in this recovery yet.

The optional Gemini input extracts one purchase into editable fields. The user must review the price, deadline and currency before the deterministic calculator runs. It does not connect to a bank. Earlier public-sample accuracy figures belong to the separate dataset engine and do not measure this app.

Income is assumed to post before debits on the same day. Salary continues monthly, essentials follow the entered budget, and the forecast only covers 90 days. Results are estimates, not guarantees.

## Checks

```bash
python3 -m unittest discover -s tests -v
```

## Deploy

In Streamlit Community Cloud, select:

- Repository: `tayebakhan/buy-or-wait`
- Branch: `main`
- Entry point: `app.py`
- Python: `3.12`

Manual entry needs no API key. To enable AI, add these values in the app's Streamlit settings under Secrets:

```toml
GEMINI_API_KEY = "your-key-from-google-ai-studio"
GEMINI_MODEL = "gemini-2.5-flash"
```

Use a model available to your Google project that supports generateContent structured output. Never commit real keys. Only the purchase message, optional uploaded image, today's date and currency context go to Gemini; sidebar balances and bills are not sent. JPG, PNG and WebP uploads are limited to 5 MB and are processed in memory. Provider request limits and charges depend on your account.

The integration uses the [Gemini REST API](https://ai.google.dev/api/generate-content). Missing details remain blank, dates outside the forecast are rejected, and currency mismatches block calculation. No AI response can change the budget or directly select a payment plan.

Tests mock provider responses to check extraction validation, failures and the review flow. They do not measure live model accuracy. A real API key is needed for an end-to-end AI check. Try explicit dates, missing prices, ambiguous deadlines and different currencies after connecting.

## Origin

Started from the [HackerRank Orchestrate Buy or Wait challenge](https://github.com/interviewstreet/hackerrank-orchestrate-september26) and continued as an independent portfolio project.
