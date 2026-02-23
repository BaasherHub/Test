"""
CTST (Claude Test) Market Maker Bot
Token: 7iqfFVKnZfDGoZTSwskSWtjHHtVKNft296pSd38rpump
Uses PumpPortal API for trading + DexScreener API for price data
"""

import os
import json
import time
import base58
import requests
import logging
from datetime import datetime
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solders.keypair import Keypair  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log")
    ]
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
PRIVATE_KEY_RAW = os.environ["PRIVATE_KEY"]   # Comma-separated bytes or Base58
RPC_URL         = os.environ["RPC_URL"]
MINT            = "7iqfFVKnZfDGoZTSwskSWtjHHtVKNft296pSd38rpump"

BUY_AMOUNT_SOL  = float(os.getenv("BUY_AMOUNT_SOL", "0.005"))
PROFIT_TARGET   = float(os.getenv("PROFIT_TARGET", "20"))
STOP_LOSS       = float(os.getenv("STOP_LOSS", "30"))
SELL_PERCENT    = os.getenv("SELL_PERCENT", "50%")
SLIPPAGE        = int(os.getenv("SLIPPAGE", "10"))
PRIORITY_FEE    = float(os.getenv("PRIORITY_FEE", "0.00005"))
CYCLE_SECONDS   = int(os.getenv("CYCLE_SECONDS", "60"))

PUMPPORTAL_API  = "https://pumpportal.fun/api/trade-local"
DEXSCREENER_API = f"https://api.dexscreener.com/latest/dex/tokens/{MINT}"

# ─── Keypair loader ───────────────────────────────────────────────────────────
def load_keypair(raw: str) -> Keypair:
    raw = raw.strip()
    if raw.startswith("["):
        return Keypair.from_bytes(bytes(json.loads(raw)))
    elif "," in raw:
        return Keypair.from_bytes(bytes([int(x.strip()) for x in raw.split(",")]))
    else:
        return Keypair.from_base58_string(raw)

# ─── Price via DexScreener ────────────────────────────────────────────────────
def get_token_info():
    try:
        r = requests.get(DEXSCREENER_API, timeout=10)
        r.raise_for_status()
        pairs = r.json().get("pairs")
        if not pairs:
            log.warning("No pairs on DexScreener yet — token may have no trades.")
            return None
        pair = sorted(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0)), reverse=True)[0]
        return {
            "name":            pair.get("baseToken", {}).get("name", "CTST"),
            "symbol":          pair.get("baseToken", {}).get("symbol", "CTST"),
            "price":           float(pair.get("priceUsd") or 0),
            "market_cap":      float(pair.get("fdv") or 0),
            "volume":          float((pair.get("volume") or {}).get("h24", 0)),
            "price_change_1h": float((pair.get("priceChange") or {}).get("h1", 0)),
        }
    except Exception as e:
        log.error(f"DexScreener fetch failed: {e}")
        return None

# ─── SOL balance ──────────────────────────────────────────────────────────────
def get_sol_balance(client: Client, pubkey) -> float:
    try:
        return client.get_balance(pubkey).value / 1e9
    except Exception as e:
        log.error(f"Balance check failed: {e}")
        return 0.0

# ─── Trade via PumpPortal ─────────────────────────────────────────────────────
def trade(keypair: Keypair, client: Client, action: str, amount) -> bool:
    try:
        payload = {
            "publicKey":        str(keypair.pubkey()),
            "action":           action,
            "mint":             MINT,
            "denominatedInSol": "true" if action == "buy" else "false",
            "amount":           amount,
            "slippage":         SLIPPAGE,
            "priorityFee":      PRIORITY_FEE,
            "pool":             "pump",
        }
        resp = requests.post(PUMPPORTAL_API, json=payload, timeout=15)
        if resp.status_code != 200:
            log.error(f"PumpPortal {resp.status_code}: {resp.text}")
            return False

        tx_bytes = resp.content
        tx = VersionedTransaction.from_bytes(tx_bytes)
        tx.sign([keypair])
        sig = client.send_raw_transaction(
            bytes(tx),
            opts=TxOpts(skip_preflight=True, preflight_commitment="confirmed"),
        )
        log.info(f"✅ {action.upper()} sent → https://solscan.io/tx/{sig.value}")
        return True
    except Exception as e:
        log.error(f"Trade error ({action}): {e}")
        return False

# ─── Bot ──────────────────────────────────────────────────────────────────────
class MarketMaker:
    def __init__(self):
        self.client    = Client(RPC_URL)
        self.keypair   = load_keypair(PRIVATE_KEY_RAW)
        self.pubkey    = self.keypair.pubkey()
        self.buy_price = None
        self.cycle     = 0
        log.info(f"🤖 Wallet  : {self.pubkey}")
        log.info(f"🪙  Token   : {MINT}")
        log.info(f"⚙️  Buy {BUY_AMOUNT_SOL} SOL | Target +{PROFIT_TARGET}% | Stop -{STOP_LOSS}%")

    def run(self):
        log.info("🚀 CTST Market Maker started!\n")
        while True:
            try:
                self.cycle += 1
                log.info(f"{'='*55}")
                log.info(f"📊 Cycle #{self.cycle}  {datetime.now().strftime('%H:%M:%S')}")

                sol_bal = get_sol_balance(self.client, self.pubkey)
                log.info(f"💳 SOL balance: {sol_bal:.4f}")

                if sol_bal < 0.007:
                    log.warning("⚠️  Low balance! Top up the bot wallet.")
                    time.sleep(CYCLE_SECONDS * 3)
                    continue

                info = get_token_info()
                if not info:
                    log.info("⏳ No price data yet. Waiting...")
                    time.sleep(CYCLE_SECONDS)
                    continue

                log.info(
                    f"📈 {info['name']} | Price: ${info['price']:.8f} | "
                    f"MCap: ${info['market_cap']:.0f} | "
                    f"Vol 24h: ${info['volume']:.0f} | "
                    f"1h: {info['price_change_1h']:+.1f}%"
                )

                if self.buy_price is None:
                    log.info(f"🟢 No position. Buying {BUY_AMOUNT_SOL} SOL of $CTST...")
                    if trade(self.keypair, self.client, "buy", BUY_AMOUNT_SOL):
                        self.buy_price = info["price"]
                        log.info(f"📌 Entry price: ${self.buy_price:.8f}")
                else:
                    pnl = ((info["price"] - self.buy_price) / self.buy_price) * 100
                    log.info(f"📉 P&L since entry: {pnl:+.2f}%")

                    if pnl >= PROFIT_TARGET:
                        log.info(f"🎯 +{PROFIT_TARGET}% hit! Selling {SELL_PERCENT}...")
                        if trade(self.keypair, self.client, "sell", SELL_PERCENT):
                            self.buy_price = None
                    elif pnl <= -STOP_LOSS:
                        log.warning(f"🛑 Stop loss -{STOP_LOSS}% hit. Selling 100%...")
                        if trade(self.keypair, self.client, "sell", "100%"):
                            self.buy_price = None
                    else:
                        log.info(f"⏳ Holding. Target: +{PROFIT_TARGET}% | Stop: -{STOP_LOSS}%")

            except KeyboardInterrupt:
                log.info("🛑 Stopped.")
                break
            except Exception as e:
                log.error(f"Unexpected error: {e}")

            log.info(f"💤 Sleeping {CYCLE_SECONDS}s...\n")
            time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    MarketMaker().run()
