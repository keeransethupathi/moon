import time
import json
import pyotp
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import requests
import hashlib

def auto_login(creds=None, headless=False):
    # Load credentials if not provided
    if creds is None:
        with open('credentials.json', 'r') as f:
            creds = json.load(f)

    # Generate TOTP
    totp = pyotp.TOTP(creds['totp_key'])
    token = totp.now()
    print(f"Generated TOTP: {token}")

    # Setup Selenium
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        # Navigate to login page
        auth_url = f"https://auth.flattrade.in/?app_key={creds['api_key']}"
        driver.get(auth_url)
        print("Navigated to login page")

        # Wait for and fill username
        wait = WebDriverWait(driver, 15)
        user_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='User ID']")))
        user_input.send_keys(creds['username'])
        print("Entered username")

        # Fill password
        pass_input = driver.find_element(By.XPATH, "//input[@placeholder='Password']")
        pass_input.send_keys(creds['password'])
        print("Entered password")

        # Fill TOTP
        totp_input = driver.find_element(By.XPATH, "//input[@placeholder='OTP / TOTP']")
        totp_input.send_keys(token)
        print("Entered TOTP")

        # Click Login
        print("Clicking login button...")
        time.sleep(2)  # Wait for inputs to be registered
        try:
            # Use JavaScript to find the button with "Log In" text and click it
            # This is much more robust against nested spans and case-sensitivity/white-space
            script = """
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                if (buttons[i].textContent.includes('Log In')) {
                    buttons[i].click();
                    return true;
                }
            }
            return false;
            """
            clicked = driver.execute_script(script)
            if clicked:
                print("Clicked login button via JS")
            else:
                # Fallback to standard wait if JS fails to find it
                login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Log In')]")))
                driver.execute_script("arguments[0].click();", login_btn)
                print("Clicked login button via backup XPath")
        except Exception as e:
            print(f"Failed to click login button: {e}")
            # Final attempt: try clicking any button that looks like the primary one
            try:
                primary_btn = driver.find_element(By.CSS_SELECTOR, "button.shine-button")
                driver.execute_script("arguments[0].click();", primary_btn)
                print("Clicked primary button via CSS selector as last resort")
            except:
                return {"status": "error", "message": f"Login button click failed: {str(e)}"}

        # Wait for redirect and capture code
        print("Waiting for redirect...")
        # Increased wait time and use conditional wait for URL change
        try:
            WebDriverWait(driver, 15).until(lambda d: "code=" in d.current_url)
        except:
            pass
            
        current_url = driver.current_url
        print(f"Current URL: {current_url}")

        if 'code=' in current_url:
            request_code = current_url.split('code=')[1].split('&')[0]
            print(f"Captured request_code: {request_code}")
            return {"status": "success", "code": request_code}
        else:
            # Check if there's an error message on the page
            error_msg = "Failed to capture request_code from URL"
            try:
                error_element = driver.find_element(By.CLASS_NAME, "v-snack__content")
                if error_element.is_displayed():
                    error_msg = error_element.text
                    print(f"Login error: {error_msg}")
            except:
                pass
            return {"status": "error", "message": error_msg}

    except Exception as e:
        print(f"Automation error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        driver.quit()

def generate_access_token(request_code):
    with open('credentials.json', 'r') as f:
        creds = json.load(f)

    token_url = "https://authapi.flattrade.in/trade/apitoken"
    hash_value = hashlib.sha256((creds['api_key'] + request_code + creds['api_secret']).encode()).hexdigest()

    payload = {
        "api_key": creds['api_key'],
        "request_code": request_code,
        "api_secret": hash_value
    }

    response = requests.post(token_url, json=payload)
    if response.status_code == 200:
        data = response.json()
        if data.get("stat") == "Ok":
            return data["token"]
        else:
            print(f"Error in token generation: {data.get('emsg')}")
    return None

if __name__ == "__main__":
    result = auto_login()
    if result["status"] == "success":
        code = result["code"]
        final_token = generate_access_token(code)
        if final_token:
            print(f"SUCCESS! Access Token: {final_token}")
            # Save token for other scripts
            with open('flattrade_auth.json', 'w') as f:
                json.dump({"token": final_token}, f)
        else:
            print("Failed to generate access token from code.")
    else:
        print(f"Automation failed: {result.get('message')}")
