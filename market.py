import asyncio
import websockets
import bson
import requests
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# WebSocket endpoint for Universalis
WEBSOCKET_URL = "wss://universalis.app/api/ws"

# API constants
BASE_URL = "https://universalis.app/api/v2"
DATA_CENTER = "Light"  # Update as needed
ITEMS_LIMIT = 100  # Max number of items per request
PROFIT_MARGIN = 0.1  # Desired profit margin (e.g., 10%)
MIN_SALES_COUNT = 5  # Min sales to consider an item
MIN_PROFIT_AMOUNT = 2000  # Min profit to consider an item
LOOP_DELAY = 4  # Delay between iterations in seconds
NUM_THREADS = 5  # Number of parallel threads for requests
COLLECT_LIMIT = 100  # Number of unique item IDs to collect before processing


SERVER_DICT = [
    {"Name": "Alpha", "ID": 402},
    {"Name": "Lich", "ID": 36},
    {"Name": "Odin", "ID": 66},
    {"Name": "Phoenix", "ID": 56},
    {"Name": "Raiden", "ID": 403},
    {"Name": "Shiva", "ID": 67},
    {"Name": "Twintania", "ID": 33},
    {"Name": "Zodiark", "ID": 42},
]

# In-memory storage for item listings
collected_listings = []

def get_item_average_prices(item_ids):
    item_ids_str = ','.join(map(str, item_ids))
    url = f"{BASE_URL}/aggregated/{DATA_CENTER}/{item_ids_str}"
    params = {
        'entriesToReturn': 1800,
        'statsWithin': 604800,
        'entriesWithin': 604800,
        'entriesUntil': int(time.time()),
        'minSalePrice': 0,
        'maxSalePrice': 2147483647
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get('results', [])

def process_batch(item_ids):
    average_prices_data = []
    
    for i in range(0, len(item_ids), ITEMS_LIMIT):
        batch_ids = item_ids[i:i + ITEMS_LIMIT]
        average_prices_data.extend(get_item_average_prices(batch_ids))

    below_market_items = []
    
    for item in average_prices_data:
        item_id = item.get('itemId')
        nq_data = item.get('nq', {})
        
        average_price = nq_data.get('averageSalePrice', {}).get('region', {}).get('price', 0)
        min_listing_price = nq_data.get('minListing', {}).get('region', {}).get('price', 0)
        sales_count = nq_data.get('dailySaleVelocity', {}).get('region', {}).get('quantity', 0)

        if average_price > 0 and sales_count >= MIN_SALES_COUNT:
            for listing in collected_listings:
                if listing['item'] == item_id:
                    listing_price = listing['pricePerUnit']
                    profit_from_current = average_price - listing_price
                    margin_profit = listing_price * PROFIT_MARGIN

                    if profit_from_current >= MIN_PROFIT_AMOUNT and min_listing_price <= margin_profit:
                        below_market_items.append({
                            'item_id': item_id,
                            'listing_price': listing_price,
                            'average_price': average_price,
                            'min_listing_price': min_listing_price,
                            'sales_count': sales_count,
                            'profit_from_current': profit_from_current
                        })
                    break

    return below_market_items

async def handle_messages(websocket):
    global collected_listings
    async for message in websocket:
        data = bson.loads(message)
        
        if data.get('event') == 'listings/add':
            listings = data.get('listings', [])
            timestamp = datetime.now().isoformat()
            for listing in listings:
                collected_listings.append({
                    'timestamp': timestamp,
                    'item': data.get('item'),
                    'world': data.get('world'),
                    'creatorID': listing.get('creatorID'),
                    'creatorName': listing.get('creatorName'),
                    'hq': listing.get('hq'),
                    'isCrafted': listing.get('isCrafted'),
                    'lastReviewTime': listing.get('lastReviewTime'),
                    'listingID': listing.get('listingID'),
                    'pricePerUnit': listing.get('pricePerUnit'),
                    'quantity': listing.get('quantity'),
                    'retainerCity': listing.get('retainerCity'),
                    'retainerID': listing.get('retainerID'),
                    'retainerName': listing.get('retainerName'),
                    'sellerID': listing.get('sellerID'),
                    'stainID': listing.get('stainID'),
                    'total': listing.get('total')
                })

            if len(collected_listings) >= COLLECT_LIMIT:
                item_ids = list(set([listing['item'] for listing in collected_listings]))
                all_below_market_items = []

                with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
                    futures = [executor.submit(process_batch, item_ids[i:i + ITEMS_LIMIT]) for i in range(0, len(item_ids), ITEMS_LIMIT)]
                    for future in futures:
                        all_below_market_items.extend(future.result())

                for item in all_below_market_items:
                    #print server name, item name, profit, sales count, listing price, average price
                    print(f"{data.get('world')}: {item['item_id']} - {item['profit_from_current']} - {item['sales_count']} - {item['listing_price']} - {item['average_price']}")

                collected_listings.clear()

async def main():
    async with websockets.connect(WEBSOCKET_URL) as websocket:
        for server in SERVER_DICT:
            world_id = server['ID']
            subscribe_msg = bson.dumps({"event": "subscribe", "channel": f"listings/add{{world={world_id}}}"})
            await websocket.send(subscribe_msg)
            print(f"Subscribed to listings/add channel for world {server['Name']} ({world_id}).")

        await handle_messages(websocket)

if __name__ == "__main__":
    asyncio.run(main())

