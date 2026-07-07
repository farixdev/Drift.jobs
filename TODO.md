# TODO — Drift

Everything from the original TODO (Google source, more jobs per source, better
scan feedback) shipped in **2.0**. The pause/continue idea was replaced with a
proper concurrent scan + Stop button. See `CHANGELOG.md`.

## Next up

### Full JD fetch for browser sources
- [ ] For LinkedIn/Indeed cards, fetch the detail page to get the real
      description (currently only the title is available), so scoring is as
      good as it is for the JSON API sources.

### Saved profiles + scheduling
- [ ] Save a named preset (resume + sources + threshold).
- [ ] Optional background re-run; notify on new high matches.

### Resume gap coach
- [ ] Aggregate `missing_skills` across all matches → "learn X to unlock N more
      jobs."

### More sources
- [ ] Otta, Y Combinator (Work at a Startup), Wellfound.

### Nice-to-haves
- [ ] Per-source result counts as chips on the results header.
- [ ] Sort options (newest, salary) in addition to best-match.
- [ ] Email digest export.
