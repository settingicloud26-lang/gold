import io
import json
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Gold Intelligence Dashboard", page_icon="🪙", layout="wide")

st.title("🪙 XAUUSD Institutional Terminal")
st.caption("Automated fundamental tracking & directional bias (Refreshes every 60s)")

@st.fragment(run_every=60)
def fetch_and_display_market_data():
    with st.spinner("Analyzing macro flows & institutional sentiment..."):
        # 1. Market Data (Gold, Silver, DXY, GLD)
        tickers = yf.download(
            ["GC=F", "SI=F", "DX-Y.NYB", "GLD"],
            period="6mo",
            interval="1d",
            progress=False,
        )
        close_df = tickers["Close"]

        latest_gold = round(float(close_df["GC=F"].dropna().iloc[-1]), 2)
        latest_silver = round(float(close_df["SI=F"].dropna().iloc[-1]), 2)
        latest_dxy = round(float(close_df["DX-Y.NYB"].dropna().iloc[-1]), 2)

        gsr = round(latest_gold / latest_silver, 2)
        returns = close_df[["GC=F", "DX-Y.NYB"]].pct_change().dropna()
        rolling_corr = returns["GC=F"].rolling(30).corr(returns["DX-Y.NYB"]).dropna()
        latest_corr = round(float(rolling_corr.iloc[-1]), 3)

        vol_df = tickers["Volume"]["GLD"].dropna()
        gld_rel_vol = round(float(vol_df.iloc[-1] / vol_df.mean()), 2)

        # 2. 10Y Yield (^TNX)
        try:
            tnx = yf.Ticker("^TNX")
            tnx_val = float(tnx.history(period="5d")["Close"].dropna().iloc[-1])
            latest_yield = round(tnx_val, 2)
        except Exception:
            latest_yield = None

        # 3. OPEX Magnet (GLD Options)
        try:
            gld_opts = yf.Ticker("GLD")
            nearest_exp = gld_opts.options[0]
            calls = gld_opts.option_chain(nearest_exp).calls
            max_call_strike = calls.loc[calls["openInterest"].idxmax()]["strike"]
        except Exception:
            max_call_strike = "N/A"

        # 4. COT Report (CFTC Net Positioning)
        try:
            url = "https://publicreporting.cftc.gov/resource/jun7-fc8e.json?$limit=200&$order=report_date_as_yyyy_mm_dd%20DESC"
            res = requests.get(url, timeout=10)
            cot_data = res.json()
            net_spec_val = None
            for row in cot_data:
                market_name = str(row.get("market_and_exchange_names", "")).upper()
                if "GOLD" in market_name and "COMMODITY EXCHANGE" in market_name:
                    nc_long = int(row.get("noncomm_positions_long_all", 0))
                    nc_short = int(row.get("noncomm_positions_short_all", 0))
                    net_spec_val = nc_long - nc_short
                    break
        except Exception:
            net_spec_val = None

        # 5. CPI Inflation (Bureau of Labor Statistics)
        try:
            curr_y = datetime.now().year
            payload = json.dumps({
                "seriesid": ["CUSR0000SA0"],
                "startyear": str(curr_y - 2),
                "endyear": str(curr_y),
            })
            p = requests.post(
                "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                data=payload,
                headers={"Content-type": "application/json"},
                timeout=8,
            )
            cpi_pts = p.json()["Results"]["series"][0]["data"]
            cpi_num = round(
                ((float(cpi_pts[0]["value"]) - float(cpi_pts[12]["value"]))
                / float(cpi_pts[12]["value"])) * 100, 1,
            )
        except Exception:
            cpi_num = None

        # 6. US National Debt (Treasury API)
        try:
            d_url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?sort=-record_date&page[size]=1"
            d_res = requests.get(d_url, timeout=8).json()
            debt_val = round(float(d_res["data"][0]["tot_pub_debt_out_amt"]) / 1e12, 2)
        except Exception:
            debt_val = None

    # --- MACRO BIAS ALGORITHM & EXPLICIT LABELS ---
    bullish_points = 0
    total_criteria = 5

    # Criterion 1: DXY Correlation
    if latest_corr < -0.30: 
        bullish_points += 1       
        corr_label = "Bullish (Normal Inverse)"
    else:
        corr_label = "- Bearish (Divergence)"

    # Criterion 2: Gold-Silver Ratio
    if gsr > 75: 
        bullish_points += 1                  
        gsr_label = "Bullish (Risk-Off)"
    else:
        gsr_label = "- Bearish (Risk-On)"

    # Criterion 3: 10Y Yields
    if latest_yield and latest_yield < 4.5: 
        bullish_points += 1  
        yield_label = "Bullish (Low Opportunity Cost)"
    else:
        yield_label = "- Bearish (High Opportunity Cost)"

    # Criterion 4: CPI
    if cpi_num and cpi_num > 2.5: 
        bullish_points += 1 
        cpi_label = "Bullish (Inflation Floor)"
    else:
        cpi_label = "- Bearish (Cooling Inflation)"

    # Criterion 5: Institutional COT
    if net_spec_val and net_spec_val > 0: 
        bullish_points += 1    
        cot_label = "Bullish (Net Long)"
    else:
        cot_label = "- Bearish (Net Short)"
    
    bearish_points = total_criteria - bullish_points

    # --- UI LAYOUT: TABBED NAVIGATION ---
    tab_summary, tab_charts = st.tabs(["📊 Executive Summary", "📈 Deep Dive Charts"])

    with tab_summary:
        # THE SPEEDOMETER GAUGE
        c_left, c_gauge, c_right = st.columns([1, 2, 1])
        with c_gauge:
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=bullish_points,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "Institutional Bias Score (0=Bearish, 5=Bullish)", 'font': {'size': 18}},
                gauge={
                    'axis': {'range': [0, 5], 'tickwidth': 1, 'tickcolor': "white"},
                    'bar': {'color': "rgba(255, 255, 255, 0.5)", 'thickness': 0.25},
                    'bgcolor': "black",
                    'steps': [
                        {'range': [0, 2], 'color': "#EF553B"}, # Red
                        {'range': [2, 3], 'color': "#F6C85F"}, # Yellow
                        {'range': [3, 5], 'color': "#00CC96"}  # Green
                    ]
                }
            ))
            fig_gauge.update_layout(height=250, margin=dict(l=10, r=10, t=40, b=10), template="plotly_dark")
            st.plotly_chart(fig_gauge, use_container_width=True)

        # DYNAMIC TEXT BANNER 
        if bullish_points >= 4:
            st.success(f"🟢 **OVERALL BIAS: STRONG BULLISH** ({bullish_points}/{total_criteria} metrics favor long setups)")
        elif bullish_points == 3:
            st.info(f"🟡 **OVERALL BIAS: NEUTRAL / RANGEBOUND** (Market forces are balanced)")
        else:
            st.error(f"🔴 **OVERALL BIAS: BEARISH / DEFENSIVE** ({bearish_points}/{total_criteria} metrics favor pullbacks and shorts)")

        st.markdown("---")

        # SIMPLIFIED METRIC CARDS WITH EXPLICIT COLORS
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Spot Gold", f"${latest_gold:,.2f}", delta="Live Market", delta_color="off", help="Current live price of Gold per ounce.")
        
        dxy_status = "Tailwind" if latest_dxy < 103 else "Headwind"
        c2.metric("US Dollar (DXY)", f"{latest_dxy:,.2f}", delta=dxy_status, delta_color="off", help="If the Dollar is strong (Headwind), gold struggles.")
        
        c3.metric("Gold-Silver Ratio", f"{gsr}", delta=gsr_label, help="High number = Global fear (Good for Gold). Low number = Global greed.")
        c4.metric("30D DXY Correlation", f"{latest_corr}", delta=corr_label, help="Gold and the Dollar should move in opposite directions (Negative number).")
        c5.metric("Headline CPI", f"{cpi_num}%" if cpi_num else "N/A", delta=cpi_label, help="High inflation forces investors to buy gold to protect their wealth.")

        c6, c7, c8, c9, c10 = st.columns(5)
        c6.metric("GLD Rel. Volume", f"{gld_rel_vol}x", delta="ETF Volume Proxy", delta_color="off", help="Shows if Wall Street is aggressively trading gold ETFs today.")
        c7.metric("10Y Treasury Yield", f"{latest_yield}%" if latest_yield else "N/A", delta=yield_label, help="Gold pays 0% interest. If bond yields are high, investors sell gold to buy bonds.")
        c8.metric("Nearest OPEX Magnet", f"${max_call_strike}", delta="Options Magnet", delta_color="off", help="The price level where the most options traders are placing their bets.")
        c9.metric("COT Net Positioning", f"{net_spec_val:,}" if net_spec_val else "N/A", delta=cot_label, help="Positive = Hedge funds are betting gold goes up. Negative = They are betting it drops.")
        c10.metric("US National Debt", f"${debt_val}T" if debt_val else "N/A", delta="Total Sovereign Debt", delta_color="off", help="As national debt explodes, paper money loses value.")

    with tab_charts:
        chart_col, season_col = st.columns([1, 1])
        with chart_col:
            st.subheader("Gold Price Action (6 Months)")
            fig_price = go.Figure()
            fig_price.add_trace(
                go.Scatter(x=close_df.index, y=close_df["GC=F"], name="Gold", line=dict(color="#FFD700", width=2))
            )
            fig_price.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_price, use_container_width=True)

        with season_col:
            st.subheader("10-Year Historical Seasonality (% Avg Return)")
            gold_10y = yf.Ticker("GC=F").history(period="10y", interval="1mo")["Close"].dropna()
            monthly_returns = gold_10y.pct_change() * 100
            seasonality = monthly_returns.groupby(monthly_returns.index.strftime("%b")).mean()
            months_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            seasonality = seasonality.reindex(months_order).dropna()

            colors = ["#00CC96" if v >= 0 else "#EF553B" for v in seasonality.values]
            fig_season = go.Figure()
            fig_season.add_trace(go.Bar(x=seasonality.index, y=seasonality.values, marker_color=colors))
            fig_season.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, t=30, b=0), yaxis_title="% Return")
            st.plotly_chart(fig_season, use_container_width=True)

fetch_and_display_market_data()