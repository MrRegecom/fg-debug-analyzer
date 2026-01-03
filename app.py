import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Technicals - Multi Ativos", layout="wide")

DEFAULT_TICKERS = [
    "VALE3.SA", "PETR4.SA", "ITUB4.SA", "PETR3.SA", "BBDC4.SA",
    "ABEV3.SA", "B3SA3.SA", "BBAS3.SA", "RENT3.SA", "WEGE3.SA",
    "SUZB3.SA", "AXIA3.SA", "BPAC11.SA", "TIMS3.SA", "VIVT3.SA",
    "EQTL3.SA", "PRIO3.SA", "CPLE3.SA", "SBSP3.SA", "CMIG4.SA"
]


# -------------------------
# Indicadores
# -------------------------
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    avg_gain = gain.rolling(n).mean()
    avg_loss = loss.rolling(n).mean().replace(0, np.nan)
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9):
    mf = ema(close, fast)
    ms = ema(close, slow)
    m = mf - ms
    s = ema(m, sig)
    h = m - s
    return m, s, h


def classify(score: int, strong: int = 6) -> str:
    if score >= strong:
        return "STRONG BUY"
    if score >= 2:
        return "BUY"
    if score <= -strong:
        return "STRONG SELL"
    if score <= -2:
        return "SELL"
    return "NEUTRAL"


def color(label: str) -> str:
    return {
        "STRONG BUY": "#1b8f3a",
        "BUY": "#2ecc71",
        "NEUTRAL": "#7f8c8d",
        "SELL": "#e67e22",
        "STRONG SELL": "#c0392b",
    }.get(label, "#7f8c8d")


@st.cache_data(ttl=60 * 60, show_spinner=False)
def fetch(ticker: str, period: str = "1y") -> pd.DataFrame:
    df = yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    return df.dropna()


def signal_rsi(v: float) -> int:
    if np.isnan(v):
        return 0
    if v < 30:
        return +1
    if v > 70:
        return -1
    return 0


def signal_macd(hist: float) -> int:
    if np.isnan(hist):
        return 0
    if hist > 0:
        return +1
    if hist < 0:
        return -1
    return 0


def signal_ma(close: float, ma: float) -> int:
    if np.isnan(ma):
        return 0
    return +1 if close > ma else -1


def analyze(df: pd.DataFrame):
    if df.empty or len(df) < 210:
        return None

    close = df["Close"]
    last_close = float(close.iloc[-1])

    r = float(rsi(close, 14).iloc[-1])
    _, _, h = macd(close)
    hist = float(h.iloc[-1]) if pd.notna(h.iloc[-1]) else np.nan

    # ✅ BLOCO CORRIGIDO (sem parênteses faltando)
    ema10 = float(ema(close, 10).iloc[-1])
    ema20 = float(ema(close, 20).iloc[-1])
    ema50 = float(ema(close, 50).iloc[-1])
    ema100 = float(ema(close, 100).iloc[-1])
    ema200 = float(ema(close, 200).iloc[-1])

    # Osciladores (MVP leve)
    osc_score = signal_rsi(r) + signal_macd(hist)
    osc_label = classify(osc_score, strong=2)

    # Médias móveis
    ma_score = (
        signal_ma(last_close, ema10)
        + signal_ma(last_close, ema20)
        + signal_ma(last_close, ema50)
        + signal_ma(last_close, ema100)
        + signal_ma(last_close, ema200)
    )
    ma_label = classify(ma_score, strong=4)

    summary_score = int(round(0.5 * ma_score + 0.5 * osc_score))
    summary_label = classify(summary_score, strong=3)

    return {
        "Close": last_close,
        "Summary": summary_label,
        "Osc": osc_label,
        "MAs": ma_label,
        "Score": summary_score,
        "RSI14": r,
        "MACD_hist": hist,
    }


# -------------------------
# UI
# -------------------------
st.title("📊 Technicals Multi-Ativos (estilo TradingView)")
st.caption("Resumo / Osciladores / Médias para vários ativos na mesma tela. Clique para atualizar.")

with st.sidebar:
    st.header("⚙️ Configurações")
    period = st.selectbox("Histórico", ["6mo", "1y", "2y", "5y"], index=1)
    cols = st.slider("Colunas na grade", 2, 6, 4)
    tickers_text = st.text_area("Tickers (um por linha)", value="\n".join(DEFAULT_TICKERS), height=220)
    tickers = [t.strip().upper() for t in tickers_text.splitlines() if t.strip()]
    run = st.button("🔄 Atualizar painel")

if not run:
    st.info("Clique em **Atualizar painel** para calcular os sinais.")
    st.stop()

results = []
for tk in tickers:
    try:
        df = fetch(tk, period=period)
        out = analyze(df)
        if out:
            out["Ticker"] = tk
            results.append(out)
    except Exception:
        # Se um ticker falhar, não derruba o painel inteiro
        continue

if not results:
    st.warning("Não consegui obter dados suficientes agora. Tente novamente em instantes.")
    st.stop()

dfres = pd.DataFrame(results).sort_values("Score", ascending=False).reset_index(drop=True)

# Grade de cards
grid = st.columns(cols)
for i, row in dfres.iterrows():
    c = grid[i % cols]
    label = row["Summary"]
    c.markdown(
        f"""
        <div style="border:1px solid #2c3e50;border-radius:14px;padding:14px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div style="font-size:18px;font-weight:700;">{row["Ticker"]}</div>
            <div style="padding:6px 10px;border-radius:10px;background:{color(label)};color:white;font-weight:800;">
              {label}
            </div>
          </div>
          <div style="margin-top:10px;font-size:14px;line-height:1.55;">
            <b>Close:</b> {row["Close"]:.2f}<br/>
            <b>Osc:</b> {row["Osc"]} &nbsp; | &nbsp; <b>MAs:</b> {row["MAs"]}<br/>
            <b>RSI14:</b> {row["RSI14"]:.1f} &nbsp; | &nbsp; <b>MACD hist:</b> {row["MACD_hist"]:.3f}
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

with st.expander("📋 Tabela (ranking)"):
    st.dataframe(
        dfres[["Ticker", "Summary", "Osc", "MAs", "Close", "RSI14", "MACD_hist", "Score"]],
        use_container_width=True,
        hide_index=True,
    )

st.caption("⚠️ Educacional. Não é recomendação de investimento.")
