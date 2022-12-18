import logging
import os
import re
import time
from retry import retry
from typing import List, Tuple

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select
from tycoon.utils.browser import js_click
from tycoon.utils.data import (
    RouteStat,
    RouteStats,
    ScheduledAircraftConfig,
    WaveStat,
    non_decimal,
)
from selenium.common.exceptions import NoSuchElementException


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


@retry(delay=5, tries=3)
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


def find_hub_id(driver, hub: str) -> int:
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
    hub_id = find_hub_id(driver, hub)
    driver.get(f"http://tycoon.airlines-manager.com/network/showhub/{hub_id}/linelist")
    route_elements = driver.find_elements(By.XPATH, '//*[@id="lineList"]/div')
    destinations = []
    for route_element in route_elements:
        destinations.append(_extract_destination(hub, route_element))

    logging.info(f"Found {len(destinations)} destinations at hub {hub}")
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


def buy_route(driver: WebDriver, hub: str, destination: str, hub_id: int):
    if not hub_id:
        raise Exception("Unknown hub")

    driver.get(
        f"http://tycoon.airlines-manager.com/network/newlinefinalize/{hub_id}/{destination.lower()}"
    )
    driver.find_element(By.XPATH, '//*[@id="linePurchaseForm"]/input').submit()
    logging.info(f"Bought route {hub} -- {destination}")


def _assigned_flight_count(driver, hub, destination):
    _select_route(driver, f"{hub} - {destination}")
    time.sleep(2)
    return int(
        driver.find_element(
            By.XPATH, '//div[@id="showLine"]/div[3]/ul[1]/li[2]/strong'
        ).text
    )


def _searchable_aircraft_model(raw: str):
    return raw.replace("Ił-", "")


def _select_flight(
    driver: WebDriver,
    hub_id: int,
    aircraft_model: str,
    sort_by="utilizationPercentageAsc",
):
    time.sleep(1)
    js_click(driver, driver.find_element(By.XPATH, f"//span[@data-hubid='{hub_id}']"))
    time.sleep(1)
    js_click(driver, driver.find_element(By.XPATH, f"//span[@data-hubid='{hub_id}']"))
    time.sleep(1)
    el = driver.find_element("id", "aircraftNameFilter")
    el.clear()
    el.send_keys(_searchable_aircraft_model(aircraft_model))
    time.sleep(1)
    js_click(
        driver,
        driver.find_element(By.CSS_SELECTOR, f"input[type='radio'][value='{sort_by}']"),
    )


def _check_for_free_aircraft(driver: WebDriver, hub, aircraft_model):
    time.sleep(1)
    try:
        use = driver.find_element(
            By.XPATH, "//*[@class='aircraftsBox']/div[1]/div[2]/span[1]/b"
        )
        if use.text != "0%":
            raise Exception(f"No free flights in HUB {hub} of type {aircraft_model}")
    except NoSuchElementException:
        raise Exception(f"No flights in HUB {hub} of type {aircraft_model}")


def _select_route_for_aircraft(driver: WebDriver, hub: str, destination: str):
    js_click(
        driver,
        driver.find_element(
            By.XPATH, f"//span[contains(text(), '{hub} / {destination}')]"
        ),
    )


def _schedule_a_flight(driver: WebDriver, hub_id, hub, destination, aircraft_model):
    driver.get("http://tycoon.airlines-manager.com/network/planning")
    _select_flight(driver, hub_id, aircraft_model)
    _check_for_free_aircraft(driver, hub, aircraft_model)
    _select_route_for_aircraft(driver, hub, destination)

    js_click(
        driver,
        driver.find_element(
            By.XPATH, '//table[@class="planningArea"]/tbody/tr[2]/td[3]'
        ),
    )
    js_click(
        driver,
        driver.find_element(
            By.XPATH, '//div[@id="planning"]/table[1]/tbody/tr[2]/td[1]/img'
        ),
    )
    js_click(driver, driver.find_element("id", "planningSubmit"))


@retry(delay=5, tries=5)
def assign_flights(
    driver: WebDriver,
    hub_id: int,
    hub: str,
    destination: str,
    route_stats: RouteStats,
    aircraft_model: str,
    nth_best_config: 2,
):
    best_config = route_stats.wave_stats[
        list(route_stats.wave_stats.keys())[-nth_best_config]
    ]
    logging.info(
        f"Configuring route {hub} - {destination} with best config:\n\t{best_config}"
    )
    assigned_aircrafts = _assigned_flight_count(driver, hub, destination)
    if assigned_aircrafts > 0 and assigned_aircrafts != len(
        route_stats.scheduled_flights
    ):
        logging.error(
            "The route has already scheduled flights that are outside of this script."
        )

    logging.info(
        f"Excluding already configured {assigned_aircrafts}, scheduing {best_config.no - assigned_aircrafts} flights"
    )
    for i in range(0, best_config.no - assigned_aircrafts):
        logging.info(f"Scheduling flight {i+1}...")
        _schedule_a_flight(driver, hub_id, hub, destination, aircraft_model)


@retry(delay=2, tries=5)
def remove_wrong_flights(
    driver: WebDriver,
    hub_id: int,
    hub: str,
    destination: str,
    config: RouteStat,
    aircraft_model: str,
):
    name_prefix = f"{hub}-{destination}"
    while True:
        assigned_aircrafts = _assigned_flight_count(driver, hub, destination)
        if assigned_aircrafts <= config.no:
            break

        logging.error(
            f"The route has {assigned_aircrafts-config.no} more flights than required"
        )
        driver.get("http://tycoon.airlines-manager.com/network/planning")
        _select_flight(driver, hub_id, name_prefix, sort_by="utilizationPercentageDesc")
        time.sleep(1)
        from IPython import embed

        embed()
        _check_assigned_flight(driver, hub, aircraft_model, name_prefix)
        js_click(driver, driver.find_element("id", "tableButtonClearSchedule"))
        time.sleep(1)
        js_click(driver, driver.find_element("id", "planningSubmit"))
        time.sleep(1)


def _check_assigned_flight(
    driver: WebDriver, hub: str, aircraft_model: str, name_prefix: str
):
    try:
        name = driver.find_element(By.XPATH, "//*[@class='aircraftsBox']/div[1]/div[1]")
        if name_prefix in name.text:
            return True

        raise Exception(
            f"Wrong flight, found flight {name.text} instead of {name_prefix}"
        )
    except NoSuchElementException:
        raise Exception(f"No flights in HUB {hub} of name {name_prefix}")


def buy_aircraft(
    driver: WebDriver,
    hub: str,
    destination: str,
    aircraft_make: str,
    aircraft_model: str,
    number: int,
    seat_config: WaveStat = None,
):
    logging.info(f"Buying {number} of {aircraft_make} - {aircraft_model} to HUB {hub}")
    driver.get(
        f"https://tycoon.airlines-manager.com/aircraft/buy/new/{aircraft_make.lower()}"
    )
    time.sleep(5)
    aircraft_list = driver.find_elements(By.XPATH, '//div[@class="aircraftList"]/div')
    for aircraft in aircraft_list:
        if aircraft.get_attribute("id") == "noAircraftFound":
            continue
        if (
            f"{aircraft_model.lower()} / {aircraft_make.lower()}"
            in aircraft.find_element(By.CLASS_NAME, "title").text.lower()
        ):
            js_click(
                driver,
                aircraft.find_element(By.XPATH, "form/div[1]/div[3]/div/span[1]/img"),
            )
            el = aircraft.find_element(
                By.XPATH, "form/div[1]/div[3]/div/span[2]/input[1]"
            )
            el.clear()
            el.send_keys(str(number))
            el.send_keys(Keys.ENTER)
            time.sleep(2)
            aircraft_hub = Select(driver.find_element("id", "aircraft_hub"))
            for option in aircraft_hub.options:
                if hub.lower() in option.text.lower():
                    option.click()

            time.sleep(2)
            driver.find_element(
                By.XPATH,
                '//*[@id="buyAircraft_bucket"]/form/div[1]/div[1]/div[2]/span[1]/img',
            ).click()
            el = driver.find_element(
                By.XPATH,
                '//*[@id="buyAircraft_bucket"]/form/div[1]/div[1]/div[2]/span[2]/input[1]',
            )
            if seat_config:
                _clear_all_and_enter(
                    [
                        (
                            driver.find_element(By.CSS_SELECTOR, ".ecoManualInput"),
                            seat_config.economy,
                        ),
                        (
                            driver.find_element(By.CSS_SELECTOR, ".busManualInput"),
                            seat_config.business,
                        ),
                        (
                            driver.find_element(By.CSS_SELECTOR, ".firstManualInput"),
                            seat_config.first,
                        ),
                        (
                            driver.find_element(By.CSS_SELECTOR, ".cargoManualInput"),
                            seat_config.cargo,
                        ),
                        (
                            driver.find_element(
                                By.CSS_SELECTOR, ".aircraftName"
                            ).find_element(By.XPATH, "div/input"),
                            f"{hub}-{destination}",
                        ),
                    ]
                )
            el.clear()
            el.send_keys(Keys.BACKSPACE * 1)
            el.send_keys(number)
            el.send_keys(Keys.ENTER)
            js_click(
                driver,
                driver.find_element(
                    By.XPATH,
                    '//*[@id="resumeBoxForJs"]/div[2]/form/div[2]/input',
                ),
            )
            time.sleep(5)
            logging.info(f"Bought {number} of {aircraft_model} to HUB {hub}")
            rc = driver.find_element(By.XPATH, '//*[@id="ressource3"]').text
            logging.info(f"Remaining cash == ${rc}")
            return

    raise Exception("Error finding the aircraft to buy")
