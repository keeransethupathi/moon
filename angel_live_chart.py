import json
import pandas as pd
import numpy as np
from datetime import datetime
import threading
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from lightweight_charts import Chart
from logzero import logger
import traceback


# ================= CONFIG =================
TICK_THRESHOLD = 5       # TICK BAR SIZE
VWMA_PERIOD = 20         # Period for VWMA calculation
correlation_id = "abc123"
mode = 3  # FULL mode
token_list = [{"exchangeType": 2, "tokens": ["48203"]}] # BSE Sensex example

# ================= LOAD AUTH =================
try:
    with open("auth.json", "r") as f:
        auth_data = json.load(f)
    AUTH_TOKEN = auth_data["Authorization"]
    API_KEY = auth_data["api_key"]
    FEED_TOKEN = auth_data["feedtoken"]
    CLIENT_CODE = auth_data["client_code"]
except FileNotFoundError:
    print("Error: auth.json not found. Please run angel_login.py first.")
    exit()

# ================= STORAGE & STATE =================
lock = threading.Lock()
tick_bars = pd.DataFrame(columns=["time", "open", "high", "low", "close", "Ticks", "VWAP"])
current_bar = {
    "open": None,
    "high": -float("inf"),
    "low": float("inf"),
    "close": None,
    "ticks": 0,
    "volume": 0
}

# Session values for VWAP
session_pv = 0.0
session_vol = 0
latest_values = {"ltp": 0, "ltq": 0, "vwap": 0, "vwma": 0}

chart = None
chart_initialized = False


def vwma(close, volume, period):
    if len(close) < period: return 0
    return (close * volume).rolling(period).sum().iloc[-1] / volume.rolling(period).sum().iloc[-1]

def save_to_json(filename, data):
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving to {filename}: {e}")

# ================= WEBSOCKET CALLBACKS =================
def on_data(wsapp, message):
    global current_bar, tick_bars, chart, session_pv, session_vol, latest_values, chart_initialized

    if message is None or not isinstance(message, dict):
        return

    # Check for required tick data keys
    if "last_traded_price" not in message or "exchange_timestamp" not in message:
        # Log non-tick messages for debugging
        if "subscription_mode" not in str(message) and "heartbeat" not in str(message).lower():
            logger.info(f"Non-tick message: {message}")
        return

    try:
        ltp = message["last_traded_price"] / 100
        qty = message.get("last_traded_quantity") or message.get("ltq") or 1
        ts = datetime.fromtimestamp(message["exchange_timestamp"] / 1000)
        time_str = ts.strftime('%Y-%m-%d %H:%M:%S')

        with lock:
            # Live Feed Calculations
            session_pv += ltp * qty
            session_vol += qty
            vwap_val = session_pv / session_vol
            
            latest_values["ltp"] = ltp
            latest_values["ltq"] = qty
            latest_values["vwap"] = vwap_val
            latest_values["timestamp"] = time_str
            
            # Save live data to JSON
            save_to_json("live_data.json", latest_values)

            if current_bar["open"] is None:
                current_bar["open"] = ltp

            current_bar["high"] = max(current_bar["high"], ltp)
            current_bar["low"] = min(current_bar["low"], ltp)
            current_bar["close"] = ltp
            current_bar["ticks"] += 1
            current_bar["volume"] += qty

            # Prepare data for real-time update
            update_data = {
                'time': time_str,
                'open': current_bar['open'],
                'high': current_bar['high'],
                'low': current_bar['low'],
                'close': current_bar['close'],
                'volume': current_bar['volume']
            }

            # Update the chart in real-time
            if chart:
                if not chart_initialized:
                    chart.set(pd.DataFrame([update_data]))
                    chart_initialized = True
                else:
                    chart.update(pd.Series(update_data))
                # Update legend or title with latest values
                chart.legend(visible=True, font_size=14)
                
            # If bar completes, add to tick_bars for VWMA
            if current_bar["ticks"] >= TICK_THRESHOLD:
                new_row = pd.DataFrame([{
                    "time": ts,
                    "open": current_bar["open"],
                    "high": current_bar["high"],
                    "low": current_bar["low"],
                    "close": current_bar["close"],
                    "Ticks": current_bar["ticks"],
                    "volume": current_bar["volume"],
                    "VWAP": vwap_val
                }])
                tick_bars = pd.concat([tick_bars, new_row], ignore_index=True)
                
                # Calculate VWMA if we have enough bars
                if len(tick_bars) >= VWMA_PERIOD:
                    latest_values["vwma"] = vwma(tick_bars["close"], tick_bars["Ticks"], VWMA_PERIOD)

                # Reset bar for next interval
                current_bar = {
                    "open": None, "high": -float("inf"), "low": float("inf"),
                    "close": None, "ticks": 0, "volume": 0
                }
                
            if chart:
                info_text = f"LTP: {ltp:.2f} | VWAP: {vwap_val:.2f} | VWMA: {latest_values['vwma']:.2f}"
                # Using watermarks for live values as side panel isn't directly available
                chart.watermark(info_text, color='rgba(180, 180, 255, 0.5)')

    except Exception as e:
        logger.error(f"Error in on_data: {e}")
        logger.error(traceback.format_exc())

def on_open(wsapp):
    logger.info("WebSocket opened")
    sws.subscribe(correlation_id, mode, token_list)

def on_error(wsapp, error):
    logger.error(f"WebSocket Error: {error}")

def on_close(wsapp):
    logger.info("WebSocket closed")

# ================= INIT SOCKET =================
sws = SmartWebSocketV2(AUTH_TOKEN, API_KEY, CLIENT_CODE, FEED_TOKEN)
sws.on_open = on_open
sws.on_data = on_data
sws.on_error = on_error
sws.on_close = on_close

def run_ws():
    sws.connect()

# ================= MAIN =================
def main():
    global chart
    
    # Initialize the chart
    chart = Chart(title='AngelOne Live Tick Chart', width=1200, height=700)
    
    # Customize appearance
    chart.grid(vert_enabled=True, horz_enabled=True)
    chart.layout(background_color='#131722', text_color='#d1d4dc', font_size=12)
    chart.candle_style(up_color='#26a69a', down_color='#ef5350')
    chart.volume_config(up_color='#26a69a', down_color='#ef5350')
    
    # Start WebSocket in a separate thread
    ws_thread = threading.Thread(target=run_ws, daemon=True)
    ws_thread.start()
    
    print("Chart is running. Live data will appear once received.")
    print("Close the window to exit.")
    
    # Show the chart (blocks execution)
    chart.show(block=True)

if __name__ == '__main__':
    main()
