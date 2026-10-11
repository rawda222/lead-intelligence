"""Step 3: Week-1 analysis. Computes KPIs, saves charts and an auto-generated report.

Every number in reports/week1/EDA_REPORT.md comes from this script (nothing typed by hand).

Usage:  python -m src.analysis.eda
"""
import json

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src import config

sns.set_theme(style="whitegrid", context="notebook")
COL = {"Won": "#2e7d32", "Lost": "#c62828", "Open": "#1565c0"}


def load() -> pd.DataFrame:
    return pd.read_parquet(config.PROCESSED_DIR / "leads_master.parquet")


def save(fig, name: str) -> None:
    config.CHART_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(config.CHART_DIR / name, dpi=130)
    plt.close(fig)


def win_rate_table(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Win rate among CLOSED leads (Won / (Won + Lost)). Open leads are excluded."""
    closed = df[df["status"].isin(["Won", "Lost"])]
    g = closed.groupby(col).agg(closed=("target_won", "size"), won=("target_won", "sum"))
    g["win_rate"] = g["won"] / g["closed"]
    return g.reset_index().sort_values("win_rate", ascending=False)


def compute_kpis(df: pd.DataFrame) -> dict:
    closed = df[df["status"].isin(["Won", "Lost"])]
    won = df[df["status"] == "Won"]
    lost_known = df[(df["status"] == "Lost") & df["closed_date_known"]]
    k = {
        "total_leads": int(len(df)),
        "status_counts": df["status"].value_counts().to_dict(),
        "closed_leads": int(len(closed)),
        "win_rate_among_closed": float(closed["target_won"].mean()),
        "won_share_of_all_leads": float((df["status"] == "Won").mean()),
        "days_to_close_won": {
            "n": int(len(won)), "mean": float(won["days_to_close"].mean()),
            "median": float(won["days_to_close"].median()),
            "p25": float(won["days_to_close"].quantile(.25)), "p75": float(won["days_to_close"].quantile(.75)),
            "min": float(won["days_to_close"].min()), "max": float(won["days_to_close"].max()),
        },
        "days_to_close_lost_known": {
            "n": int(len(lost_known)), "mean": float(lost_known["days_to_close"].mean()),
            "median": float(lost_known["days_to_close"].median()),
        },
        "lost_without_closing_date": int(((df["status"] == "Lost") & ~df["closed_date_known"]).sum()),
        "open_leads_age_days": {
            "mean": float(df.loc[df["status"] == "Open", "observed_days"].mean()),
            "median": float(df.loc[df["status"] == "Open", "observed_days"].median()),
        },
        "observation_end": str(df["observation_end"].iloc[0].date()),
        "lead_created_range": [str(df["lead_created_at"].min().date()), str(df["lead_created_at"].max().date())],
        "stage_counts_final": df["final_stage"].value_counts().to_dict(),
        "deal_value": {
            "share_leads_with_value": float(df["deal_value_usd"].notna().mean()),
            "won_total": float(won["deal_value_usd"].sum()),
            "open_total": float(df.loc[df["status"] == "Open", "deal_value_usd"].sum()),
            "won_median": float(won["deal_value_usd"].median()),
            "lost_median": float(df.loc[df["status"] == "Lost", "deal_value_usd"].median()),
        },
    }
    won_opp = won.dropna(subset=["opp_created_day"])
    k["milestones_won_median_days"] = {
        "lead_to_opportunity": float(won_opp["opp_created_day"].median()),
        "opportunity_to_close": float((won_opp["days_to_close"] - won_opp["opp_created_day"]).median()),
    }
    k["milestone_counts"] = {
        "all_leads": int(len(df)),
        "sales_activity_within_snapshot": int((df["snap_activity_count"] > 0).sum()),
        "meeting_set_within_snapshot": int(df["snap_meeting_set"].sum()),
        "demo_done_within_snapshot": int(df["snap_demo_done"].sum()),
        "opportunity_created": int(df["opp_created_at"].notna().sum()),
        "won": int((df["status"] == "Won").sum()),
    }
    k["win_rate_by"] = {c: win_rate_table(df, c).round(4).to_dict("records")
                        for c in ["lead_source", "industry", "region", "employee_band",
                                  "estimated_revenue_band", "owner_rep_id", "first_touch_channel"]}
    return k


# ----------------------------------------------------------------------------- charts
def chart_status(df):
    c = df["status"].value_counts().reindex(["Won", "Lost", "Open"])
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].bar(c.index, c.values, color=[COL[i] for i in c.index])
    for i, v in enumerate(c.values):
        ax[0].text(i, v, f"{v:,}\n({v / c.sum():.1%})", ha="center", va="bottom")
    ax[0].set_title("Leads by status (all leads)"); ax[0].set_ylim(0, c.max() * 1.2)
    closed = df[df["status"].isin(["Won", "Lost"])]["status"].value_counts().reindex(["Won", "Lost"])
    ax[1].pie(closed.values, labels=[f"{i}\n{v:,}" for i, v in zip(closed.index, closed.values)],
              colors=[COL[i] for i in closed.index], autopct="%1.1f%%", startangle=90)
    ax[1].set_title("Win vs Lost (closed leads only)")
    save(fig, "01_status_win_vs_lost.png")


def chart_milestones(k):
    m = k["milestone_counts"]
    labels = ["All leads", "Sales activity\n(first 30d)", "Meeting set\n(first 30d)", "Demo done\n(first 30d)",
              "Opportunity\ncreated", "Won"]
    vals = list(m.values())
    fig, ax = plt.subplots(figsize=(10, 4.5))
    bars = ax.barh(labels[::-1], vals[::-1], color="#1565c0")
    for b, v in zip(bars, vals[::-1]):
        ax.text(v, b.get_y() + b.get_height() / 2, f" {v:,} ({v / vals[0]:.0%})", va="center")
    ax.set_xlim(0, vals[0] * 1.2)
    ax.set_title("Milestone reach (derived from events, NOT from a stage history)")
    save(fig, "02_milestone_funnel.png")


def chart_final_stage(df):
    c = df["final_stage"].value_counts()
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.barh(c.index[::-1], c.values[::-1], color="#546e7a")
    for i, v in enumerate(c.values[::-1]):
        ax.text(v, i, f" {v:,}", va="center")
    ax.set_title("Where leads ended up (final pipeline stage)")
    ax.set_xlim(0, c.max() * 1.15)
    save(fig, "03_final_stage_counts.png")


def chart_leads_over_time(df):
    w = df.set_index("lead_created_at").resample("W").size()
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(w.index, w.values, marker="o")
    ax.set_title("Leads created per week (all leads were created in one month)")
    ax.set_ylabel("Leads"); fig.autofmt_xdate()
    save(fig, "04_leads_over_time.png")


def chart_duration(df, k):
    won = df[df["status"] == "Won"]["days_to_close"]
    lost = df[(df["status"] == "Lost") & df["closed_date_known"]]["days_to_close"]
    fig, ax = plt.subplots(figsize=(10, 4.3))
    bins = np.arange(0, 95, 5)
    ax.hist(won, bins=bins, alpha=.7, color=COL["Won"], label=f"Won (n={len(won)})")
    ax.hist(lost, bins=bins, alpha=.55, color=COL["Lost"], label=f"Lost with known date (n={len(lost)})")
    d = k["days_to_close_won"]
    ax.axvline(d["mean"], color="k", ls="--", label=f"Won mean {d['mean']:.1f}d")
    ax.axvline(d["median"], color="k", ls=":", label=f"Won median {d['median']:.0f}d")
    ax.set_xlabel("Days from lead creation to close"); ax.set_ylabel("Leads")
    ax.set_title("Time to close (simulator window caps this at about 90 days)"); ax.legend()
    save(fig, "05_days_to_close_hist.png")


def chart_win_rates(df, k):
    cols = ["lead_source", "industry", "employee_band", "estimated_revenue_band", "region", "first_touch_channel"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    base = k["win_rate_among_closed"]
    for ax, c in zip(axes.ravel(), cols):
        t = win_rate_table(df, c)
        ax.barh(t[c].astype(str), t["win_rate"], color="#2e7d32")
        for i, (r, n) in enumerate(zip(t["win_rate"], t["closed"])):
            ax.text(r, i, f" {r:.0%} (n={n})", va="center", fontsize=8)
        ax.axvline(base, color="k", ls="--", lw=1)
        ax.set_xlim(0, 1); ax.set_title(f"Win rate by {c}")
    fig.suptitle(f"Win rate among CLOSED leads (dashed = overall {base:.1%})", y=1.0)
    save(fig, "06_win_rate_by_segment.png")


def chart_reps(df, k):
    t = win_rate_table(df, "owner_rep_id").sort_values("win_rate")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(t["owner_rep_id"], t["win_rate"], color="#6a1b9a")
    for i, (r, n) in enumerate(zip(t["win_rate"], t["closed"])):
        ax.text(r, i, f" {r:.0%} (n={n})", va="center", fontsize=8)
    ax.axvline(k["win_rate_among_closed"], color="k", ls="--", lw=1); ax.set_xlim(0, 1)
    ax.set_title("Win rate by rep (analysis only, not for judging individuals)")
    save(fig, "07_win_rate_by_rep.png")


def chart_activity_by_status(df):
    cols = ["snap_touch_count", "snap_session_count", "snap_activity_count", "snap_meetings", "snap_demos",
            "snap_pricing_page_views", "snap_connected_count"]
    m = df.groupby("status")[cols].mean().T[["Won", "Lost", "Open"]]
    ax = m.plot(kind="bar", figsize=(11, 4.5), color=[COL[c] for c in m.columns])
    ax.set_title("Average first-30-day activity by status"); ax.set_ylabel("Average count")
    plt.xticks(rotation=25, ha="right")
    save(ax.figure, "08_activity_by_status.png")


def chart_corr(df):
    closed = df[df["status"].isin(["Won", "Lost"])]
    cols = [c for c in closed.columns if c.startswith("snap_")] + ["target_won"]
    corr = closed[cols].corr(numeric_only=True)
    fig, ax = plt.subplots(figsize=(11, 9))
    sns.heatmap(corr, cmap="coolwarm", center=0, ax=ax, cbar_kws={"shrink": .7})
    ax.set_title("Correlation of snapshot features with the target (closed leads)")
    save(fig, "09_correlation_heatmap.png")
    return corr["target_won"].drop("target_won").sort_values(key=abs, ascending=False)


def chart_deal_value(df):
    d = df.dropna(subset=["deal_value_usd"])
    fig, ax = plt.subplots(figsize=(8, 4.3))
    sns.boxplot(data=d, x="status", y="deal_value_usd", order=["Won", "Lost", "Open"],
                palette=COL, ax=ax, showfliers=False)
    ax.set_title("Deal value (estimated ACV) by status"); ax.set_ylabel("USD")
    save(fig, "10_deal_value_by_status.png")


def chart_milestone_days(k):
    m = k["milestones_won_median_days"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(["Lead to\nopportunity", "Opportunity\nto close"], [m["lead_to_opportunity"], m["opportunity_to_close"]],
           color=["#1565c0", "#2e7d32"])
    for i, v in enumerate(m.values()):
        ax.text(i, v, f"{v:.0f}d", ha="center", va="bottom")
    ax.set_title("Median days per segment (Won leads)\nNo stage history exists, so only 2 segments")
    save(fig, "11_median_days_per_segment.png")


# ----------------------------------------------------------------------------- report
def write_report(k, corr_top, path):
    d = k["days_to_close_won"]; s = k["status_counts"]
    pct = lambda x: f"{x:.1%}"
    lines = [
        "# Week 1 EDA Report (auto-generated)",
        "",
        "> Data: synthetic, produced by leadforge 1.0.0 "
        f"(recipe `{config.LEADFORGE_RECIPE}`, seed {config.LEADFORGE_SEED}, mode `{config.LEADFORGE_MODE}`). "
        "Every figure below describes the simulator, not real sales behavior.",
        "",
        "## 1. Counts",
        f"- Total leads: **{k['total_leads']:,}**",
        f"- Won: **{s.get('Won', 0):,}** | Lost: **{s.get('Lost', 0):,}** | Open: **{s.get('Open', 0):,}**",
        f"- Closed leads (usable for training): **{k['closed_leads']:,}**",
        f"- Win rate among closed leads: **{pct(k['win_rate_among_closed'])}**",
        f"- Won as a share of all leads: **{pct(k['won_share_of_all_leads'])}**",
        f"- Lead creation range: {k['lead_created_range'][0]} to {k['lead_created_range'][1]}; "
        f"data observed until {k['observation_end']}",
        "",
        "## 2. Average duration to become a customer (Won leads)",
        f"- Mean: **{d['mean']:.1f} days** | Median: **{d['median']:.0f} days** "
        f"(IQR {d['p25']:.0f} to {d['p75']:.0f}, min {d['min']:.0f}, max {d['max']:.0f}, n={d['n']:,})",
        f"- Median segments: lead to opportunity **{k['milestones_won_median_days']['lead_to_opportunity']:.0f} days**, "
        f"opportunity to close **{k['milestones_won_median_days']['opportunity_to_close']:.0f} days**",
        f"- Lost leads with a known closing date (n={k['days_to_close_lost_known']['n']:,}): "
        f"mean {k['days_to_close_lost_known']['mean']:.1f} days, median {k['days_to_close_lost_known']['median']:.0f}",
        "- **Caveat 1:** the simulator's window caps durations at about 90 days, so this is not a realistic ERP/CRM sales cycle.",
        f"- **Caveat 2:** {k['open_leads_age_days']['mean']:.0f} days is the average age of Open leads at the observation end. "
        "Open leads are censored: averaging only Won leads ignores them (survival analysis in Week 2 handles this).",
        f"- **Caveat 3:** {k['lost_without_closing_date']:,} Lost leads never had an opportunity, so they have no closing date.",
        "",
        "## 3. Deal value (estimated ACV)",
        f"- Leads with a deal value: {pct(k['deal_value']['share_leads_with_value'])}",
        f"- Total value of Won deals: ${k['deal_value']['won_total']:,.0f}; "
        f"total value of Open pipeline (unweighted): ${k['deal_value']['open_total']:,.0f}",
        f"- Median deal: Won ${k['deal_value']['won_median']:,.0f} vs Lost ${k['deal_value']['lost_median']:,.0f}",
        "",
        "## 4. Milestone reach (derived from events; the data has NO stage history)",
    ]
    for name, v in k["milestone_counts"].items():
        lines.append(f"- {name.replace('_', ' ')}: {v:,} ({v / k['total_leads']:.0%})")
    lines += ["", "## 5. Win rate by segment (closed leads only; see charts for n per bar)"]
    for col, rows in k["win_rate_by"].items():
        parts = ", ".join(f"{r[col]}: {r['win_rate']:.0%} (n={int(r['closed'])})" for r in rows)
        lines.append(f"- **{col}**: {parts}")
    lines += ["", "## 6. Strongest correlations with Won (snapshot features, closed leads)"]
    for name, v in corr_top.head(8).items():
        lines.append(f"- `{name}`: {v:+.3f}")
    lines += [
        "",
        "## 7. Things to remember",
        "- Open leads look more like Won than Lost on first-30-day activity (see chart 08). "
        "A model trained on closed leads may be applied to a different population. Week 2 must check this.",
        "- Only 2 regions (UK, US) and 4 industries exist, so geography is thin.",
        "- All leads were created within one month, so time trends are not meaningful.",
        "- `is_sql` is excluded from features until its timing is verified.",
        "",
        "## 8. Charts",
    ]
    for p in sorted(config.CHART_DIR.glob("*.png")):
        lines.append(f"- `charts/{p.name}`")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    df = load()
    k = compute_kpis(df)
    chart_status(df); chart_milestones(k); chart_final_stage(df); chart_leads_over_time(df)
    chart_duration(df, k); chart_win_rates(df, k); chart_reps(df, k); chart_activity_by_status(df)
    corr_top = chart_corr(df); chart_deal_value(df); chart_milestone_days(k)
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (config.REPORT_DIR / "kpis.json").write_text(json.dumps(k, indent=2, default=str), encoding="utf-8")
    write_report(k, corr_top, config.REPORT_DIR / "EDA_REPORT.md")
    print("Charts:", len(list(config.CHART_DIR.glob('*.png'))))
    print((config.REPORT_DIR / "EDA_REPORT.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
