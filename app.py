from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from html import escape
import os

import streamlit as st

from buy_or_wait.purchase_ai import extract_purchase, ExtractionError, DEFAULT_MODEL
from buy_or_wait.money import display
from buy_or_wait.scenario import Scenario, analyse


st.set_page_config(page_title="Buy or Wait?", page_icon="💸", layout="wide")
st.markdown("""
<style>
.stApp {background: radial-gradient(circle at 10% 0%, #172554 0, #080b16 35%, #05070d 100%);}
.block-container {max-width: 1180px; padding-top: 2.2rem;}
[data-testid="stMetric"] {background:#101726; border:1px solid #27334a; padding:18px; border-radius:16px;}
.hero {padding:26px 30px; border:1px solid #293552; border-radius:22px;
 background:linear-gradient(135deg,rgba(37,99,235,.20),rgba(16,185,129,.08)); margin-bottom:22px;}
.eyebrow {color:#63e6be; font-weight:700; letter-spacing:.14em; font-size:.78rem;}
.hero h1 {font-size:3rem; margin:.25rem 0;}
.hero p {color:#aebbd0; font-size:1.05rem; max-width:760px;}
.result {padding:22px; border-radius:18px; border:1px solid #334155; background:#0f172a;}
</style>
<div class="hero"><div class="eyebrow">A LITTLE HELP BEFORE YOU BUY</div>
<h1>Buy or Wait?</h1><p>Thinking about a purchase? See how it fits around your bills, payday and the money you want to keep aside.</p></div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Your finances")
    currency = st.selectbox("Currency", ["GBP", "USD", "EUR", "INR", "ZAR", "IDR"])
    balance = st.number_input("Current balance", min_value=0.0, value=2500.0, step=50.0)
    floor = st.number_input("Money to keep aside", min_value=0.0, value=500.0, step=50.0)
    salary = st.number_input("Monthly salary", min_value=0.0, value=1800.0, step=50.0)
    payday = st.date_input("Next payday", value=date.today() + timedelta(days=14), min_value=date.today())
    rent = st.number_input("Monthly rent", min_value=0.0, value=700.0, step=25.0)
    rent_date = st.date_input("Next rent payment", value=date.today() + timedelta(days=7), min_value=date.today())
    essentials = st.number_input("Other monthly essentials", min_value=0.0, value=350.0, step=25.0)
    pending = st.number_input("Pending payments", min_value=0.0, value=100.0, step=25.0)


def setting(name, default=""):
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.environ.get(name, default)

with st.expander("Tell us what you'd like to buy"):
    st.write("Describe one purchase and we'll help fill in the details.")
    st.caption("Your message is sent to Google Gemini when you click Read my request. Your sidebar budget is not sent. Keep account details out of your message.")
    request_text = st.text_area("Your purchase", placeholder="Can I afford a £900 laptop by 30 September?", max_chars=2000)
    api_key = setting("GEMINI_API_KEY")
    if not api_key:
        st.info("AI isn't connected yet. You can still enter the details below.")
    if st.button("Read my request", disabled=not bool(api_key)):
        st.session_state.pop("ai_source", None)
        st.session_state["ai_confirmed"] = False
        try:
            with st.spinner("Reading your request..."):
                details = extract_purchase(request_text, api_key, date.today(), currency, setting("GEMINI_MODEL", DEFAULT_MODEL))
            st.session_state["purchase_item"] = details["item"] or ""
            st.session_state["purchase_amount"] = details["amount"]
            st.session_state["purchase_deadline"] = details["deadline"]
            st.session_state["ai_currency"] = details["currency"]
            st.session_state["ai_source"] = request_text
            st.session_state["ai_review"] = True
        except ExtractionError as exc:
            st.error(str(exc))
    if st.session_state.get("ai_source") is not None and request_text != st.session_state["ai_source"]:
        st.info("Your message has changed. Click Read my request again to use the new wording.")


st.subheader("What are you thinking of buying?")
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    item = st.text_input("Expense", value="Laptop", key="purchase_item", on_change=lambda: st.session_state.update(ai_confirmed=False))
with c2:
    amount = st.number_input("Price", min_value=1.0, value=900.0, step=25.0, max_value=1000000000.0, key="purchase_amount", on_change=lambda: st.session_state.update(ai_confirmed=False))
with c3:
    deadline = st.date_input("Payment deadline", value=date.today() + timedelta(days=75), min_value=date.today(), max_value=date.today() + timedelta(days=90), key="purchase_deadline", on_change=lambda: st.session_state.update(ai_confirmed=False))

o1, o2, o3 = st.columns(3)
with o1:
    partial = st.checkbox("Allow partial payment", value=False)
with o2:
    installments = st.checkbox("Consider instalments", value=False)
with o3:
    months = st.selectbox("Instalment months", [2, 3], index=1, disabled=not installments)
fee = st.number_input("Total instalment fee", min_value=0.0, value=30.0, step=5.0,
                      disabled=not installments)

st.caption("Only select split payments if the seller offers them. Instalments here start today and repeat monthly. Enter the total fee from the offer.")

review_ready = True
if st.session_state.get("ai_review"):
    st.write("Check the details above before we work out your options.")
    if not item.strip():
        st.info("What would you like to buy? Enter it in Expense.")
    if amount is None:
        st.info("How much does it cost? Enter the full price.")
    if deadline is None:
        st.info("When would you like to finish paying? Choose a payment deadline.")
    extracted_currency = st.session_state.get("ai_currency")
    currency_ok = extracted_currency is None or extracted_currency == currency
    if not currency_ok:
        st.warning(f"Your request uses {extracted_currency}, but your budget uses {currency}. Update the sidebar currency and budget to match. We don't convert currencies.")
    review_ready = st.checkbox(f"I've checked the purchase, price and date. All amounts are in {currency}.", key="ai_confirmed") and currency_ok
    if st.button("Use the manual form"):
        st.session_state["ai_review"] = False
        st.session_state.pop("ai_source", None)
        st.rerun()
if st.button("Can I afford it?", type="primary", width="stretch",
             disabled=not (review_ready and item.strip() and amount is not None and deadline is not None)):
    scenario = Scenario(
        today=date.today(), balance=Decimal(str(balance)), minimum_balance=Decimal(str(floor)),
        purchase_amount=Decimal(str(amount)), deadline=deadline, next_salary_date=payday,
        monthly_salary=Decimal(str(salary)), monthly_rent=Decimal(str(rent)),
        monthly_essentials=Decimal(str(essentials)), pending_payments=Decimal(str(pending)),
        allows_partial=partial, allows_installments=installments,
        installment_months=months, installment_fee=Decimal(str(fee)), next_rent_date=rent_date,
    )
    result = analyse(scenario)
    symbol = {"GBP":"£", "USD":"$", "EUR":"€", "INR":"₹", "ZAR":"R", "IDR":"Rp"}[currency]
    label = {"affordable_now": "You can buy it today", "affordable_with_plan": "You can spread the cost", "affordable_later": "Give it a little time", "not_affordable": "This purchase would leave you short"}[result["status"]]
    st.markdown(f'<div class="result"><div class="eyebrow">Your plan for {escape(item)}</div><h2>{label}</h2><p>{result["explanation"]}</p></div>', unsafe_allow_html=True)
    st.write("")
    m1, m2, m3 = st.columns(3)
    m1.metric("Safe to pay today", f"{symbol}{display(result['safe_today'], fixed=True)}")
    m2.metric("How to pay", {"full_payment": "Pay in full", "partial_payment": "Pay in two parts", "installments": "Monthly instalments", "wait": "Wait", "not_recommended": "Hold off"}[result["method"]])
    m3.metric("Lowest projected balance", f"{symbol}{display(result['projected_low'], fixed=True)}")
    if result["earliest"]:
        st.write(f"You could pay in full on {result['earliest'].strftime('%d %B %Y')}, based on these numbers.")
    if not result["baseline_safe"]:
        st.warning("Your bills alone could take you below the amount you want to keep aside, even without this purchase.")
    if result["payments"]:
        st.subheader("Payment plan")
        st.dataframe([{"Date": p.day.isoformat(), "Amount": f"{symbol}{display(p.amount, fixed=True)}"}
                      for p in result["payments"]], width="stretch", hide_index=True)
    st.subheader("90-day balance forecast")
    st.line_chart(result["timeline"], x="date", y=["balance", "floor"],
                  color=["#63e6be", "#fb7185"])
    st.caption("This is an estimate based on the numbers you entered. Income may arrive late and bills can change.")
    with st.expander("How we worked this out"):
        st.write("Salary and rent repeat monthly from the dates you entered. Other essentials are spread across each calendar month. Pending payments are taken out today. Income is assumed to arrive before spending on the same day. Everything uses your selected currency.")
else:
    st.info("Adjust the numbers, then click **Can I afford it?** to see your options.")
