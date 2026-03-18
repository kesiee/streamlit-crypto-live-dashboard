"""
CryptoLive — Real-Time Crypto Dashboard
Data: CoinGecko (tickers) + CryptoCompare (OHLCV) — both work on Streamlit Cloud
Light theme · Persistent candle cache · Toggleable indicators
"""

import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time, os

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CryptoLive · KC",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS — clean light theme ───────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    color: #1e293b;
  }
  .stApp { background: #f8fafc; }

  /* ── Ticker cards ── */
  .ticker-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    position: relative; overflow: hidden;
    transition: box-shadow .15s;
  }
  .ticker-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.10); }
  .ticker-card::before {
    content:''; position:absolute; top:0;left:0;right:0; height:3px;
    background: linear-gradient(90deg, #6366f1, #0ea5e9);
  }
  .ticker-symbol {
    font-family:'DM Mono',monospace; font-size:10px; font-weight:500;
    color:#94a3b8; letter-spacing:.12em; text-transform:uppercase;
  }
  .ticker-price {
    font-family:'DM Mono',monospace; font-size:20px; font-weight:500;
    color:#0f172a; margin: 5px 0 3px;
  }
  .chg-up  { color:#059669; font-size:12px; font-weight:600; }
  .chg-dn  { color:#dc2626; font-size:12px; font-weight:600; }
  .ticker-meta { color:#cbd5e1; font-size:10px; margin-top:4px; font-family:'DM Mono',monospace; }

  /* ── Section labels ── */
  .sec-label {
    font-family:'DM Mono',monospace; font-size:9px; letter-spacing:.18em;
    color:#6366f1; text-transform:uppercase; margin: 22px 0 10px;
    display:flex; align-items:center; gap:8px;
  }
  .sec-label::after {
    content:''; flex:1; height:1px; background:#e2e8f0;
  }

  /* ── Cache badge ── */
  .cache-badge {
    display:inline-flex; align-items:center; gap:6px;
    background:#f0f9ff; border:1px solid #bae6fd;
    border-radius:20px; padding:3px 12px;
    font-family:'DM Mono',monospace; font-size:10px; color:#0369a1;
  }

  /* ── Live dot ── */
  .live-dot {
    display:inline-block; width:7px; height:7px; background:#10b981;
    border-radius:50%; margin-right:5px; animation: pulse 1.4s infinite;
  }
  @keyframes pulse {
    0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.3;transform:scale(1.6)}
  }
  .live-lbl {
    font-family:'DM Mono',monospace; font-size:10px;
    color:#059669; letter-spacing:.08em;
  }

  /* ── Page header ── */
  .page-title {
    font-size:22px; font-weight:600; color:#0f172a; margin:0;
    letter-spacing:-.3px;
  }
  .page-sub { color:#94a3b8; font-size:12px; margin-top:3px; }

  /* ── Error / warning chips ── */
  .warn-chip {
    background:#fef9c3; border:1px solid #fde047; border-radius:8px;
    padding:8px 14px; font-size:12px; color:#713f12; margin:8px 0;
  }

  /* Streamlit chrome */
  #MainMenu,footer,header{visibility:hidden}
  .block-container{padding-top:1.2rem; max-width:100%;}
  [data-testid="stSidebar"]{background:#ffffff; border-right:1px solid #e2e8f0;}
  [data-testid="stSidebar"] section { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
CACHE_DIR = "/tmp/cryptolive_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# CoinGecko IDs ↔ display symbols
COIN_MAP = {
    "BTC":  "bitcoin",
    "ETH":  "ethereum",
    "SOL":  "solana",
    "BNB":  "binancecoin",
    "XRP":  "ripple",
    "ADA":  "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "DOT":  "polkadot",
    "LTC":  "litecoin",
    "ARB":  "arbitrum",
}
ALL_SYMBOLS = list(COIN_MAP.keys())

# CryptoCompare interval map  →  (timeframe, endpoint)
CC_INTERVALS = {
    "1m":  ("minute", 1),
    "5m":  ("minute", 5),
    "15m": ("minute", 15),
    "30m": ("minute", 30),
    "1h":  ("hour",   1),
    "4h":  ("hour",   4),
    "1d":  ("day",    1),
}

# ── Formatters ────────────────────────────────────────────────────────────────
def fmt_price(p):
    if p >= 1000:  return f"${p:,.2f}"
    if p >= 1:     return f"${p:.4f}"
    return f"${p:.6f}"

def fmt_vol(v):
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"

# ── Data fetchers ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=6)
def fetch_ticker24(symbols: tuple) -> dict:
    """CoinGecko simple price — works on Streamlit Cloud."""
    ids = ",".join(COIN_MAP[s] for s in symbols if s in COIN_MAP)
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids,
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                    "include_high_low_24h": "true"},
            headers={"accept": "application/json"},
            timeout=8,
        )
        raw = r.json()
        out = {}
        for sym in symbols:
            cid = COIN_MAP.get(sym)
            if cid and cid in raw:
                d = raw[cid]
                out[sym] = {
                    "price":    d.get("usd", 0),
                    "change24": d.get("usd_24h_change", 0),
                    "vol24":    d.get("usd_24h_vol", 0),
                    "high24":   d.get("usd_24h_high", 0),
                    "low24":    d.get("usd_24h_low", 0),
                }
        return out
    except Exception as e:
        return {}

def fetch_ohlcv_cc(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
    """
    CryptoCompare OHLCV — free tier, no key needed for reasonable limits.
    Handles minute/hour/day aggregation.
    """
    timeframe, agg = CC_INTERVALS.get(interval, ("hour", 1))
    endpoint = {
        "minute": "https://min-api.cryptocompare.com/data/v2/histominute",
        "hour":   "https://min-api.cryptocompare.com/data/v2/histohour",
        "day":    "https://min-api.cryptocompare.com/data/v2/histoday",
    }[timeframe]

    try:
        r = requests.get(endpoint, params={
            "fsym": symbol, "tsym": "USD",
            "limit": limit, "aggregate": agg,
        }, timeout=10)
        data = r.json()
        if data.get("Response") != "Success":
            return pd.DataFrame()

        rows = data["Data"]["Data"]
        df = pd.DataFrame(rows)
        df["open_time"]  = pd.to_datetime(df["time"], unit="s")
        df["close_time"] = df["open_time"] + pd.Timedelta(seconds=agg * {"minute":60,"hour":3600,"day":86400}[timeframe] - 1)
        df = df.rename(columns={"open":"open","high":"high","low":"low",
                                 "close":"close","volumefrom":"volume"})
        df["quote_vol"] = df["volume"] * df["close"]
        df = df[["open_time","open","high","low","close","volume","quote_vol","close_time"]]
        for c in ["open","high","low","close","volume","quote_vol"]:
            df[c] = df[c].astype(float)
        return df[df["open"] > 0].reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame()

# ── Candle cache ──────────────────────────────────────────────────────────────
def cache_path(symbol, interval):
    return os.path.join(CACHE_DIR, f"{symbol}_{interval}.parquet")

def load_cache(symbol, interval):
    p = cache_path(symbol, interval)
    if os.path.exists(p):
        try: return pd.read_parquet(p)
        except: return pd.DataFrame()
    return pd.DataFrame()

def save_cache(symbol, interval, df):
    try: df.tail(500).to_parquet(cache_path(symbol, interval), index=False)
    except: pass

def get_candles(symbol, interval):
    cached = load_cache(symbol, interval)
    if cached.empty:
        fresh = fetch_ohlcv_cc(symbol, interval, limit=300)
        if not fresh.empty:
            save_cache(symbol, interval, fresh)
        return fresh
    # Incremental update
    fresh = fetch_ohlcv_cc(symbol, interval, limit=50)
    if fresh.empty:
        return cached
    merged = (pd.concat([cached, fresh], ignore_index=True)
              .drop_duplicates("open_time", keep="last")
              .sort_values("open_time")
              .reset_index(drop=True))
    save_cache(symbol, interval, merged)
    return merged

# ── Indicators ────────────────────────────────────────────────────────────────
def ema(s, n):    return s.ewm(span=n, adjust=False).mean()
def bb(s, n, k):
    mid = s.rolling(n).mean(); sd = s.rolling(n).std()
    return mid - k*sd, mid, mid + k*sd
def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))
def macd(s, f=12, sl=26, sg=9):
    m = ema(s,f)-ema(s,sl); sig=ema(m,sg); return m, sig, m-sig
def vwap(df):
    tp = (df["high"]+df["low"]+df["close"])/3
    return (tp*df["volume"]).cumsum()/df["volume"].cumsum()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📡 CryptoLive")
    st.caption("Binance data · Light theme")
    st.markdown("---")

    watchlist = st.multiselect("Watchlist", ALL_SYMBOLS,
        default=["BTC","ETH","SOL","BNB"])
    chart_symbol = st.selectbox("Chart Symbol",
        watchlist if watchlist else ALL_SYMBOLS)
    interval_label = st.radio("Interval", list(CC_INTERVALS.keys()), index=4, horizontal=True)
    interval = interval_label
    chart_type = st.radio("Chart Type", ["Candlestick","Line"], horizontal=True)

    st.markdown("---")
    st.markdown("**📊 Indicators**")
    show_volume = st.checkbox("Volume", value=True)

    show_ema = st.checkbox("EMA", value=True)
    ema_periods = []
    if show_ema:
        raw_ema = st.text_input("EMA periods (comma-separated)", value="9,21,55")
        ema_periods = [int(x.strip()) for x in raw_ema.split(",")
                       if x.strip().isdigit() and 1 <= int(x.strip()) <= 500]

    show_bb = st.checkbox("Bollinger Bands", value=False)
    bb_period, bb_std = 20, 2.0
    if show_bb:
        c1,c2 = st.columns(2)
        bb_period = int(c1.number_input("BB Period", 5, 100, 20))
        bb_std    = float(c2.number_input("BB Std", 0.5, 4.0, 2.0, step=0.5))

    show_rsi  = st.checkbox("RSI", value=False)
    rsi_period = 14
    if show_rsi:
        rsi_period = st.slider("RSI Period", 5, 30, 14)

    show_macd = st.checkbox("MACD", value=False)
    show_vwap = st.checkbox("VWAP", value=False)

    st.markdown("---")
    refresh_sec = st.slider("Auto-refresh (sec)", 10, 120, 30)
    st.markdown('<span class="live-dot"></span><span class="live-lbl">LIVE · COINGECKO</span>',
                unsafe_allow_html=True)
    st.caption(f"Updated {datetime.now().strftime('%H:%M:%S')}")

# ── Page header ───────────────────────────────────────────────────────────────
c1,c2 = st.columns([5,1])
with c1:
    st.markdown('<p class="page-title">📡 CryptoLive</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-sub">Real-time market data · CoinGecko + CryptoCompare · Candle history cache</p>',
                unsafe_allow_html=True)
with c2:
    st.markdown('<div style="text-align:right;padding-top:12px">'
                '<span class="live-dot"></span><span class="live-lbl">LIVE</span></div>',
                unsafe_allow_html=True)
st.markdown("---")

# ── Ticker cards ──────────────────────────────────────────────────────────────
if watchlist:
    tickers = fetch_ticker24(tuple(watchlist))
    st.markdown('<div class="sec-label">Watchlist</div>', unsafe_allow_html=True)
    cols = st.columns(min(len(watchlist), 4))
    for i, sym in enumerate(watchlist):
        t = tickers.get(sym, {})
        price = t.get("price", 0)
        chg   = t.get("change24", 0)
        arrow = "▲" if chg >= 0 else "▼"
        cls   = "chg-up" if chg >= 0 else "chg-dn"
        with cols[i % 4]:
            st.markdown(f"""
            <div class="ticker-card">
              <div class="ticker-symbol">{sym} / USD</div>
              <div class="ticker-price">{fmt_price(price)}</div>
              <div class="{cls}">{arrow} {chg:+.2f}%</div>
              <div class="ticker-meta">
                Vol {fmt_vol(t.get("vol24",0))} &nbsp;·&nbsp;
                H {fmt_price(t.get("high24",0))} &nbsp;·&nbsp;
                L {fmt_price(t.get("low24",0))}
              </div>
            </div>""", unsafe_allow_html=True)

# ── Chart header ──────────────────────────────────────────────────────────────
st.markdown(f'<div class="sec-label">{chart_symbol} / USD &nbsp;·&nbsp; {interval_label}</div>',
            unsafe_allow_html=True)

df = get_candles(chart_symbol, interval)

# Cache badge
if not df.empty:
    oldest = df["open_time"].min().strftime("%b %d %H:%M")
    newest = df["open_time"].max().strftime("%b %d %H:%M")
    st.markdown(f'<span class="cache-badge">📦 {len(df)} candles &nbsp;·&nbsp; {oldest} → {newest}</span>',
                unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

# ── Build chart ───────────────────────────────────────────────────────────────
PAPER = "#ffffff"
PLOT  = "#ffffff"
GRID  = "#f1f5f9"
AXIS  = "#94a3b8"
FONT  = "DM Mono, monospace"

if not df.empty:
    row_h = [0.55]
    vol_row = rsi_row = macd_row = None
    if show_volume: row_h.append(0.12); vol_row  = len(row_h)
    if show_rsi:    row_h.append(0.15); rsi_row  = len(row_h)
    if show_macd:   row_h.append(0.18); macd_row = len(row_h)
    n = len(row_h); total = sum(row_h)
    row_h = [h/total for h in row_h]

    fig = make_subplots(rows=n, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=row_h)

    # Price
    if chart_type == "Candlestick":
        fig.add_trace(go.Candlestick(
            x=df["open_time"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="OHLC",
            increasing_line_color="#059669", increasing_fillcolor="#d1fae5",
            decreasing_line_color="#dc2626", decreasing_fillcolor="#fee2e2",
        ), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(
            x=df["open_time"], y=df["close"], mode="lines", name="Price",
            line=dict(color="#6366f1", width=2),
            fill="tozeroy", fillcolor="rgba(99,102,241,0.05)",
        ), row=1, col=1)

    # EMAs
    EMA_COLORS = ["#f59e0b","#8b5cf6","#06b6d4","#f97316","#ec4899"]
    for j, p in enumerate(ema_periods[:5]):
        fig.add_trace(go.Scatter(
            x=df["open_time"], y=ema(df["close"], p),
            mode="lines", name=f"EMA {p}",
            line=dict(color=EMA_COLORS[j%5], width=1.4),
        ), row=1, col=1)

    # Bollinger Bands
    if show_bb:
        blo, bmid, bhi = bb(df["close"], bb_period, bb_std)
        fig.add_trace(go.Scatter(
            x=df["open_time"], y=bhi, mode="lines",
            name=f"BB({bb_period},{bb_std})",
            line=dict(color="#94a3b8", width=1, dash="dot"),
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df["open_time"], y=blo, mode="lines", name="BB Lower",
            line=dict(color="#94a3b8", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(148,163,184,0.07)",
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df["open_time"], y=bmid, mode="lines", name="BB Mid",
            line=dict(color="#64748b", width=1),
        ), row=1, col=1)

    # VWAP
    if show_vwap:
        fig.add_trace(go.Scatter(
            x=df["open_time"], y=vwap(df),
            mode="lines", name="VWAP",
            line=dict(color="#db2777", width=1.5, dash="dash"),
        ), row=1, col=1)

    # Volume
    if show_volume and vol_row:
        vcols = ["#bbf7d0" if c >= o else "#fecaca"
                 for c, o in zip(df["close"], df["open"])]
        fig.add_trace(go.Bar(
            x=df["open_time"], y=df["volume"],
            name="Volume", marker_color=vcols,
            marker_line_width=0, opacity=0.9,
        ), row=vol_row, col=1)

    # RSI
    if show_rsi and rsi_row:
        fig.add_trace(go.Scatter(
            x=df["open_time"], y=rsi(df["close"], rsi_period),
            mode="lines", name=f"RSI({rsi_period})",
            line=dict(color="#6366f1", width=1.5),
        ), row=rsi_row, col=1)
        for lvl, col in [(70,"#dc2626"),(30,"#059669"),(50,"#e2e8f0")]:
            fig.add_hline(y=lvl, line_dash="dot", line_color=col,
                          line_width=0.8, row=rsi_row, col=1)

    # MACD
    if show_macd and macd_row:
        ml, sl_, hist_ = macd(df["close"])
        hcols = ["#bbf7d0" if v >= 0 else "#fecaca" for v in hist_]
        fig.add_trace(go.Bar(
            x=df["open_time"], y=hist_,
            name="MACD Hist", marker_color=hcols,
            marker_line_width=0,
        ), row=macd_row, col=1)
        fig.add_trace(go.Scatter(
            x=df["open_time"], y=ml, mode="lines", name="MACD",
            line=dict(color="#6366f1", width=1.3),
        ), row=macd_row, col=1)
        fig.add_trace(go.Scatter(
            x=df["open_time"], y=sl_, mode="lines", name="Signal",
            line=dict(color="#f59e0b", width=1.3),
        ), row=macd_row, col=1)

    # Layout
    fig.update_layout(
        height=340 + n * 80,
        paper_bgcolor=PAPER, plot_bgcolor=PLOT,
        font=dict(family=FONT, size=10, color=AXIS),
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=10),
                    bordercolor="#e2e8f0", borderwidth=1),
        margin=dict(l=8, r=8, t=24, b=8),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0",
                        font=dict(family=FONT, size=11)),
    )
    for i in range(1, n+1):
        xk = "xaxis" if i==1 else f"xaxis{i}"
        yk = "yaxis" if i==1 else f"yaxis{i}"
        fig.update_layout(**{
            xk: dict(gridcolor=GRID, zerolinecolor=GRID,
                     showspikes=True, spikecolor="#cbd5e1",
                     spikedash="dot", spikethickness=1,
                     tickfont=dict(color=AXIS)),
            yk: dict(gridcolor=GRID, zerolinecolor=GRID,
                     side="right", tickfont=dict(color=AXIS)),
        })

    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": True, "displaylogo": False,
                            "modeBarButtonsToRemove": ["lasso2d","select2d","autoScale2d"]})
else:
    st.markdown('<div class="warn-chip">⚠️ Could not load candle data — CryptoCompare may be rate-limiting. Try again in a few seconds.</div>',
                unsafe_allow_html=True)

# ── Market overview table ─────────────────────────────────────────────────────
st.markdown('<div class="sec-label">Market Overview</div>', unsafe_allow_html=True)
if watchlist:
    tickers = fetch_ticker24(tuple(watchlist))
    rows = []
    for sym in watchlist:
        t = tickers.get(sym, {})
        if not t: continue
        chg = t.get("change24", 0)
        rows.append({
            "Symbol"  : sym,
            "Price"   : fmt_price(t.get("price",0)),
            "24h %"   : f"{chg:+.2f}%",
            "24h High": fmt_price(t.get("high24",0)),
            "24h Low" : fmt_price(t.get("low24",0)),
            "Volume"  : fmt_vol(t.get("vol24",0)),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("CoinGecko · CryptoCompare · Built by Shashank (KC) · [Portfolio](https://portfolio-shashank-kammanahalli.vercel.app)")

time.sleep(refresh_sec)
st.rerun()
