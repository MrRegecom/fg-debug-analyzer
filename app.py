import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Painel Técnico Multi-Ativos", layout="wide")

# -------------------------
# Config
# -------------------------
DEFAULT_TICKERS = [
    "VALE3.SA","PETR4.SA","ITUB4.SA","PETR3.SA","BBDC4.SA",
    "ABEV3.SA","B3SA3.SA","BBAS3.SA","RENT3.SA","WEGE3.SA",
    "SUZB3.SA","AXIA3.SA","BPAC11.SA","TIMS3.SA","VIVT3.SA",
    "EQTL3.SA","PRIO3.SA","CPLE3.SA","SBSP3.SA","CMIG4.SA"
]

# -------------------------
# Indicadores
# -------------------------
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def rsi(close, n=14):
    d = close.diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    avg_gain = gain.rolling(n).mean()
    avg_loss = loss.rolling(n).mean().replace(0, np.nan)
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(close, fast=12, slow=26, sig=9):
    mf = ema(close, fast)
    ms = ema(close, slow)
    m = mf - ms
    s = ema(m, sig)
    h = m - s
    return m, s, h

@st.cache_data(ttl=60*60, show_spinner=False)
def fetch(ticker, period="1y"):
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=False, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.dropna()

def classify_score(x, strong=6):
    # x é soma de sinais (ex: -10 a +10)
    if x >= strong: return "STRONG BUY"
    if x >= 2:      return "BUY"
    if x <= -strong:return "STRONG SELL"
    if x <= -2:     return "SELL"
    return "NEUTRAL"

def badge_color(label):
    return {
        "STRONG BUY": "#1b8f3a",
        "BUY": "#2ecc71",
        "NEUTRAL": "#7f8c8d",
        "SELL": "#e67e22",
        "STRONG SELL": "#c0392b",
    }.get(label, "#7f8c8d")

def signal_rsi(r):
    if np.isnan(r): return 0
    if r < 30: return +1
    if r > 70: return -1
    return 0

def signal_macd(hist):
    if np.isnan(hist): return 0
    return +1 if hist > 0 else (-1 if hist < 0 else 0)

def signal_ma(close, ma):
    if np.isnan(ma): return 0
    return +1 if close > ma else -1

def build_signals(df):
    # precisa de histórico mínimo
    if df.empty or len(df) < 210:
        return None

    close = df["Close"]
    last_close = float(close.iloc[-1])

    r = rsi(close, 14).iloc[-1]
    m_line, s_line, hist = macd(close)
    hist_last = float(hist.iloc[-1]) if pd.notna(hist.iloc[-1]) else np.nan

    # MAs
    ema10 = float(ema(close, 10).iloc[-1])
    ema20 = float(ema(close, 20).iloc[-1])
    ema50 = float(ema(close, 50).iloc[-1])
    ema100= float(ema(close,100).iloc[-1])
    ema200= float(ema(close,200).iloc[-1])

    # --- Oscillators group (simples e leve p/ MVP)
    osc = {
        "RSI(14)": signal_rsi(float(r)),
        "MACD(Hist)": signal_macd(hist_last),
    }
    osc_score = sum(osc.values())
    osc_label = classify_score(osc_score, strong=2)  # aqui 2 já vira "strong"

    # --- Moving averages group
    mas = {
        "EMA10": signal_ma(last_close, ema10),
        "EMA20": signal_ma(last_close, ema20),
        "EMA50": signal_ma(last_close, ema50),
        "EMA100": signal_ma(last_close, ema100),
        "EMA200": signal_ma(last_close, ema200),
    }
    ma_score = sum(mas.values())
    ma_label = classify_score(ma_score, strong=4)

    # --- Summary (ponderado)
    summary_score = int(round(0.5*ma_score + 0.5*osc_score))
    summary_label = classify_score(summary_score, strong=3)

    return {
        "last_close": last_close,
        "osc_label": osc_label,
        "ma_label": ma_label,
        "summary_label": summary_label,
        "osc_score": osc_score,
        "ma_score": ma_score,
        "summary_score": summary_score,
        "rsi": float(r) if pd.notna(r) else np.nan,
        "macd_hist": hist_last,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
    }

# -------------------------
# UI
# -------------------------
st.title("📊 Painel Técnico Multi-Ativos (estilo TradingView)")
st.caption("Resumo + Osciladores + Médias móveis para vários ativos na mesma tela. (MVP leve)")

with st.sidebar:
    st.header("⚙️ Configurações")
    period = st.selectbox("Histórico", ["6mo","1y","2y","5y"], index=1)
    cols = st.slider("Colunas na grade", 2, 6, 4)
    tickers_text = st.text_area("Tickers (um por linha)", value="\n".join(DEFAULT_TICKERS), height=220)
    tickers = [t.strip().upper() for t in tickers_text.splitlines() if t.strip()]
    run = st.button("🔄 Atualizar painel")

if not run:
    st.info("Clique em **Atualizar painel** para calcular os sinais.")
    st.stop()

cards = []
for tk in tickers:
    df = fetch(tk, period=period)
    sig = build_signals(df)
    if sig:
        cards.append((tk, sig))

if not cards:
    st.warning("Não consegui montar sinais (dados insuficientes ou download falhou).")
    st.stop()

# ranking por score
cards = sorted(cards, key=lambda x: x[1]["summary_score"], reverse=True)

grid = st.columns(cols)
for i, (tk, sig) in enumerate(cards):
    col = grid[i % cols]
    label = sig["summary_label"]
    col.markdown(
        f"""
        <div style="border:1px solid #2c3e50;border-radius:14px;padding:14px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div style="font-size:18px;font-weight:700;">{tk}</div>
            <div style="padding:6px 10px;border-radius:10px;background:{badge_color(label)};color:white;font-weight:700;">
              {label}
            </div>
          </div>
          <div style="margin-top:10px;font-size:14px;">
            <b>Close:</b> {sig["last_close"]:.2f}<br/>
            <b>Osc:</b> {sig["osc_label"]} (score {sig["osc_score"]})<br/>
            <b>MAs:</b> {sig["ma_label"]} (score {sig["ma_score"]})<br/>
            <b>RSI14:</b> {sig["rsi"]:.1f} &nbsp; | &nbsp; <b>MACD hist:</b> {sig["macd_hist"]:.3f}
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

st.caption("⚠️ Educacional. Não é recomendação de investimento.")
