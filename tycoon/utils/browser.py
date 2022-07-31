from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver


def js_click(driver: WebDriver, element: WebElement):
    driver.execute_script("arguments[0].click();", element)
