# 📡 CryptoLive — Real-Time Crypto Dashboard

A live crypto market dashboard built with **Streamlit + Binance REST API**.

## Features
- 🔴 Live price tickers with 24h stats (price, % change, volume, high/low)
- 📊 Candlestick & line charts with auto-refresh
- 📈 Moving averages (MA 20 / MA 50) overlay
- 📉 Volume bars with buy/sell coloring
- ⚙️ Configurable watchlist, interval, chart type
- 🌑 Dark trading-terminal aesthetic

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click **New app** → select your repo → `app.py`
4. Deploy — no secrets needed (uses public Binance API)

## Stack
- `streamlit` — UI framework
- `plotly` — interactive charts
- `requests` — Binance REST API calls
- `pandas` — data wrangling

## Data Source
[Binance REST API](https://binance-docs.github.io/apidocs/spot/en/) — public endpoints, no API key required.

---
Built by **Shashank (KC)** · [Portfolio](https://portfolio-shashank-kammanahalli.vercel.app)
