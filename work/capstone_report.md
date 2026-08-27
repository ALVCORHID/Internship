# Capstone Report — Freestyle: Search-Visibility Decline Risk Scoring

- **Author:** Álvaro Correa Hidalgo
- **Lane:** Freestyle B — Growth / Recovery / Momentum Prediction (framed as a ranking/scoring problem)
- **Repo:** https://github.com/ALVCORHID/Internship
- **Deployed paper:** https://alvcorhid.github.io/Internship/
- **Date:** 2026-08-27

> This report mirrors the deployed research paper and the capstone notebook
> (`work/notebooks/capstone.ipynb`). Every number here is recomputed in a notebook that ran
> against real FlyRank warehouse data, not restated from memory. The eight sections map to
> the Pass / Needs-Work rubric axes.

---

## 1. Problem framing

**Decision supported:** which pages a content/SEO editorial team reviews *first*. Review
capacity is fixed; this work decides where it goes.

- **Unit of analysis:** one `(client_hash_id, content_hash_id)` pair — a single page for a
  single client.
- **Output:** a ranked, reason-coded content action queue (`work/outputs/content_action_playbook.csv`) —
  decision-support for a human, never an automated action.
- **Action a human takes:** open the top of the queue and decide *refresh / review / monitor*
  for each page, using the attached reason codes and a review checklist.
- **Cost of a wrong call:** a false positive wastes a slot of scarce editorial time on a
  healthy page; a false negative lets a page keep losing search visibility unnoticed. Both
  are review-prioritisation costs, not irreversible content changes.

**Why ML helps:** ~104k pages is far past what a team can eyeball. A transparent rule already
sorts them (the Week-4 baseline); a model earns its place only if it ranks the *top* of the
queue better than that rule on the same data. Section 5 shows it does.

**Research question (from `w01_research_question.ipynb`, framed in `w02_ml_task_framing.ipynb`):**
*Using the last 90 days of client + content behaviour, what is the probability that a page
suffers a ≥30% search-impression drop in the following month?* Treated as
ranking/scoring (Average Precision / Precision@K), not a yes/no classifier, because what
matters is the order of the queue.

## 2. Data safety

- **Source:** FlyRank ML Internship warehouse release
  (`hf://datasets/FlyRank/internship-warehouse`), aggregated with the DuckDB-over-Hugging-Face
  workflow from `notebooks/03_working_with_the_full_release.ipynb` and
  `work/scripts/build_dataset.py`.
- **Grain / windows:** one row per (client, page); a 90-day feature window (Jan–Mar 2026 in
  this build); label window = the following 30 days (April 2026).
- **Build size:** 103,691 rows across 42 clients.

**Columns deliberately excluded, and why** (this list is the direct output of the ML-04 /
ML-05 leakage hunt in `w03_feature_leakage_check.ipynb`, re-verified in
`w06_validation_audit.ipynb` §3 on the exact feature set used):

| Excluded | Reason |
|---|---|
| `impressions_mar` | numerator of the label formula — direct leakage |
| `impressions_apr` | the label window itself — direct leakage |
| `pct_change` | computed from the two columns above — direct leakage |
| `trend_direction` | derived from `pct_change` — direct leakage (also the starter pipeline's label) |
| `trend_pct` | percentage form of `pct_change` — direct leakage |
| `client_hash_id` / `content_hash_id` | pseudonymous IDs — used only to group/split, never as a feature |

**Public-safe by construction:** the hash IDs have no reversible link to real client names,
domains, URLs, page titles, or search queries anywhere in the dataset (per `DATA_USE.md` and
`docs/data-dictionary.md`). Nothing client-identifying appears anywhere in `work/`.

## 3. Baseline

A transparent, hand-written rule — `w04_baseline_score.ipynb` (ML-07). No fitted weights.

- **Score:** `visibility_score × risk_composite`. `visibility_score` is the percentile rank
  of `log1p(impressions_90d)` (heavy-tail-safe, per the ML-06 audit). `risk_composite` is a
  hand-weighted blend (0.45 / 0.30 / 0.25) of in-window momentum, rank position, and
  visibility consistency — the three signals ML-06 tested. Visibility **gates** the score:
  a page nobody sees scores near zero regardless of its other numbers.
- **Six reason codes:** `visible_declining_momentum`, `visible_poor_rank`,
  `inconsistent_visibility`, `low_ctr_visible_page`, `low_engagement_visible_page`,
  `general_review_candidate`.
- **Structural-missing handling:** `has_momentum == 0` rows (no Jan–Feb base to compute a
  trend) get a **neutral** 0.5 momentum-risk score — treating "unknown" as "safe" or "risky"
  would inject a fabricated signal.

**Why it's a fair comparison:** it is scored on the same rows, the same
`is_declining_label`, and the same Precision@K metric as the model, on the same
client-grouped test split.

**Baseline numbers (client-grouped test split, `w05_model.ipynb` §3):**
Precision@10 = 0.40, Precision@25 = 0.28, **Precision@50 = 0.28** — against a test base rate
of 0.301.

**Honest read of the baseline:** ML-06 found two of its three risk signals point the wrong
way — `avg_position_90d` and `active_days_90d` run **OPPOSITE** to the rule's assumption
(better rank / more consistent visibility predict *more* decline here), and `momentum_pct`
alone tested **FALSE** (no meaningful univariate swing). 11 of the baseline's top 20 picks
are false positives, all 11 carrying `visible_declining_momentum`. Most of the baseline's
modest lift comes from the visibility gate, not from the risk signals being well-aimed —
which is exactly the weakness the model is asked to beat.

## 4. Model / analysis

**Method:** three sklearn classifiers, scored as rankers by `predict_proba`:
`logistic_regression` (scaled, `class_weight="balanced"`), `decision_tree` (`max_depth=5`,
`min_samples_leaf=50`), `random_forest` (`n_estimators=200`, `max_depth=10`,
`class_weight="balanced_subsample"`). `RANDOM_STATE = 42` throughout.

**Why it fits the lane:** the lane is a scoring/ranking problem over a fixed review budget.
Probability outputs give a natural ranking; Precision@K measures exactly what a
capacity-limited team cares about.

**Feature list (14, all from the 90-day feature window only):**
`impressions_90d`, `clicks_90d`, `ctr_90d`, `avg_position_90d`, `sessions_90d`,
`pageviews_90d`, `engaged_sessions_90d`, `organic_sessions_90d`, `impressions_last30`,
`impressions_first60`, `momentum_pct`, `active_days_90d`, `has_ga4_data`, `has_momentum`.
Left out on purpose: every column in the §2 exclusion table.

**Target:** `is_declining_label` — 1 if GSC impressions dropped ≥30% from the end of the
feature window into the 30-day label window; built strictly from the label window.

## 5. Evaluation

**Split:** client-grouped 80/20 holdout (`w05_model.ipynb` §2). ~20% of *clients* (8 of 42)
are held out entirely — never rows. Verified train/test client overlap = 0. Chosen because a
row-random split lets a client's pages sit on both sides and the model memorises the client,
not the signal.

**Model vs baseline, same split, same metric** (test base rate = **0.301**):

| Model | P@10 | P@25 | P@50 | Avg Precision | ROC AUC |
|---|---|---|---|---|---|
| baseline (Week-4 rule) | 0.40 | 0.28 | 0.28 | 0.290 | 0.500 |
| **logistic_regression** | 0.50 | 0.60 | **0.74** | 0.419 | 0.629 |
| decision_tree | 0.70 | 0.60 | 0.58 | 0.394 | 0.640 |
| random_forest | 1.00 | 0.88 | 0.72 | 0.407 | 0.643 |

**Headline:** logistic regression reaches **Precision@50 = 0.74, a 2.64× lift** over the
baseline's 0.28. All three models beat the baseline on every metric shown. `random_forest`
actually leads at the very top of the queue (P@10 = 1.00, P@25 = 0.88); `logistic_regression`
is chosen as the operating model because P@50 matches a realistic weekly review batch and it
is the most inspectable of the three.

**Does the gap survive a weaker split?** `w06_validation_audit.ipynb` §2 reruns everything on
a naive row-random split (38 clients overlapping train/test). Average Precision and ROC AUC
are uniformly higher on that leaky split (e.g. LR AvgPrec 0.541 vs 0.419, RF 0.626 vs 0.407),
and random forest's Precision@50 inflates from 0.72 to 0.82 — so the client-grouped numbers
above are the conservative ones. The model-beats-baseline ordering holds on both splits.

**Error analysis (`w05_model.ipynb`):**

- Feature importance (LR |coef| on scaled inputs): `active_days_90d` (0.41), `ctr_90d`
  (0.36), `clicks_90d` (0.33), `pageviews_90d` (0.27), `avg_position_90d` (0.23). Raw
  `impressions_90d` barely matters once the behaviour features are in.
- Accuracy is worst in the mid-rank band (`avg_position_90d` ≈ 6–13: accuracy ~0.48),
  consistent with ML-06's finding that rank runs backwards from intuition here.
- Concrete misses include a page with a huge in-window impression spike (`momentum_pct`
  ≈ 6754) that the model rates 0.80 risk but did **not** decline — spike-driven momentum is
  a known weak spot.
- ROC AUC 0.629 — real signal, not suspiciously perfect.

## 6. Interpretation

What the model actually found, in plain words:

- **Behavioural consistency and engagement quality beat raw size.** `active_days_90d`,
  `ctr_90d`, and `clicks_90d` carry the model; a page's sheer impression count does almost
  no work once those are present.
- **The baseline's intuitions are partly inverted.** Poor rank and thin active-day counts
  associate with *more* decline in this data, not less (ML-06 OPPOSITE verdicts). The model
  gets its lift largely by *not* trusting those signals the way the hand rule did.
- **Structural missingness is a flag, not a value.** `has_ga4_data == 0` shows a higher
  decline rate (44.2% vs 35.3%, ML-06 CONFIRMED) — but a per-client breakdown traced that
  gap to one outlier client, so `has_ga4_data` is kept as a structural flag and *excluded*
  as a raw signal rather than trusted.
- **Negative result worth keeping:** `momentum_pct` on its own is not a usable univariate
  predictor here (ML-06 FALSE). A well-understood "no effect" is still a result.

**Archetypes (`w07_action_playbook.ipynb`, 103,691 pages scored):**

| Archetype | Pages | Action |
|---|---|---|
| Low Visibility | 51,830 | monitor |
| Visible but Under-converting | 22,932 | refresh metadata / content |
| Model-flagged Opportunity | 17,998 | review |
| Stable / General Watch | 5,233 | monitor |
| Inconsistent Visibility | 2,862 | monitor |
| Model-confirmed Decline | 2,052 | refresh |
| Declining & Under-ranked | 784 | refresh |

## 7. Recommendation

The ranked action queue a FlyRank editor would open tomorrow (`content_action_playbook.csv`,
top of queue first):

1. **Refresh** the `Declining & Under-ranked` and `Model-confirmed Decline` archetypes first
   (2,836 pages) — the transparent rule *and* the model agree these are highest-risk.
2. **Review** (not auto-fix) `Visible but Under-converting` pages (22,932) for metadata / CTR
   issues — they already earn impressions, so the fix is capture, not visibility.
3. Treat `Model-flagged Opportunity` (17,998) as a **lighter-touch review tier** — the model
   sees risk the rule doesn't, with less corroborating evidence.
4. **Monitor only** `Stable / General Watch` and `Low Visibility` — keep them out of this
   cycle's active queue.

Confidence tiers: 20,739 pages **high** (multiple independent signals agree), 31,107
**medium**, 51,845 **low** (score riding on visibility alone — do not schedule dedicated time
from this tier). Each tier ships with a human-review checklist and a **no-go list** (never
auto-publish / auto-delete / auto-rewrite; never treat the score as proof a refresh recovers
traffic; never use it for personnel, vendor, or budget calls).

**Limits, stated plainly:** one time window, one snapshot; a proxy label, not a
content-quality verdict; cross-sectional association, not causation; sensitive to the exact
split. Every recommendation is a review priority for a human.

## 8. Reproducibility

From a fresh clone:

```bash
git clone https://github.com/ALVCORHID/Internship.git
cd Internship
pip install -r requirements.txt
pip install duckdb huggingface_hub                       # notebook 03 / build_dataset.py deps

# 1. Build the modelling table from the hosted release (needs a read HF token):
export HF_TOKEN=...            # request access at the dataset page first
python work/scripts/build_dataset.py                     # writes work/outputs/dataset.csv

# 2. Run the notebooks top to bottom, in order:
#    w01 → w02 → w03_data_contract → w03_feature_leakage_check → w04_baseline_score
#    → w04_signal_audit → w05_model → w06_validation_audit → w07_action_playbook → capstone
jupyter nbconvert --to notebook --execute --inplace work/notebooks/*.ipynb
```

- **Seeds:** `RANDOM_STATE = 42` in every modelling notebook.
- **Environment:** `requirements.txt` (pandas, numpy, scikit-learn, matplotlib, reportlab,
  duckdb, huggingface_hub) + Python 3.11/3.12. The random-forest Precision@50 is
  library-version sensitive (±0.03); the ~2.6× lift over baseline is the stable claim.
- **Run receipts (committed):** `work/outputs/playbook_summary.json`,
  `work/outputs/monitoring_snapshot.json`. The large CSVs are gitignored by design and
  regenerate on every run.
- **Notebooks:** all under [`work/notebooks/`](https://github.com/ALVCORHID/Internship/tree/main/work/notebooks).

## 9. Acknowledgments & data credit

Built on the **FlyRank ML Internship dataset** — https://flyrank.ai. Crediting the data
source is standard research practice and tells the reader this is real search data, not a toy
set. Track leads: Mirza Ašćerić (ML), Hole (data engineering). Code under MIT (`LICENSE`);
data under `DATA_USE.md`.

---

> **Claims checklist:** observed / measured / directional / decision-support language
> throughout · base rate (0.301) reported next to every Precision@K · lift over baseline is
> the headline discrimination number · no causal claims · no "predicted Google's algorithm" ·
> no client-identifying details · every number matches a fresh notebook re-run.
