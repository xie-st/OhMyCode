# Issue Tracker

Issues for this repo live in GitHub Issues on the maintainer's fork:
**https://github.com/xie-st/OhMyCode/issues**

The upstream is `AlphaLab-USTC/OhMyCode`; the maintainer uses their personal fork
as the primary issue store while iterating. Skills should target the fork
explicitly via `--repo xie-st/OhMyCode` rather than auto-detecting from `origin`
(which points at the upstream).

## CLI

Use the `gh` CLI with explicit repo:

```powershell
gh issue create --repo xie-st/OhMyCode --title "..." --body "..." --label needs-triage
gh issue list   --repo xie-st/OhMyCode --label needs-triage
gh issue edit <num> --repo xie-st/OhMyCode --add-label ready-for-agent --remove-label needs-triage
gh issue close  <num> --repo xie-st/OhMyCode
```

## Skill consumers

- `to-issues` — break plans into issues; opens issues with `ready-for-agent` or `ready-for-human` label
- `triage` — moves issues through the state machine via label swaps
- `to-prd` — opens a PRD as an issue with body = the PRD content
- `qa` — opens QA bug reports with `needs-triage`

## Migration to upstream

When work stabilizes, issues can be migrated to `AlphaLab-USTC/OhMyCode` by
re-pointing this file's `--repo` flag. Until then, the fork is the source of
truth for tracking.
