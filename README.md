# REMNANT — archived

> Because the worst thing a civilization can do is solve a problem twice.

One-evening research scaffold (June 2026) for epistemic decay monitoring —
tracking when solved knowledge loses salience and gets re-derived.

**Archived deliberately.** The same evening it was scaffolded, a six-critic
internal review (preserved in [`docs/findings/`](docs/findings/)) found the
core outputs unvalidatable as built: citation data was never populated, so
every decay score was noise, and collision detection could not distinguish
*approaching* a concept from *mentioning* it. The honest conclusion was to
stop, not to iterate.

The thesis lives on where it is tractable and measurable:

- **[Scar](https://github.com/Daily-Nerd/Scar)** — negative knowledge at
  repository scale: recorded dead ends fire before an agent repeats them.
- **[daimon](https://github.com/Daily-Nerd/daimon)** — session memory with
  verifiable claims; salience via proactive recall, decay via evidence-gated
  staleness handling.

The critic reviews in `docs/findings/` remain the most useful artifact here —
including the observation that embedding similarity measures shared
vocabulary, not epistemic stance, which later informed daimon's recall work.
