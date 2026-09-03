# NIST AI RMF Mapping Worksheet — [Your System Name]

*This is the BLANK template. Each section below has a "Given example"
(the same one every student starts from — double-check its exact wording
against the official spec in Admin/Capstone/Milestone6_ProjectSpecs/,
since this copy was carried over from the reference build, not re-pulled
fresh) and a "Your answer" section, which is where YOUR own evidence from
YOUR own deployment goes — that part must be your own, not copied from
`nist_ai_rmf_worksheet_demo_filled.md`, which is a different app.*

## 1. GOVERN

**Given example:** The trainer/team lead owns this system's behavior; the
guardrail/validation logic is the rule that risky actions never execute
without review — decided before deploy, not improvised afterward.

**Your answer:** [Who is accountable for your deployment? What's one
rule you decided in advance — written into your code before any testing —
rather than patched in reactively after you found a gap?]

## 2. MAP

**Given example:** The red-team exercise maps 5 categories of risk in
advance (prompt injection, jailbreaks, PII extraction, harmful content,
scope abuse) before any real user hits the system.

**Your answer:** [Before you ran the red-team prompts, what did you
predict your guardrail would and wouldn't catch, and why? Which category
worried you most going in, and did the real result confirm or surprise
you?]

## 3. MEASURE

**Given example:** Disparate Impact ratio and P95 response time under
load are both real numbers, not impressions.

**Your answer:** [Your real numbers: disparate_impact,
statistical_parity_difference, equal_opportunity_difference from Step 5;
your guardrail block rate from Step 3 (X/50 overall, broken down by
category if you can); your P95 latency and failure count from Step 4.
Every number here should be one you actually generated, not estimated.]

## 4. MANAGE

**Given example:** If a red-team prompt bypassed a guardrail, the fix is
adding that pattern to the validation logic before going live again.

**Your answer:** [At least one concrete, real finding from your own build
to act on before real production — something your guardrail missed,
something your load test revealed, or a risk category your system
doesn't cover yet. Say what the fix would be, even if you don't implement
it today — an honest, written-down gap is the point, not a perfect
system.]
