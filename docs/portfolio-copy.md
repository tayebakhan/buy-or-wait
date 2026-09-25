# Portfolio copy

## Short project description

Buy or Wait is an AI-assisted financial planning agent that forecasts a user's balance for 90 days and recommends whether to pay now, split the cost, use instalments, wait, or avoid a purchase. It combines natural-language and image extraction with a deterministic decision engine so every recommendation can be tested and explained.

## CV version

**Buy or Wait | Python, Streamlit, Gemini, GitHub Actions**

- Built and deployed an AI-assisted affordability agent that evaluates income, recurring bills, pending payments, payment options and a user-defined safety buffer across a 90-day forecast.
- Designed a deterministic decision engine using `Decimal` arithmetic and explainable rules, keeping AI limited to structured extraction from natural language and images.
- Created a reproducible evaluation pipeline and automated tests, reaching 84% payment-method accuracy and placing 88% of safe-payment predictions within 5% of the requested amount on 25 public samples.

## LinkedIn or portfolio version

I built Buy or Wait to answer a question that a bank balance alone cannot: can I make this purchase and still stay financially safe? The app forecasts upcoming income and expenses, compares full payment, partial payment and instalment options, and shows the recommendation alongside a payment plan and balance chart. I used Gemini for extracting details from text or images, while the final financial decision stays deterministic and testable.

## 30-second interview explanation

The hardest part was separating AI extraction from financial decision-making. Gemini can turn an unstructured request or receipt into structured fields, but it does not decide whether the user can afford the purchase. A deterministic engine builds a 90-day daily cashflow forecast, tries each permitted payment option and rejects plans that fall below the user's minimum balance. I also built a sample-based evaluator and CI tests so I could measure changes instead of tuning by intuition.

## Links

- [Live app](https://buy-or-wait-xf8arqodck2gxvkesbckb5.streamlit.app/)
- [GitHub repository](https://github.com/tayebakhan/buy-or-wait)
- [10-second demo](demo.mp4)
