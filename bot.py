"""
CTST (Claude Test) Market Maker Bot
Token: 7iqfFVKnZfDGoZTSwskSWtjHHtVKNft296pSd38rpump
Uses PumpPortal API for trading - https://pumpportal.fun
"""

import os
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
PRIVATE_KEY_RAW  = os.environ["PRIVATE_KEY"]   # Accepts Base58 string OR JSON array like [1,2,3,...]
RPC_URL          = os.environ["RPC_URL"]        # Helius or QuickNode RPC URL
MINT             = "7iqfFVKnZfDGoZTSwskSWtjHHtVKNft296pSd38rpump"

BUY_AMOUNT_SOL   = float(os.getenv("BUY_AMOUNT_SOL", "0.005"))
PROFIT_TARGET    = float(os.getenv("PROFIT_TARGET", "20"))     # % gain to sell
STOP_LOSS        = float(os.getenv("STOP_LOSS", "30"))         # % loss to cut
SELL_PERCENT     = os.getenv("SELL_PERCENT", "50%")            # e.g. "50%"
SLIPPAGE         = int(os.getenv("SLIPPAGE", "10"))
PRIORITY_FEE     = float(os.getenv("PRIORITY_FEE", "0.00005"))
CYCLE_SECONDS    = int(os.getenv("CYCLE_SECONDS", "60"))

PUMPPORTAL_API   = "https://pumpportal.fun/api/trade-local"

def load_keypair(raw: str) -> Keypair:
    """Load keypair from either Base58 string or JSON byte array format."""
    raw = raw.strip()
    if raw.startswith("["):
        # JSON array format: [1,2,3,...]
        import json
        byte_list = json.loads(raw)
        return Keypair.from_bytes(bytes(byte_list))
    elif "," in raw:
        # Comma-separated without brackets: 1,2,3,...
        byte_list = [int(x.strip()) for x in raw.split(",")]
        return Keypair.from_bytes(bytes(byte_list))
    else:
        # Base58 string
        return Keypair.from_base58_string(raw)
PUMP_FUN_API     = "https://frontend-api.pump.fun/coins"

# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_token_info():
    """Fetch token info from pump.fun frontend API."""
    try:
        r = requests.get(f"{PUMP_FUN_API}/{MINT}", timeout=10)
        r.raise_for_status()
        d = r.json()
        return {
            "name":       d.get("name", "Unknown"),
            "symbol":     d.get("symbol", "???"),
            "market_cap": d.get("usd_market_cap", 0),
            "volume":     d.get("volume_24h", 0),
            # Price approximation from market cap / supply
            "price":      d.get("usd_market_cap", 0) / max(d.get("total_supply", 1), 1),
        }
    except Exception as e:
        log.error(f"Token info fetch failed: {e}")
        return None


def get_sol_balance(client: Client, pubkey) -> float:
    """Return wallet SOL balance."""
    try:
        return client.get_balance(pubkey).value / 1e9
    except Exception as e:
        log.error(f"Balance check failed: {e}")
        return 0.0


def trade(keypair: Keypair, client: Client, action: str, amount) -> bool:
    """
    Execute a buy or sell via PumpPortal local trade API.
    action: "buy" or "sell"
    amount: SOL float for buy, or "50%" string for sell
    """
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
        # PumpPortal returns a serialized transaction
        resp = requests.post(
            PUMPPORTAL_API,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if resp.status_code != 200:
            log.error(f"PumpPortal error {resp.status_code}: {resp.text}")
            return False

        # Deserialize, sign, and send
        tx_bytes = base58.b58decode(resp.content)
        tx = VersionedTransaction.from_bytes(tx_bytes)
        tx.sign([keypair])

        sig = client.send_raw_transaction(
            bytes(tx),
            opts=TxOpts(skip_preflight=True, preflight_commitment="confirmed"),
        )
        log.info(f"✅ {action.upper()} tx sent: https://solscan.io/tx/{sig.value}")
        return True

    except Exception as e:
        log.error(f"Trade error ({action}): {e}")
        return False


# ─── Bot ──────────────────────────────────────────────────────────────────────
class MarketMaker:
    def __init__(self):
        self.client   = Client(RPC_URL)
        self.keypair  = load_keypair(PRIVATE_KEY_RAW)
        self.pubkey   = self.keypair.pubkey()
        self.buy_price = None
        self.cycle     = 0
        log.info(f"🤖 Bot wallet  : {self.pubkey}")
        log.info(f"🪙  Token       : {MINT}")
        log.info(f"⚙️  Buy {BUY_AMOUNT_SOL} SOL | Target +{PROFIT_TARGET}% | Stop -{STOP_LOSS}%")

    def run(self):
        log.info("🚀 CTST Market Maker started!\n")
        while True:
            try:
                self.cycle += 1
                log.info(f"{'='*55}")
                log.info(f"📊 Cycle #{self.cycle}  {datetime.now().strftime('%H:%M:%S')}")

                sol_bal = get_sol_balance(self.client, self.pubkey)
                log.info(f"💳 SOL balance : {sol_bal:.4f}")

                # Safety: keep at least 0.005 SOL for fees
                if sol_bal < 0.007:
                    log.warning("⚠️  Low balance! Waiting for top-up...")
                    time.sleep(CYCLE_SECONDS * 3)
                    continue

                info = get_token_info()
                if not info:
                    time.sleep(CYCLE_SECONDS)
                    continue

                log.info(f"📈 {info['name']} (${info['symbol']}) | "
                         f"MCap ${info['market_cap']:.2f} | "
                         f"Vol ${info['volume']:.2f}")

                # ── Strategy ──────────────────────────────────────────────
                if self.buy_price is None:
                    # No position — BUY
                    log.info(f"🟢 Opening position: buying {BUY_AMOUNT_SOL} SOL of $CTST...")
                    success = trade(self.keypair, self.client, "buy", BUY_AMOUNT_SOL)
                    if success:
                        self.buy_price = info["price"]
                        log.info(f"📌 Entry price recorded: {self.buy_price:.10f}")

                else:
                    if self.buy_price > 0:
                        pnl = ((info["price"] - self.buy_price) / self.buy_price) * 100
                        log.info(f"📉 P&L: {pnl:+.2f}%")

                        if pnl >= PROFIT_TARGET:
                            log.info(f"🎯 Profit target hit! Selling {SELL_PERCENT}...")
                            success = trade(self.keypair, self.client, "sell", SELL_PERCENT)
                            if success:
                                self.buy_price = None  # Reset — will rebuy next cycle

                        elif pnl <= -STOP_LOSS:
                            log.warning(f"🛑 Stop loss hit! Selling 100% to protect capital...")
                            success = trade(self.keypair, self.client, "sell", "100%")
                            if success:
                                self.buy_price = None

                        else:
                            log.info(f"⏳ Holding... target: +{PROFIT_TARGET}% | stop: -{STOP_LOSS}%")

            except KeyboardInterrupt:
                log.info("🛑 Stopped by user.")
                break
            except Exception as e:
                log.error(f"Unexpected error: {e}")

            log.info(f"💤 Next cycle in {CYCLE_SECONDS}s...")
            time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    MarketMaker().run()
