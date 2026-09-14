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

- Manual budget entry and a minimum balance to keep aside
- Explicit next salary and rent dates
- Monthly income and rent schedules with calendar month-end handling
- Essential spending spread across each calendar month
- Full, partial, monthly instalment and delayed payment comparisons
- A payment schedule, earliest full-payment date and balance chart
- Decimal arithmetic for monetary calculations

Instalments are hypothetical user-entered offers, starting today with equal monthly payments plus any rounding adjustment in the last payment. Only select them if the seller offers those terms. Pending payments must not already be deducted from the starting balance.

## Current scope

This repository restores the standalone Streamlit demo from the earlier Buy or Wait hackathon project. The original CSV pipeline, OCR/message extraction, dataset and evaluation scripts are not included in this recovery yet.

This demo uses deterministic calculations. It does not currently call an LLM or connect to a bank. Earlier public-sample accuracy figures belong to the separate dataset engine and do not measure this app.

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

No API key is required.

## Origin

Started from the [HackerRank Orchestrate Buy or Wait challenge](https://github.com/interviewstreet/hackerrank-orchestrate-september26) and continued as an independent portfolio project.
