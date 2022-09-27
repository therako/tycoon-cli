import argparse
import logging
import os
from tycoon.utils.airline_manager import (
    buy_route,
    find_hub_id,
    get_all_routes,
    login,
    reconfigure_flight_seats,
    route_stats,
)
from tycoon.utils.command import Command
from tycoon.utils.data import RouteStats
from tycoon.utils.noway import find_routes_from, find_seat_config
import pandas as pd
from enum import Enum


class Status(Enum):
    UNRESOLVED = 1
    PRE_EXISTING = 2
    DEMAND = 3
    SEAT_CONFIG = 4
    SCHEDULED = 5
    NEGATIVE_DEMAND = 6
    RECONFIGURED = 7
    PERFECT = 8
    UNKNOWN_ERROR = 20


class LongHauls(Command):
    @classmethod
    def options(cls, parser: argparse.ArgumentParser):
        sub_parser = parser.add_parser(
            "long_hauls", help="Find & Scheduler long haul flights for the hub"
        )
        sub_parser.add_argument(
            "--min_duration",
            "-min",
            type=int,
            help="""
                Minimum flight duration in hours (Default: 20 hours)
            """,
            default=20,
        )
        sub_parser.add_argument(
            "--max_duration",
            "-max",
            type=int,
            help="""
                Maximum flight duration in hours (Default: 24 hours)
            """,
            default=24,
        )
        sub_parser.add_argument(
            "--allow_negative",
            "-an",
            action="store_true",
            help="""
                Allow negative config of seats (Default: False)
            """,
        )
        sub_parser.add_argument(
            "--nth_best_config",
            "-n",
            type=int,
            help="Configure with the nth best seat config based on turnover (Default: 2)",
            default=2,
        )
        super().options(sub_parser)

    def _find_routes(self, data_file: str):
        routes = find_routes_from(
            self.driver,
            self.options.hub,
            self.options.aircraft_make,
            self.options.aircraft_model,
            self.options.min_duration,
            self.options.max_duration,
        )
        routes_df = pd.DataFrame(routes[1:], columns=routes[0])
        routes_df = routes_df.set_index("id")
        routes_df["status"] = Status.UNRESOLVED.value
        return routes_df

    def _save_data(self):
        self.routes_df.to_csv(self.data_file)
        logging.debug(self.routes_df)
        logging.info(f"Stored routes in {self.data_file}")

    def _mark_pre_existing(self):
        df = self.routes_df[self.routes_df["status"] == Status.UNRESOLVED.value]
        if not df.empty:
            bought_routes = list(
                filter(None, get_all_routes(self.driver, self.options.hub))
            )
            self.routes_df.loc[
                self.routes_df["IATA"].isin(bought_routes), "status"
            ] = Status.PRE_EXISTING.value
            self._save_data()

    def _buy_new_routes(self):
        df = self.routes_df[self.routes_df["status"] != Status.PRE_EXISTING.value]
        hub_id = find_hub_id(self.driver, self.options.hub)
        for row in df.itertuples():
            try:
                buy_route(
                    self.driver,
                    self.options.hub,
                    row.IATA,
                    hub_id,
                )
            except Exception as ex:
                self.routes_df.loc[row.Index, "error"] = ex
                self.routes_df.loc[row.Index, "status"] = Status.UNKNOWN_ERROR.value
        self._save_data()
        self._mark_pre_existing()
        df = self.routes_df[self.routes_df["status"] != Status.PRE_EXISTING.value]
        logging.error(f"Missing routes to: {df.IATA.values}")

    def _fetch_demands(self):
        df = self.routes_df[self.routes_df["status"] == Status.PRE_EXISTING.value]
        for row in df.itertuples():
            self.routes_df.loc[row.Index, "route_stats"] = route_stats(
                self.driver, self.options.hub, row.IATA
            ).to_json()
            self.routes_df.loc[row.Index, "status"] = Status.DEMAND.value
            logging.info(f"Updated route_stats for {self.options.hub} - {row.IATA}")
            self._save_data()

    def _find_seat_configs(self):
        df = self.routes_df[self.routes_df["status"] == Status.DEMAND.value]
        for row in df.itertuples():
            _rs = RouteStats.from_json(self.routes_df.loc[row.Index, "route_stats"])
            self.routes_df.loc[row.Index, "route_stats"] = find_seat_config(
                self.driver,
                self.options.hub,
                row.IATA,
                self.options.aircraft_make,
                self.options.aircraft_model,
                _rs,
                self.options.allow_negative,
            ).to_json()
            self.routes_df.loc[row.Index, "status"] = Status.SEAT_CONFIG.value
            logging.info(f"Updated seat_configs for {self.options.hub} - {row.IATA}")
            self._save_data()

    def _mark_negative_demands(self):
        df = self.routes_df[self.routes_df["status"] == Status.SEAT_CONFIG.value]
        for row in df.itertuples():
            _rs = RouteStats.from_json(self.routes_df.loc[row.Index, "route_stats"])
            if (
                int(_rs.economy.remaining_demand) < 0
                or int(_rs.business.remaining_demand) < 0
                or int(_rs.first.remaining_demand) < 0
                or int(_rs.cargo.remaining_demand) < 0
            ):
                logging.info(
                    f"Found negative demand in {self.options.hub} - {row.IATA}, {_rs}"
                )
                self.routes_df.loc[row.Index, "status"] = Status.NEGATIVE_DEMAND.value
                self._save_data()

    def _reconfigure_wrong_flights(self):
        df = self.routes_df[self.routes_df["status"] == Status.NEGATIVE_DEMAND.value]
        for row in df.itertuples():
            _rs = RouteStats.from_json(self.routes_df.loc[row.Index, "route_stats"])
            logging.info(f"Reconfigure {self.options.hub} - {row.IATA} flights...")
            reconfigure_flight_seats(
                self.driver,
                self.options.hub,
                row.IATA,
                _rs.wave_stats[
                    list(_rs.wave_stats.keys())[-self.options.nth_best_config]
                ],
            )
            _new_rs = route_stats(self.driver, self.options.hub, row.IATA)
            _rs.economy = _new_rs.economy
            _rs.business = _new_rs.business
            _rs.first = _new_rs.first
            _rs.cargo = _new_rs.cargo
            _rs.scheduled_flights = _new_rs.scheduled_flights
            self.routes_df.loc[row.Index, "route_stats"] = _rs.to_json()
            self.routes_df.loc[row.Index, "status"] = Status.RECONFIGURED.value
            logging.info(f"Reconfigured {self.options.hub} - {row.IATA} flights")
            self._save_data()

    def run(self):
        self.data_file = os.path.join(
            self.options.tmp_folder, f"{self.options.hub}_routes_df.csv"
        )
        if os.path.exists(self.data_file):
            logging.info(f"Found data at {self.data_file}")
            self.routes_df = pd.read_csv(self.data_file, index_col=["id"])
        else:
            self.routes_df = self._find_routes(self.data_file)

        login(self.driver)
        self._mark_pre_existing()
        self._buy_new_routes()
        self._fetch_demands()
        self._find_seat_configs()
        self._mark_negative_demands()
        self._reconfigure_wrong_flights()
