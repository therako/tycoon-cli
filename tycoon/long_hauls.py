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
    remove_wrong_flights,
    route_stats,
)
from tycoon.utils.command import Command
from tycoon.utils.data import RouteStats
from tycoon.utils.noway import find_routes_from, find_seat_config, print_wave_stats
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
                Minimum flight duration in hours (Default: 18 hours)
            """,
            default=18,
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
            default=False,
        )
        sub_parser.add_argument(
            "--nth_best_config",
            "-n",
            type=int,
            help="Configure with the nth best seat config based on turnover (Default: 2)",
            default=2,
        )
        sub_parser.add_argument(
            "--analyse",
            action="store_true",
            help="""
                Go back and all scheduled flights for config (Default: False)
            """,
            default=False,
        )
        sub_parser.add_argument(
            "--retry_failed",
            action="store_true",
            help="""
                Retry failed routes (Default: False)
            """,
            default=False,
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

    def _save_data(self, print_stats=False):
        self.routes_df.to_csv(self.data_file)
        logging.info(f"Stored routes in {self.data_file}")
        if print_stats:
            logging.info("***** Stats of stored *****")
            self.routes_df.groupby(["status"]).count()["IATA"].reset_index(
                name="count"
            ).apply(
                lambda x: logging.info(
                    f"{Status(x.status)}, no of routes: {x['count']}"
                ),
                axis=1,
            )
            logging.info("**********")

    def _mark_pre_existing(self):
        df = self.routes_df[self.routes_df["status"] == Status.UNRESOLVED.value]
        if not df.empty:
            bought_routes = list(
                filter(None, get_all_routes(self.driver, self.options.hub))
            )
            if df["IATA"].isin(bought_routes).any():
                self.routes_df.loc[
                    df["IATA"].isin(bought_routes).index, "status"
                ] = Status.PRE_EXISTING.value

    def _fetch_demands(self, idx: int, row: pd.Series):
        try:
            self.routes_df.loc[idx, "route_stats"] = route_stats(
                self.driver, self.options.hub, row.IATA
            ).to_json()
            self.routes_df.loc[idx, "status"] = Status.DEMAND.value
            logging.info(f"Updated route_stats for {self.options.hub} - {row.IATA}")
        except Exception as ex:
            logging.error(f"Route {self.options.hub} - {row.IATA}", ex)
            self.routes_df.loc[idx, "error"] = ex
            self.routes_df.loc[idx, "status"] = Status.UNKNOWN_ERROR.value

    def _find_seat_configs(self, idx: int, row: pd.Series):
        _rs = RouteStats.from_json(self.routes_df.loc[idx, "route_stats"])
        self.routes_df.loc[idx, "route_stats"] = find_seat_config(
            self.driver,
            self.options.hub,
            row.IATA,
            self.options.aircraft_make,
            self.options.aircraft_model,
            _rs,
            not self.options.allow_negative,
        ).to_json()
        self.routes_df.loc[idx, "status"] = Status.SEAT_CONFIG.value
        logging.info(f"Updated seat_configs for {self.options.hub} - {row.IATA}")

    def _configured_correct(self, idx: int, row: pd.Series, reset_status=True) -> bool:
        if reset_status:
            self._fetch_stats(idx, row)
        _rs = RouteStats.from_json(self.routes_df.loc[idx, "route_stats"])
        picked_config = _rs.wave_stats[
            list(_rs.wave_stats.keys())[-self.options.nth_best_config]
        ]
        if len(_rs.scheduled_flights) != picked_config.no:
            logging.error(
                f"No. of flight configured not matching, config: {len(_rs.scheduled_flights)}, required: {picked_config.no}"
            )
            remove_wrong_flights(
                self.driver,
                self.hub_id,
                self.options.hub,
                row.IATA,
                picked_config,
                self.options.aircraft_model,
            )
            return False

        for sf in _rs.scheduled_flights:
            seat_config = re.search(AIRCRAFT_SEAT_REGX, sf.seat_config)
            if (
                int(seat_config.group(1)) != int(picked_config.economy)
                or int(seat_config.group(2)) != int(picked_config.business)
                or int(seat_config.group(3)) != int(picked_config.first)
            ):
                if reset_status:
                    self.routes_df.loc[idx, "status"] = Status.RECONFIGURE.value
                    logging.error(
                        f"Seat config not matching {sf.seat_config} to {picked_config}"
                    )
                return False

        if reset_status:
            self.routes_df.loc[idx, "status"] = Status.PERFECT.value
            logging.info(f"All is perfect for {self.options.hub} - {row.IATA}")
        return True

    def _reconfigure_flights(self, idx: int, row: pd.Series):
        _rs = RouteStats.from_json(self.routes_df.loc[idx, "route_stats"])
        logging.info(f"Reconfigure {self.options.hub} - {row.IATA} flights...")
        reconfigure_flight_seats(
            self.driver,
            self.options.hub,
            row.IATA,
            _rs.wave_stats[list(_rs.wave_stats.keys())[-self.options.nth_best_config]],
        )
        self.routes_df.loc[idx, "status"] = Status.SCHEDULED.value

    def _fetch_stats(self, idx: int, row: pd.Series):
        _rs = RouteStats.from_json(self.routes_df.loc[idx, "route_stats"])
        _new_rs = route_stats(self.driver, self.options.hub, row.IATA)
        logging.debug(_new_rs)
        _rs.economy = _new_rs.economy
        _rs.business = _new_rs.business
        _rs.first = _new_rs.first
        _rs.cargo = _new_rs.cargo
        _rs.scheduled_flights = _new_rs.scheduled_flights
        self.routes_df.loc[idx, "route_stats"] = _rs.to_json()

    def _schedule_flights(self, idx: int, row: pd.Series):
        _rs = RouteStats.from_json(self.routes_df.loc[idx, "route_stats"])
        choosen_config = _rs.wave_stats[
            list(_rs.wave_stats.keys())[-self.options.nth_best_config]
        ]
        if len(_rs.scheduled_flights) >= choosen_config.no:
            if (
                len(set([x.model for x in _rs.scheduled_flights])) != 1
                or set([x.model for x in _rs.scheduled_flights]).pop().lower()
                != self.options.aircraft_model.lower()
            ):
                logging.error(
                    f"Route has different flight configured already: {_rs.scheduled_flights}"
                )
                raise Exception("Wrong aircraft config requested")

            logging.info(
                f"Route already has {choosen_config.no} flights configured, skipping."
            )
            self.routes_df.loc[idx, "status"] = Status.SCHEDULED.value
            return

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

    def _check_wrong_seat_configs(self):
        logging.info("Checking all configured flights for incorrect config...")
        selected_df = self.routes_df[
            self.routes_df["status"] != Status.UNKNOWN_ERROR.value
        ]
        for idx in selected_df.index:
            row = selected_df.loc[idx]
            _rs: RouteStats = RouteStats.from_json(row["route_stats"])
            if not self._configured_correct(idx, row, False):
                logging.info(f"Misconfig in route {self.options.hub} - {row.IATA}")
                if len(_rs.scheduled_flights) > 0:
                    logging.info(
                        f"Scheduled {len(_rs.scheduled_flights)} flights with config {_rs.scheduled_flights[-1]}"
                    )
                else:
                    logging.error("No flights scheduled here")
                logging.info(f"All configs:")
                print_wave_stats(_rs.wave_stats)
        logging.info("Done checking")
        logging.info("If any mistakes found run again with --analyse")

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
            Status.SCHEDULED.value: self._configured_correct,
            Status.RECONFIGURE.value: self._reconfigure_flights,
        }

        login(self.driver)
        try:
            self.hub_id = find_hub_id(self.driver, self.options.hub)
            if self.options.analyse:
                self.routes_df.loc[
                    self.routes_df["status"] == Status.PERFECT.value, "status"
                ] = Status.SEAT_CONFIG.value
                self._save_data(True)
            if self.options.retry_failed:
                self.routes_df.loc[
                    self.routes_df["status"] == Status.UNKNOWN_ERROR.value, "status"
                ] = Status.UNRESOLVED.value
                self._save_data(True)
            self._mark_pre_existing()
            self._save_data(True)
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
            self._check_wrong_seat_configs()
        except Exception as ex:
            raise ex
        finally:
            self._save_data(True)
