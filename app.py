import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Technicals - Multi Ativos", layout="wide")

DEFAULT_TICKERS = [
    "VALE3.SA","PETR4.SA","ITUB4.SA","PETR3.SA","BBDC4.SA",
    "ABEV3.SA","B3SA3.SA","BBAS3.SA","RENT3.SA","WEGE3.SA",
    "SUZB3.SA","AXIA3.SA","BPAC11.SA","TIMS3.SA","VIVT3.SA",
    "EQTL3.SA","PRIO3.SA","CPLE3.SA","SBSP3.SA","CMIG4.SA"
]

def ema(s, n): 
    return s.ewm(span=n, adjust=False).mean()

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

def classify(score, strong=6):
    if score >= strong: return "STRONG BUY"
    if score >= 2:      return "BUY"
    if score <= -strong:return "STRONG SELL"
    if score <= -2:     return "SELL"
    return "NEUTRAL"

def color(label):
    return {
        "STRONG BUY": "#1b8f3a",
        "BUY": "#2ecc71",
        "NEUTRAL": "#7f8c8d",
        "SELL": "#e67e22",
        "STRONG SELL": "#c0392b",
    }.get(label, "#7f8c8d")

@st.cache_data(ttl=60*60, show_spinner=False)
def fetch(ticker, period="1y"):
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=False, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.dropna()

def signal_rsi(v):
    if np.isnan(v): return 0
    if v < 30: return +1
    if v > 70: return -1
    return 0

def signal_macd(hist):
    if np.isnan(hist): return 0
    return +1 if hist > 0 else (-1 if hist < 0 else 0)

def signal_ma(close, ma):
    if np.isnan(ma): return 0
    return +1 if close > ma else -1

def analyze(df):
    if df.empty or len(df) < 210:
        return None

    close = df["Close"]
    last_close = float(close.iloc[-1])

    r = float(rsi(close, 14).iloc[-1])
    _, _, h = macd(close)
    hist = float(h.iloc[-1]) if pd.notna(h.iloc[-1]) else np.nan

    ema10  = float(ema(close, 10).iloc[-1])
    ema20  = float(ema(close, 20).iloc[-1])
    ema50  = float(ema(close, 50).iloc[-1])
    ema100 = float(ema(close,100).iloc[-1])
    ema200 = float(ema(close,200
