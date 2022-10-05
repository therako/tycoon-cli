import argparse
import logging
import time

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

    def buy_aircraft(self, number: int):
        logging.info(
            f"Buying {number} of {self.options.aircraft_make} - {self.options.aircraft_model} to HUB {self.options.hub}"
        )
        self.driver.get(
            f"https://tycoon.airlines-manager.com/aircraft/buy/new/{self.options.aircraft_make.lower()}"
        )
        time.sleep(5)
        aircraft_list = self.driver.find_elements(
            By.XPATH, '//div[@class="aircraftList"]/div'
        )
        for aircraft in aircraft_list:
            if aircraft.get_attribute("id") == "noAircraftFound":
                continue
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
                el.send_keys(str(number))
                el.send_keys(Keys.ENTER)
                time.sleep(2)
                aircraft_hub = Select(self.driver.find_element("id", "aircraft_hub"))
                for option in aircraft_hub.options:
                    if self.options.hub.lower() in option.text.lower():
                        option.click()

                time.sleep(2)
                self.driver.find_element(
                    By.XPATH,
                    '//*[@id="buyAircraft_bucket"]/form/div[1]/div[1]/div[2]/span[1]/img',
                ).click()
                el = self.driver.find_element(
                    By.XPATH,
                    '//*[@id="buyAircraft_bucket"]/form/div[1]/div[1]/div[2]/span[2]/input[1]',
                )
                el.clear()
                el.send_keys(Keys.BACKSPACE * 1)
                el.send_keys(number)
                el.send_keys(Keys.ENTER)
                js_click(
                    self.driver,
                    self.driver.find_element(
                        By.XPATH,
                        '//*[@id="resumeBoxForJs"]/div[2]/form/div[2]/input',
                    ),
                )
                time.sleep(5)
                logging.info(
                    f"Bought {number} of {self.options.aircraft_model} to HUB {self.options.hub}"
                )
                rc = self.driver.find_element(By.XPATH, '//*[@id="ressource3"]').text
                logging.info(f"Remaining cash == ${rc}")
                return

        raise Exception("Error finding the aircraft to buy")

    def run(self):
        login(self.driver)
        if self.options.number >= 30:
            for i in range(0, int(self.options.number / 30)):
                logging.info(f"Buying in batch of 30, batch {i}...")
                self.buy_aircraft(30)
        else:
            self.buy_aircraft(self.options.number)
