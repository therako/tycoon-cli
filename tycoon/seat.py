import argparse
import pandas as pd
import logging
import time
import os

from tycoon.utils.airline_manager import login
from tycoon.utils.browser import js_click
from tycoon.utils.command import Command
from tycoon.utils.browser import js_click
from retry import retry
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
)
from tycoon.utils.data import RouteStats, non_decimal, split_destination, WaveStat


class Seat(Command):
    @classmethod
    def options(cls, parser: argparse.ArgumentParser):
        sub_parser = parser.add_parser("seat", help="Find Seat config for routes")
        super().options(sub_parser)
        sub_parser.add_argument(
            "destinations",
            type=split_destination,
            help="""
                List of destination airport code (comma seperated)
                eg: TFS,ZRH,AGP,CPH,ARN,GVA
            """,
        )
        sub_parser.add_argument(
            "--allow_negative",
            "-an",
            action="store_true",
            help="""
                Allow negative config of seats (Default: False)
            """,
        )

    def clear_previous_configs(self):
        rows = self.driver.find_elements(
            By.XPATH, '//*[@id="nwy_seatconfigurator_circuitinfo"]/table/tbody/tr'
        )
        for row in rows:
            try:
                row.find_element(By.XPATH, "td[10]/input").click()
            except NoSuchElementException:
                pass

    def seat_configs_df(self, wave_stats) -> pd.DataFrame:
        df = pd.DataFrame(wave_stats)
        df["total_turnover"] = pd.to_numeric(df["total_turnover"], downcast="integer")
        df["turnover_per_wave"] = pd.to_numeric(
            df["turnover_per_wave"], downcast="integer"
        )
        df.loc[:, "total_turnover_str"] = df["total_turnover"].map("{:,}".format)
        df["note"] = ""
        df.iloc[df["roi"].idxmax(), df.columns.get_loc("note")] = "Best ROI"
        df.iloc[
            df["total_turnover"].idxmax(), df.columns.get_loc("note")
        ] = "Best Turnover"
        print(df)
        return df

    @retry(
        (NoSuchElementException, ElementClickInterceptedException),
        delay=5,
        tries=6,
        logger=None,
    )
    def calculate_seat_config(self):
        if not self.options.allow_negative:
            js_click(self.driver, self.driver.find_element("id", "nonegativeconfig"))

        js_click(self.driver, self.driver.find_element("id", "calculate_button"))

    @retry(ElementClickInterceptedException, delay=5, tries=6, logger=None)
    def change_to_airport_codes(self):
        try:
            for el in self.driver.find_elements(By.LINK_TEXT, "Quick Entry"):
                el.click()
        except NoSuchElementException:
            pass

    def fillin_route_stats(self, source: str, destination: str):
        logging.info(f"Finding route stats from {source} to {destination}")
        cf_hub_src = self.driver.find_element("id", "cf_hub_src")
        cf_hub_src.send_keys(source)
        cf_hub_dst = self.driver.find_element("id", "cf_hub_dst")
        cf_hub_dst.send_keys(destination)

        route_stats: RouteStats = self.read_route_stats(source, destination)
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
            self.driver.find_element("id", k).send_keys(v)

        self.add_to_circuit()

    @retry(ElementClickInterceptedException, delay=5, tries=6, logger=None)
    def add_to_circuit(self):
        js_click(self.driver, self.driver.find_element("id", "add2circuit_button"))

    def scan_seat_configs(self, maxWave=10):
        wave_stats = []
        for wave in range(1, maxWave):
            if wave != 1:
                if not self.select_wave(wave):
                    break

            wave_stats.append(self.extract_wave_config(wave))

        return wave_stats

    @retry(NoSuchElementException, delay=5, tries=6, logger=None)
    def extract_wave_config(self, wave: int):
        wave_stat_el = self.driver.find_element(
            "id", f"nwy_seatconfigurator_wave_{wave}_stats"
        )
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
            turnover_per_wave=self.decodeCost(seat_config_el[5].text),
            roi=float(non_decimal.sub("", seat_config_el[6].text)),
            total_turnover=self.decodeCost(total_seat_config_el[5].text),
            turnover_days=int(non_decimal.sub("", total_seat_config_el[6].text)),
            max_configured=wave_stat_el.find_element(
                By.XPATH, "table[2]/tbody/tr[3]/td[9]"
            ).text,
        )

    def select_wave(self, wave: int):
        try:
            wave_selector = Select(
                self.driver.find_element(
                    By.NAME, f"nwy_seatconfigurator_wave_{wave-1}_selector"
                )
            )
            wave_selector.select_by_visible_text(str(wave))
            return wave
        except NoSuchElementException:
            print(f"No config for wave: {wave}")

    def read_route_stats(self, source: str, destination: str):
        stats_path = f"tmp/{source}/{destination}.json"
        if not os.path.exists(stats_path):
            raise Exception(f"Can't find stats at {stats_path}")

        with open(stats_path, "r") as f:
            return RouteStats.from_json(f.read())

    def config_metadata(self):
        cf_aircraftmake = Select(self.driver.find_element("id", "cf_aircraftmake"))
        for option in cf_aircraftmake.options:
            if self.options.aircraft_make.lower() in option.text.lower():
                option.click()

        cf_aircraftmodel = Select(self.driver.find_element("id", "cf_aircraftmodel"))
        for option in cf_aircraftmodel.options:
            if f"{self.options.aircraft_model.lower()} (" in option.text.lower():
                option.click()

        self.change_to_airport_codes()

    def find_seat_config(self) -> pd.DataFrame:
        self.driver.get(
            "https://destinations.noway.info/en/seatconfigurator/index.html"
        )
        self.clear_previous_configs()
        self.config_metadata()
        for destination in self.options.destinations:
            self.fillin_route_stats(self.options.hub, destination)

        time.sleep(5)
        self.calculate_seat_config()
        wave_stats = self.scan_seat_configs()
        self.clear_previous_configs()
        return self.seat_configs_df(wave_stats)

    def run(self):
        login(self.driver)
        # for destination in self.options.destinations:
        # extract_route_price_stats(self.driver, self.options.hub, destination)
        # self.find_seat_config()
