import argparse
import logging

from tycoon.utils.airline_manager import login
from tycoon.utils.browser import js_click
from tycoon.utils.command import Command
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select


class Aircraft(Command):
    @classmethod
    def options(cls, parser: argparse.ArgumentParser):
        sub_parser = parser.add_parser("aircraft", help="Buy new aircrafts")
        super().options(sub_parser)
        sub_parser.add_argument(
            "--number",
            "-n",
            type=int,
            help="No. of flights to buy (Default: 30)",
            default=30,
        )

    def buy_aircraft(self):
        logging.info(
            f"Buying {self.options.number} of {self.options.aircraft_make} - {self.options.aircraft_model} to HUB {self.options.hub}"
        )
        self.driver.get(
            f"https://tycoon.airlines-manager.com/aircraft/buy/new/{self.options.aircraft_make.lower()}"
        )

        aircraft_list = self.driver.find_elements(
            By.XPATH, '//div[@class="aircraftList"]/div'
        )
        for aircraft in aircraft_list:
            if (
                f"{self.options.aircraft_model.lower()} / {self.options.aircraft_make.lower()}"
                in aircraft.find_element(By.CLASS_NAME, "title").text.lower()
            ):
                js_click(
                    self.driver,
                    aircraft.find_element(
                        By.XPATH, "form/div[1]/div[3]/div/span[1]/img"
                    ),
                )
                el = aircraft.find_element(
                    By.XPATH, "form/div[1]/div[3]/div/span[2]/input[1]"
                )
                el.clear()
                el.send_keys(str(self.options.number))
                el.send_keys(Keys.ENTER)

                aircraft_hub = Select(self.driver.find_element("id", "aircraft_hub"))
                for option in aircraft_hub.options:
                    if self.options.hub.lower() in option.text.lower():
                        option.click()

                js_click(
                    self.driver,
                    self.driver.find_element(
                        By.XPATH,
                        '//*[@id="aircraft_buyNew_step3"]/div/div[2]/div[10]/div[2]/input',
                    ),
                )
                logging.info(
                    f"Bought {self.options.number} of {self.options.aircraft_model} to HUB {self.options.hub}"
                )

    def run(self):
        login(self.driver)
        self.buy_aircraft()
