import logging
import time
from typing import Dict, Any, List

from retry import retry
import pandas as pd
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from tycoon.utils.browser import js_click
from tycoon.utils.data import (
    CircuitInfo,
    CircuitRow,
    RouteStats,
    WaveStat,
    decode_cost,
    non_decimal,
)


@retry(ElementClickInterceptedException, delay=5, tries=6, logger=None)
def _change_to_airport_codes(driver):
    try:
        for el in driver.find_elements(By.LINK_TEXT, "Quick Entry"):
            el.click()
    except NoSuchElementException:
        pass


def _clear_previous_configs(driver):
    rows = driver.find_elements(
        By.XPATH, '//*[@id="nwy_seatconfigurator_circuitinfo"]/table/tbody/tr'
    )
    for row in rows:
        try:
            row.find_element(By.XPATH, "td[10]/input").click()
        except (NoSuchElementException, ElementClickInterceptedException):
            pass


@retry(ElementClickInterceptedException, delay=5, tries=6, logger=None)
def _add_to_circuit(driver):
    js_click(driver, driver.find_element("id", "add2circuit_button"))


def _fillin_route_stats(driver, source: str, destination: str, route_stats: RouteStats):
    cf_hub_src = driver.find_element("id", "cf_hub_src")
    cf_hub_src.send_keys(source)
    cf_hub_dst = driver.find_element("id", "cf_hub_dst")
    cf_hub_dst.send_keys(destination)

    form_map = {
        "auditprice_eco": route_stats.economy.price,
        "auditprice_bus": route_stats.business.price,
        "auditprice_first": route_stats.first.price,
        "auditprice_cargo": route_stats.cargo.price,
        "demand_eco": route_stats.economy.demand,
        "demand_bus": route_stats.business.demand,
        "demand_first": route_stats.first.demand,
        "demand_cargo": route_stats.cargo.demand,
    }
    for k, v in form_map.items():
        driver.find_element("id", k).send_keys(v)

    _add_to_circuit(driver)


@retry(
    (NoSuchElementException, ElementClickInterceptedException),
    delay=5,
    tries=6,
    logger=None,
)
def _calculate_seat_config(driver, no_negative=False):
    if no_negative:
        js_click(driver, driver.find_element("id", "nonegativeconfig"))

    js_click(driver, driver.find_element("id", "calculate_button"))


def _select_wave(driver, wave: int):
    try:
        wave_selector = Select(
            driver.find_element(By.NAME, f"nwy_seatconfigurator_wave_{wave-1}_selector")
        )
        wave_selector.select_by_visible_text(str(wave))
        return wave
    except NoSuchElementException:
        logging.info(f"No config for wave: {wave}, mush have reached max waves")


@retry(NoSuchElementException, delay=5, tries=6, logger=None)
def _extract_wave_config(driver, wave: int) -> WaveStat:
    wave_stat_el = driver.find_element("id", f"nwy_seatconfigurator_wave_{wave}_stats")
    seat_config_el = wave_stat_el.find_elements(
        By.XPATH,
        "table[1]/tbody/tr[3]/td",
    )
    total_seat_config_el = wave_stat_el.find_elements(
        By.XPATH,
        "table[1]/tbody/tr[4]/td",
    )

    return WaveStat(
        no=wave,
        economy=int(seat_config_el[1].text),
        business=int(seat_config_el[2].text),
        first=int(seat_config_el[3].text),
        cargo=int(seat_config_el[4].text),
        turnover_per_wave=decode_cost(seat_config_el[5].text),
        roi=float(non_decimal.sub("", seat_config_el[6].text)),
        total_turnover=decode_cost(total_seat_config_el[5].text),
        turnover_days=int(non_decimal.sub("", total_seat_config_el[6].text)),
        max_configured=wave_stat_el.find_element(
            By.XPATH, "table[2]/tbody/tr[3]/td[9]"
        ).text,
    )


def _scan_seat_configs(driver, maxWave=50) -> Dict[int, WaveStat]:
    wave_stats = {}
    for wave in range(1, maxWave):
        if wave != 1:
            if not _select_wave(driver, wave):
                break

        wave_stats[wave] = _extract_wave_config(driver, wave)

    return wave_stats


def _select_option(driver, id: str, value: Any):
    ele = Select(driver.find_element("id", id))
    for option in ele.options:
        if str(value).lower() in option.text.lower():
            option.click()


def _select_aircraft(driver, aircraft_make: str, aircraft_model: str):
    cf_aircraftmake = Select(driver.find_element("id", "cf_aircraftmake"))
    for option in cf_aircraftmake.options:
        if aircraft_make.lower() in option.text.lower():
            option.click()

    cf_aircraftmodel = Select(driver.find_element("id", "cf_aircraftmodel"))
    for option in cf_aircraftmodel.options:
        if f"{aircraft_model.lower()} (" in option.text.lower():
            option.click()


def find_seat_config(
    driver,
    source: str,
    destination: str,
    aircraft_make: str,
    aircraft_model: str,
    route_stats: RouteStats,
    no_negative=False,
) -> RouteStats:
    logging.info(
        f"Finding seat configs for {source} to {destination} with {aircraft_make} {aircraft_model}"
    )
    driver.get("https://destinations.noway.info/en/seatconfigurator/index.html")
    _clear_previous_configs(driver)
    _select_option(driver, "cf_aircraftmake", aircraft_make)
    _select_option(driver, "cf_aircraftmodel", aircraft_model)

    _change_to_airport_codes(driver)
    _fillin_route_stats(driver, source, destination, route_stats)

    time.sleep(5)
    _calculate_seat_config(driver, no_negative)
    route_stats.wave_stats = _scan_seat_configs(driver)
    return route_stats


def find_seat_config_for_multiple_routes(
    driver,
    source: str,
    destinations: List[str],
    aircraft_make: str,
    aircraft_model: str,
    route_stats_list: List[RouteStats],
    no_negative=False,
) -> Dict[int, WaveStat]:
    logging.info(
        f"Finding seat configs for {source} to {destinations} with {aircraft_make} {aircraft_model}"
    )
    driver.get("https://destinations.noway.info/en/seatconfigurator/index.html")
    _clear_previous_configs(driver)
    _select_option(driver, "cf_aircraftmake", aircraft_make)
    _select_option(driver, "cf_aircraftmodel", aircraft_model)

    _change_to_airport_codes(driver)
    for idx, route_stats in enumerate(route_stats_list):
        _fillin_route_stats(driver, source, destinations[idx], route_stats)

    time.sleep(5)
    _calculate_seat_config(driver, no_negative)
    return _scan_seat_configs(driver)


def _scrape_route_details(driver) -> List[List[str]]:
    routes_table = driver.find_element("id", "routefinderresults")
    routes = [["id", "country", "IATA", "cat", "stars", "duration", "distance"]]
    for idx, row in enumerate(routes_table.find_elements(By.XPATH, "tbody/tr")):
        routes.append(
            [
                idx,
                row.find_element(By.XPATH, "td[1]").text,
                row.find_element(By.XPATH, "td[2]").text,
                row.find_element(By.XPATH, "td[3]").text,
                row.find_element(By.XPATH, "td[4]").text,
                row.find_element(By.XPATH, "td[5]").text,
                row.find_element(By.XPATH, "td[6]").text,
            ]
        )
    logging.info(f"Found {len(routes)-1} routes with given config")
    logging.debug(f"Found routes:\n{routes}")
    return routes


def find_routes_from(
    driver,
    hub: str,
    aircraft_make: str,
    aircraft_model: str,
    min_duration: int,
    max_duration: int,
) -> List[List[str]]:
    logging.info(
        f"Finding routes from {hub} with {aircraft_make} {aircraft_model} and duration between {min_duration} <> {max_duration} hours"
    )
    driver.get("https://destinations.noway.info/en/routefinder/index.html")
    _change_to_airport_codes(driver)
    cf_hub_src = driver.find_element("id", "cf_hub_src")
    cf_hub_src.send_keys(hub)
    _select_option(driver, "aircraftmake", aircraft_make)
    _select_option(driver, "aircraftmodel", aircraft_model)
    _select_option(driver, "route_duration_from_hh", min_duration)
    _select_option(driver, "route_duration_to_hh", max_duration)
    js_click(driver, driver.find_element("id", "df_search"))
    time.sleep(5)
    return _scrape_route_details(driver)


def _fillin_circuit_info(driver, source: str, excluded_dest: str, hours: int):
    cf_hub_src = driver.find_element("id", "cf_hub_src")
    cf_hub_src.send_keys(source)
    elem = driver.find_element("id", "cf_hub_list_exclude")
    elem.send_keys(excluded_dest)
    circut = Select(driver.find_element("id", "cf_config_circuit_length"))
    circut.select_by_visible_text(f"{hours} hours")


def _get_circuit_info(driver, next_id: int, new_circuit_status: int) -> CircuitInfo:
    circuit_rows = []
    for idx, element in enumerate(
        driver.find_elements(
            By.XPATH,
            '//*[@id="nwy_circuitfinder_circuit_content"]/table/tbody/tr/td/table[1]/tbody/tr',
        )
    ):
        if idx < 2:
            # Skip headers
            continue

        try:
            circuit_rows.append(
                CircuitRow(
                    no=int(element.find_element(By.XPATH, "td[1]").text),
                    destination=element.find_element(By.XPATH, "td[2]").text,
                    country=element.find_element(By.XPATH, "td[3]").text,
                    cat=int(element.find_element(By.XPATH, "td[4]").text),
                    stars=int(element.find_element(By.XPATH, "td[5]").text),
                    distance=element.find_element(By.XPATH, "td[6]").text,
                    time=element.find_element(By.XPATH, "td[7]").text,
                )
            )
        except Exception:
            break

    circuit_rows
    return CircuitInfo(id=next_id, rows=circuit_rows, status=new_circuit_status)


def find_circuit(
    driver,
    source: str,
    exclude_routes: str,
    hours: int,
    aircraft_make: str,
    aircraft_model: str,
    next_id: int,
    new_circuit_status=3,
) -> CircuitInfo:
    driver.get("https://destinations.noway.info/en/circuitfinder/index.html")
    _select_aircraft(driver, aircraft_make, aircraft_model)
    _change_to_airport_codes(driver)
    _fillin_circuit_info(driver, source, exclude_routes, hours)
    js_click(driver, driver.find_element("id", "cf_search"))
    time.sleep(10)
    return _get_circuit_info(driver, next_id, new_circuit_status)


def print_wave_stats(stats: Dict[int, WaveStat]):
    df = pd.DataFrame()
    for k, v in stats.items():
        df.loc[k, "wave_no"] = v.no
        df.loc[k, "economy"] = v.economy
        df.loc[k, "business"] = v.business
        df.loc[k, "first"] = v.first
        df.loc[k, "cargo"] = v.cargo
        df.loc[k, "turnover_per_wave"] = v.turnover_per_wave
        df.loc[k, "roi"] = v.roi
        df.loc[k, "total_turnover"] = v.total_turnover
        df.loc[k, "turnover_days"] = v.turnover_days
        df.loc[k, "max_configured"] = v.max_configured
    print(df)
