"""Week 1 tests: data integrity and leakage guards. Run:  pytest -q"""
import pandas as pd
import pytest

from src import config

T = config.RAW_DIR / "tables"


@pytest.fixture(scope="module")
def df():
    return pd.read_parquet(config.PROCESSED_DIR / "leads_master.parquet")


@pytest.fixture(scope="module")
def dictionary():
    return pd.read_csv(config.PROCESSED_DIR / "data_dictionary.csv")


def test_one_row_per_lead(df):
    assert df["lead_id"].is_unique
    assert len(df) == config.LEADFORGE_N_LEADS


def test_status_partition_and_target(df):
    assert set(df["status"].unique()) == {"Won", "Lost", "Open"}
    assert df.loc[df.status == "Won", "target_won"].eq(1).all()
    assert df.loc[df.status == "Lost", "target_won"].eq(0).all()
    assert df.loc[df.status == "Open", "target_won"].isna().all()


def test_closed_dates_are_valid(df):
    known = df[df["closed_date_known"]]
    assert (known["closed_date"] >= known["lead_created_at"]).all()
    assert (known["days_to_close"] >= 0).all()
    assert df.loc[df.status == "Won", "closed_date_known"].all()      # every Won lead has a date
    assert not df.loc[df.status == "Open", "closed_date_known"].any()  # Open leads have none


def test_snapshot_date(df):
    delta = (df["snapshot_date"] - df["lead_created_at"]).dt.days
    assert (delta == config.SNAPSHOT_DAYS).all()


def test_no_outcome_column_inside_snapshot_features(df, dictionary):
    snap = set(c for c in df.columns if c.startswith("snap_"))
    leak_cols = set(dictionary.loc[dictionary["role"].str.contains("LEAKAGE"), "column"])
    assert snap.isdisjoint(leak_cols)
    roles = dictionary.set_index("column")["role"]
    assert all(roles[c] == "feature_snapshot" for c in snap)


def test_dictionary_covers_every_column(df, dictionary):
    assert set(df.columns) == set(dictionary["column"])


def test_snapshot_filter_really_removes_future_events(df):
    """Recompute activity counts from raw data and prove the window matters."""
    acts = pd.read_parquet(T / "sales_activities.parquet")
    acts["activity_timestamp"] = pd.to_datetime(acts["activity_timestamp"])
    m = acts.merge(df[["lead_id", "lead_created_at"]], on="lead_id")
    m["d"] = (m["activity_timestamp"].dt.normalize() - m["lead_created_at"]).dt.days
    inside = m[m["d"] <= config.SNAPSHOT_DAYS].groupby("lead_id").size()
    expected = df["lead_id"].map(inside).fillna(0)
    assert (df["snap_activity_count"].values == expected.values).all()
    all_events = m.groupby("lead_id").size().sum()
    assert all_events > inside.sum()   # the raw table contains events AFTER the snapshot


def test_all_snapshot_day_features_within_window(df):
    for c in ["snap_last_touch_day", "snap_last_activity_day", "snap_first_touch_day", "snap_first_activity_day"]:
        assert df[c].dropna().le(config.SNAPSHOT_DAYS).all(), c
