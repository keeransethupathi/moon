import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def debug_selectors():
    # Load credentials for URL
    with open('credentials.json', 'r') as f:
        creds = json.load(f)

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        auth_url = f"https://auth.flattrade.in/?app_key={creds['api_key']}"
        driver.get(auth_url)
        print(f"Navigated to: {auth_url}")
        
        # Wait for potential loading
        time.sleep(5)
        
        # Dump page source
        with open("page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        
        # Save screenshot
        driver.save_screenshot("login_page_screenshot.png")
        print("Saved page_source.html and login_page_screenshot.png")

        # List all inputs
        inputs = driver.find_elements(By.TAG_NAME, "input")
        print(f"Found {len(inputs)} input elements:")
        for i, input_el in enumerate(inputs):
            print(f"Input {i}: id='{input_el.get_attribute('id')}', name='{input_el.get_attribute('name')}', type='{input_el.get_attribute('type')}', placeholder='{input_el.get_attribute('placeholder')}'")

        # List all buttons
        buttons = driver.find_elements(By.TAG_NAME, "button")
        print(f"Found {len(buttons)} button elements:")
        for i, btn in enumerate(buttons):
            print(f"Button {i}: id='{btn.get_attribute('id')}', text='{btn.text}'")

    finally:
        driver.quit()

if __name__ == "__main__":
    debug_selectors()
