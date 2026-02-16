import streamlit as st
import json
import subprocess
import os
import signal
import time
import pandas as pd
from streamlit_lightweight_charts import renderLightweightCharts
from logzero import logger
import requests
import pyotp

# ================= CONFIG =================
DATA_FILE = "market_data.json"
BG_SCRIPT = "background_ws.py"
PID_FILE = "ws_pid.txt"

# Hardcoded credentials (kept as is)
# Credentials from st.secrets (defined in .streamlit/secrets.toml locally or Cloud dashboard)
TOTP_SECRET = st.secrets["TOTP_SECRET"]
API_KEY = st.secrets["API_KEY"]
CLIENT_CODE = st.secrets["CLIENT_CODE"]
PASSWORD = st.secrets["PASSWORD"]

# ================= HELPER FUNCTIONS =================
def perform_angel_login():
    try:
        totp = pyotp.TOTP(TOTP_SECRET)
        current_code = totp.now()
        url = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"
        
        payload = {
            "clientcode": CLIENT_CODE,
            "password": PASSWORD,
            "totp": current_code,
            "state": "12345"
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-UserType': 'USER',
            'X-SourceID': 'WEB',
            'X-ClientLocalIP': '127.0.0.1',
            'X-ClientPublicIP': '106.193.147.98',
            'X-MACAddress': 'fe80::216e:6507:4b7c:bc7',
            'X-PrivateKey': API_KEY
        }
        
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        if response.status_code == 200:
            resp_json = response.json()
            if resp_json.get('status'):
                auth_data = {
                    "Authorization": "Bearer " + resp_json['data']['jwtToken'],
                    "api_key": API_KEY,
                    "feedtoken": resp_json['data']['feedToken'],
                    "client_code": CLIENT_CODE
                }
                with open("auth.json", "w") as f:
                    json.dump(auth_data, f, indent=4)
                return True, "Login Successful"
            return False, f"Login Failed: {resp_json.get('message', 'Unknown Error')}"
        
        error_detail = response.text
        return False, f"HTTP {response.status_code}: {error_detail}"
    except Exception as e:
        return False, str(e)

def is_ws_running():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            # Check if process exists
            try:
                os.kill(pid, 0)
                return True, pid
            except OSError:
                return False, None
        except ValueError:
            return False, None
    return False, None

def start_ws_process():
    running, _ = is_ws_running()
    if running:
        return True, "Already running"
    
    try:
        # Prepare environment for background process (pass secrets)
        env = os.environ.copy()
        env["TOTP_SECRET"] = TOTP_SECRET
        env["API_KEY"] = API_KEY
        env["CLIENT_CODE"] = CLIENT_CODE
        env["PASSWORD"] = PASSWORD
        
        if os.name == 'nt':
            # Use CREATE_NO_WINDOW (0x08000000) to hide the console window
            process = subprocess.Popen(
                ["python", BG_SCRIPT], 
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env
            )
        else:
            process = subprocess.Popen(
                ["python3", BG_SCRIPT],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env
            )
            
        with open(PID_FILE, "w") as f:
            f.write(str(process.pid))
            
        return True, "Started"
    except Exception as e:
        return False, str(e)

def stop_ws_process():
    running, pid = is_ws_running()
    if not running: 
        if os.path.exists(PID_FILE):
             os.remove(PID_FILE)
        return True, "Not running (cleaned up pid file)"
    
    stop_file = "stop_signal.txt"
    try:
        # Create stop signal
        with open(stop_file, "w") as f:
            f.write("stop")
            
        # Wait for up to 5 seconds for graceful shutdown
        for i in range(5):
            running, _ = is_ws_running()
            if not running:
                if os.path.exists(stop_file):
                    os.remove(stop_file)
                if os.path.exists(PID_FILE): # Double check cleanup
                     os.remove(PID_FILE)
                return True, "Stopped gracefully (Unsubscribed)"
            time.sleep(1)
            
        # Fallback to force kill
        os.kill(pid, signal.SIGTERM)
        if os.path.exists(stop_file):
            os.remove(stop_file)
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return True, "Stopped forcefully (Timeout)"
    except Exception as e:
        if os.path.exists(stop_file):
            os.remove(stop_file)
        return False, str(e)

def load_market_data():
    if not os.path.exists(DATA_FILE):
        return None
        
    for i in range(3):
        try:
            with open(DATA_FILE, "r") as f:
                # Load quickly to minimize lock
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # File might be mid-write or locked
            time.sleep(0.05)
            continue
    return None

# ================= STREAMLIT UI =================
st.set_page_config(page_title="AngelOne Live Chart", layout="wide")

st.title("📈 AngelOne Live Tick Chart (Background Mode)")

# Initialize session state for auto-refresh
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True

# Sidebar
with st.sidebar:
    st.header("🔐 Login")
    if st.button("Run Login Script", use_container_width=True):
        with st.spinner("Logging in..."):
            success, message = perform_angel_login()
            if success:
                st.success(message)
            else:
                st.error(message)
    
    st.divider()
    
    st.header("⚙️ Process Control")
    
    try:
        running, pid = is_ws_running()
        status_icon = "🟢" if running else "🔴"
        status_text = f"Running (PID: {pid})" if running else "Stopped"
        st.write(f"Status: {status_icon} {status_text}")
    except Exception as e:
        st.error(f"Error checking status: {e}")
        running, pid = False, None
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Start WS", use_container_width=True, disabled=running):
            success, msg = start_ws_process()
            if success:
                st.rerun()
            else:
                st.error(msg)
    
    with col2:
        if st.button("Stop WS", use_container_width=True, disabled=not running):
            success, msg = stop_ws_process()
            if success:
                st.rerun()
            else:
                st.error(msg)
    
    # New Reset Data Button
    if st.button("🗑️ Reset Market Data", use_container_width=True, help="Stops WS and clears all market data"):
        # 1. Stop the process first to clear memory
        stop_ws_process()
        
        # 2. Delete the file
        if os.path.exists(DATA_FILE):
            try:
                os.remove(DATA_FILE)
                st.success("Market data reset! Please Start WS again.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to clear data: {e}")
        else:
             st.success("Market data already cleared. Please Start WS.")
             time.sleep(1)
             st.rerun()
                
    if st.button("⚠️ Force Reset State", use_container_width=True, help="Click this if the buttons are stuck"):
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
                st.success("PID file removed. Please refresh.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to remove PID file: {e}")
    
    st.divider()
    
    st.checkbox("Auto Refresh", key="auto_refresh")
    if st.button("Manual Refresh", use_container_width=True):
        st.rerun()

# Main Area
data = load_market_data()

if data:
    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Latest VWAP", f"{data.get('latest_vwap', 0):.2f}")
    m2.metric("Latest VWMA", f"{data.get('latest_vwma', 0):.2f}")
    m3.metric("Last Update", data.get("last_updated", "N/A"))

    # Chart
    tick_data = data.get("tick_data", [])
    vwap_data = data.get("vwap_data", [])
    vwma_data = data.get("vwma_data", [])

    # Adjust for IST (UTC+5:30)
    # The chart library uses UTC by default, so we add 19800 seconds to shift it
    IST_OFFSET = 19800
    for item in tick_data:
        item["time"] += IST_OFFSET
    for item in vwap_data:
        item["time"] += IST_OFFSET
    for item in vwma_data:
        item["time"] += IST_OFFSET

    if tick_data:
        chartOptions = {
            "width": 1200, # Increased width
            "height": 600, # Increased height
            "layout": {
                "background": {"color": "#131722"},
                "textColor": "#d1d4dc",
                "fontSize": 16 # Increased font size
            },
            "grid": {
                "vertLines": {"color": "#334158"},
                "horzLines": {"color": "#334158"}
            },
            "timeScale": {
                "timeVisible": True,
                "secondsVisible": True,
                "fontSize": 14
            },
            "rightPriceScale": {
                "fontSize": 14
            }
        }
        
        seriesCandlestickChart = [{
            "type": 'Candlestick',
            "data": tick_data,
            "options": {
                "upColor": '#26a69a',
                "downColor": '#ef5350',
                "borderVisible": False,
                "wickUpColor": '#26a69a',
                "wickDownColor": '#ef5350'
            }
        }]
        
        if vwma_data:
            seriesCandlestickChart.append({
                "type": 'Line',
                "data": vwma_data,
                "options": {
                    "color": 'cyan',
                    "lineWidth": 2
                    # "title": 'VWMA' removed as per request
                }
            })
        
        renderLightweightCharts([
            {
                "chart": chartOptions,
                "series": seriesCandlestickChart
            }
        ], 'candlestick')
    else:
        st.warning("Data file exists but contains no tick data available.")
else:
    if running:
        st.info("📡 Background process running. Waiting for data...")
    else:
        st.info("No market data found. Please login and start the WebSocket process.")




# Auto-refresh loop
if st.session_state.auto_refresh:
    time.sleep(1)
    st.rerun()
