import logging
import os
import re
import time
from typing import List, Tuple

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select
from tycoon.utils.data import (
    RouteStat,
    RouteStats,
    ScheduledAircraftConfig,
    WaveStat,
    non_decimal,
)


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


def _get_flight_stats(driver) -> List[ScheduledAircraftConfig]:
    flights_list = driver.find_elements(
        By.XPATH, '//div[@class="aircraftListView"]/div'
    )
    flight_stats = []
    for flight in flights_list:
        flight = flights_list[0]
        flight_stats.append(
            ScheduledAircraftConfig(
                model=flight.find_element(By.XPATH, "div[1]/span")
                .text.split("/")[0]
                .strip(),
                seat_config=flight.find_element(
                    By.XPATH, "div[2]/div/span[4]/b"
                ).text.strip(),
                result=non_decimal.sub(
                    "",
                    flight.find_element(By.XPATH, "div[2]/div/span[6]/b").text.strip(),
                ),
            )
        )

    return flight_stats


def route_stats(driver, hub: str, route: str) -> RouteStats:
    route_text = f"{hub} - {route}"
    _select_route(driver, route_text)
    flight_stats = _get_flight_stats(driver)
    route_stats = RouteStats(
        category=_get_max_category(driver),
        distance=_get_distance(driver),
        scheduled_flights=flight_stats,
    )

    prices = driver.find_element(By.LINK_TEXT, "Route prices")
    driver.get(prices.get_attribute("href"))
    priceLists = driver.find_elements(
        By.XPATH, '//*[@id="marketing_linePricing"]/div[@class="box2"]/div'
    )

    for priceList in priceLists:
        route_stats.__setattr__(*_extract_route_stat(priceList))

    return route_stats


def _extract_destination(hub: str, route_element) -> str:
    if "lineListBox" in route_element.get_attribute("class"):
        title = route_element.find_element(By.CLASS_NAME, "title").text
        match = re.search("([A-Z]{3}) \/ ([A-Z]{3})", title)
        if match and match.group(1) == hub:
            return match.group(2)


def _find_hub_id(driver, hub: str) -> int:
    driver.get("http://tycoon.airlines-manager.com/network/")
    driver.find_elements(By.XPATH, '//*[@id="lineList"]/div')
    hubs = driver.find_elements(
        By.XPATH, '//*[@id="displayRegular"]/div[@class="hubListBox"]/div'
    )
    for hub_element in hubs:
        match = re.search("Owned hub ([A-Z]{3}) -", hub_element.text)
        if match and match.group(1) == hub:
            hub_id = int(
                hub_element.find_element(By.LINK_TEXT, "Hub details")
                .get_attribute("href")
                .split("/")[-1],
            )
            return hub_id


def get_all_routes(driver, hub: str) -> List[str]:
    hub_id = _find_hub_id(driver, hub)
    driver.get(f"http://tycoon.airlines-manager.com/network/showhub/{hub_id}/linelist")
    route_elements = driver.find_elements(By.XPATH, '//*[@id="lineList"]/div')

    destinations = []
    for route_element in route_elements:
        destinations.append(_extract_destination(hub, route_element))

    return destinations


def _clear_all_and_enter(inputs):
    for set in inputs:
        set[0].clear()
        set[0].send_keys("0")
    time.sleep(2)
    for set in inputs:
        set[0].clear()
        set[0].send_keys(str(set[1]))
        time.sleep(2)


def reconfigure_flight_seats(
    driver: WebDriver,
    hub: str,
    destination: str,
    seat_config: pd.Series,
):
    _select_route(driver, f"{hub} - {destination}")
    aircrafts = driver.find_elements(By.XPATH, '//div[@class="aircraftListView"]/div')
    aircraft_links = []
    for aircraft in aircrafts:
        aircraft_links.append(
            aircraft.find_element(By.LINK_TEXT, "Aircraft details").get_attribute(
                "href"
            )
        )

    for i, aircraft_link in enumerate(aircraft_links):
        logging.info(f"Reconfiguring seat on Aircraft {i+1}")
        driver.get(aircraft_link + "/reconfigure")
        _clear_all_and_enter(
            [
                (driver.find_element("id", "ecoManualInput"), seat_config["economy"]),
                (driver.find_element("id", "busManualInput"), seat_config["business"]),
                (driver.find_element("id", "firstManualInput"), seat_config["first"]),
                (driver.find_element("id", "cargoManualInput"), seat_config["cargo"]),
                (
                    driver.find_element("id", "aircraft_name"),
                    f"{hub}-{destination}-{i}",
                ),
            ]
        )
        driver.find_element(
            By.XPATH, '//input[@value="Confirm the reconfiguration"]'
        ).submit()


def reconfigure_flight_seats(
    driver: WebDriver,
    hub: str,
    destination: str,
    seat_config: WaveStat,
):
    _select_route(driver, f"{hub} - {destination}")
    aircrafts = driver.find_elements(By.XPATH, '//div[@class="aircraftListView"]/div')
    aircraft_links = []
    for aircraft in aircrafts:
        aircraft_links.append(
            aircraft.find_element(By.LINK_TEXT, "Aircraft details").get_attribute(
                "href"
            )
        )

    for i, aircraft_link in enumerate(aircraft_links):
        logging.info(f"Reconfiguring seat on Aircraft {i+1}")
        driver.get(aircraft_link + "/reconfigure")
        _clear_all_and_enter(
            [
                (driver.find_element("id", "ecoManualInput"), seat_config.economy),
                (driver.find_element("id", "busManualInput"), seat_config.business),
                (driver.find_element("id", "firstManualInput"), seat_config.first),
                (driver.find_element("id", "cargoManualInput"), seat_config.cargo),
                (
                    driver.find_element("id", "aircraft_name"),
                    f"{hub}-{destination}-{i}",
                ),
            ]
        )
        driver.find_element(
            By.XPATH, '//input[@value="Confirm the reconfiguration"]'
        ).submit()
