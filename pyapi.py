import requests
from PIL import Image
from io import BytesIO

# Fetch JSON data from the API
response = requests.get("https://xivapi.com/Item/1675")
data = response.json()

# Extract relevant data
level_item = data['LevelItem']
name_en = data['Name_en']
icon_url = f"https://xivapi.com/{data['Icon']}"

# Print item details
print(f"I.Lv {level_item} {name_en}")

# Download and display the image
response = requests.get(icon_url)
img = Image.open(BytesIO(response.content))
img.show()  # This will open the image in the default image viewer
