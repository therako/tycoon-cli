import argparse
from selenium.webdriver.remote.webdriver import WebDriver
from typing import Any


class Command:
    @classmethod
    def options(cls, parser):
        parser.add_argument(
            "hub", help="Enter HUB name you need to extract route stats for"
        )
        parser.add_argument(
            "--aircraft_make",
            "-m",
            help="Aircraft maker name as per Airline Tycoon eg., Ilyushin (Default: Boeing)",
            default="Boeing",
        )
        parser.add_argument(
            "--aircraft_model",
            "-a",
            help="Aircraft model name for the Aircraft maker eg., 96-300 (Default: 747-400)",
            default="747-400",
        )
        parser.add_argument(
            "-d",
            "--debug",
            dest="debug_mode",
            action="store_true",
            help="Debug mode on.",
        )
        parser.add_argument(
            "--no_headless",
            "-nh",
            action="store_true",
            help="Disable headless and show browser",
        )

    def __init__(self, driver: WebDriver, options: Any) -> None:
        self.driver = driver
        self.options = options