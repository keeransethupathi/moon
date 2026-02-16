import os
from supabase import create_client, Client
import json
from datetime import datetime
import logging

# Configure logger
logger = logging.getLogger(__name__)

# Constants
SUPABASE_URL = os.environ.get("SUPABASE_URL") or "https://hrkqqifsghdkvkymuyxf.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "sb_publishable_wXsqquNdtTjTzfF-66I3Cw_48CLwhjp"
TABLE_NAME = "market_data"
DEFAULT_ID = 1  # We use a single row for this simple app

def init_supabase():
    """Initialize Supabase client if credentials exist."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("SUPABASE_URL or SUPABASE_KEY not set. Database operations will be skipped.")
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        return None

def save_market_data(data):
    """Save market data to Supabase."""
    supabase: Client = init_supabase()
    if not supabase:
        return False

    try:
        # Prepare payload
        payload = {
            "id": DEFAULT_ID,
            "tick_data": data.get("tick_data"),
            "vwap_data": data.get("vwap_data"),
            "vwma_data": data.get("vwma_data"),
            "latest_vwap": data.get("latest_vwap"),
            "latest_vwma": data.get("latest_vwma"),
            "last_updated": datetime.now().isoformat()
        }
        
        # Upsert data (insert or update)
        response = supabase.table(TABLE_NAME).upsert(payload).execute()
        return True
    except Exception as e:
        logger.error(f"Error saving to Supabase: {e}")
        return False

def load_market_data():
    """Load market data from Supabase."""
    supabase: Client = init_supabase()
    if not supabase:
        return None

    try:
        response = supabase.table(TABLE_NAME).select("*").eq("id", DEFAULT_ID).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error loading from Supabase: {e}")
        return None

def clear_market_data():
    """Clear market data from Supabase."""
    supabase: Client = init_supabase()
    if not supabase:
        return False

    try:
        # We can just delete the row
        response = supabase.table(TABLE_NAME).delete().eq("id", DEFAULT_ID).execute()
        return True
    except Exception as e:
        logger.error(f"Error clearing Supabase data: {e}")
        return False
