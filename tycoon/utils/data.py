from dataclasses import dataclass
from dataclasses_json import dataclass_json
from typing import List
import re


non_decimal = re.compile(r"[^\d.]+")


@dataclass_json
@dataclass
class RouteStat:
    price: int
    demand: int
    remaining_demand: int


@dataclass_json
@dataclass
class RouteStats:
    economy: RouteStat = None
    business: RouteStat = None
    first: RouteStat = None
    cargo: RouteStat = None
    category: int = 0
    distance: int = 0


@dataclass
class WaveStat:
    no: int
    economy: int
    business: int
    first: int
    cargo: int

    turnover_per_wave: float
    roi: float
    total_turnover: float
    turnover_days: int
    max_configured: str


def split_destination(input: str, delimiter=",") -> List[str]:
    return input.split(delimiter)
