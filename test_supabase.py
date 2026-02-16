import os
from db import init_supabase, load_market_data
import logging

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_connection():
    logger.info("Testing Supabase connection...")
    supabase = init_supabase()
    
    if supabase:
        logger.info("Supabase client initialized successfully.")
        try:
            # Try to load data - this will verify if the table and connection work
            data = load_market_data()
            logger.info("Successfully attempted to load data from Supabase.")
            if data:
                logger.info(f"Retrieved data: {data}")
            else:
                logger.info("No data found in market_data table (or table might be empty).")
            return True
        except Exception as e:
            logger.error(f"Error during data operation: {e}")
            return False
    else:
        logger.error("Failed to initialize Supabase client.")
        return False

if __name__ == "__main__":
    success = test_connection()
    if success:
        print("\n--- Supabase Connection Test Passed! ---")
    else:
        print("\n--- Supabase Connection Test Failed! ---")
