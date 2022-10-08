import argparse
from enum import Enum
import logging
import os
import pandas as pd
import numpy as np
from tycoon.utils.airline_manager import (
    buy_route,
    find_hub_id,
    get_all_routes,
    login,
    route_stats,
)

from tycoon.utils.command import Command
from tycoon.utils.data import CircuitInfo, RouteStats
from tycoon.utils.noway import find_circuit, find_seat_config


class Status(Enum):
    PRE_EXISTING = 2
    NEW_CIRCUIT = 3
    BOUGHT_CIRCUIT = 4
    DEMAND_FETCHED = 5
    SEAT_CONFIG_CALCULATED = 6
    UNKNOWN_ERROR = 20


class Circuit(Command):
    @classmethod
    def options(cls, parser: argparse.ArgumentParser):
        sub_parser = parser.add_parser(
            "circuit", help="Build a new circuit route network"
        )
        super().options(sub_parser)
        sub_parser.add_argument(
            "--circuit_hours",
            "-c",
            type=int,
            help="Hours for the circuit to shcedule flights for (Default: 168 hours)",
            default=168,
        )
        sub_parser.add_argument(
            "--allow_negative",
            "-an",
            action="store_false",
            help="""
                Allow negative config of seats (Default: True)
            """,
            default=True,
        )
        sub_parser.add_argument(
            "--find_new_circuit",
            "-fnc",
            action="store_true",
            help="""
                Find a new circuit and plan flights in them (Default: False)
            """,
            default=False,
        )

    def _new_df(self) -> pd.DataFrame:
        dtypes = np.dtype(
            [
                ("circuit_id", int),
                ("status", int),
                ("no", int),
                ("destination", str),
                ("country", str),
                ("cat", int),
                ("stars", int),
                ("distance", str),
                ("time", str),
                ("aircraft_make", str),
                ("aircraft_model", str),
                ("wave_stats", str),
                ("scheduled_flights_count", int),
                ("raw_stat", str),
                ("error", str),
            ]
        )
        df = pd.DataFrame(np.empty(0, dtype=dtypes))
        return df

    def _transform_circuit_routes_to_df(self, circuit: CircuitInfo):
        pass
        for row in circuit.rows:
            self.df.loc[len(self.df)] = [
                circuit.id,
                circuit.status,
                row.no,
                row.destination,
                row.country,
                row.cat,
                row.stars,
                row.distance,
                row.time,
                self.options.aircraft_make,
                self.options.aircraft_model,
                None,
                0,
                None,
                None,
            ]
        print(self.df)

    def _find_a_new_circuit(self, circuit_id: int):
        logging.info(
            f"Finding circuit for hub {self.options.hub} excluding the exiting routes"
        )
        _routes = list(filter(None, get_all_routes(self.driver, self.options.hub)))
        existing_routes = ",".join(_routes)
        logging.debug(f"Existing routes: {existing_routes}")
        circuit = find_circuit(
            self.driver,
            self.options.hub,
            existing_routes,
            self.options.circuit_hours,
            self.options.aircraft_make,
            self.options.aircraft_model,
            circuit_id,
            Status.NEW_CIRCUIT.value,
        )
        logging.info(f"Found a circuit for {self.options.hub}, Circuit info: {circuit}")
        self._transform_circuit_routes_to_df(circuit)

    def _save_data(self, print_stats=False):
        self.df.to_csv(self.data_file)
        logging.info(f"Stored routes in {self.data_file}")
        if print_stats:
            logging.info("***** Stats of stored *****")
            self.df.groupby(["status"]).count()["circuit_id"].reset_index(
                name="count"
            ).apply(
                lambda x: logging.info(
                    f"{Status(x.status)}, no of routes: {x['count']}"
                ),
                axis=1,
            )
            logging.info("**********")

    def _buy_circuit_routes(self):
        for row in self.df[self.df["status"] == Status.NEW_CIRCUIT.value].itertuples():
            buy_route(
                self.driver,
                self.options.hub,
                row.destination,
                self.hub_id,
            )
            self.df.loc[row.Index, "route_stats"] = route_stats(
                self.driver, self.options.hub, row.destination
            ).to_json()
            logging.info(
                f"Updated route_stats for {self.options.hub} - {row.destination}"
            )
            self.df.loc[row.Index, "status"] = Status.DEMAND_FETCHED.value
            self._save_data()

    def _get_seat_configs(self):
        for row in self.df[
            self.df["status"] == Status.DEMAND_FETCHED.value
        ].itertuples():
            _rs = RouteStats.from_json(self.df.loc[row.Index, "route_stats"])
            self.df.loc[row.Index, "route_stats"] = find_seat_config(
                self.driver,
                self.options.hub,
                row.destination,
                self.options.aircraft_make,
                self.options.aircraft_model,
                _rs,
                not self.options.allow_negative,
            ).to_json()
            logging.info(
                f"Updated route_stats for {self.options.hub} - {row.destination}"
            )
            self.df.loc[row.Index, "status"] = Status.SEAT_CONFIG_CALCULATED.value
            self._save_data()

    def run(self):
        self.data_file = os.path.join(
            self.options.tmp_folder, f"{self.options.hub}_circuit_df.csv"
        )
        if os.path.exists(self.data_file):
            logging.info(f"Found data at {self.data_file}")
            self.df = pd.read_csv(self.data_file)
        else:
            self.df = self._new_df()

        self._save_data(True)
        if self.options.find_new_circuit:
            logging.info("Requested for a new circuit")
            self._find_a_new_circuit(
                1
                if np.isnan(self.df["circuit_id"].max())
                else self.df["circuit_id"].max() + 1
            )
        login(self.driver)
        self.hub_id = find_hub_id(self.driver, self.options.hub)
        self._buy_circuit_routes()
        self._get_seat_configs()
        self._save_data(True)
