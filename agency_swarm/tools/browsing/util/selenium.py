import json
import os
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
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.headless = True

    wd = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install(), options=chrome_options))

    wd.implicitly_wait(3)

    stealth(wd,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
            )

    return wd


def set_web_driver(new_wd):
    global wd
    wd = remove_highlight_and_labels(wd)
    wd = new_wd

