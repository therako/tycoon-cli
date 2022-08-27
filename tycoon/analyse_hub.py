import argparse
from datetime import datetime
import logging
from typing import List
import pandas as pd

from tycoon.utils.airline_manager import get_all_routes, login, route_stats
from tycoon.utils.command import Command
from tycoon.utils.store import get_hub_df


class AnalyseHub(Command):
    @classmethod
    def options(cls, parser: argparse.ArgumentParser):
        sub_parser = parser.add_parser("analyse_hub", help="Analyse all routes in hub")
        super().options(sub_parser)

    def run(self):
        login(self.driver)
        _routes = get_all_routes(self.driver, self.options.hub)
        _routes = list(filter(None, _routes))
        _df = get_hub_df(self.options.hub)
        logging.info(f"Found {len(_routes)} routes in hub {self.options.hub}")
        logging.debug(f"Destinations: {_routes}")
        _df = self._fetch_route_stats(_df, self.options.hub, _routes)
        _df.to_csv(f"./{self.options.hub}.csv", index=False, header=True)

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
            df.loc[dest_idx, "updated_at"] = pd.to_datetime(now)
            try:
                _rs = route_stats(self.driver, hub, _route)
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
                df.loc[
                    dest_idx, ["first_demand", "first_remaining_demand", "first_price"]
                ] = [_rs.first.demand, _rs.first.remaining_demand, _rs.first.price]
                df.loc[
                    dest_idx, ["cargo_demand", "cargo_remaining_demand", "cargo_price"]
                ] = [_rs.cargo.demand, _rs.cargo.remaining_demand, _rs.cargo.price]
                df.loc[
                    dest_idx,
                    ["scheduled_flights_count", "raw_stat"],
                ] = [len(_rs.scheduled_flights), _rs.to_json()]
                logging.info(f"Processed destination {_route}")
                logging.debug(f"Route stat for {_route} = {_rs}")
            except Exception as ex:
                df.loc[dest_idx, "error"] = str(ex)
                logging.error(f"Error processing {hub} to {_route}. Ex={ex}")
                logging.error(traceback.print_exception(*sys.exc_info()))

        return df
