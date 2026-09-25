# Buy or Wait?

An AI-assisted financial planning project that answers a simple question: can someone safely afford a purchase now, with a plan, later, or not within the next 90 days?

Try the live app: [buy-or-wait-xf8arqodck2gxvkesbckb5.streamlit.app](https://buy-or-wait-xf8arqodck2gxvkesbckb5.streamlit.app/)

The project now has two connected parts:

- A friendly Streamlit calculator for one purchase
- A batch agent that reads the original challenge CSV files and produces the exact `output.csv` schema

## How the agent works

1. It joins each request to the user's financial profile, events, payment options, messages and images.
2. It converts foreign-currency events using the supplied dated exchange rates.
3. It ignores unsafe evidence such as pending income, failed payments and unrealized investment values.
4. It learns stable 5 to 24 day and monthly patterns from settled history, then builds a 90-day cash forecast. It uses recent medians for groceries and dining, longer history for transport, and six-payment averages for variable monthly bills.
5. It tests full payment, exactly two partial payments, supplied installment offers, waiting and up to three permitted spending changes.
6. It rejects any plan that misses the requested date or lets the balance fall below the user's chosen minimum.
7. It writes and validates the eight required output columns.

Money calculations use `Decimal`, not floating-point arithmetic. AI can read a missing amount from a linked image, but AI never makes the affordability decision.

## Run the Streamlit app locally

Requires Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

## Run the challenge dataset

Download the original challenge data and place its CSV files and `media/` folder inside a local `dataset/` directory. The dataset is intentionally not committed to this portfolio repository.

```bash
python3 code/main.py --dataset dataset --output output.csv
```

The command stops with a clear error if a required file or column is missing. On success it checks the output column order, request IDs, labels, dates, payment-plan format and spending-change format.

If an event amount is only available in an image, set `GEMINI_API_KEY`. To make repeated runs cheaper and reproducible, you may instead create `dataset/evidence_cache.json`:

```json
{
  "image_01": {"amount": "1250.00"}
}
```

Only cache a value after checking the linked image yourself.

## Evaluate against the solved samples

First generate predictions for the sample request rows, then compare them with the completed columns in `sample_requests.csv`:

```bash
python3 evaluation/evaluate.py \
  --predictions sample_output.csv \
  --expected dataset/sample_requests.csv
```

This creates `evaluation/report.md` and `evaluation/report.json` with exact-row and per-field accuracy. Equivalent money formats such as `100` and `100.00` are treated as equal. It also reports request-normalized monetary error and the share of predictions within 1% and 5% of the requested amount. Free-text explanations are excluded from exact matching.

The reproducible public-sample workflow currently scores 25 solved requests at 80% for affordability status, 84% for the recommended payment method, 80% for the payment plan and 84% for the earliest full-payment date. For `amount_safe_to_pay`, the mean request-normalized error is 2.95%, 52% of predictions are within 1% of the requested amount and 88% are within 5%. Exact monetary equality remains the main improvement area.

Before presenting a final full-dataset run, complete `evaluation/usage_report.md` with the actual provider calls, tokens and cost. The deterministic forecasting engine itself makes zero model calls.

## What is included

- Natural-language and image extraction for product listings, bills, receipts and payment messages
- Exact challenge CSV ingestion and output validation
- Dated currency conversion
- Conflict handling for linked, cancelled, failed, settled and pending records
- Common explicit message amendments for amounts, salary dates, payroll arrears, rent rises, retried bills and confirmed transfers between a user's own accounts
- One-cycle reduced salary handling and confirmed provider invoice income
- Recurring cashflow inference from settled history
- Full, partial, installment, delayed and flexible-spending comparisons
- A payment schedule, earliest full-payment date and 90-day balance forecast
- A public-sample evaluation workflow
- Automated tests and GitHub Actions checks

## Current limitations

This is a measured reproducible baseline, not a claim of perfect hidden-test accuracy. Message wording outside the supported explicit patterns may need a richer multilingual evidence normalizer. Image extraction also needs either a Gemini key or a reviewed cache entry. The local cache builder compares standard and sparse OCR layout modes to reduce missed printed and handwritten receipt totals. The public workflow reruns all 25 solved samples after relevant engine changes so improvements can be measured without hardcoding answers.

The app and batch engine do not connect to a bank. Results are estimates based only on the supplied information and are not financial advice.

## Streamlit deployment

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

Never commit real keys. In the Streamlit app, only the purchase message, optional uploaded image, current date and currency context go to Gemini. Sidebar balances and bills are not sent. JPG, PNG and WebP uploads are limited to 5 MB and processed in memory.

## Checks

```bash
python3 -m unittest discover -s tests -v
```

## Origin

Started from the [HackerRank Orchestrate Buy or Wait challenge](https://github.com/interviewstreet/hackerrank-orchestrate-september26) and continued as an independent portfolio project.
