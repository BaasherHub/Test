"""
CTST (Claude Test) Pump.fun Market Maker Bot
Token: 7iqfFVKnZfDGoZTSwskSWtjHHtVKNft296pSd38rpump
"""

import os
import time
import requests
import logging
from datetime import datetime
from solana.rpc.api import Client
from solders.keypair import Keypair  # type: ignore
from pump_fun import buy, sell

# ─── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log")
    ]
)
log = logging.getLogger(__name__)

# ─── Config (loaded from environment variables) ────────────────────────────────
PRIVATE_KEY   = os.environ["PRIVATE_KEY"]        # Base58 string of your bot wallet
RPC_URL       = os.environ["RPC_URL"]            # e.g. Helius RPC URL
MINT          = "7iqfFVKnZfDGoZTSwskSWtjHHtVKNft296pSd38rpump"

# Strategy settings
BUY_AMOUNT_SOL   = float(os.getenv("BUY_AMOUNT_SOL", "0.005"))   # SOL per buy
SELL_PERCENT     = float(os.getenv("SELL_PERCENT", "50"))          # % of tokens to sell each cycle
SLIPPAGE         = int(os.getenv("SLIPPAGE", "10"))               # % slippage tolerance
CYCLE_SECONDS    = int(os.getenv("CYCLE_SECONDS", "60"))          # seconds between cycles
PROFIT_TARGET    = float(os.getenv("PROFIT_TARGET", "20"))        # % gain to trigger sell
UNIT_BUDGET      = 200_000
UNIT_PRICE       = 1_000_000

# ─── Pump.fun price fetcher ────────────────────────────────────────────────────
def get_token_price():
    """Fetch current price of CTST from pump.fun API."""
    try:
        url = f"https://frontend-api.pump.fun/coins/{MINT}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        price = data.get("usd_market_cap", 0) / data.get("total_supply", 1)
        volume = data.get("volume_24h", 0)
        market_cap = data.get("usd_market_cap", 0)
        return {
            "price": price,
            "market_cap": market_cap,
            "volume_24h": volume,
            "name": data.get("name"),
            "symbol": data.get("symbol"),
        }
    except Exception as e:
        log.error(f"Price fetch error: {e}")
        return None

def get_sol_balance(client, pubkey):
    """Get SOL balance of wallet."""
    try:
        resp = client.get_balance(pubkey)
        return resp.value / 1e9  # lamports to SOL
    except Exception as e:
        log.error(f"Balance fetch error: {e}")
        return 0

# ─── Strategy ─────────────────────────────────────────────────────────────────
class MarketMaker:
    def __init__(self):
        self.client = Client(RPC_URL)
        self.keypair = Keypair.from_base58_string(PRIVATE_KEY)
        self.pubkey = self.keypair.pubkey()
        self.buy_price = None
        self.cycle = 0
        log.info(f"🤖 Bot wallet: {self.pubkey}")
        log.info(f"🪙 Token: {MINT}")
        log.info(f"💰 Buy amount: {BUY_AMOUNT_SOL} SOL | Profit target: {PROFIT_TARGET}%")

    def run(self):
        log.info("🚀 CTST Market Maker Bot started!")
        while True:
            try:
                self.cycle += 1
                log.info(f"\n{'='*50}")
                log.info(f"📊 Cycle #{self.cycle} — {datetime.now().strftime('%H:%M:%S')}")

                # Check SOL balance
                sol_balance = get_sol_balance(self.client, self.pubkey)
                log.info(f"💳 Wallet SOL balance: {sol_balance:.4f} SOL")

                if sol_balance < 0.002:
                    log.warning("⚠️  Low SOL balance! Need at least 0.002 SOL. Waiting...")
                    time.sleep(CYCLE_SECONDS * 2)
                    continue

                # Fetch token price
                info = get_token_price()
                if not info:
                    log.warning("Could not fetch price, skipping cycle.")
                    time.sleep(CYCLE_SECONDS)
                    continue

                current_price = info["price"]
                log.info(f"📈 {info['name']} (${info['symbol']}) | Market Cap: ${info['market_cap']:.2f} | Volume 24h: ${info['volume_24h']:.2f}")

                # ── Decision logic ──────────────────────────────────────────
                if self.buy_price is None:
                    # First cycle: BUY to support the token
                    log.info(f"🟢 BUY signal — buying {BUY_AMOUNT_SOL} SOL worth of CTST")
                    try:
                        buy(
                            self.client,
                            self.keypair,
                            MINT,
                            BUY_AMOUNT_SOL,
                            SLIPPAGE,
                            UNIT_BUDGET,
                            UNIT_PRICE
                        )
                        self.buy_price = current_price
                        log.info(f"✅ Bought at price: {self.buy_price:.8f}")
                    except Exception as e:
                        log.error(f"❌ Buy failed: {e}")

                else:
                    # Check if profit target hit
                    if self.buy_price > 0:
                        gain_pct = ((current_price - self.buy_price) / self.buy_price) * 100
                        log.info(f"📉 P&L since last buy: {gain_pct:+.2f}%")

                        if gain_pct >= PROFIT_TARGET:
                            log.info(f"🎯 Profit target hit ({gain_pct:.1f}%)! Selling {SELL_PERCENT}% of tokens...")
                            try:
                                sell(
                                    self.client,
                                    self.keypair,
                                    MINT,
                                    SELL_PERCENT,
                                    SLIPPAGE,
                                    UNIT_BUDGET,
                                    UNIT_PRICE
                                )
                                log.info(f"✅ Sold {SELL_PERCENT}% of holdings")
                                self.buy_price = None  # Reset, will rebuy next cycle
                            except Exception as e:
                                log.error(f"❌ Sell failed: {e}")

                        elif gain_pct <= -30:
                            # Stop loss at -30%
                            log.warning(f"🛑 Stop loss triggered ({gain_pct:.1f}%)! Selling to protect capital...")
                            try:
                                sell(self.client, self.keypair, MINT, 100, SLIPPAGE, UNIT_BUDGET, UNIT_PRICE)
                                log.info("✅ Stop loss sell executed")
                                self.buy_price = None
                            except Exception as e:
                                log.error(f"❌ Stop loss sell failed: {e}")

                        else:
                            log.info(f"⏳ Holding... waiting for {PROFIT_TARGET}% target")

            except KeyboardInterrupt:
                log.info("🛑 Bot stopped by user.")
                break
            except Exception as e:
                log.error(f"Unexpected error in cycle: {e}")

            log.info(f"💤 Sleeping {CYCLE_SECONDS}s until next cycle...")
            time.sleep(CYCLE_SECONDS)


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot = MarketMaker()
    bot.run()
