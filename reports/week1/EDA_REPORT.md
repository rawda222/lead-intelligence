# Week 1 EDA Report (auto-generated)

> Data: synthetic, produced by leadforge 1.0.0 (recipe `b2b_saas_procurement_v1`, seed 42, mode `research_instructor`). Every figure below describes the simulator, not real sales behavior.

## 1. Counts
- Total leads: **5,000**
- Won: **1,049** | Lost: **1,527** | Open: **2,424**
- Closed leads (usable for training): **2,576**
- Win rate among closed leads: **40.7%**
- Won as a share of all leads: **21.0%**
- Lead creation range: 2024-01-01 to 2024-01-30; data observed until 2024-04-28

## 2. Average duration to become a customer (Won leads)
- Mean: **64.6 days** | Median: **66 days** (IQR 53 to 77, min 1, max 89, n=1,049)
- Median segments: lead to opportunity **13 days**, opportunity to close **50 days**
- Lost leads with a known closing date (n=1,168): mean 47.9 days, median 47
- **Caveat 1:** the simulator's window caps durations at about 90 days, so this is not a realistic ERP/CRM sales cycle.
- **Caveat 2:** 103 days is the average age of Open leads at the observation end. Open leads are censored: averaging only Won leads ignores them (survival analysis in Week 2 handles this).
- **Caveat 3:** 359 Lost leads never had an opportunity, so they have no closing date.

## 3. Deal value (estimated ACV)
- Leads with a deal value: 92.8%
- Total value of Won deals: $64,214,711; total value of Open pipeline (unweighted): $149,039,670
- Median deal: Won $49,579 vs Lost $48,640

## 4. Milestone reach (derived from events; the data has NO stage history)
- all leads: 5,000 (100%)
- sales activity within snapshot: 4,550 (91%)
- meeting set within snapshot: 2,686 (54%)
- demo done within snapshot: 2,674 (53%)
- opportunity created: 4,641 (93%)
- won: 1,049 (21%)

## 5. Win rate by segment (closed leads only; see charts for n per bar)
- **lead_source**: sdr_outbound: 42% (n=891), inbound_marketing: 42% (n=1203), partner_referral: 36% (n=482)
- **industry**: manufacturing: 46% (n=667), healthcare_non_clinical: 41% (n=646), professional_services: 39% (n=635), logistics: 38% (n=628)
- **region**: US: 41% (n=1234), UK: 40% (n=1342)
- **employee_band**: 2000+: 44% (n=257), 200-499: 42% (n=945), 500-999: 40% (n=881), 1000-1999: 38% (n=493)
- **estimated_revenue_band**: $200M+: 43% (n=250), $10M-$50M: 42% (n=983), $1M-$10M: 40% (n=670), $50M-$200M: 40% (n=673)
- **owner_rep_id**: rep_000009: 44% (n=273), rep_000007: 43% (n=264), rep_000004: 41% (n=251), rep_000001: 41% (n=275), rep_000008: 41% (n=247), rep_000010: 41% (n=233), rep_000002: 40% (n=243), rep_000003: 39% (n=260), rep_000005: 39% (n=268), rep_000006: 39% (n=262)
- **first_touch_channel**: sdr_outbound: 42% (n=891), inbound_marketing: 42% (n=1203), partner_referral: 36% (n=482)

## 6. Strongest correlations with Won (snapshot features, closed leads)
- `snap_days_silent_at_snapshot`: -0.370
- `snap_last_touch_day`: +0.321
- `snap_opp_exists`: +0.312
- `snap_last_activity_day`: +0.270
- `snap_activity_count`: +0.270
- `snap_touch_count`: +0.219
- `snap_demos`: +0.176
- `snap_demo_done`: +0.171

## 7. Things to remember
- Open leads look more like Won than Lost on first-30-day activity (see chart 08). A model trained on closed leads may be applied to a different population. Week 2 must check this.
- Only 2 regions (UK, US) and 4 industries exist, so geography is thin.
- All leads were created within one month, so time trends are not meaningful.
- `is_sql` is excluded from features until its timing is verified.

## 8. Charts
- `charts/01_status_win_vs_lost.png`
- `charts/02_milestone_funnel.png`
- `charts/03_final_stage_counts.png`
- `charts/04_leads_over_time.png`
- `charts/05_days_to_close_hist.png`
- `charts/06_win_rate_by_segment.png`
- `charts/07_win_rate_by_rep.png`
- `charts/08_activity_by_status.png`
- `charts/09_correlation_heatmap.png`
- `charts/10_deal_value_by_status.png`
- `charts/11_median_days_per_segment.png`