import asyncio
import json
import websockets
import bson
import pandas as pd
import aiohttp
import requests
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import ssl

XIVAPI_BASE_URL = "https://beta.xivapi.com/api/1"
# WebSocket endpoint for Universalis
WEBSOCKET_URL = "wss://universalis.app/api/ws"

# API constants
BASE_URL = "https://universalis.app/api/v2"
DATA_CENTER = "Light"

ITEMS_LIMIT = 100
PROFIT_MARGIN = 0.1
MIN_SALES_COUNT = 1
MIN_PROFIT_AMOUNT = 30000

MIN_VOLUME_PROFIT_AMOUNT = 2000
HIGH_VOLUME_THRESHOLD = 50

LOOP_DELAY = 1
NUM_THREADS = 5
COLLECT_LIMIT = 50
DISCORD_ALERT = True
USE_AVERAGE_OF_LOWEST_THREE = False 
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1275810577565876224/k20OC4n4ldTzCmhsbXNbb8xcYyXn6yU0UfvMtJkxEgoemTG5sb71jJleGt_oAgwclekL'
ROLE_ID = '1275812558736986205'  

# Modified to include webhook URLs for each world
SERVER_DICT = [
    {"Name": "Alpha", "ID": 402, "Webhook": "https://discord.com/api/webhooks/1355293457283023058/wmte8w5rutFr1ME5Tfn8M3Z9Ms5cMcfdqf-7Mp8D3B68N94wEXx1qTtXf0JZzfYNqM4U"},
    {"Name": "Lich", "ID": 36, "Webhook": "https://discord.com/api/webhooks/1355293230488359116/U3769_BTERYlyEzjt3owgHY9zZEhL3sBkXUaPfIJL7UZOQ6nhuxWcxaSACdg2-A58VOs"},
    {"Name": "Odin", "ID": 66, "Webhook": "https://discord.com/api/webhooks/1355293366149058731/ULLA-OFzgit9l2o7PU59ra6chQR3MSu7ub48fW21pjzZrqRAXZwVbR21dKnnD7UkxlZM"},
    {"Name": "Phoenix", "ID": 56, "Webhook": "https://discord.com/api/webhooks/1355293551566655660/PRW_IeIba5ptei5fy9U86iWOhXUE7Be2QxRqGxnT5AJf5hlg-Nasw772uEDbg6ZyX8pN"},
    {"Name": "Raiden", "ID": 403, "Webhook": DISCORD_WEBHOOK_URL},  # Using default webhook for Raiden
    {"Name": "Shiva", "ID": 67, "Webhook": "https://discord.com/api/webhooks/1355293626011357336/aSo3cLNajYPq3l4tawRl0-QGs7UTwvEBPzM2Py3db41WsGCloML5t-ZOBD6oCRIcid5V"},
    {"Name": "Twintania", "ID": 33, "Webhook": "https://discord.com/api/webhooks/1355293692327493752/Ke27iQAwdVAAtQTnK3Og2wqXcclSJC1lBAobqKvWnAgKKHj6Tl0hR72NCpHTHWjsTLGb"},
    {"Name": "Zodiark", "ID": 42, "Webhook": "https://discord.com/api/webhooks/1355293766445170859/U0eXGxumDHSgW_xcmhSXuGe7EY8Py1S_1b7l3Hejq7rsyfMF6mo1S9VSNA6a4qJgwXyj"},
]

SPECIFIC_ITEM_IDS = {
    35833: 80000
}

ITEM_DATA_CSV = 'data/item.csv'

RETAINER_NAMES = {
    "Octantis": 403, 
    "Polantis": 403   
}

item_df = pd.read_csv(ITEM_DATA_CSV, header=2, usecols=[0, 10])
item_df.columns = ['ID', 'Name']
item_lookup = dict(zip(item_df['ID'], item_df['Name']))
collected_listings = []

ALERT_CONFIG = {
    'profitable_item': {
        'role_id': '1276848379548274688',
        'webhook_url': 'https://discord.com/api/webhooks/1276848719383232604/VsFxB5gF8_clTdKCnrzOOXssb0gC-_UWfhZRn-2QwOMo7-TD10UBCsfXBFka1-ldqTja'
    },
    'specific_item': {
        'role_id': '1276848425643802635',
        'webhook_url': 'https://discord.com/api/webhooks/1276848857522634752/_IBHVuD8w1v2pHgNgyvSeqwfEouOWtQn3v4BSzy2BP98Tfv9a-NnwiaVf-kka6jqB1Y8'
    },
    'undercut': {
        'role_id': '1276848476684288072',
        'webhook_url': 'https://discord.com/api/webhooks/1276848811167322174/N3Qws2-QLDG-1loMsRkCtUb0urbvhsHfQ8nUX5nnzzBnug2pPopC1FDNHEwJs_4LjvBu'
    }
}

def send_alert(title, description, color, fields, role_id, webhook_url, item_icon_url=None):
    content = f"<@&{role_id}> {title}"

    embed = {
        'title': title,
        'description': description,
        'color': color,
        'fields': fields,
        'footer': {'text': 'Automated Alert System'},
        'timestamp': datetime.utcnow().isoformat()
    }

    if item_icon_url:
        embed['thumbnail'] = {'url': item_icon_url}

    payload = {
        'content': content,
        'embeds': [embed]
    }

    response = requests.post(webhook_url, json=payload)
    if response.status_code != 204:
        print(f"Failed to send alert: {response.status_code} {response.text}")


async def send_discord_alert(item_name, item_id, is_hq, listing_price_without_tax, listing_price_with_tax, price_without_tax, price_with_tax, profit_without_tax, profit_with_tax, home_sales_count, dc_sales_count, world_name, tax_buying, tax_selling, item_icon_url):
    fields = [
        {'name': 'Item', 'value': f"[**{item_name}**](https://universalis.app/market/{item_id})\n*ID:* `{item_id}`", 'inline': False},
        {'name': 'Details', 'value': f"**HQ:** {'True' if is_hq else 'False'}\n**World:** {world_name}", 'inline': True},
        {'name': 'Prices', 'value': f"**Buying:** `${listing_price_without_tax:,.2f}`\n**Selling:** `${price_without_tax:,.2f}`\n**Profit:** `${profit_without_tax:,.2f}`", 'inline': True},
        {'name': 'Prices (Tax)', 'value': f"**Buying:** `${listing_price_with_tax:,.2f}`\n**Selling:** `${price_with_tax:,.2f}`\n**Profit:** `${profit_with_tax:,.2f}`", 'inline': True},
        {'name': 'Taxes', 'value': f"**Buying Tax:** `${tax_buying:,.2f}`\n**Selling Tax:** `${tax_selling:,.2f}`", 'inline': True},
        {'name': 'Sales', 'value': f"**Home Sales Count:** `{int(round(home_sales_count))}`\n**DC Sales Count:** `{int(round(dc_sales_count))}`", 'inline': True}
    ]
    
    # Find the correct webhook URL for the world
    webhook_url = ALERT_CONFIG['profitable_item']['webhook_url']  # Default webhook
    for server in SERVER_DICT:
        if server['Name'] == world_name:
            webhook_url = server['Webhook']
            break
    
    role_id = ALERT_CONFIG['profitable_item']['role_id']
    
    title = f'📈 {world_name} Item Alert!'
    description = ''
    color = 0x00FF00

    send_alert(title, description, color, fields, role_id, webhook_url, item_icon_url)


def send_specific_item_alert(item_name, item_id, is_hq, listing_price, world_name):
    fields = [
        {'name': 'Item', 'value': f"[**{item_name}**](https://universalis.app/market/{item_id})\n*ID:* `{item_id}`", 'inline': False},
        {'name': 'Details', 'value': f"**HQ:** {'Yes' if is_hq else 'No'}\n**World:** {world_name}", 'inline': False},
        {'name': 'Prices', 'value': f"**Current Price:** `${listing_price:.2f}`\n**Target Price:** `${SPECIFIC_ITEM_IDS.get(item_id, 'N/A'):.2f}`", 'inline': False},
        {'name': 'Link', 'value': f'[🔗 View Listing](https://universalis.app/market/{item_id})', 'inline': False}
    ]
    
    # Find the correct webhook URL for the world
    webhook_url = ALERT_CONFIG['specific_item']['webhook_url']  # Default webhook
    for server in SERVER_DICT:
        if server['Name'] == world_name:
            webhook_url = server['Webhook']
            break
    
    role_id = ALERT_CONFIG['specific_item']['role_id']
    
    send_alert(f'📈 {world_name} Specific Item Alert!', 'A specific item is being sold at or below the target price!', 0xFF4500, fields, role_id, webhook_url)

def send_undercut_alert(item_name, item_id, listing_price, world_name, retainer_name, retainer_id, seller_id):
    fields = [
        {'name': 'Item', 'value': f"[**{item_name}**](https://universalis.app/market/{item_id})\n*ID:* `{item_id}`", 'inline': False},
        {'name': 'Price', 'value': f"**Current Price:** `${listing_price:.2f}`", 'inline': False},
        {'name': 'World', 'value': f"**World:** {world_name}", 'inline': False},
        {'name': 'Retainer', 'value': f"**Name:** {retainer_name}\n**ID:** `{retainer_id}`", 'inline': False},
        {'name': 'Seller', 'value': f"**ID:** `{seller_id}`", 'inline': False},
        {'name': 'Link', 'value': f'[🔗 View Listing](https://universalis.app/market/{item_id})', 'inline': False}
    ]
    
    # Find the correct webhook URL for the world
    webhook_url = ALERT_CONFIG['undercut']['webhook_url']  # Default webhook
    for server in SERVER_DICT:
        if server['Name'] == world_name:
            webhook_url = server['Webhook']
            break
    
    role_id = ALERT_CONFIG['undercut']['role_id']
    
    send_alert(f'⚠️ {world_name} Undercut Alert!', 'A listing has been detected as the lowest price among retainers!', 0xFF0000, fields, role_id, webhook_url)


def check_specific_items(collected_listings):
    for listing in collected_listings:
        item_id = listing['item']
        if item_id in SPECIFIC_ITEM_IDS:
            target_price = SPECIFIC_ITEM_IDS[item_id]
            if listing['pricePerUnit'] <= target_price:
                world_name = next((server['Name'] for server in SERVER_DICT if server['ID'] == listing['world']), 'Unknown World')
                send_specific_item_alert(listing['itemName'], item_id, listing['hq'], listing['pricePerUnit'], world_name)


def get_item_current_prices(world_dc_region, item_ids):
    url = f"{BASE_URL}/{world_dc_region}/" + ','.join(map(str, item_ids))
    params = {
        'entriesToReturn': 5,
        'statsWithin': 604800,
        'entriesWithin': 604800,
        'entriesUntil': int(time.time()),
        'minSalePrice': 0,
        'maxSalePrice': 2147483647
    }
    
    try:
        response = requests.get(url=url, params=params)
        response.raise_for_status()
        data = response.json()
        
        results = {}

        for item_id in item_ids:
            item_data = data 
            
            results[item_id] = {
                "lowest_nq_price": item_data.get("minPriceNQ", 0),
                "lowest_hq_price": item_data.get("minPriceHQ", 0),
                "nq_sales": item_data.get("nqSaleVelocity", 0),
                "hq_sales": item_data.get("hqSaleVelocity", 0),
                "hq_cheapest_world": min(
                    (x for x in item_data.get("listings", []) if x.get("hq", False)),
                    key=lambda x: x.get("pricePerUnit", float('inf')),
                    default={}
                ).get("retainerCity", 0),
                "nq_cheapest_world": min(
                    (x for x in item_data.get("listings", []) if not x.get("hq", False)),
                    key=lambda x: x.get("pricePerUnit", float('inf')),
                    default={}
                ).get("retainerCity", 0),
                "units_for_sale": item_data.get("unitsForSale", 0),
                "units_sold": item_data.get("unitsSold", 0)
            }
        return results

    except requests.RequestException as e:
        print(f"Error: {str(e)}")
        return {}


def get_item_average_prices(item_ids, world_dc_region):
    item_ids_str = ','.join(map(str, item_ids))
    url = f"{BASE_URL}/aggregated/{world_dc_region}/{item_ids_str}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json().get('results', [])

        results = {}
        for item in data:
            item_id = item.get('itemId')
            if not item_id:
                continue

            nq = item.get('nq', {})
            hq = item.get('hq', {})

            results[item_id] = {
                # Normal Quality (NQ) data
                "lowest_nq_price_world": nq.get('minListing', {}).get('world', {}).get('price', 0),
                "lowest_nq_world_id": nq.get('minListing', {}).get('dc', {}).get('worldId', 0),
                
                "lowest_nq_price_dc": nq.get('minListing', {}).get('dc', {}).get('price', 0),
                "nq_cheapest_world_id_dc": nq.get('minListing', {}).get('dc', {}).get('worldId', 0),

                "lowest_nq_price_region": nq.get('minListing', {}).get('region', {}).get('price', 0),
                "nq_cheapest_world_id_region": nq.get('minListing', {}).get('region', {}).get('worldId', 0),

                "nq_sales_world": nq.get('dailySaleVelocity', {}).get('world', {}).get('quantity', 0),
                "nq_sales_dc": nq.get('dailySaleVelocity', {}).get('dc', {}).get('quantity', 0),
                "nq_sales_region": nq.get('dailySaleVelocity', {}).get('region', {}).get('quantity', 0),

                "average_nq_price_world": nq.get('averageSalePrice', {}).get('world', {}).get('price', 0),
                "average_nq_price_dc": nq.get('averageSalePrice', {}).get('dc', {}).get('price', 0),
                "average_nq_price_region": nq.get('averageSalePrice', {}).get('region', {}).get('price', 0),

                # High Quality (HQ) data
                "lowest_hq_price_world": hq.get('minListing', {}).get('world', {}).get('price', 0),
                "lowest_hq_world_id": hq.get('minListing', {}).get('dc', {}).get('worldId', 0),

                "lowest_hq_price_dc": hq.get('minListing', {}).get('dc', {}).get('price', 0),
                "hq_cheapest_world_id_dc": hq.get('minListing', {}).get('dc', {}).get('worldId', 0),

                "lowest_hq_price_region": hq.get('minListing', {}).get('region', {}).get('price', 0),
                "hq_cheapest_world_id_region": hq.get('minListing', {}).get('region', {}).get('worldId', 0),

                "hq_sales_world": hq.get('dailySaleVelocity', {}).get('world', {}).get('quantity', 0),
                "hq_sales_dc": hq.get('dailySaleVelocity', {}).get('dc', {}).get('quantity', 0),
                "hq_sales_region": hq.get('dailySaleVelocity', {}).get('region', {}).get('quantity', 0),

                "average_hq_price_world": hq.get('averageSalePrice', {}).get('world', {}).get('price', 0),
                "average_hq_price_dc": hq.get('averageSalePrice', {}).get('dc', {}).get('price', 0),
                "average_hq_price_region": hq.get('averageSalePrice', {}).get('region', {}).get('price', 0)
            }
        
        return results

    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return {}

    
def check_retainer_listings_for_undercut(collected_listings):
    for listing in collected_listings:
        retainer_name = listing.get('retainerName')
        if retainer_name in RETAINER_NAMES:
            retainer_id = RETAINER_NAMES[retainer_name]
            item_id = listing['item']
            world_name = next((server['Name'] for server in SERVER_DICT if server['ID'] == listing['world']), 'Unknown World')
            
            item_data = get_item_current_prices(DATA_CENTER, [item_id], listing.get('hq', False))
            lowest_price = item_data.get(item_id, {}).get('nq_price' if not listing.get('hq', False) else 'hq_price', float('inf'))
            
            if listing['pricePerUnit'] > lowest_price:
                send_undercut_alert(
                    item_name=item_lookup.get(item_id, 'Unknown Item'),
                    item_id=item_id,
                    listing_price=listing['pricePerUnit'],
                    world_name=world_name,
                    retainer_name=retainer_name,
                    retainer_id=retainer_id,
                    seller_id=listing['sellerID']
                )
                print(f"Undercut Detected: {item_lookup.get(item_id, 'Unknown Item')} - Your Retainer: {retainer_name} - Your Price: {listing['pricePerUnit']} - Lowest Price: {lowest_price}")

def average_of_lowest_three(prices):
    sorted_prices = sorted(prices)
    lowest_three = sorted_prices[:3]
    return sum(lowest_three) / len(lowest_three) if lowest_three else 0

def convert_to_dict(prices_list):
    prices_dict = {}
    for item in prices_list:
        item_id = item.get('item_id')
        if item_id:
            prices_dict[item_id] = item
    return prices_dict

async def get_item_icon_url(item_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://xivapi.com/Item/{item_id}") as response:
            data = await response.json()
            return f"https://xivapi.com/{data['Icon']}"

async def handle_messages(websocket):
    global collected_listings
    async for message in websocket:
        data = bson.loads(message)
        if data.get('event') == 'listings/add':
            collected_listings.extend(format_listings(data))

        if len(collected_listings) >= COLLECT_LIMIT:
            await process_listings()
        await asyncio.sleep(LOOP_DELAY)

def format_listings(data):
    timestamp = datetime.now().isoformat()
    return [{
        'timestamp': timestamp,
        'item': data.get('item'),
        'itemName': item_lookup.get(data.get('item'), 'Unknown Item'),
        'world': data.get('world'),
        'creatorID': l.get('creatorID'),
        'creatorName': l.get('creatorName'),
        'hq': l.get('hq', False),
        'isCrafted': l.get('isCrafted'),
        'lastReviewTime': l.get('lastReviewTime'),
        'listingID': l.get('listingID'),
        'pricePerUnit': l.get('pricePerUnit'),
        'quantity': l.get('quantity'),
        'retainerCity': l.get('retainerCity'),
        'retainerID': l.get('retainerID'),
        'retainerName': l.get('retainerName'),
        'sellerID': l.get('sellerID'),
        'stainID': l.get('stainID'),
        'total': l.get('total')
    } for l in data.get('listings', [])]

async def process_listings():
    item_ids = list(set(l['item'] for l in collected_listings))
    current_prices = get_item_average_prices(item_ids, "Raiden")
    processed = set()

    for item in collected_listings:
        if item['item'] not in processed:
            processed.add(item['item'])
            if item['item'] in current_prices:
                await evaluate_and_send_alert(item, current_prices[item['item']])

    collected_listings.clear()

async def evaluate_and_send_alert(item, prices):
    is_hq = item['hq']
    dc_price, home_price = get_price(prices, is_hq)
    profit_no_tax, profit_w_tax = get_profit(dc_price, home_price)

    if valid_sale(profit_w_tax, home_price, prices, is_hq):
        print(f"Item Name: {item['itemName']}")
        print(f"Item ID: {item['item']}")
        print(f"High Quality: {is_hq}")
        print(f"Data Center Price: {dc_price}")
        print(f"Data Center Price with 5% Tax: {dc_price * 1.05}")
        print(f"Home Price: {home_price}")
        print(f"Home Price with 5% Discount: {home_price * 0.95}")
        print(f"Profit without Tax: {profit_no_tax}")
        print(f"Profit with Tax: {profit_w_tax}")
        print(f"Sales World: {prices['hq_sales_world'] if is_hq else prices['nq_sales_world']}")
        print(f"Sales Data Center: {prices['hq_sales_dc'] if is_hq else prices['nq_sales_dc']}")
        print(f"World Name: {get_world_name(prices, is_hq)}")
        print(f"Data Center Tax Amount: {dc_price * 0.05}")
        print(f"Home Tax Amount: {home_price * 0.05}")
        
        try:
            # Fetch the item's icon URL using the new API
            item_icon_url = await get_item_icon_url(item['item'])
        except Exception as e:
            print(f"Error fetching icon URL for item {item['item']}: {e}")
            # Fallback to a default icon or handle as needed
            item_icon_url = "https://xivapi.com/placeholder_icon.png"

        await send_discord_alert(
            item_name=item['itemName'], 
            item_id=item['item'], 
            is_hq=is_hq,
            listing_price_without_tax=dc_price, 
            listing_price_with_tax=dc_price * 1.05, 
            price_without_tax=home_price, 
            price_with_tax=home_price * 0.95,
            profit_without_tax=profit_no_tax, 
            profit_with_tax=profit_w_tax,
            home_sales_count=prices["hq_sales_world"] if is_hq else prices["nq_sales_world"],
            dc_sales_count=prices["hq_sales_dc"] if is_hq else prices["nq_sales_dc"],
            world_name=get_world_name(prices, is_hq),
            tax_buying=dc_price * 0.05, 
            tax_selling=home_price * 0.05,
            item_icon_url=item_icon_url
        )


def get_price(prices, is_hq):
    return (
        prices["lowest_hq_price_dc"] if is_hq else prices["lowest_nq_price_dc"],
        prices["lowest_hq_price_world"] if is_hq else prices["lowest_nq_price_world"]
    )

def get_profit(dc_price, home_price):
    return home_price - dc_price, (home_price * 0.95) - (dc_price * 1.05)

def valid_sale(profit_w_tax, home_price, prices, is_hq):
    sales_count = prices["hq_sales_world" if is_hq else "nq_sales_world"]
    
    # Normal condition: minimum sales count and minimum profit
    normal_valid = (
        sales_count >= MIN_SALES_COUNT and
        profit_w_tax >= MIN_PROFIT_AMOUNT 
    )
    
    # High volume condition: high volume sales count and lower profit threshold
    high_volume_valid = (
        sales_count >= HIGH_VOLUME_THRESHOLD and
        profit_w_tax >= MIN_VOLUME_PROFIT_AMOUNT
    )
    
    # Return True if either condition is met
    return normal_valid or high_volume_valid

def get_world_name(prices, is_hq):
    world_id_key = "lowest_hq_world_id" if is_hq else "lowest_nq_world_id"
    world_id = prices.get(world_id_key, 0)
    return next((server['Name'] for server in SERVER_DICT if server['ID'] == world_id), 'Unknown World')


async def main():
    while True:
        try:
            async with websockets.connect(WEBSOCKET_URL, ping_interval=None, ping_timeout=None, close_timeout=40) as websocket:
                for server in SERVER_DICT:
                    world_id = server['ID']
                    subscribe_msg = bson.dumps({"event": "subscribe", "channel": f"listings/add{{world={world_id}}}"})
                    await websocket.send(subscribe_msg)
                    print(f"Subscribed to listings/add channel for world {server['Name']} ({world_id}).")

                async def ping_server():
                    while True:
                        try:
                            await websocket.ping()
                            await asyncio.sleep(30)  
                        except Exception as e:
                            print(f"Ping failed: {e}")
                            break
                ping_task = asyncio.create_task(ping_server())
                await handle_messages(websocket)
                await ping_task

        except websockets.ConnectionClosedError as e:
            print(f"Connection closed with error: {e}. Retrying in 1 seconds...")
            await asyncio.sleep(1)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            break

if __name__ == "__main__":
    asyncio.run(main())