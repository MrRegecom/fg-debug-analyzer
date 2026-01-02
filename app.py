import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="Swing Scanner (IBOV)", layout="wide")

# ---------------------------
# Helpers: indicadores
# ---------------------------
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean().replace(0, np.nan)
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

@st.cache_data(ttl=60*60, show_spinner=False)
def fetch_ohlcv(ticker: str, period: str = "2y") -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=False, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna()
    return df

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["EMA20"] = ema(df["Close"], 20)
    df["EMA50"] = ema(df["Close"], 50)
    df["EMA200"] = ema(df["Close"], 200)
    df["RSI14"] = rsi(df["Close"], 14)
    df["ATR14"] = atr(df, 14)
    df["VOL20"] = df["Volume"].rolling(20).mean()
    df["HH20"] = df["High"].rolling(20).max()
    df["HH50"] = df["High"].rolling(50).max()
    df["LL20"] = df["Low"].rolling(20).min()
    return df

# ---------------------------
# Setups
# ---------------------------
def setup_pullback(df: pd.DataFrame, rsi_low=40, rsi_high=60, atr_mult=1.5):
    """
    Pullback em tendência:
    - Close > EMA200
    - EMA20 > EMA50
    - Close próximo de EMA20 ou EMA50 (distância pequena)
    - RSI dentro de faixa
    - Candle de reação: Close > Open
    """
    if len(df) < 260:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    if not (last["Close"] > last["EMA200"] and last["EMA20"] > last["EMA50"]):
        return None

    if not (rsi_low <= last["RSI14"] <= rsi_high):
        return None

    # proximidade do pullback: distância percentual
    dist_ema20 = abs(last["Close"] - last["EMA20"]) / last["Close"]
    dist_ema50 = abs(last["Close"] - last["EMA50"]) / last["Close"]
    if min(dist_ema20, dist_ema50) > 0.02:  # 2% (ajustável depois)
        return None

    # reação simples
    if not (last["Close"] > last["Open"]):
        return None

    entry = float(last["Close"])
    # stop: abaixo da EMA50 OU ATR
    stop_ema = float(last["EMA50"] * 0.995)  # pequena folga
    stop_atr = float(entry - (last["ATR14"] * atr_mult)) if pd.notna(last["ATR14"]) else stop_ema
    stop = min(stop_ema, stop_atr)

    risk = entry - stop
    if risk <= 0:
        return None

    target = entry + (2.0 * risk)  # 2R

    # score simples: tendência + volume + pullback limpo
    vol_score = 1.0 if (pd.notna(last["VOL20"]) and last["Volume"] >= last["VOL20"]) else 0.5
    trend_score = 1.0 if (last["EMA20"] > last["EMA50"] > last["EMA200"]) else 0.7
    pullback_score = 1.0 - min(dist_ema20, dist_ema50) * 20  # quanto mais perto, melhor
    score = 100 * (0.45*trend_score + 0.25*vol_score + 0.30*pullback_score)

    return {
        "setup": "Pullback",
        "entry": entry,
        "stop": stop,
        "target": target,
        "score": float(score),
        "notes": f"Close>EMA200, EMA20>EMA50, RSI ok, pullback ~{min(dist_ema20, dist_ema50)*100:.2f}%"
    }

def setup_breakout(df: pd.DataFrame, lookback=50, vol_mult=1.1, atr_mult=1.5):
    """
    Rompimento com confirmação:
    - Close > máxima (lookback) anterior
    - Volume > média 20 * vol_mult
    - Evitar RSI esticado demais (ex: < 75)
    """
    if len(df) < lookback + 30:
        return None

    last = df.iloc[-1]
    prior = df.iloc[-(lookback+1):-1]
    prev_high = prior["High"].max()

    if not (last["Close"] > prev_high):
        return None

    if pd.notna(last["VOL20"]):
        if not (last["Volume"] > last["VOL20"] * vol_mult):
            return None

    if pd.notna(last["RSI14"]) and last["RSI14"] > 75:
        return None

    entry = float(last["Close"])
    stop_atr = float(entry - (last["ATR14"] * atr_mult)) if pd.notna(last["ATR14"]) else float(prev_high * 0.985)
    stop = min(stop_atr, float(prev_high * 0.99))

    risk = entry - stop
    if risk <= 0:
        return None

    target = entry + (2.0 * risk)

    vol_score = 1.0 if (pd.notna(last["VOL20"]) and last["Volume"] > last["VOL20"] * 1.5) else 0.7
    breakout_strength = (entry - prev_high) / entry
    breakout_score = min(1.0, 0.6 + breakout_strength * 20)
    score = 100 * (0.5*breakout_score + 0.3*vol_score + 0.2*(1.0 if last["Close"] > last["EMA200"] else 0.7))

    return {
        "setup": f"Rompimento({lookback})",
        "entry": entry,
        "stop": stop,
        "target": target,
        "score": float(score),
        "notes": f"Close rompeu {prev_high:.2f}, volume confirma, RSI ok"
    }

# ---------------------------
# UI
# ---------------------------
st.title("📈 Swing Scanner (IBOV) — Portal Streamlit")
st.caption("Scanner técnico (Pullback + Rompimento) em ações líquidas. Sem execução automática — só análise e ranking.")

default_tickers = [
    "VALE3.SA","PETR4.SA","ITUB4.SA","BBDC4.SA","ABEV3.SA","WEGE3.SA","B3SA3.SA","BBAS3.SA",
    "PRIO3.SA","TAEE11.SA","ELET3.SA","ELET6.SA","SUZB3.SA","RENT3.SA","VIVT3.SA","TIMS3.SA",
    "CSAN3.SA","RAIL3.SA","EQTL3.SA","CMIG4.SA","HAPV3.SA","GGBR4.SA","AZZA3.SA","EMBR3.SA"
]

with st.sidebar:
    st.header("⚙️ Configurações")
    tickers_text = st.text_area("Tickers (um por linha) — use .SA para B3", value="\n".join(default_tickers), height=220)
    tickers = [t.strip().upper() for t in tickers_text.splitlines() if t.strip()]

    data_period = st.selectbox("Histórico para cálculo", ["1y","2y","3y","5y"], index=1)

    st.subheader("Pullback")
    rsi_low = st.slider("RSI mínimo", 20, 60, 40)
    rsi_high = st.slider("RSI máximo", 40, 80, 60)
    atr_mult_pb = st.slider("ATR múltiplo (Stop)", 0.5, 3.0, 1.5, 0.1)

    st.subheader("Rompimento")
    lookback = st.selectbox("Lookback rompimento", [20, 50, 100], index=1)
    vol_mult = st.slider("Volume confirmação (x média 20)", 1.0, 2.0, 1.1, 0.05)
    atr_mult_bo = st.slider("ATR múltiplo (Stop)", 0.5, 3.0, 1.5, 0.1)

    run = st.button("🔎 Rodar scanner")

if not run:
    st.info("Ajuste as configurações na barra lateral e clique em **Rodar scanner**.")
    st.stop()

rows = []
progress = st.progress(0)
status = st.empty()

for i, tk in enumerate(tickers):
    status.write(f"Analisando **{tk}** ...")
    df = fetch_ohlcv(tk, period=data_period)
    if df.empty or len(df) < 260:
        progress.progress((i+1)/max(1,len(tickers)))
        continue

    df = compute_features(df)

    s1 = setup_pullback(df, rsi_low=rsi_low, rsi_high=rsi_high, atr_mult=atr_mult_pb)
    s2 = setup_breakout(df, lookback=lookback, vol_mult=vol_mult, atr_mult=atr_mult_bo)

    best = None
    if s1 and s2:
        best = s1 if s1["score"] >= s2["score"] else s2
    else:
        best = s1 or s2

    if best:
        last = df.iloc[-1]
        rows.append({
            "Ticker": tk,
            "Setup": best["setup"],
            "Entrada": best["entry"],
            "Stop": best["stop"],
            "Alvo(2R)": best["target"],
            "Score": best["score"],
            "RSI14": float(last["RSI14"]) if pd.notna(last["RSI14"]) else np.nan,
            "Notes": best["notes"]
        })

    progress.progress((i+1)/max(1,len(tickers)))

status.empty()

res = pd.DataFrame(rows)
if res.empty:
    st.warning("Nenhum sinal encontrado com esses parâmetros hoje.")
    st.stop()

res = res.sort_values("Score", ascending=False).reset_index(drop=True)

st.subheader("🏁 Ranking de oportunidades")
st.dataframe(res, use_container_width=True, hide_index=True)

# Detalhe: gráfico do selecionado
st.subheader("🔍 Detalhe do ativo")
col1, col2 = st.columns([1, 2])

with col1:
    chosen = st.selectbox("Escolha um ticker para ver o gráfico", res["Ticker"].tolist())
    chosen_row = res[res["Ticker"] == chosen].iloc[0]
    st.metric("Setup", chosen_row["Setup"])
    st.metric("Score", f"{chosen_row['Score']:.1f}")
    st.metric("Entrada", f"{chosen_row['Entrada']:.2f}")
    st.metric("Stop", f"{chosen_row['Stop']:.2f}")
    st.metric("Alvo(2R)", f"{chosen_row['Alvo(2R)']:.2f}")
    st.caption(chosen_row["Notes"])

with col2:
    dfc = compute_features(fetch_ohlcv(chosen, period=data_period))
    dfc = dfc.dropna().tail(220)

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=dfc.index, open=dfc["Open"], high=dfc["High"], low=dfc["Low"], close=dfc["Close"],
        name="Preço"
    ))
    fig.add_trace(go.Scatter(x=dfc.index, y=dfc["EMA20"], name="EMA20"))
    fig.add_trace(go.Scatter(x=dfc.index, y=dfc["EMA50"], name="EMA50"))
    fig.add_trace(go.Scatter(x=dfc.index, y=dfc["EMA200"], name="EMA200"))

    # Linhas de entrada/stop/alvo
    fig.add_hline(y=chosen_row["Entrada"], line_dash="dash", annotation_text="Entrada")
    fig.add_hline(y=chosen_row["Stop"], line_dash="dash", annotation_text="Stop")
    fig.add_hline(y=chosen_row["Alvo(2R)"], line_dash="dash", annotation_text="Alvo(2R)")

    fig.update_layout(height=520, margin=dict(l=10,r=10,t=10,b=10), xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

st.caption("⚠️ Aviso: Isso é um scanner educacional. Não é recomendação de investimento.")
