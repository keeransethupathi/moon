import requests
import json

url = "https://piconnect.flattrade.in/PiConnectTP/PlaceOrder"

# Load jkey from flattrade_auth.json
try:
    with open('flattrade_auth.json', 'r') as f:
        auth_data = json.load(f)
        jkey = auth_data.get('token')
        if not jkey:
            raise ValueError("Token not found in flattrade_auth.json")
except FileNotFoundError:
    print("Error: flattrade_auth.json not found.")
    exit(1)
except json.JSONDecodeError:
    print("Error: Failed to decode flattrade_auth.json.")
    exit(1)
except Exception as e:
    print(f"Error loading auth data: {e}")
    exit(1)

order_data = {
    "uid": "FZ23457",
    "actid": "FZ23457",
    "exch": "NFO",
    "tsym": "NIFTY24FEB26C26000",
    "qty": "65",
    "prd": "M",            # NRML
    "trantype": "S",       # BUY
    "prctyp": "MKT",       # LIMIT
    "prc": "0",         # Order price
    "blprc": "0",       # ✅ REQUIRED
    "ret": "DAY"
}

body = (
    "jData=" + json.dumps(order_data, separators=(",", ":")) +
    "&jKey=" + jkey
)

headers = {
    "Content-Type": "application/x-www-form-urlencoded"
}

response = requests.post(url, data=body, headers=headers)

print("HTTP:", response.status_code)
print("Response:", response.text)

