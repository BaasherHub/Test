# 🤖 CTST Market Maker Bot

Automated market maker bot for **Claude Test ($CTST)** on Pump.fun.
Token: `7iqfFVKnZfDGoZTSwskSWtjHHtVKNft296pSd38rpump`

---

## 🧠 What the Bot Does

- Monitors $CTST price every 60 seconds
- **Buys** small amounts to support liquidity
- **Sells** when profit target is reached (default: +20%)
- **Stop loss** triggers automatically at -30%
- Logs everything to `bot.log`

---

## ⚙️ Setup

### Step 1: Create a Bot Wallet
> ⚠️ NEVER use your main Phantom wallet as the bot wallet. Create a new one!

1. Go to [phantom.app](https://phantom.app)
2. Create a new wallet
3. Export its **private key** (Settings → Security → Export Private Key)
4. Send ~0.02–0.05 SOL to this new wallet from your main wallet

### Step 2: Get a Free RPC URL
1. Go to [helius.dev](https://helius.dev) and sign up (free tier available)
2. Create a new project and copy your **RPC URL**

### Step 3: Deploy to Railway

1. Push this folder to a GitHub repo
2. Go to [railway.app](https://railway.app) and create a new project from your repo
3. Go to **Variables** and add:
   ```
   PRIVATE_KEY = your_bot_wallet_private_key
   RPC_URL = your_helius_rpc_url
   ```
4. Railway will auto-deploy and run the bot 24/7 ✅

---

## 🎛️ Tuning the Bot

You can adjust these in Railway's Variables tab:

| Variable | Default | Description |
|----------|---------|-------------|
| `BUY_AMOUNT_SOL` | `0.005` | SOL spent per buy |
| `PROFIT_TARGET` | `20` | % gain to trigger sell |
| `SELL_PERCENT` | `50` | % of tokens to sell |
| `SLIPPAGE` | `10` | Slippage tolerance |
| `CYCLE_SECONDS` | `60` | Seconds between cycles |

---

## ⚠️ Disclaimer

This bot is for educational purposes. Crypto trading carries significant risk.
Never put in more than you can afford to lose. $CTST is a meme coin — treat it as such.
