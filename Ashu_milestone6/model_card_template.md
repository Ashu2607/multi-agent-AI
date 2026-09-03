# Model Card — [Your System Name]

*This is the BLANK template — fill in your own real numbers and answers
from Steps 3-5 of your build. Delete the bracketed instructions as you
replace them. See `model_card_demo_filled.md` alongside this file for a
worked example of what a completed one looks like (don't copy its
content — it's a different app; copy its shape).*

## 1. Overview

- **System name:** [your app's name]
- **One-sentence description:** [what your app does, one sentence]
- **Owner / team responsible:** [your name]
- **Date this card was written:** [today's date]

## 2. Intended Use

- **What is this system meant to be used for?** [the actual purpose of
  your M3-5 app]
- **Who is the intended user?** [who would realistically use this]
- **What should this system NOT be used for?** [scope boundaries — what
  questions/tasks it wasn't built to handle]

## 3. How It Works

- **What model powers it?** [which LLM/API you call, and how you
  authenticate to it]
- **What does it have access to?** [databases, files, tools, other
  services your app calls]
- **Fallback if the main model is unreachable?** [does your app fail
  gracefully, or fail hard? describe what actually happens]

## 4. Known Limitations

- **What can this system get wrong?** [honest limitations — what kinds
  of questions or inputs produce bad or misleading answers]
- **Bias findings (Step 5, AIF360):** [your real disparate_impact,
  statistical_parity_difference, and equal_opportunity_difference numbers
  from `bias_audit.py` — not placeholders]
- **Red-team findings (Step 3, shared 50-prompt set):** [your real block
  count from `redteam_results.json`, broken down by category if you can,
  plus your own one-line verdict on whether that result is acceptable]

## 5. Performance Under Load

- **What load was it tested at?** [your actual Locust command and
  settings — number of users, duration]
- **Did it meet the target?** [your real P95 latency and failure count
  from `load_test_stats.csv` — report the real number even if it's
  worse than you hoped]

## 6. Who to Contact

- **If this system does something wrong, who should be told?** [you, or
  whoever owns this in a real deployment]
- **How often should this Model Card be reviewed?** [your honest answer
  — e.g. every redeploy, every code change, on a schedule]
