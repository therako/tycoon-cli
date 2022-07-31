import os
from typing import Tuple
from selenium.webdriver.remote.webdriver import WebDriver
from tycoon.utils.data import RouteStats, non_decimal, RouteStat
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By


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


def _select_route(driver, route_text: str):
    driver.get(f"https://tycoon.airlines-manager.com/network/")
    routes = Select(driver.find_element(By.CLASS_NAME, "linePicker"))
    routes.select_by_visible_text(route_text)


def _get_max_category(driver) -> int:
    try:
        max_cat = driver.find_element(By.XPATH, '//*[@id="box2"]/li[1]/b/img[3]')
        return int(non_decimal.sub("", max_cat.get_attribute("alt")))
    except Exception:
        pass


def _get_distance(driver) -> int:
    dist = driver.find_element(By.XPATH, '//*[@id="box2"]/li[2]')
    return int(non_decimal.sub("", dist.text))


def _extract_route_stat(priceList) -> Tuple[str, RouteStat]:
    return (
        priceList.find_element(By.CLASS_NAME, "title")
        .text.replace("class", "")
        .strip()
        .lower(),
        RouteStat(
            price=non_decimal.sub(
                "",
                priceList.find_element(By.CLASS_NAME, "price")
                .find_element(By.TAG_NAME, "b")
                .text,
            ),
            demand=non_decimal.sub(
                "", priceList.find_element(By.CLASS_NAME, "demand").text
            ),
            remaining_demand=non_decimal.sub(
                "", priceList.find_element(By.CLASS_NAME, "paxLeft").text
            ),
        ),
    )


def _get_route_stats(driver, route_text: str) -> RouteStats:
    _select_route(driver, route_text)
    route_stats = RouteStats(
        category=_get_max_category(driver), distance=_get_distance(driver)
    )

    prices = driver.find_element(By.LINK_TEXT, "Route prices")
    driver.get(prices.get_attribute("href"))
    priceLists = driver.find_elements(
        By.XPATH, '//*[@id="marketing_linePricing"]/div[@class="box2"]/div'
    )

    for priceList in priceLists:
        route_stats.__setattr__(*_extract_route_stat(priceList))

    return route_stats


def _save_output(hub: str, route: str, route_stats: RouteStats):
    if not os.path.exists(f"tmp/{hub}"):
        os.makedirs(f"tmp/{hub}")
    with open(f"tmp/{hub}/{route}.json", "w+") as f:
        f.write(route_stats.to_json())


def _is_extracted(hub: str, route: str):
    return os.path.exists(f"tmp/{hub}/{route}.json")


def extract_route_price_stats(driver, hub: str, route: str, force=False):
    if route and (not _is_extracted(hub, route) or force):
        route_name = f"{hub} - {route}"
        route_stats = _get_route_stats(driver, route_name)
        _save_output(hub, route, route_stats)
        print(f"{route_name}: \n\t {route_stats}")
