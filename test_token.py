import requests
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = os.getenv("VK_GROUP_ID")
V = "5.199"

def test(method, params):
    resp = requests.get(f"https://api.vk.com/method/{method}", params={**params, "access_token": TOKEN, "v": V})
    data = resp.json()
    if "error" in data:
        print(f"  ОШИБКА [{method}]: {data['error']['error_code']} — {data['error']['error_msg']}")
    else:
        print(f"  OK [{method}]: получено данных — {len(data.get('response', data['response'] if 'response' in data else []))}")

print(f"Токен: {TOKEN[:20]}...")
print(f"Group ID: {GROUP_ID}\n")

print("1. video.get:")
test("video.get", {"owner_id": f"-{GROUP_ID}", "count": 1})

print("2. stats.get:")
test("stats.get", {"group_id": GROUP_ID, "interval": "month"})

print("3. groups.getById:")
test("groups.getById", {"group_id": GROUP_ID})
