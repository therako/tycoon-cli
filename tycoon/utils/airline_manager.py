import os
from selenium.webdriver.remote.webdriver import WebDriver


def login(driver: WebDriver):
    if os.getenv("TYCOON_EMAIL", "") == "" or os.getenv("TYCOON_PASSWORD", "") == "":
        raise Exception(
            "Missing env variables TYCOON_EMAIL/TYCOON_PASSWORD, required for login to http://tycoon.airlines-manager.com"
        )

    driver.get("http://tycoon.airlines-manager.com/network/")
    username = driver.find_element("id", "username")
    username.send_keys(os.getenv("TYCOON_EMAIL"))
    password = driver.find_element("id", "password")
    password.send_keys(os.getenv("TYCOON_PASSWORD"))
    login = driver.find_element("id", "loginSubmit")
    login.click()
