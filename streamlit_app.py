import streamlit as st
import json
import pandas as pd
import time
import os
import subprocess
import requests
import pyotp
import sys
from streamlit_lightweight_charts import renderLightweightCharts

# ================= STREAMLIT CONFIG =================
st.set_page_config(layout="wide", page_title="AngelOne Intelligence Hub")

# UI Styling
st.markdown("""
<style>
    .main { background-color: #0e1117; color: #d1d4dc; }
    .stMetric { background-color: #161b22; padding: 10px; border-radius: 8px; border: 1px solid #30363d; }
    [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
    h1 { font-size: 1.8rem !important; }
</style>
""", unsafe_allow_html=True)

# ================= CONFIG =================
DATA_FILE = "market_data.json"
STOP_FILE = "stop_backend.txt"
BACKEND_SCRIPT = "backend.py"

# ================= HELPERS =================
def is_backend_running():
    if not os.path.exists(DATA_FILE):
        return False
    mtime = os.path.getmtime(DATA_FILE)
    # If file updated in last 10 seconds, backend is active
    return (time.time() - mtime) < 10

# ================= UI =================
# ================= UI =================
st.title("🛡️ AngelOne Intelligence Hub")

# Sidebar Menu for Navigation
with st.sidebar:
    st.header(" NAVIGATION")
    menu = st.radio("Go to", ["📊 Dashboard", "🔐 Login Portal", "📈 Flattrade Login"])
    st.divider()

if menu == "📊 Dashboard":
    with st.sidebar:
        st.header("Systems Control")
        
        # Selection UI
        st.subheader("Instrument Selection")
        exchange_mapping = {
            "NSE": 1,
            "NFO": 2,
            "MCX": 5,
            "BSE": 3,
            "CDS": 4
        }
        selected_exchange_name = st.selectbox("Exchange", options=list(exchange_mapping.keys()), index=2) # Default MCX
        exchange_type = exchange_mapping[selected_exchange_name]
        token_id = st.text_input("Token ID", value="472789")
        
        st.divider()
        
        running = is_backend_running()
        
        if not running:
            if st.button("🚀 Start Backend System", type="primary"):
                if os.path.exists(STOP_FILE):
                    os.remove(STOP_FILE)
                # Kill existing ones just in case (Windows only)
                if os.name == 'nt':
                     try:
                         subprocess.run(["taskkill", "/F", "/IM", "python.exe"], capture_output=True)
                     except:
                         pass
                time.sleep(1)
                # Run backend with arguments
                args = [sys.executable, BACKEND_SCRIPT, str(exchange_type), token_id]
                subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
                st.success(f"Backend starting for {selected_exchange_name}:{token_id}...")
                time.sleep(2)
                st.rerun()
        else:
            if st.button("🛑 Stop Backend System"):
                with open(STOP_FILE, "w") as f:
                    f.write("stop")
                st.warning("Stop signal sent.")
                time.sleep(2)
                st.rerun()
                
        st.write(f"**System Status:** {'🟢 ONLINE' if running else '🔴 OFFLINE'}")
        
        if st.button("🗑️ Reset Data"):
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            st.rerun()

    # Layout
    col1, col2 = st.columns(2)
    ltp_metric = col1.empty()
    vwma_metric = col2.empty()
    chart_placeholder = st.empty()

    # Data Refresh
    if running or os.path.exists(DATA_FILE):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                
                ltp = data.get("ltp", 0.0)
                ohlc = data.get("ohlc", [])
                vwma = data.get("vwma", [])
                
                latest_vwma = vwma[-1]['value'] if vwma else 0.0
                
                ltp_metric.metric("Current Price", f"₹{ltp:,.2f}")
                vwma_metric.metric("VWMA (20)", f"₹{latest_vwma:,.2f}")
                
                if ohlc:
                    chart_options = {
                        "height": 500,
                        "layout": {
                            "background": {"type": 'solid', "color": '#0e1117'},
                            "textColor": '#d1d4dc',
                            "fontSize": 10
                        },
                        "grid": {"vertLines": {"color": "#242733"}, "horzLines": {"color": "#242733"}},
                        "timeScale": {
                            "timeVisible": True,
                            "secondsVisible": True,
                            "borderColor": '#485c7b',
                        },
                    }
                    series = [{"type": 'Candlestick', "data": ohlc, "options": {"upColor": '#26a69a', "downColor": '#ef5350'}}]
                    if vwma:
                        series.append({"type": 'Line', "data": vwma, "options": {"color": '#2196f3', "lineWidth": 2, "title": 'VWMA'}})
                    
                    with chart_placeholder:
                        renderLightweightCharts([{"chart": chart_options, "series": series}], 'decoupled_chart')
                else:
                    chart_placeholder.info("Connected. Waiting for the first bar (5 ticks)...")
            else:
                chart_placeholder.info("Backend started. Waiting for data file...")
        except:
            pass
            
        time.sleep(1)
        st.rerun()
    else:
        chart_placeholder.info("System Offline. Start backend in sidebar or login via 'Login Portal'.")

elif menu == "🔐 Login Portal": # Login Portal
    st.header("🔐 AngelOne Login")
    
    # Try to load existing data
    existing_auth = {}
    if os.path.exists("auth.json"):
        with open("auth.json", "r") as f:
            existing_auth = json.load(f)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            c_code = st.text_input("Client Code", value=existing_auth.get("client_code", "K135836"))
            pwd = st.text_input("Password", type="password", value="1997")
            api_k = st.text_input("API Key", value=existing_auth.get("api_key", "LZnKUxh1"))
            totp_s = st.text_input("TOTP Secret", value="YGDC6I7VDV7KJSIELCN626FKBY")
            
            submit = st.form_submit_button("LOGIN", type="primary", use_container_width=True)
            
            if submit:
                try:
                    totp = pyotp.TOTP(totp_s)
                    current_code = totp.now()
                    url = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"
                    
                    payload = {
                        "clientcode": c_code,
                        "password": pwd,
                        "totp": current_code,
                        "state": "12345"
                    }
                    
                    headers = {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'X-UserType': 'USER',
                        'X-SourceID': 'WEB',
                        'X-ClientLocalIP': '127.0.0.1',
                        'X-ClientPublicIP': '127.0.0.1',
                        'X-MACAddress': 'MAC_ADDRESS',
                        'X-PrivateKey': api_k
                    }
                    
                    with st.spinner("Logging in..."):
                        response = requests.post(url, headers=headers, data=json.dumps(payload))
                    
                    if response.status_code == 200:
                        resp_json = response.json()
                        if resp_json.get('status'):
                            jwt_token = "Bearer " + resp_json['data']['jwtToken']
                            save_data = {
                                "Authorization": jwt_token,
                                "api_key": api_k,
                                "feedtoken": resp_json['data']['feedToken'],
                                "client_code": c_code
                            }
                            with open("auth.json", "w") as f:
                                json.dump(save_data, f, indent=4)
                            st.success("Login Successful!")
                            st.balloons()
                        else:
                            st.error(f"Login Failed: {resp_json.get('message')}")
                    else:
                        st.error(f"HTTP Error {response.status_code}")
                except Exception as e:
                    st.error(f"Error: {e}")

else: # Flattrade Login
    st.header("📈 Flattrade Login")
    
    API_KEY = "b5768d873c474155a3d09d56a50f5314"
    API_SECRET = "2025.3bb14ae6afd04844b10e338a6f388a9c7416205cb6990c69"
    AUTH_URL = f"https://auth.flattrade.in/?app_key={API_KEY}"
    TOKEN_URL = "https://authapi.flattrade.in/trade/apitoken"

    st.info("Follow these steps to authenticate with Flattrade:")
    st.markdown(f"1. Open the [Flattrade Auth URL]({AUTH_URL}) in your browser.")
    st.markdown("2. Log in and authorize the application.")
    st.markdown("3. Copy the `request_code` from the redirect URL (it looks like `?code=...`).")
    
    st.link_button("Open Flattrade Auth", AUTH_URL, use_container_width=True)
    
    with st.form("flattrade_login_form"):
        request_code = st.text_input("Enter request_code")
        submit_flat = st.form_submit_button("GENERATE TOKEN", type="primary", use_container_width=True)
        
        if submit_flat:
            if not request_code:
                st.warning("Please enter the request_code.")
            else:
                try:
                    import hashlib
                    hash_value = hashlib.sha256((API_KEY + request_code + API_SECRET).encode()).hexdigest()

                    payload = {
                        "api_key": API_KEY,
                        "request_code": request_code,
                        "api_secret": hash_value
                    }

                    with st.spinner("Generating access token..."):
                        response = requests.post(TOKEN_URL, json=payload)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("stat") == "Ok":
                            st.success("Access token generated successfully!")
                            token = data['token']
                            st.code(token, language="text")
                            
                            # Save to JSON
                            flat_auth = {
                                "api_key": API_KEY,
                                "token": token
                            }
                            with open("flattrade_auth.json", "w") as f:
                                json.dump(flat_auth, f, indent=4)
                            st.info("Token saved to `flattrade_auth.json`")
                        else:
                            st.error(f"Error: {data.get('emsg', 'Unknown error')}")
                    else:
                        st.error(f"Failed to generate access token. HTTP Status: {response.status_code}")
                except Exception as e:
                    st.error(f"An error occurred: {e}")
