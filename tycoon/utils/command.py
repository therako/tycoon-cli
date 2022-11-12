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
            help="Aircraft maker name as per Airline Tycoon eg., Ilyushin (Default: Airbus)",
            default="Airbus",
        )
        parser.add_argument(
            "--aircraft_model",
            "-a",
            help="Aircraft model name for the Aircraft maker eg., 96-300 (Default: A380-800)",
            default="A380-800",
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
        parser.add_argument(
            "--firefox",
            action="store_true",
            help="Use firefox instead of chrome",
        )
        parser.add_argument(
            "--tmp_folder",
            "-tmp",
            type=str,
            help="""
                Where all the data will stored (Default: ./tmp)
            """,
            default="./tmp",
        )

    def __init__(self, driver: WebDriver, options: Any) -> None:
        self.driver: WebDriver = driver
        self.options = options
