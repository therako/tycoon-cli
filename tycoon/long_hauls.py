import argparse
import logging
import os
import re
from tycoon.utils.airline_manager import (
    assign_flights,
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
    RECONFIGURE = 7
    PERFECT = 8
    UNKNOWN_ERROR = 20


AIRCRAFT_SEAT_REGX = r"\((\d+)\/(\d+)\/(\d+)\)"


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
        logging.info(f"Stored routes in {self.data_file}")

    def _mark_pre_existing(self):
        df = self.routes_df[self.routes_df["status"] == Status.UNRESOLVED.value]
        if not df.empty:
            bought_routes = list(
                filter(None, get_all_routes(self.driver, self.options.hub))
            )
            self.routes_df.loc[
                df["IATA"].isin(bought_routes).index, "status"
            ] = Status.PRE_EXISTING.value
            self._save_data()

    def _fetch_demands(self, idx: int, row: pd.Series):
        self.routes_df.loc[idx, "route_stats"] = route_stats(
            self.driver, self.options.hub, row.IATA
        ).to_json()
        self.routes_df.loc[idx, "status"] = Status.DEMAND.value
        logging.info(f"Updated route_stats for {self.options.hub} - {row.IATA}")

    def _find_seat_configs(self, idx: int, row: pd.Series):
        _rs = RouteStats.from_json(self.routes_df.loc[idx, "route_stats"])
        self.routes_df.loc[idx, "route_stats"] = find_seat_config(
            self.driver,
            self.options.hub,
            row.IATA,
            self.options.aircraft_make,
            self.options.aircraft_model,
            _rs,
            self.options.allow_negative,
        ).to_json()
        self.routes_df.loc[idx, "status"] = Status.SEAT_CONFIG.value
        logging.info(f"Updated seat_configs for {self.options.hub} - {row.IATA}")

    def _check_configuration(self, idx: int, row: pd.Series):
        _rs = RouteStats.from_json(self.routes_df.loc[idx, "route_stats"])
        picked_config = _rs.wave_stats[
            list(_rs.wave_stats.keys())[-self.options.nth_best_config]
        ]
        for sf in _rs.scheduled_flights:
            seat_config = re.search(AIRCRAFT_SEAT_REGX, sf.seat_config)
            if (
                int(seat_config.group(1)) != int(picked_config.economy)
                or int(seat_config.group(2)) != int(picked_config.business)
                or int(seat_config.group(3)) != int(picked_config.first)
            ):
                self.routes_df.loc[idx, "status"] = Status.RECONFIGURE.value
                logging.info(
                    f"Seat config not matching {sf.seat_config} to {picked_config}"
                )
                return

        logging.info(f"All is perfect for {self.options.hub} - {row.IATA}")
        self.routes_df.loc[idx, "status"] = Status.PERFECT.value

    def _reconfigure_flights(self, idx: int, row: pd.Series):
        _rs = RouteStats.from_json(self.routes_df.loc[idx, "route_stats"])
        logging.info(f"Reconfigure {self.options.hub} - {row.IATA} flights...")
        reconfigure_flight_seats(
            self.driver,
            self.options.hub,
            row.IATA,
            _rs.wave_stats[list(_rs.wave_stats.keys())[-self.options.nth_best_config]],
        )
        _new_rs = route_stats(self.driver, self.options.hub, row.IATA)
        logging.debug(_new_rs)
        _rs.economy = _new_rs.economy
        _rs.business = _new_rs.business
        _rs.first = _new_rs.first
        _rs.cargo = _new_rs.cargo
        _rs.scheduled_flights = _new_rs.scheduled_flights
        self.routes_df.loc[idx, "route_stats"] = _rs.to_json()
        self.routes_df.loc[idx, "status"] = Status.SCHEDULED.value
        logging.info(f"ReconfigurE {self.options.hub} - {row.IATA} flights")

    def _schedule_flights(self, idx: int, row: pd.Series):
        _rs = RouteStats.from_json(self.routes_df.loc[idx, "route_stats"])
        assign_flights(
            self.driver,
            self.hub_id,
            self.options.hub,
            row.IATA,
            _rs,
            self.options.aircraft_model,
            self.options.nth_best_config,
        )
        self.routes_df.loc[idx, "status"] = Status.SCHEDULED.value
        logging.info(f"Scheduled flights for {self.options.hub} - {row.IATA}")

    def _buy_route(self, idx: int, row: pd.Series):
        try:
            buy_route(
                self.driver,
                self.options.hub,
                row.IATA,
                self.hub_id,
            )
            self.routes_df.loc[idx, "status"] = Status.PRE_EXISTING.value
        except Exception as ex:
            logging.error(f"Route {self.options.hub} - {row.IATA}", ex)
            self.routes_df.loc[idx, "error"] = ex
            self.routes_df.loc[idx, "status"] = Status.UNKNOWN_ERROR.value

    def run(self):
        self.data_file = os.path.join(
            self.options.tmp_folder, f"{self.options.hub}_routes_df.csv"
        )
        if os.path.exists(self.data_file):
            logging.info(f"Found data at {self.data_file}")
            self.routes_df = pd.read_csv(self.data_file, index_col=["id"])
        else:
            self.routes_df = self._find_routes(self.data_file)

        fnMap = {
            Status.UNRESOLVED.value: self._buy_route,
            Status.PRE_EXISTING.value: self._fetch_demands,
            Status.DEMAND.value: self._find_seat_configs,
            Status.SEAT_CONFIG.value: self._schedule_flights,
            Status.SCHEDULED.value: self._check_configuration,
            Status.RECONFIGURE.value: self._reconfigure_flights,
        }

        print(self.routes_df.groupby(["status"]).count()["IATA"])
        login(self.driver)
        try:
            self._mark_pre_existing()
            self.hub_id = find_hub_id(self.driver, self.options.hub)
            for idx in self.routes_df.index:
                row = self.routes_df.loc[idx]
                logging.debug(row)
                while fnMap.get(row.status, None):
                    logging.info(
                        f"Processing route to {row.IATA} with status {row.status} with {fnMap.get(row.status).__name__}"
                    )
                    fnMap.get(row.status)(idx, row)
                    self._save_data()
                    row = self.routes_df.loc[idx]
                    logging.debug(row)
        except Exception as ex:
            raise ex
        finally:
            self._save_data()
            print(self.routes_df.groupby(["status"]).count()["IATA"])
