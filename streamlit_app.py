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
from datetime import datetime
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
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

# ================= STATE MANAGEMENT =================
if 'ohlc_data' not in st.session_state:
    st.session_state.ohlc_data = []
if 'vwma_data' not in st.session_state:
    st.session_state.vwma_data = []
if 'current_ltp' not in st.session_state:
    st.session_state.current_ltp = 0.0
if 'backend_running' not in st.session_state:
    st.session_state.backend_running = False

# Global variable to hold the backend thread instance
# Using session_state for the instance might be tricky if it reloads, 
# but for simple threading it often works.
if 'backend_thread' not in st.session_state:
    st.session_state.backend_thread = None

# ================= BACKEND LOGIC =================
class StreamlitMarketBackend:
    def __init__(self, exchange_type, token_id, auth_data):
        self.exchange_type = exchange_type
        self.token_id = token_id
        self.auth_data = auth_data
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        
        self.ohlc_bars = []
        self.vwma_bars = []
        self.raw_bars = []
        self.current_bar = {"open": None, "high": -float("inf"), "low": float("inf"), "close": None, "ticks": 0, "volume": 0}
        self.latest_ltp = 0.0
        
        self.sws = None
        self.vwma_period = 20
        self.tick_bar_size = 5

    def on_open(self, wsapp):
        try:
            time.sleep(2)
            token_list = [{"exchangeType": self.exchange_type, "tokens": [self.token_id]}]
            correlation_id = f"st_{self.token_id}"
            self.sws.subscribe(correlation_id, 3, token_list)
        except Exception as e:
            print(f"Subscription Error: {e}")

    def on_data(self, wsapp, message):
        if message and isinstance(message, dict) and "last_traded_price" in message:
            try:
                ltp = message["last_traded_price"] / 100
                qty = message.get("last_traded_quantity") or 1
                ts = datetime.fromtimestamp(message["exchange_timestamp"] / 1000)
                self.add_tick(ltp, qty, ts)
            except Exception as e:
                print(f"Tick processing error: {e}")

    def add_tick(self, ltp, qty, ts):
        with self.lock:
            self.latest_ltp = ltp
            if self.current_bar["open"] is None:
                self.current_bar["open"] = ltp
            self.current_bar["high"] = max(self.current_bar["high"], ltp)
            self.current_bar["low"] = min(self.current_bar["low"], ltp)
            self.current_bar["close"] = ltp
            self.current_bar["ticks"] += 1
            self.current_bar["volume"] += qty

            if self.current_bar["ticks"] >= self.tick_bar_size:
                # Add 5 hours 30 minutes for IST correction
                chart_time = int(ts.timestamp()) + 19800
                bar = {
                    "time": chart_time,
                    "open": self.current_bar["open"],
                    "high": self.current_bar["high"],
                    "low": self.current_bar["low"],
                    "close": self.current_bar["close"],
                    "volume": self.current_bar["volume"]
                }
                self.ohlc_bars.append(bar)
                self.raw_bars.append(bar)
                
                if len(self.raw_bars) >= self.vwma_period:
                    df = pd.DataFrame(self.raw_bars[-self.vwma_period:])
                    vwma_val = (df['close'] * df['volume']).sum() / df['volume'].sum()
                    self.vwma_bars.append({"time": chart_time, "value": float(vwma_val)})
                
                if len(self.ohlc_bars) > 500:
                    self.ohlc_bars.pop(0)
                    if self.vwma_bars: self.vwma_bars.pop(0)
                
                # Update st.session_state from background thread
                # NOTE: This might not trigger a rerun, but the main loop will catch it
                st.session_state.ohlc_data = self.ohlc_bars.copy()
                st.session_state.vwma_data = self.vwma_bars.copy()
                st.session_state.current_ltp = float(self.latest_ltp)
                
                self.current_bar = {"open": None, "high": -float("inf"), "low": float("inf"), "close": None, "ticks": 0, "volume": 0}

    def run(self):
        try:
            self.sws = SmartWebSocketV2(
                self.auth_data["Authorization"], 
                self.auth_data["api_key"], 
                self.auth_data["client_code"], 
                self.auth_data["feedtoken"]
            )
            self.sws.on_open = self.on_open
            self.sws.on_data = self.on_data
            
            # Run WebSocket in a blocking call within this thread
            self.sws.connect()
        except Exception as e:
            print(f"Backend thread error: {e}")
        finally:
            st.session_state.backend_running = False

    def stop(self):
        if self.sws:
            try:
                self.sws.close()
            except:
                pass
        self.stop_event.set()

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
                    
                    # Initialize and start backend thread
                    backend = StreamlitMarketBackend(exchange_type, token_id, auth_data)
                    st.session_state.backend_thread = backend
                    
                    thread = threading.Thread(target=backend.run, daemon=True)
                    thread.start()
                    
                    st.session_state.backend_running = True
                    st.success(f"System Online for {selected_exchange_name}:{token_id}")
                    time.sleep(1)
                    st.rerun()
        else:
            if st.button("🛑 Stop Backend System"):
                if st.session_state.backend_thread:
                    st.session_state.backend_thread.stop()
                st.session_state.backend_running = False
                st.session_state.ohlc_data = [] # Reset data
                st.session_state.vwma_data = []
                st.warning("System Stopped.")
                time.sleep(1)
                st.rerun()
                
        st.write(f"**System Status:** {'🟢 ONLINE' if st.session_state.backend_running else '🔴 OFFLINE'}")
        
        if st.button("🗑️ Reset Data"):
            st.session_state.ohlc_data = []
            st.session_state.vwma_data = []
            st.session_state.current_ltp = 0.0
            st.rerun()

    # Layout
    col1, col2 = st.columns(2)
    ltp_metric = col1.empty()
    vwma_metric = col2.empty()
    chart_placeholder = st.empty()

    # Data Display
    if st.session_state.backend_running or st.session_state.ohlc_data:
        try:
            ltp = st.session_state.current_ltp
            ohlc = st.session_state.ohlc_data
            vwma = st.session_state.vwma_data
            
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
                    "timeScale": {"timeVisible": True, "secondsVisible": True, "borderColor": '#485c7b'},
                }
                series = [{"type": 'Candlestick', "data": ohlc, "options": {"upColor": '#26a69a', "downColor": '#ef5350'}}]
                if vwma:
                    series.append({"type": 'Line', "data": vwma, "options": {"color": '#2196f3', "lineWidth": 2, "title": 'VWMA'}})
                
                with chart_placeholder:
                    renderLightweightCharts([{"chart": chart_options, "series": series}], 'integrated_chart')
            else:
                chart_placeholder.info("Connected. Waiting for the first bar (5 ticks)...")
        except Exception as e:
            st.error(f"UI Error: {e}")
            
        time.sleep(1)
        st.rerun()
    else:
        chart_placeholder.info("System Offline. Start backend in sidebar or login via 'Portal'.")

elif menu == "🔐 Login Portal": # Login Portal
    st.header("🔐 AngelOne Login")
    
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
