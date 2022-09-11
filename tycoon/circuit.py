import argparse
import logging
from tycoon.utils.airline_manager import get_all_routes, login

from tycoon.utils.command import Command
from tycoon.utils.noway import find_circuit


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

    def config(self):
        logging.info(
            f"Finding circuit for hub {self.options.hub} excluding the exiting routes"
        )
        _routes = get_all_routes(self.driver, self.options.hub)
        _routes = list(filter(None, _routes))
        existing_routes = ",".join(_routes)
        logging.debug(f"Existing routes: {existing_routes}")
        circuit_routes = find_circuit(
            self.driver,
            self.options.hub,
            existing_routes,
            self.options.circuit_hours,
            self.options.aircraft_make,
            self.options.aircraft_model,
        )
        logging.info(
            f"""
            Found a circuit for {self.options.hub}
            \t Circuit routes info: {circuit_routes}
        """
        )

    def run(self):
        login(self.driver)
        self.config()
        raise Exception("Incomplete")
