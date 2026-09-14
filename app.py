from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import streamlit as st

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
<div class="hero"><div class="eyebrow">EXPLAINABLE FINANCIAL AGENT</div>
<h1>Buy or Wait?</h1><p>Test an expense against the next 90 days—not just today's balance. The agent protects your emergency buffer, forecasts essentials and verifies each payment plan.</p></div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Your finances")
    currency = st.selectbox("Currency", ["GBP", "USD", "EUR", "INR", "ZAR", "IDR"])
    balance = st.number_input("Current balance", min_value=0.0, value=2500.0, step=50.0)
    floor = st.number_input("Minimum balance to protect", min_value=0.0, value=500.0, step=50.0)
    salary = st.number_input("Monthly salary", min_value=0.0, value=1800.0, step=50.0)
    payday = st.date_input("Next salary date", value=date.today() + timedelta(days=14))
    rent = st.number_input("Monthly rent", min_value=0.0, value=700.0, step=25.0)
    essentials = st.number_input("Other monthly essentials", min_value=0.0, value=350.0, step=25.0)
    pending = st.number_input("Pending payments", min_value=0.0, value=100.0, step=25.0)

st.subheader("What would you like to afford?")
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    item = st.text_input("Expense", value="Laptop")
with c2:
    amount = st.number_input("Price", min_value=1.0, value=900.0, step=25.0)
with c3:
    deadline = st.date_input("Payment deadline", value=date.today() + timedelta(days=75))

o1, o2, o3 = st.columns(3)
with o1:
    partial = st.checkbox("Allow partial payment", value=True)
with o2:
    installments = st.checkbox("Consider instalments", value=True)
with o3:
    months = st.selectbox("Instalment months", [2, 3], index=1, disabled=not installments)
fee = st.number_input("Total instalment fee", min_value=0.0, value=30.0, step=5.0,
                      disabled=not installments)

if st.button("Can I afford it?", type="primary", width="stretch"):
    if floor > balance:
        st.error("Your protected minimum cannot be higher than your current balance.")
        st.stop()
    scenario = Scenario(
        today=date.today(), balance=Decimal(str(balance)), minimum_balance=Decimal(str(floor)),
        purchase_amount=Decimal(str(amount)), deadline=deadline, next_salary_date=payday,
        monthly_salary=Decimal(str(salary)), monthly_rent=Decimal(str(rent)),
        monthly_essentials=Decimal(str(essentials)), pending_payments=Decimal(str(pending)),
        allows_partial=partial, allows_installments=installments,
        installment_months=months, installment_fee=Decimal(str(fee)),
    )
    result = analyse(scenario)
    symbol = {"GBP":"£", "USD":"$", "EUR":"€", "INR":"₹", "ZAR":"R", "IDR":"Rp"}[currency]
    label = result["status"].replace("_", " ").title()
    st.markdown(f'<div class="result"><div class="eyebrow">RECOMMENDATION FOR {item.upper()}</div><h2>{label}</h2><p>{result["explanation"]}</p></div>', unsafe_allow_html=True)
    st.write("")
    m1, m2, m3 = st.columns(3)
    m1.metric("Safe to pay today", f"{symbol}{display(result['safe_today'], fixed=True)}")
    m2.metric("Recommended method", result["method"].replace("_", " ").title())
    m3.metric("Lowest projected balance", f"{symbol}{display(result['projected_low'], fixed=True)}")
    if result["payments"]:
        st.subheader("Payment plan")
        st.dataframe([{"Date": p.day.isoformat(), "Amount": f"{symbol}{display(p.amount, fixed=True)}"}
                      for p in result["payments"]], width="stretch", hide_index=True)
    st.subheader("90-day balance forecast")
    st.line_chart(result["timeline"], x="date", y=["balance", "floor"],
                  color=["#63e6be", "#fb7185"])
    st.caption("Educational estimate only—not regulated financial advice. No banking credentials are collected.")
else:
    st.info("Adjust the numbers, then click **Can I afford it?** to generate a recommendation.")
