import random
import logging
import time
from supabase import create_client, Client
import requests
import os
from dotenv import load_dotenv
from rate_limiter import RateLimiter
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("p2p_collector.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("P2PSentinel")

class BinanceP2PExtractor:
    
    TARGET_MARKETS = {
        "USDT": ["EUR", "USD"], # High priority
    }
        
    def __init__(self):
        
        # Ensure keys are present before initializing
        load_dotenv()
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        # verify if credentials are available
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase credentials not found in environment variables")
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # inti requests session and API endpoint
        self.url = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'
        self.session = requests.Session()
        
        # Rotatable headers to prevent fingerprinting
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]
        
        # init rate limiter
        self.limiter = RateLimiter(base_delay=2.5)
        
        # cache to avoid duplicates in same run
        self.seen = set()

    # Rotates User-Agent to avoid simple bot detection.
    def update_headers(self):
        """Rotates User-Agent to avoid simple bot detection."""
        self.session.headers.update({
            'accept': '*/*',
            'clienttype': 'web',
            'content-type': 'application/json',
            'user-agent': random.choice(self.user_agents),
            'origin': 'https://p2p.binance.com',
            'referer': 'https://p2p.binance.com/en/trade/all-payments/USDT?fiat=EUR'
        })
        
    # Implements retry logic with exponential backoff and adaptive rate limiting based on API responses
    def fetch_with_retry(self, payload, retries=5):

        for attempt in range(retries):

            try:
                self.limiter.wait()
                self.update_headers()

                response = self.session.post(
                    self.url,
                    json=payload,
                    timeout=10
                )

                # ADAPTIVE RATE LIMITING
                if response.status_code == 429:
                    logger.warning("429 detected → increasing delay")
                    self.limiter.increase_delay()
                    time.sleep(self.limiter.base_delay)
                    continue

                response.raise_for_status()

                # success → slowly reduce delay (adaptive recovery)
                self.limiter.decrease_delay()

                return response.json()

            except Exception as e:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Retry {attempt+1}/{retries} in {wait:.2f}s")
                time.sleep(wait)

        return None
    
    # Fetches raw market data from Binance P2P API based on trade type, asset, and fiat currency
    def fetch_data(self, trade_type, asset, fiat):

        payload = {
            "fiat": fiat,
            "page": 1,
            "rows": 20,
            "tradeType": trade_type,
            "asset": asset,
            "countries": [],
            "proMerchantAds": False,
            "shieldMerchantAds": False,
            "filterType": "all",
            "periods": [],
            "additionalKycVerifyFilter": 0,
            "publisherType": None,
            "payTypes": [],
            "classifies": ["mass", "profession", "fiat_trade"],
            "tradedWith": False,
            "followed": False
        }

        return self.fetch_with_retry(payload)
    

    # Cleans and transforms raw API data into structured format for storage
    def clean_data(self, data, trade_type, asset, fiat):

        snapshot_time = datetime.now(timezone.utc).isoformat()
        records = []

        for item in data.get("data", []):

            adv = item.get("adv", {})
            advertiser = item.get("advertiser", {})

            adv_no = adv.get("advNo")

            # dedup
            key = f"{adv_no}-{trade_type}-{asset}-{fiat}"
            if key in self.seen:
                continue
            self.seen.add(key)
            
            entry = {
                "snapshot_time": snapshot_time,
                "adv_no": adv.get('advNo'),
                "asset": asset,
                "fiat": fiat,
                "trade_type": trade_type,
                "price": self.to_float(adv.get('price') or 0),
                "surplus_amount": self.to_float(adv.get('surplusAmount') or 0),
                "tradable_quantity" : self.to_float(adv.get('tradableQuantity') or 0),
                "min_amount": self.to_float(adv.get('minSingleTransAmount') or 0),
                "max_amount": self.to_float(adv.get('maxSingleTransAmount') or 0),
                "payment_methods": [m.get('identifier') for m in adv.get('tradeMethods', [])], # Stored as list/JSONB
                
                # Merchant Info
                "merchant_id": advertiser.get('userNo'),
                "merchant_name": advertiser.get('nickName'),
                "month_orders": int(advertiser.get('monthOrderCount', 0) or 0),
                "month_finish_rate": self.to_float(advertiser.get('monthFinishRate') or 0),
                "positive_rate": self.to_float(advertiser.get('positiveRate') or 0),
                "user_grade" : advertiser.get('userGrade'),
                "vip_level": advertiser.get('vipLevel'),
                "active_seconds": int(advertiser.get('activeTimeInSecond', 0) or 0),
                "badges": advertiser.get('badges', []) or [], # Stored as list/JSONB
                "pay_time_limit": int(adv.get('payTimeLimit', 0) or 0),
                
                # Initial Trust Score Calculation
                "opportunity_score": self.calculate_score(adv, advertiser)
            }

            records.append(entry)

        return records

    # Initial Trust Score Calculation
    def calculate_score(self, adv, advertiser):

        liquidity = self.to_float(adv.get("tradableQuantity")) / 5000
        liquidity = min(liquidity, 1.0) * 100

        trust = (
            self.to_float(advertiser.get("monthFinishRate")) * 50 +
            self.to_float(advertiser.get("positiveRate")) * 50
        )

        speed = max(0, 100 - int(advertiser.get("activeTimeInSecond") or 0))

        return liquidity * 0.3 + trust * 0.5 + speed * 0.2
    
    
    # Cleaning numeric values (handling potential None/Strings)
    def to_float(self, val):
        try:
            return float(val) if val is not None else 0.0
        except:
            return 0.0

    # Bulk inserts records into the Supabase table.
    def store(self, records):

        if not records:
            return

        BATCH_SIZE = 100

        for i in range(0, len(records), BATCH_SIZE):

            batch = records[i:i + BATCH_SIZE]

            try:
                self.supabase.table(
                    "p2p_market_data"
                ).insert(batch).execute()

                logger.info(f"Inserted batch {i}-{i+len(batch)}")

            except Exception as e:
                logger.error(f"Insert error: {e}")
    
    # Main execution loop that iterates through target markets and fetches, cleans, and stores data for both BUY and SELL trade types
    def run(self):

        for asset, fiats in self.TARGET_MARKETS.items():
            for fiat in fiats:
                for trade_type in ["BUY", "SELL"]:

                    logger.info(f"Fetching {asset}/{fiat} {trade_type}")

                    data = self.fetch_data(trade_type, asset, fiat)

                    if not data:
                        continue

                    cleaned = self.clean_data(
                        data,
                        trade_type,
                        asset,
                        fiat
                    )

                    self.store(cleaned)

                    # extra natural jitter between markets
                    time.sleep(random.uniform(2.0, 6.0))
                

# Usage
if __name__ == "__main__":
    extractor = BinanceP2PExtractor()
    extractor.run()
