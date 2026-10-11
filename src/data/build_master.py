"""Step 2: turn the relational leadforge tables into ONE row per lead.

Output: data/processed/leads_master.parquet  (+ data_dictionary.csv)

Design rules (see docs/ and PROJECT_CONTEXT.md):
  * status:   Won / Lost / Open, taken from leads.current_stage (the final pipeline stage).
  * outcome-only columns (closed date, final stage, days_to_close) are NEVER model features.
  * snap_* columns only use events that happened within SNAPSHOT_DAYS after lead creation.
    Leadforge's research_instructor tables hold the FULL timeline (about 89 days), so we
    must filter by timestamp ourselves. Using all events would leak the future.

Usage:  python -m src.data.build_master
"""
import numpy as np
import pandas as pd

from src import config

T = config.RAW_DIR / "tables"


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(T / f"{name}.parquet")


def _to_dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _within_snapshot(events: pd.DataFrame, leads: pd.DataFrame, ts_col: str) -> pd.DataFrame:
    """Keep only events with timestamp <= lead_created_at + SNAPSHOT_DAYS (inclusive, by day)."""
    ev = events.merge(leads[["lead_id", "lead_created_at"]], on="lead_id", how="inner")
    ev[ts_col] = _to_dt(ev[ts_col])
    ev["days_since_created"] = (ev[ts_col].dt.normalize() - ev["lead_created_at"]).dt.days
    return ev[ev["days_since_created"] <= config.SNAPSHOT_DAYS].copy()


def build() -> pd.DataFrame:
    leads = _read("leads")
    opps = _read("opportunities")
    accounts = _read("accounts")
    contacts = _read("contacts")
    acts = _read("sales_activities")
    sessions = _read("sessions")
    touches = _read("touches")

    leads["lead_created_at"] = _to_dt(leads["lead_created_at"])

    # ---- base table: lead + account + contact + opportunity -------------------------------
    df = leads.drop(columns=["converted_within_90_days", "conversion_timestamp"]).copy()
    df = df.merge(
        accounts[["account_id", "company_name", "industry", "region", "employee_band",
                  "estimated_revenue_band", "process_maturity_band"]],
        on="account_id", how="left")
    df = df.merge(
        contacts[["contact_id", "role_function", "seniority", "buyer_role", "email_domain_type"]],
        on="contact_id", how="left")
    opp = opps.rename(columns={"created_at": "opp_created_at", "stage": "opp_stage_final",
                               "estimated_acv": "deal_value_usd", "closed_at": "opp_closed_at"})
    df = df.merge(opp.drop(columns=["opportunity_id"]), on="lead_id", how="left")
    df["opp_created_at"] = _to_dt(df["opp_created_at"])
    df["opp_closed_at"] = _to_dt(df["opp_closed_at"])

    # ---- outcome ------------------------------------------------------------------------------
    df["final_stage"] = df["current_stage"]
    df["status"] = np.select(
        [df["final_stage"] == config.WON_STAGE, df["final_stage"] == config.LOST_STAGE],
        ["Won", "Lost"], default="Open")
    df["target_won"] = np.where(df["status"] == "Won", 1.0, np.where(df["status"] == "Lost", 0.0, np.nan))

    # closing date: only exists through the opportunity record
    df["closed_date"] = df["opp_closed_at"].where(df["status"] != "Open")
    df["days_to_close"] = (df["closed_date"] - df["lead_created_at"]).dt.days
    df["closed_date_known"] = df["closed_date"].notna()

    # observation end = last event timestamp in the whole dataset (used for open-lead ages)
    obs_end = max(_to_dt(acts["activity_timestamp"]).max(), _to_dt(touches["touch_timestamp"]).max(),
                  _to_dt(sessions["session_timestamp"]).max(), df["opp_closed_at"].max())
    df["observation_end"] = obs_end.normalize()
    df["observed_days"] = np.where(
        df["status"] == "Open",
        (df["observation_end"] - df["lead_created_at"]).dt.days,
        df["days_to_close"])

    # ---- opportunity timing relative to the snapshot (safe: known at creation) ---------
    df["opp_created_day"] = (df["opp_created_at"] - df["lead_created_at"]).dt.days
    df["snap_opp_exists"] = (df["opp_created_day"] <= config.SNAPSHOT_DAYS).fillna(False).astype(int)
    # deal value is only a safe *feature* if the opportunity existed at the snapshot;
    # in any case it is used for revenue forecasting, not for predicting Win/Lost.

    # ---- snapshot-safe aggregates -----------------------------------------------------------
    snap_day = config.SNAPSHOT_DAYS
    t = _within_snapshot(touches, df, "touch_timestamp")
    g = t.groupby("lead_id")
    agg_t = pd.DataFrame({
        "snap_touch_count": g.size(),
        "snap_touch_inbound": g["touch_direction"].apply(lambda s: (s == "inbound").sum()),
        "snap_touch_outbound": g["touch_direction"].apply(lambda s: (s == "outbound").sum()),
        "snap_last_touch_day": g["days_since_created"].max(),
        "snap_first_touch_day": g["days_since_created"].min(),
    })
    for typ in ["content_download", "webinar", "call", "email", "linkedin_message"]:
        agg_t[f"snap_touch_{typ}"] = t[t["touch_type"] == typ].groupby("lead_id").size()

    s = _within_snapshot(sessions, df, "session_timestamp")
    gs = s.groupby("lead_id")
    agg_s = pd.DataFrame({
        "snap_session_count": gs.size(),
        "snap_page_views": gs["page_views"].sum(),
        "snap_pricing_page_views": gs["pricing_page_views"].sum(),
        "snap_demo_page_views": gs["demo_page_views"].sum(),
        "snap_session_seconds": gs["session_duration_seconds"].sum(),
    })

    a = _within_snapshot(acts, df, "activity_timestamp")
    ga = a.groupby("lead_id")
    agg_a = pd.DataFrame({
        "snap_activity_count": ga.size(),
        "snap_last_activity_day": ga["days_since_created"].max(),
        "snap_first_activity_day": ga["days_since_created"].min(),
        "snap_connected_count": ga["activity_outcome"].apply(lambda x: (x == "connected").sum()),
        "snap_no_answer_count": ga["activity_outcome"].apply(lambda x: (x == "no_answer").sum()),
        "snap_voicemail_count": ga["activity_outcome"].apply(lambda x: (x == "left_voicemail").sum()),
    })
    for typ in ["call", "email", "meeting", "demo"]:
        agg_a[f"snap_{typ}s"] = a[a["activity_type"] == typ].groupby("lead_id").size()
    agg_a["snap_demo_done"] = (a[a["activity_outcome"] == "demo_completed"].groupby("lead_id").size() > 0).astype(int)
    agg_a["snap_meeting_set"] = (a[a["activity_outcome"] == "meeting_set"].groupby("lead_id").size() > 0).astype(int)

    df = df.merge(agg_t, left_on="lead_id", right_index=True, how="left")
    df = df.merge(agg_s, left_on="lead_id", right_index=True, how="left")
    df = df.merge(agg_a, left_on="lead_id", right_index=True, how="left")

    count_cols = [c for c in df.columns if c.startswith("snap_") and not c.endswith("_day")]
    df[count_cols] = df[count_cols].fillna(0)
    # *_day columns stay NaN when the lead had no such event inside the snapshot window
    df["snap_days_silent_at_snapshot"] = snap_day - df[["snap_last_touch_day", "snap_last_activity_day"]].max(axis=1)

    df["snapshot_date"] = df["lead_created_at"] + pd.Timedelta(days=snap_day)
    df["created_month"] = df["lead_created_at"].dt.to_period("M").astype(str)

    keep_order = [
        "lead_id", "company_name", "lead_created_at", "snapshot_date", "created_month",
        "lead_source", "first_touch_channel", "owner_rep_id", "industry", "region", "employee_band",
        "estimated_revenue_band", "process_maturity_band", "role_function", "seniority", "buyer_role",
        "email_domain_type", "is_sql",
        "opp_created_at", "opp_created_day", "deal_value_usd",
        "status", "target_won", "final_stage", "opp_stage_final", "close_outcome",
        "closed_date", "closed_date_known", "days_to_close", "observation_end", "observed_days",
    ]
    snap_cols = sorted(c for c in df.columns if c.startswith("snap_"))
    df = df[keep_order + snap_cols]
    return df


DICTIONARY = [
    # column, description, role
    ("lead_id", "Unique lead id (join key)", "id"),
    ("company_name", "Account name (synthetic)", "display_only"),
    ("lead_created_at", "Date the lead was created", "time_anchor"),
    ("snapshot_date", "lead_created_at + SNAPSHOT_DAYS; features only use events up to this date", "time_anchor"),
    ("created_month", "Month of creation (for charts)", "analysis_only"),
    ("lead_source", "inbound_marketing / sdr_outbound / partner_referral", "feature"),
    ("first_touch_channel", "Channel of the first touch", "feature"),
    ("owner_rep_id", "Sales rep id (10 reps). Analysis; test model with and without", "sensitive_feature"),
    ("industry", "Account industry (4 values)", "feature"),
    ("region", "UK or US (leadforge has no country)", "feature"),
    ("employee_band", "Company size band", "feature"),
    ("estimated_revenue_band", "Company revenue band", "feature"),
    ("process_maturity_band", "Process maturity of the account", "feature"),
    ("role_function", "Contact role function", "feature"),
    ("seniority", "Contact seniority", "feature"),
    ("buyer_role", "Contact buyer role", "feature"),
    ("email_domain_type", "Type of contact email domain", "feature"),
    ("is_sql", "Sales-qualified flag. Timing is unclear (set at some point in the funnel); EXCLUDED from features until verified", "excluded_unverified"),
    ("opp_created_at", "Date the opportunity was created (NaT if none)", "analysis_only"),
    ("opp_created_day", "Days from lead creation to opportunity creation", "analysis_only"),
    ("deal_value_usd", "Estimated ACV of the opportunity. Used for revenue forecast, NOT to predict Win/Lost", "revenue_only"),
    ("status", "Won / Lost / Open from final pipeline stage", "target_source"),
    ("target_won", "1 = Won, 0 = Lost, NaN = Open (train on non-NaN only)", "target"),
    ("final_stage", "Final pipeline stage", "outcome_only_LEAKAGE"),
    ("opp_stage_final", "Final opportunity stage (reveals the outcome)", "outcome_only_LEAKAGE"),
    ("close_outcome", "Opportunity outcome (reveals the outcome)", "outcome_only_LEAKAGE"),
    ("closed_date", "Closing date of Won/Lost leads (NaT if unknown or Open)", "outcome_only_LEAKAGE"),
    ("closed_date_known", "False for Lost leads that never had an opportunity (no closing date recorded)", "outcome_only_LEAKAGE"),
    ("days_to_close", "closed_date - lead_created_at (days)", "outcome_only_LEAKAGE"),
    ("observation_end", "Last event date in the dataset (censoring date for Open leads)", "analysis_only"),
    ("observed_days", "days_to_close for closed leads; observation_end - created for Open leads (censored)", "outcome_only_LEAKAGE"),
]
SNAP_DESCRIPTIONS = {
    "snap_opp_exists": "1 if the opportunity was created within the snapshot window",
    "snap_touch_count": "Marketing/SDR touches within snapshot",
    "snap_touch_inbound": "Inbound touches within snapshot",
    "snap_touch_outbound": "Outbound touches within snapshot",
    "snap_first_touch_day": "Day (since creation) of first touch in window",
    "snap_last_touch_day": "Day (since creation) of last touch in window",
    "snap_session_count": "Product/web sessions within snapshot",
    "snap_page_views": "Page views within snapshot",
    "snap_pricing_page_views": "Pricing page views within snapshot",
    "snap_demo_page_views": "Demo page views within snapshot",
    "snap_session_seconds": "Total session seconds within snapshot",
    "snap_activity_count": "Sales activities (calls/emails/meetings/demos) within snapshot",
    "snap_first_activity_day": "Day of first sales activity in window",
    "snap_last_activity_day": "Day of last sales activity in window",
    "snap_connected_count": "Activities with outcome 'connected'",
    "snap_no_answer_count": "Activities with outcome 'no_answer'",
    "snap_voicemail_count": "Activities with outcome 'left_voicemail'",
    "snap_calls": "Calls within snapshot", "snap_emails": "Emails within snapshot",
    "snap_meetings": "Meetings within snapshot", "snap_demos": "Demos within snapshot",
    "snap_demo_done": "1 if any demo_completed outcome within snapshot",
    "snap_meeting_set": "1 if any meeting_set outcome within snapshot",
    "snap_days_silent_at_snapshot": "Days between the last touch/activity and the snapshot date",
}


def write_dictionary(df: pd.DataFrame) -> pd.DataFrame:
    rows = [(c, d, r, "yes (leadforge)") for c, d, r in DICTIONARY]
    for c in df.columns:
        if c.startswith("snap_"):
            desc = SNAP_DESCRIPTIONS.get(c, "Touch count by type within snapshot" if c.startswith("snap_touch_") else "Snapshot feature")
            rows.append((c, desc, "feature_snapshot", "yes (leadforge)"))
    dd = pd.DataFrame(rows, columns=["column", "description", "role", "synthetic"])
    dd.to_csv(config.PROCESSED_DIR / "data_dictionary.csv", index=False)
    return dd


def main() -> None:
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df = build()
    df.to_parquet(config.PROCESSED_DIR / "leads_master.parquet", index=False)
    write_dictionary(df)
    print("leads_master:", df.shape)
    print(df["status"].value_counts().to_string())


if __name__ == "__main__":
    main()
