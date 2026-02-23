import streamlit as st
import json
import pandas as pd
import numpy as np
import time
import os
import requests
import pyotp
import sys
import threading
import traceback
import logging
import re
from datetime import datetime
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from streamlit_lightweight_charts import renderLightweightCharts
from order import place_flattrade_order

# ================= STREAMLIT CONFIG =================
st.set_page_config(layout="wide", page_title="AngelOne Intelligence Hub")

def safe_get_secret(key, default=None):
    """Safely get a secret from streamlit secrets or environment variables."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)

@st.fragment(run_every="1s")
def display_dashboard_fragment(token_id, exchange_type, exchange_mapping):
    # Data Sync
    DATA_FILE = "market_data.json"
    data = {}
    data_found = False
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            
            last_update = data.get("last_update", 0)
            if time.time() - last_update < 10:
                st.session_state.backend_running = True
                st.session_state.ohlc_data = data.get("ohlc", [])
                st.session_state.vwma_data = data.get("vwma", [])
                st.session_state.current_ltp = float(data.get("ltp", 0.0))
                st.session_state.last_data_ts = last_update
                data_found = True
            else:
                st.session_state.backend_running = False
    except Exception as fe:
        print(f"Local Sync Error: {fe}")

    # Layout
    col1, col2 = st.columns(2)
    ltp = st.session_state.current_ltp
    ohlc = st.session_state.ohlc_data
    vwma = st.session_state.vwma_data
    
    latest_vwma = vwma[-1]['value'] if vwma else 0.0
    col1.metric("Current Price", f"₹{ltp:,.2f}")
    col2.metric("VWMA (20)", f"₹{latest_vwma:,.2f}")
    
    if ohlc:
        chart_options = {
            "height": 500,
            "layout": {
                "background": {"type": 'solid', "color": '#0e1117'},
                "textColor": '#d1d4dc',
                "fontSize": 10
            },
            "grid": {"vertLines": {"color": "#242733"}, "horzLines": {"color": "#242733"}},
            "timeScale": {"timeVisible": True, "secondsVisible": True, "borderColor": '#485c7b'},
        }
        series = [{"type": 'Candlestick', "data": ohlc, "options": {"upColor": '#26a69a', "downColor": '#ef5350'}}]
        if vwma:
            series.append({"type": 'Line', "data": vwma, "options": {"color": '#2196f3', "lineWidth": 2, "title": 'VWMA'}})
        
        # Rendering directly in the fragment (without .empty()) reduces flicker
        renderLightweightCharts([{"chart": chart_options, "series": series}], 'integrated_chart')
    else:
        st.info("Connected. Waiting for the first bar (5 ticks)...")
            
    # ================= AUTOMATED TRADING LOGIC =================
    if st.session_state.auto_trading_active:
        try:
            # Re-read metrics for logic
            vwma_val = vwma[-1]['value'] if vwma else None
            if ltp and vwma_val:
                tsym = st.session_state.get('trade_tsym')
                num_lots = st.session_state.get('trade_num_lots', 1)
                lot_size = st.session_state.get('trade_lot_size', 1)
                qty = num_lots * lot_size
                exch = st.session_state.get('trade_exch')
                
                if tsym and qty and exch:
                    side = None
                    if ltp > vwma_val and st.session_state.last_order_side != 'BUY':
                        side = 'B'
                        side_label = 'BUY'
                    elif ltp < vwma_val and st.session_state.last_order_side != 'SELL':
                        side = 'S'
                        side_label = 'SELL'
                    
                    if side:
                        log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Attempting {side_label} for {tsym} @ {ltp} (VWMA: {vwma_val:.2f})"
                        st.session_state.trading_logs.append(log_msg)
                        response = place_flattrade_order(tsym, qty, exch, side)
                        
                        if response.get('stat') == 'Ok':
                            st.session_state.last_order_side = side_label
                            st.session_state.trading_logs.append(f"✅ {side_label} Order Placed! ID: {response.get('norenordno')}")
                        else:
                            st.session_state.trading_logs.append(f"❌ Order Failed: {response.get('emsg')}")
        except Exception as e:
            st.session_state.trading_logs.append(f"⚠️ Trading logic error: {e}")

    if not data_found:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    offline_data = json.load(f)
                if time.time() - offline_data.get("last_update", 0) < 10:
                    st.info("Live data detected locally. Connecting...")
                    st.session_state.backend_running = True
                    st.rerun()
            except:
                pass
        st.info("System Offline. Start backend in sidebar or ensure it's running.")

# ================= UI Styling =================

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

# ================= STATE MANAGEMENT =================
if 'ohlc_data' not in st.session_state:
    st.session_state.ohlc_data = []
if 'vwma_data' not in st.session_state:
    st.session_state.vwma_data = []
if 'current_ltp' not in st.session_state:
    st.session_state.current_ltp = 0.0
if 'backend_running' not in st.session_state:
    st.session_state.backend_running = False
if 'last_error' not in st.session_state:
    st.session_state.last_error = None
if 'auto_trading_active' not in st.session_state:
    st.session_state.auto_trading_active = False
if 'trading_logs' not in st.session_state:
    st.session_state.trading_logs = []
if 'last_order_side' not in st.session_state:
    st.session_state.last_order_side = None

# Silence ScriptRunContext and other warnings
logging.getLogger("streamlit.runtime.scriptrunner").setLevel(logging.ERROR)
logging.getLogger("smartWebSocketV2").setLevel(logging.ERROR)

# ================= UI =================
st.title("🛡️ AngelOne Intelligence Hub")

# Sidebar Menu for Navigation
with st.sidebar:
    st.header(" NAVIGATION")
    menu = st.radio("Go to", ["📊 Dashboard", "🔐 Login Portal", "📈 Flattrade Login", "📦 Order Portal"])
    st.divider()

if menu == "📊 Dashboard":
    with st.sidebar:
        st.header("Systems Control")
        
        # Selection UI
        exchange_mapping = {"NSE": 1, "NFO": 2, "MCX": 5, "BSE": 3, "CDS": 4}
        selected_exchange_name = st.selectbox("Exchange", options=list(exchange_mapping.keys()), index=2) # Default MCX
        exchange_type = exchange_mapping[selected_exchange_name]
        token_id = st.text_input("Token ID", value="472789")
        
        st.divider()
        
        if not st.session_state.backend_running:
            if st.button("🚀 Start Backend System", type="primary"):
                if not os.path.exists("auth.json"):
                    st.error("Authentication file `auth.json` not found. Please login via 'Login Portal' first.")
                else:
                    with open("auth.json", "r") as f:
                        auth_data = json.load(f)
                    
                    # Ensure API Key is present (might be in secrets)
                    if "api_key" not in auth_data:
                        auth_data["api_key"] = safe_get_secret("ANGEL_API_KEY")
                    
                    if not auth_data.get("api_key"):
                        st.error("AngelOne API Key not found in auth.json or secrets.")
                    else:
                        # START BACKEND via Subprocess (External Process)
                        # First check if it's already actually online locally
                        is_already_online = False
                        DATA_FILE = "market_data.json"
                        if os.path.exists(DATA_FILE):
                            try:
                                with open(DATA_FILE, "r") as f:
                                    data = json.load(f)
                                if time.time() - data.get("last_update", 0) < 10:
                                    is_already_online = True
                            except:
                                pass
                        
                        if is_already_online:
                            st.warning(f"Backend for {token_id} is already running locally.")
                        else:
                            import subprocess
                            python_exe = sys.executable
                            cmd = [python_exe, "backend.py", str(exchange_type), str(token_id)]
                            
                            # Launch backend.py as a separate process in a new console
                            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
                            st.success(f"System Launching for {selected_exchange_name}:{token_id}...")
                        
                        st.session_state.backend_running = True
                        time.sleep(2)
                        st.rerun()
        else:
            if st.button("🛑 Stop Backend System"):
                # Signal stop via file (backend.py checks for STOP_FILE)
                STOP_FILE = "stop_backend.txt"
                with open(STOP_FILE, "w") as f:
                    f.write("stop")
                st.session_state.backend_running = False
                st.warning("Stop signal sent to backend.")
                time.sleep(1)
                st.rerun()
                
        st.write(f"**System Status:** {'🟢 ONLINE' if st.session_state.backend_running else '🔴 OFFLINE'}")
        
        if st.session_state.last_error:
            st.error(f"Last Error: {st.session_state.last_error}")
            if st.button("Clear Error"):
                st.session_state.last_error = None
                st.rerun()
        
        if st.button("🗑️ Reset Data"):
            st.session_state.ohlc_data = []
            st.session_state.vwma_data = []
            st.session_state.current_ltp = 0.0
            st.rerun()

    # Call Fragment for Live Updates
    display_dashboard_fragment(token_id, exchange_type, exchange_mapping)

elif menu == "🔐 Login Portal": # Login Portal
    st.header("🔐 AngelOne Login")
    
    existing_auth = {}
    if os.path.exists("auth.json"):
        with open("auth.json", "r") as f:
            existing_auth = json.load(f)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            default_c_code = existing_auth.get("client_code") or safe_get_secret("ANGEL_CLIENT_CODE", "K135836")
            default_api_k = existing_auth.get("api_key") or safe_get_secret("ANGEL_API_KEY", "t0bsCNdW")
            default_totp_s = safe_get_secret("ANGEL_TOTP_SECRET", "YGDC6I7VDV7KJSIELCN626FKBY")

            c_code = st.text_input("Client Code", value=default_c_code)
            pwd = st.text_input("Password", type="password", value="1997")
            api_k = st.text_input("API Key", value=default_api_k)
            totp_s = st.text_input("TOTP Secret", value=default_totp_s)
            
            submit = st.form_submit_button("LOGIN", type="primary", use_container_width=True)
            
            if submit:
                try:
                    totp = pyotp.TOTP(totp_s)
                    current_code = totp.now()
                    url = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"
                    
                    payload = {"clientcode": c_code, "password": pwd, "totp": current_code, "state": "12345"}
                    headers = {
                        'Content-Type': 'application/json', 'Accept': 'application/json',
                        'X-UserType': 'USER', 'X-SourceID': 'WEB',
                        'X-ClientLocalIP': '127.0.0.1', 'X-ClientPublicIP': '127.0.0.1',
                        'X-MACAddress': 'MAC_ADDRESS', 'X-PrivateKey': api_k
                    }
                    
                    with st.spinner("Logging in..."):
                        response = requests.post(url, headers=headers, data=json.dumps(payload))
                    
                    if response.status_code == 200:
                        resp_json = response.json()
                        if resp_json.get('status'):
                            jwt_token = "Bearer " + resp_json['data']['jwtToken']
                            save_data = {
                                "Authorization": jwt_token, "api_key": api_k,
                                "feedtoken": resp_json['data']['feedToken'], "client_code": c_code
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

elif menu == "📈 Flattrade Login": # Flattrade Login
    st.header("📈 Flattrade Login")
    
    API_KEY = safe_get_secret("FT_API_KEY", "b5768d873c474155a3d09d56a50f5314")
    API_SECRET = safe_get_secret("FT_API_SECRET", "2025.3bb14ae6afd04844b10e338a6f388a9c7416205cb6990c69")
    AUTH_URL = f"https://auth.flattrade.in/?app_key={API_KEY}"
    TOKEN_URL = "https://authapi.flattrade.in/trade/apitoken"

    # Automated Login Section
    st.subheader("🤖 Automated Login")
    st.info("Click the button below to automatically login and generate your access token.")
    
    if st.button("🚀 Run Auto Login", type="primary", use_container_width=True):
        try:
            from auto_login import auto_login, generate_access_token
            
            with st.status("Running automated login...") as status:
                st.write("Initializing automation...")
                # Try loading from secrets/env first via auto_login's internal logic
                # or check if credentials.json exists as fallback
                has_secrets = safe_get_secret('FT_USERNAME') is not None
                if not os.path.exists('credentials.json') and not has_secrets:
                    st.error("No credentials found. Please set FT environment variables / secrets or provide `credentials.json`.")
                else:
                    st.write("Navigating to login page and filling details...")
                    result = auto_login(headless=True)
                    
                    if result["status"] == "success":
                        request_code = result["code"]
                        st.write(f"Captured request code: {request_code[:10]}...")
                        
                        st.write("Generating final access token...")
                        token = generate_access_token(request_code)
                        
                        if token:
                            st.success("Access token generated successfully!")
                            st.code(token, language="text")
                            
                            flat_auth = {"api_key": API_KEY, "token": token}
                            with open("flattrade_auth.json", "w") as f:
                                json.dump(flat_auth, f, indent=4)
                            st.info("Token saved to `flattrade_auth.json`")
                            status.update(label="Login Successful!", state="complete")
                        else:
                            st.error("Failed to generate access token from code.")
                            status.update(label="Token Generation Failed", state="error")
                    else:
                        st.error(f"Automation failed: {result.get('message')}")
                        status.update(label="Automation Failed", state="error")
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
            st.exception(e)

    st.divider()
    st.subheader("📂 Manual Login (Fallback)")
    st.info("Follow these steps if automated login fails:")
    st.markdown(f"1. Open the [Flattrade Auth URL]({AUTH_URL}) in your browser.")
    st.markdown("2. Log in and authorize the application.")
    st.markdown("3. Copy the `request_code` from the redirect URL (it looks like `?code=...`).")
    
    st.link_button("Open Flattrade Auth", AUTH_URL, use_container_width=True)
    
    with st.form("flattrade_login_form"):
        input_data = st.text_input("Enter request_code or full redirect URL")
        submit_flat = st.form_submit_button("GENERATE TOKEN (MANUAL)", use_container_width=True)
        
        if submit_flat:
            if not input_data:
                st.warning("Please enter the request_code or URL.")
            else:
                try:
                    # Use regex to extract code if input is a URL
                    code_match = re.search(r"[?&]code=([^&#]+)", input_data)
                    request_code = code_match.group(1) if code_match else input_data
                    
                    import hashlib
                    hash_value = hashlib.sha256((API_KEY + request_code + API_SECRET).encode()).hexdigest()
                    payload = {"api_key": API_KEY, "request_code": request_code, "api_secret": hash_value}

                    with st.spinner("Generating access token..."):
                        response = requests.post(TOKEN_URL, json=payload)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("stat") == "Ok":
                            st.success("Access token generated successfully!")
                            token = data['token']
                            st.code(token, language="text")
                            
                            flat_auth = {"api_key": API_KEY, "token": token}
                            with open("flattrade_auth.json", "w") as f:
                                json.dump(flat_auth, f, indent=4)
                            st.info("Token saved to `flattrade_auth.json`")
                        else:
                            st.error(f"Error: {data.get('emsg', 'Unknown error')}")
                    else:
                        st.error(f"Failed to generate access token. HTTP Status: {response.status_code}")
                except Exception as e:
                    st.error(f"An error occurred: {e}")

else: # Order Portal
    st.header("📦 Flattrade Order Portal")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Configuration")
        trade_tsym = st.text_input("Trading Symbol (tsym)", value="NIFTY24FEB26C26000", key="trade_tsym_input")
        st.session_state.trade_tsym = trade_tsym
        
        trade_num_lots = st.number_input("Number of Lots (n)", value=1, min_value=1, step=1, key="trade_num_lots_input")
        st.session_state.trade_num_lots = trade_num_lots
        
        trade_lot_size = st.number_input("Lot Size (m)", value=65, min_value=1, step=1, key="trade_lot_size_input")
        st.session_state.trade_lot_size = trade_lot_size
        
        total_qty = trade_num_lots * trade_lot_size
        st.write(f"**Total Quantity:** {total_qty}")
        st.session_state.trade_qty = total_qty
        
        trade_exch = st.selectbox("Exchange (exch)", options=["NSE", "NFO", "MCX", "BSE", "CDS"], index=1, key="trade_exch_input")
        st.session_state.trade_exch = trade_exch
        
        st.divider()
        
        if not st.session_state.auto_trading_active:
            if st.button("🚀 START AUTO TRADING", type="primary", use_container_width=True):
                if not st.session_state.backend_running:
                    st.error("Backend System is Offline! Start it in the Dashboard first.")
                else:
                    st.session_state.auto_trading_active = True
                    st.session_state.trading_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Auto Trading Started.")
                    st.rerun()
        else:
            if st.button("🛑 STOP AUTO TRADING", type="primary", use_container_width=True):
                st.session_state.auto_trading_active = False
                st.session_state.trading_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Auto Trading Stopped.")
                st.rerun()
        
        st.write(f"**Trading Status:** {'🟢 ACTIVE' if st.session_state.auto_trading_active else '🔴 INACTIVE'}")
        if st.session_state.last_order_side:
            st.write(f"**Last Action:** {st.session_state.last_order_side}")

    with col2:
        st.subheader("Activity Logs")
        log_container = st.container(height=400)
        with log_container:
            for log in reversed(st.session_state.trading_logs):
                st.write(log)
        
        if st.button("🗑️ Clear Logs"):
            st.session_state.trading_logs = []
            st.session_state.last_order_side = None
            st.rerun()
