import argparse
import logging
import sys
import traceback
from datetime import datetime
from typing import List

import pandas as pd

from tycoon.utils.airline_manager import (
    get_all_routes,
    login,
    reconfigure_flight_seats,
    route_stats,
)
from tycoon.utils.command import Command
from tycoon.utils.data import RouteStats
from tycoon.utils.noway import find_seat_config
from tycoon.utils.store import save_hub, get_hub


class AnalyseHub(Command):
    @classmethod
    def options(cls, parser: argparse.ArgumentParser):
        sub_parser = parser.add_parser("analyse_hub", help="Analyse all routes in hub")
        sub_parser.add_argument(
            "--nth_best_config",
            "-n",
            type=int,
            help="Configure with the nth best seat config based on turnover (Default: 2)",
            default=2,
        )
        sub_parser.add_argument(
            "--output_dir",
            "-o",
            type=str,
            help="Store all outputs in this directory (Default: ./)",
            default="./",
        )
        super().options(sub_parser)

    def run(self):
        login(self.driver)
        _routes = get_all_routes(self.driver, self.options.hub)
        _routes = list(filter(None, _routes))
        df = get_hub(self.options.hub)
        logging.info(f"Found {len(_routes)} routes in hub {self.options.hub}")
        logging.debug(f"Destinations: {_routes}")
        df = self._fetch_route_stats(df, self.options.hub, _routes)
        save_hub(self.options.hub, df, self.options.output_dir)
        df = self._mark_reconfigure(df)
        save_hub(self.options.hub, df, self.options.output_dir)
        df = self._reconfigure(df, self.options.hub, self.options.nth_best_config)
        save_hub(self.options.hub, df, self.options.output_dir)

    def _reconfigure(self, df: pd.DataFrame, hub: str, nth_best_config: int):
        for destination in df[df["reconfigure"] == True]["destination"].to_list():
            logging.info(f"Reconfiguring {hub} to {destination}")
            dest_idx = df[df["destination"] == destination].index[0]
            route_stats = RouteStats.from_json(df.loc[dest_idx, "raw_stat"])
            reconfigure_flight_seats(
                self.driver,
                hub,
                destination,
                route_stats.wave_stats[
                    list(route_stats.wave_stats.keys())[-nth_best_config]
                ],
            )
            df.loc[dest_idx, "reconfigure"] = False

        return df

    def _mark_reconfigure(self, df: pd.DataFrame) -> pd.DataFrame:
        df["reconfigure"] = False
        df.loc[df.economy_remaining_demand < 0, "reconfigure"] = True
        df.loc[df.business_remaining_demand < 0, "reconfigure"] = True
        df.loc[df.first_remaining_demand < 0, "reconfigure"] = True
        df.loc[df.cargo_remaining_demand < 0, "reconfigure"] = True
        return df

    def _extract_stats(
        self, df: pd.DataFrame, dest_idx: int, _rs: RouteStats
    ) -> pd.DataFrame:
        df.loc[
            dest_idx,
            ["economy_demand", "economy_remaining_demand", "economy_price"],
        ] = [
            _rs.economy.demand,
            _rs.economy.remaining_demand,
            _rs.economy.price,
        ]
        df.loc[
            dest_idx,
            ["business_demand", "business_remaining_demand", "business_price"],
        ] = [
            _rs.business.demand,
            _rs.business.remaining_demand,
            _rs.business.price,
        ]
        df.loc[dest_idx, ["first_demand", "first_remaining_demand", "first_price"]] = [
            _rs.first.demand,
            _rs.first.remaining_demand,
            _rs.first.price,
        ]
        df.loc[dest_idx, ["cargo_demand", "cargo_remaining_demand", "cargo_price"]] = [
            _rs.cargo.demand,
            _rs.cargo.remaining_demand,
            _rs.cargo.price,
        ]
        df.loc[
            dest_idx,
            ["scheduled_flights_count", "raw_stat"],
        ] = [len(_rs.scheduled_flights), _rs.to_json()]
        df.loc[dest_idx, "updated_at"] = pd.to_datetime(datetime.utcnow())
        return df

    def _fetch_route_stats(
        self, df: pd.DataFrame, hub: str, routes: List[str]
    ) -> pd.DataFrame:
        for _route in routes:
            now = datetime.utcnow()
            dest_idx = -1
            try:
                dest_idx = df[df["destination"] == _route].index[0]
            except IndexError:
                if not df.empty:
                    dest_idx = df.iloc[-1].name + 1
                else:
                    dest_idx = 0
                df.loc[dest_idx, "destination"] = _route
                df.loc[dest_idx, "hub"] = hub
                df.loc[dest_idx, "created_at"] = pd.to_datetime(now)
            try:
                _rs = route_stats(self.driver, hub, _route)
                _rs = find_seat_config(
                    self.driver,
                    hub,
                    _route,
                    self.options.aircraft_make,
                    self.options.aircraft_model,
                    _rs,
                    False,
                )
                df = self._extract_stats(df, dest_idx, _rs)
                logging.info(f"Processed destination {_route}")
                logging.debug(f"Route stat for {_route} = {_rs}")
            except Exception as ex:
                df.loc[dest_idx, "error"] = str(ex)
                logging.error(f"Error processing {hub} to {_route}. Ex={ex}")
                logging.error(traceback.print_exception(*sys.exc_info()))

        return df
