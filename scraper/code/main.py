

from scraper.code.extractor import BinanceP2PExtractor
from processor import P2PProcessor

# load data

client = BinanceP2PExtractor()
#data = client.main()

# process data
processor = P2PProcessor(client.supabase)
processor.main()