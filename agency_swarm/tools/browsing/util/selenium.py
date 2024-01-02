import json
import os
import time
from urllib.parse import urlparse

from .highlights import remove_highlight_and_labels

wd = None


def get_web_driver():
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service as ChromeService
    except ImportError:
        print("Selenium not installed. Please install it with pip install selenium")
        raise ImportError

    try:
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("webdriver_manager not installed. Please install it with pip install webdriver-manager")
        raise ImportError

    try:
        from selenium_stealth import stealth
    except ImportError:
        print("selenium_stealth not installed. Please install it with pip install selenium-stealth")
        raise ImportError

    global wd

    if wd:
        return wd

    chrome_options = webdriver.ChromeOptions()
    # Removed headless and other options for debugging purposes

    # Ensure the paths are correct
    user_data_dir = "/Users/vrsen/Library/Application Support/Google/Chrome Canary"
    profile_directory = "Profile 5"

    # Verify if the paths exist
    if not os.path.exists(user_data_dir):
        print(f"User data directory does not exist: {user_data_dir}")
    else:
        print(f"User data directory found: {user_data_dir}")

    chrome_driver_path = ChromeDriverManager().install()
    print(f"ChromeDriver path: {chrome_driver_path}")

    # chrome_options.add_argument('--headless')
    chrome_options.add_argument("--window-size=960,1080")
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")
    chrome_options.add_argument(f"profile-directory={profile_directory}")

    try:
        wd = webdriver.Chrome(service=ChromeService(), options=chrome_options)
        print("WebDriver initialized successfully.")
        # Print the actual profile path being used
        print(f"Profile path in use: {wd.capabilities['chrome']['userDataDir']}")
    except Exception as e:
        print(f"Error initializing WebDriver: {e}")
        raise

    stealth(
        wd,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
        )

    # wd.set_window_size(960, 1080)
    wd.implicitly_wait(3)

    return wd


def set_web_driver(new_wd):
    global wd
    wd = remove_highlight_and_labels(wd)
    wd = new_wd

