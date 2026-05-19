# Triage Labels

The 5 canonical triage roles use their default names — no renaming:

| Role | Label string | Meaning |
|---|---|---|
| `needs-triage` | `needs-triage` | Maintainer needs to evaluate |
| `needs-info` | `needs-info` | Waiting on reporter |
| `ready-for-agent` | `ready-for-agent` | Fully specified, AFK-ready (an agent can pick it up with no human context) |
| `ready-for-human` | `ready-for-human` | Needs human implementation |
| `wontfix` | `wontfix` | Will not be actioned |

## Bootstrap

The fork (`xie-st/OhMyCode`) currently has no labels. Create them once:

```powershell
gh label create needs-triage    --repo xie-st/OhMyCode --color FBCA04 --description "Maintainer needs to evaluate"
gh label create needs-info      --repo xie-st/OhMyCode --color D4C5F9 --description "Waiting on reporter"
gh label create ready-for-agent --repo xie-st/OhMyCode --color 0E8A16 --description "Fully specified, AFK-ready"
gh label create ready-for-human --repo xie-st/OhMyCode --color 1D76DB --description "Needs human implementation"
gh label create wontfix         --repo xie-st/OhMyCode --color CCCCCC --description "Will not be actioned"
```

## State machine (per triage skill)

```
                ┌──────────────┐
new issue ────► │ needs-triage │
                └──────┬───────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
  needs-info     ready-for-agent  ready-for-human    wontfix
       │               │               │             (closed)
       ▼               ▼               ▼
   (reporter        (AFK agent       (human PR)
    replies)         opens PR)
```
