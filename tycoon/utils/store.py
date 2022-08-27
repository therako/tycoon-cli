import pandas as pd
import numpy as np
import os


def get_hub_df(hub: str) -> pd.DataFrame:
    if os.path.exists(f"{hub}.csv"):
        return pd.read_csv(f"{hub}.csv")

    return new_df()


def new_df() -> pd.DataFrame:
    dtypes = np.dtype(
        [
            ("hub", str),
            ("destination", str),
            ("type", str),
            ("economy_demand", float),
            ("economy_remaining_demand", float),
            ("economy_price", float),
            ("business_demand", float),
            ("business_remaining_demand", float),
            ("business_price", float),
            ("first_demand", float),
            ("first_remaining_demand", float),
            ("first_price", float),
            ("cargo_demand", float),
            ("cargo_remaining_demand", float),
            ("cargo_price", float),
            ("aircraft_make", str),
            ("aircraft_model", str),
            ("wave_stats", str),
            ("created_at", pd.Timestamp),
            ("updated_at", pd.Timestamp),
            ("scheduled_flights_count", int),
            ("raw_stat", str),
            ("error", str),
        ]
    )
    return pd.DataFrame(np.empty(0, dtype=dtypes))
