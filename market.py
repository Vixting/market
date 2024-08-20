import requests
import time
from concurrent.futures import ThreadPoolExecutor

# Define the API endpoints and constants
BASE_URL = "https://universalis.app/api/v2"
DATA_CENTER = "Light"  # Update this as needed
ITEMS_LIMIT = 100  # Maximum number of items per request
PROFIT_MARGIN = 0.1  # Desired profit margin (e.g., 10% profit)
MIN_SALES_COUNT = 5  # Minimum number of sales required to consider an item
RECENT_ITEMS_LIMIT = 50  # Number of recent items to retrieve
MIN_PROFIT_AMOUNT = 5000  # Minimum profit amount to consider an item
LOOP_DELAY = 4  # Delay between iterations in seconds
NUM_THREADS = 5  # Number of parallel threads for making requests

def get_recently_updated_items():
    url = f"https://universalis.app/api/v2/extra/stats/most-recently-updated"
    params = {
        'dcName': DATA_CENTER,
        'entries': RECENT_ITEMS_LIMIT
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get('items', [])

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

def get_item_current_prices(item_ids):
    item_ids_str = ','.join(map(str, item_ids))
    url = f"{BASE_URL}/{DATA_CENTER}/{item_ids_str}"
    params = {
        'entriesToReturn': 100,
        'statsWithin': 604800,
        'entriesWithin': 604800,
        'entriesUntil': int(time.time()),
        'minSalePrice': 0,
        'maxSalePrice': 2147483647
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    print(response.json().get("itemIDs", []))
    print(response.json().get("items", []))
    for item in response.json():
        print(item)
    return response.json().get("itemIDs", [])

def process_batch(item_ids):
    average_prices_data = []
    current_prices_data = []
    
    # Handle item IDs in chunks of ITEMS_LIMIT
    for i in range(0, len(item_ids), ITEMS_LIMIT):
        batch_ids = item_ids[i:i + ITEMS_LIMIT]
        
        # Get average prices for this batch
        average_prices_data.extend(get_item_average_prices(batch_ids))
        
        # Get current prices for this batch
        current_prices_data.extend(get_item_current_prices(batch_ids))
    
    # Convert current prices data to a dictionary for quick lookup
    print(current_prices_data)
    current_prices_dict = {item: item for item in current_prices_data}
    print(current_prices_dict)
    
    below_market_items = []
    
    for item in average_prices_data:
        item_id = item.get('itemId')
        nq_data = item.get('nq', {})
        
        average_price = nq_data.get('averageSalePrice', {}).get('region', {}).get('price', 0)
        recent_purchase_price = nq_data.get('recentPurchase', {}).get('region', {}).get('price', 0)
        min_listing_price = nq_data.get('minListing', {}).get('region', {}).get('price', 0)
        sales_count = nq_data.get('dailySaleVelocity', {}).get('region', {}).get('quantity', 0)

        # Get current price if available
        current_data = current_prices_dict.get(item_id, {})
        print(current_data)
        current_price = current_data.get('nq', {}).get('total', {}).get('region', {}).get('pricePerUnit', 0)

        if average_price > 0 and sales_count >= MIN_SALES_COUNT:
            # Calculate profit based on average price and current price
            profit_from_average = average_price - recent_purchase_price
            profit_from_current = current_price - recent_purchase_price
            margin_profit = recent_purchase_price * PROFIT_MARGIN

            # Check if both profit criteria are met
            if profit_from_current >= MIN_PROFIT_AMOUNT and min_listing_price <= margin_profit:
                below_market_items.append({
                    'item_id': item_id,
                    'recent_purchase_price': recent_purchase_price,
                    'average_price': average_price,
                    'current_price': current_price,
                    'min_listing_price': min_listing_price,
                    'sales_count': sales_count,
                    'profit_from_current': profit_from_current
                })
    
    return below_market_items

def find_below_market_value_items():
    items = get_recently_updated_items()
    item_ids = [item.get('itemID') for item in items]
    all_below_market_items = []

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = [executor.submit(process_batch, item_ids[i:i + ITEMS_LIMIT]) for i in range(0, len(item_ids), ITEMS_LIMIT)]
        for future in futures:
            all_below_market_items.extend(future.result())

    return all_below_market_items

def main():
    while True:
        print("Checking for items sold below market value...")
        below_market_items = find_below_market_value_items()

        if below_market_items:
            print("Items being sold below market value:")
            for item in below_market_items:
                print(f"Item ID: {item['item_id']}, Recent Purchase Price: {item['recent_purchase_price']}, "
                      f"Average Price: {item['average_price']}, Current Price: {item['current_price']}, "
                      f"Min Listing Price: {item['min_listing_price']}, Sales Count: {item['sales_count']}, "
                      f"Profit from Current Price: {item['profit_from_current']}")
        else:
            print("No items found being sold below market value.")

        print(f"Waiting for {LOOP_DELAY} seconds before the next check...")
        time.sleep(LOOP_DELAY)

if __name__ == "__main__":
    main()
