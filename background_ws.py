
import json
import pandas as pd
import threading
import time
from datetime import datetime
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logzero import logger
import os
from db import save_market_data

# ================= CONFIG =================
TICK_THRESHOLD = 5
VWMA_PERIOD = 20
correlation_id = "abc123"
mode = 3
token_list = [{"exchangeType": 2, "tokens": ["48203"]}]  # Default

# ================= GLOBAL STATE =================
ws_running = False
data_lock = threading.Lock()
tick_data = []
current_bar = {
    "open": None, "high": -1e9, "low": 1e9, "close": None, "ticks": 0
}
session_pv = 0.0
session_vol = 0
latest_vwap = 0
latest_vwma = 0
tick_bars = pd.DataFrame(columns=["close", "ticks"])
vwap_data = []
vwma_data = []

DATA_FILE = "market_data.json"

# ================= HELPER FUNCTIONS =================
def vwma(close, volume, period):
    if len(close) < period:
        return 0
    return (close * volume).rolling(period).sum().iloc[-1] / volume.rolling(period).sum().iloc[-1]

def save_data():
    """Saves the current state to a JSON file (Thread Safe)."""
    with data_lock:
        data = {
            "tick_data": tick_data[-500:], # Keep last 500 candles to avoid huge file
            "vwap_data": vwap_data[-500:],
            "vwma_data": vwma_data[-500:],
            "latest_vwap": latest_vwap,
            "latest_vwma": latest_vwma,
            "last_updated": datetime.now().isoformat()
        }
    
    # 1. Try to save to Supabase (Cloud)
    if save_market_data(data):
        # If successful, we could skip local save, but keeping it as backup/cache for now
        # logger.info("Saved to Supabase")
        pass
    else:
        # logger.warning("Supabase save failed/skipped, falling back to local file")
        pass

    # 2. Save to Local File (Fallback/Legacy)

    # Use retry logic for atomic replacement
    # Use PID in temp filename to avoid conflicts with zombie processes
    temp_file = f"{DATA_FILE}.{os.getpid()}.tmp"
    try:
        # Write to temp file every time
        with open(temp_file, "w") as f:
            json.dump(data, f)
            
        # Retry loop for file replacement (fixes WinError 32)
        # Increased to 20 attempts * 0.2s = 4 seconds max wait
        for i in range(20):
            try:
                if os.path.exists(DATA_FILE):
                    os.replace(temp_file, DATA_FILE)
                else:
                    os.rename(temp_file, DATA_FILE)
                break # Success
            except OSError as e:
                # If access denied/used by another process, wait and retry
                time.sleep(0.2)
                if i == 19: # Last attempt (failed)
                    logger.error(f"Error saving data (attempt {i+1}): {e}")
                    # Try to clean up temp file if we failed to move it
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                elif i == 10:
                    logger.warning(f"File locked, retrying... ({e})")
    except Exception as e:
        logger.error(f"Error preparing data save: {e}")
        # Clean up in case of other errors
        if os.path.exists(temp_file):
             try:
                os.remove(temp_file)
             except:
                pass

def run_data_saver():
    """Background thread to save data periodically."""
    logger.info("Data saver thread started.")
    while True:
        try:
            save_data()
        except Exception as e:
            logger.error(f"Error in data saver thread: {e}")
        time.sleep(1) # Save every 1 second

# ================= WEBSOCKET CALLBACKS =================
sws = None  # Global instance

def on_data(wsapp, message):
    global current_bar, session_pv, session_vol, latest_vwap, latest_vwma, tick_bars, tick_data, vwap_data, vwma_data

    if not isinstance(message, dict) or "last_traded_price" not in message:
        return
    
    try:
        with data_lock:
            ltp = message["last_traded_price"] / 100
            qty = message.get("last_traded_quantity", 1)
            ts = int(message.get("exchange_timestamp", datetime.now().timestamp() * 1000) / 1000)

            session_pv += ltp * qty
            session_vol += qty
            latest_vwap = session_pv / session_vol

            if current_bar["open"] is None:
                current_bar["open"] = ltp
            
            current_bar["high"] = max(current_bar["high"], ltp)
            current_bar["low"] = min(current_bar["low"], ltp)
            current_bar["close"] = ltp
            current_bar["ticks"] += 1

            new_tick = {
                "time": ts,
                "open": current_bar["open"],
                "high": current_bar["high"],
                "low": current_bar["low"],
                "close": current_bar["close"]
            }
            
            # Logic to update the last candle if it has the same timestamp, otherwise append
            if tick_data and tick_data[-1]["time"] == ts:
                 tick_data[-1] = new_tick
            else:
                 tick_data.append(new_tick)

            # Update VWAP data
            new_vwap = {"time": ts, "value": latest_vwap}
            if vwap_data and vwap_data[-1]["time"] == ts:
                vwap_data[-1] = new_vwap
            else:
                vwap_data.append(new_vwap)

            # Check for bar completion (Tick based candles)
            if current_bar["ticks"] >= TICK_THRESHOLD:
                new_row = pd.DataFrame([{
                    "close": current_bar["close"],
                    "ticks": current_bar["ticks"]
                }])
                tick_bars = pd.concat([tick_bars, new_row], ignore_index=True)
                
                if len(tick_bars) >= VWMA_PERIOD:
                    latest_vwma = vwma(
                        tick_bars["close"],
                        tick_bars["ticks"],
                        VWMA_PERIOD
                    )
                    new_vwma = {"time": ts, "value": latest_vwma}
                    if vwma_data and vwma_data[-1]["time"] == ts:
                        vwma_data[-1] = new_vwma
                    else:
                        vwma_data.append(new_vwma)
                
                current_bar = {
                    "open": None, "high": -1e9, "low": 1e9, "close": None, "ticks": 0
                }
            
        # Removed save_data() call to prevent blocking WS thread
        
    except Exception as e:
        logger.error(f"Error in on_data: {e}")

def on_open(wsapp):
    logger.info("AngelOne WebSocket connected")
    if sws:
        sws.subscribe(correlation_id, mode, token_list)
    else:
        logger.error("SWS instance is None in on_open")

def on_error(wsapp, error):
    logger.error(f"AngelOne WebSocket error: {error}")

def on_close(wsapp):
    logger.warning("AngelOne WebSocket closed")

def main():
    global sws
    try:
        if not os.path.exists("auth.json"):
            logger.error("auth.json not found. Please login via Streamlit app first.")
            return

        with open("auth.json", "r") as f:
            auth_data = json.load(f)
        
        sws = SmartWebSocketV2(
            auth_data["Authorization"],
            auth_data["api_key"],
            auth_data["client_code"],
            auth_data["feedtoken"]
        )
        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close
        
        # Start data saver thread BEFORE connecting
        saver_thread = threading.Thread(target=run_data_saver, daemon=True)
        saver_thread.start()
        
        logger.info("Starting WebSocket connection...")
        sws.connect()
    except Exception as e:
        logger.error(f"Failed to start WebSocket: {e}")

def monitor_stop_signal():
    stop_file = "stop_signal.txt"
    while True:
        if os.path.exists(stop_file):
            logger.info("Stop signal received. Unsubscribing and closing...")
            if sws:
                try:
                    sws.unsubscribe(correlation_id, mode, token_list)
                    logger.info(f"Unsubscribed from: {token_list}")
                except Exception as e:
                    logger.error(f"Error unsubscribing: {e}")
                
                try:
                    # Some versions of SmartWebSocketV2 don't have close(), handle gracefully
                    if hasattr(sws, 'close'):
                        sws.close()
                    elif hasattr(sws, 'ws') and hasattr(sws.ws, 'close'):
                         sws.ws.close()
                    else:
                        logger.warning("Could not find close method on SWS object")

                except Exception as e:
                     logger.error(f"Error closing WS: {e}")
            
            # Clean up PID file if it exists (though main app might do it)
            if os.path.exists("ws_pid.txt"):
                try:
                    os.remove("ws_pid.txt")
                except:
                    pass
            
            # Clean up stop signal file? No, let main app do it or just leave it. 
            # Actually, main app creates it, so we should probably leave it for main app to know we fail?
            # Better: Main app waits for process to die.
            
            os._exit(0) # Force exit
        time.sleep(1)

if __name__ == "__main__":
    # Start stop signal monitor
    t = threading.Thread(target=monitor_stop_signal, daemon=True)
    t.start()
    
    main()
