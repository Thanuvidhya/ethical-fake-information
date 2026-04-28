import requests

API_KEY = "sk-8a7b409e3dd64d7480f6aa5d14edf490"
URL = "https://api.deepseek.com/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "user", "content": "Hello, test message"}
    ]
}

try:
    r = requests.post(URL, json=payload, headers=headers)
    print(f"Status Code: {r.status_code}")
    print(f"Response: {r.json()}")
except Exception as e:
    print(f"Error: {e}")