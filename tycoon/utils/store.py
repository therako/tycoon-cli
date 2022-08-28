import os

import numpy as np
import pandas as pd


STORE_DIR = "./"


def _new_df() -> pd.DataFrame:
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


def save_hub(hub: str, df: pd.DataFrame = _new_df(), dir=STORE_DIR):
    return df.to_csv(os.path.join(dir, f"{hub}.csv"), header=True, index=False)


def get_hub(hub: str, dir=STORE_DIR) -> pd.DataFrame:
    if os.path.exists(os.path.join(dir, f"{hub}.csv")):
        return pd.read_csv(f"{hub}.csv")

    return _new_df()
