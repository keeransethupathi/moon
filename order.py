import requests
import json

def place_flattrade_order(tsym, qty, exch, trantype):
    """
    Places an order on Flattrade.
    tsym: Trading Symbol
    qty: Quantity
    exch: Exchange
    trantype: 'B' for Buy, 'S' for Sell
    """
    url = "https://piconnect.flattrade.in/PiConnectTP/PlaceOrder"

    # Load jkey and credentials
    try:
        with open('flattrade_auth.json', 'r') as f:
            auth_data = json.load(f)
            jkey = auth_data.get('token')
            if not jkey:
                return {"stat": "Not Ok", "emsg": "Token not found in flattrade_auth.json"}
        
        # We need the uid/actid from credentials.json
        with open('credentials.json', 'r') as f:
            creds = json.load(f)
            uid = creds.get('username')
    except Exception as e:
        return {"stat": "Not Ok", "emsg": f"Auth error: {str(e)}"}

    order_data = {
        "uid": uid,
        "actid": uid,
        "exch": exch,
        "tsym": tsym,
        "qty": str(qty),
        "prd": "M",            # Margin/Intraday
        "trantype": trantype,  # 'B' or 'S'
        "prctyp": "MKT",       # Market
        "prc": "0",
        "blprc": "0",
        "ret": "DAY"
    }

    body = (
        "jData=" + json.dumps(order_data, separators=(",", ":")) +
        "&jKey=" + jkey
    )

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        response = requests.post(url, data=body, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            return {"stat": "Not Ok", "emsg": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"stat": "Not Ok", "emsg": str(e)}

if __name__ == "__main__":
    # Test order
    print("Testing order placement...")
    # res = place_flattrade_order("NIFTY24FEB26C26000", "65", "NFO", "S")
    # print(res)

