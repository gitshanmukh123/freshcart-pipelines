# Recorded Evidence

This file records only actions that were actually executed. Pending evidence is
listed explicitly and must not be described as complete.

## Local verification

```text
python -m pytest -q
15 passed
```

The notebook JSON was generated and parsed successfully with Python's `json`
module. The A3 red run produced:

```text
AssertionError: assert 105 == 120
1 failed
```

The restored A3 green run produced:

```text
1 passed
```

## GitHub Actions

Repository: https://github.com/gitshanmukh123/freshcart-pipelines

| State | Commit | Result | Run |
|---|---|---|---|
| Initial scaffold | `0e939dbbeada253dc17523bda57bce6ab24d9f5a` | success | https://github.com/gitshanmukh123/freshcart-pipelines/actions/runs/43719040946 |
| A3 red (`test_size=0.3`) | `77e3616d0e9f75a6ba1f3c8b447fb50b9b3dc780` | failure | https://github.com/gitshanmukh123/freshcart-pipelines/actions/runs/43719153937 |
| A3 green (`test_size=0.2`) | `51a3d18225a012d2b87928fc03a4168b13ab2df3` | success | https://github.com/gitshanmukh123/freshcart-pipelines/actions/runs/43719240283 |

## Pending evidence

| Evidence | Status |
|---|---|
| Snowflake B1-B5 execution | NOT RUN - no personal Snowflake session in this workspace |
| Mage UI pipeline and C2 depth runs | NOT RUN - Mage CLI/runtime not installed |
| RabbitMQ ACK/NACK logs | NOT RUN - no live broker URL used |
| Bonus replay / Snowflake lakehouse load | NOT RUN - requires live broker and optional Snowflake |
| Report screenshots and student explanations | Student-owned |
