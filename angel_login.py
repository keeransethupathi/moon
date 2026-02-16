import requests
import json
import pyotp

# Replace with your actual TOTP secret from AngelOne
TOTP_SECRET = "YGDC6I7VDV7KJSIELCN626FKBY"
api_key = 'LZnKUxh1'
totp = pyotp.TOTP(TOTP_SECRET)
current_code = totp.now()
url = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"

payload = {
    "clientcode": "K135836",
    "password": "1997",
    "totp": current_code,
    "state": "12345"
}

headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-UserType': 'USER',
    'X-SourceID': 'WEB',
    'X-ClientLocalIP': 'CLIENT_LOCAL_IP',
    'X-ClientPublicIP': 'CLIENT_PUBLIC_IP',
    'X-MACAddress': 'MAC_ADDRESS',
    'X-PrivateKey': api_key
}

print("Attempting login to AngelOne...")
response = requests.post(url, headers=headers, data=json.dumps(payload))

if response.status_code == 200:
    resp_json = response.json()
    if resp_json.get('status'):
        Authorization = "Bearer " + resp_json['data']['jwtToken']
        save_data = {
            "Authorization": Authorization,
            "api_key": api_key,
            "feedtoken": resp_json['data']['feedToken'],
            "client_code": "K135836"
        }

        # === Save to auth.json ===
        with open("auth.json", "w") as f:
            json.dump(save_data, f, indent=4)

        print("Login successful! Saved Authorization token and api_key to auth.json")
    else:
        print(f"Login failed: {resp_json.get('message')}")
else:
    print(f"HTTP Error {response.status_code}: {response.text}")
