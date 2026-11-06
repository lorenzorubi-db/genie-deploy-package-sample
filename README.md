# CX Genie · metric views and Genie agents

This repository holds the CX metric views and the CX Genie agents, and deploys them from the **dev** workspace to the
**prod** workspace. You change things in dev; GitHub deploys them to prod after a check and an approval.
The ETL that builds the gold tables lives in its own repository (see "When the ETL changes").

## Everyday use (curators)
1. Change an agent or a metric view **in the dev workspace** (Genie UI, or Genie Code).
2. Open this repo's Git folder in dev, open the notebook **`save_and_benchmark`**, and choose **Run all**.
   - First time only: fill in the fields at the top (agents, metric views, schemas, warehouses, groups). They are saved.
   - It saves the definitions into the repo and runs the benchmarks of every dev agent (a few minutes).
3. Read the summary at the bottom:
   - **PASS** for every agent → Git folder → commit and push to a new branch → open a pull request.
   - **FAIL** → improve the agent in dev (Benchmarks tab, Genie Code), then run the notebook again.
4. The pull request runs the checks automatically. When an owner approves and merges, GitHub asks the prod approvers;
   after their approval it deploys to prod and benchmarks the prod agents again.

Never edit a prod agent by hand: the next deploy overwrites it.

## What happens on a merge
```
① metric views created or replaced on the prod schema     ci/apply_metric_views.py
② agents deployed (updated in place: same agent, same id)  databricks bundle deploy -t prod
③ benchmarks re-run on the prod agents                     ci/benchmark_gate.py  (≥ threshold, no regression vs dev)
④ release tag                                              cx-genie-YYYYMMDD-N
```
If ③ fails the run is red. Fix in dev and save again, or roll back (below).

## Buttons (GitHub → Actions → cx-genie → Run workflow)
- **rebenchmark-prod**: re-runs the prod benchmarks without deploying. Use it after every ETL release.
- **rollback** with a release tag: redeploys that version (metric views and agents) and benchmarks it.

## Files
| Path | Written by | What it is |
|---|---|---|
| `settings.yml` | notebook | The fields of the notebook: agents, metric views, schemas, warehouses, groups, threshold |
| `databricks.yml` | notebook | Bundle configuration (dev and prod targets, retarget rule, groups) |
| `metric_views/<name>.sql` | notebook | Each metric view, with `<catalog>.<schema>` instead of the dev schema |
| `src/<key>.geniespace.json` | notebook | Each agent's full definition, exactly as in dev (never edit by hand) |
| `resources/<key>.genie_space.yml` | notebook | Each agent's bundle resource: title, description, permissions, protection |
| `benchmarks/<key>.json` | notebook | The dev benchmark result for exactly that definition (score, failures, hash) |
| `ci/*.py`, `.github/workflows/cx-genie.yml`, `pyproject.toml` | platform team | The pipeline |

## One-time setup (platform team)
1. GitHub repository from this template; protect `main` (pull requests and one review required).
2. Prod service principal: CAN MANAGE on the agents folder, `USE CATALOG`/`USE SCHEMA`/`SELECT` on the prod gold
   schema, `CREATE TABLE` on it (to create the metric views), CAN USE on the prod warehouse.
3. GitHub → Settings → Environments → **prod**: required reviewers; secrets `DATABRICKS_CLIENT_ID`,
   `DATABRICKS_CLIENT_SECRET`; variable `DATABRICKS_HOST` = prod workspace URL.
4. In the dev workspace: add this repo as a Git folder; curators run `save_and_benchmark` once to fill `settings.yml`.
5. **If the agents already exist in prod** (built by hand), bind them once before the first deploy, otherwise the deploy
   creates second copies: `databricks bundle deployment bind <key> <prod_space_id> -t prod` for each agent.

## Rules that keep prod agents in place (their history, links and ids)
- Never rename an agent key (`cx_insights`, …): a new key is a new agent. Every agent has `prevent_destroy`.
- Never change `prod_root_path`: the deployment state lives there.
- Never deploy prod from a laptop: only this pipeline deploys prod.

## When the ETL changes
The metric views read the gold tables and columns listed in their SQL. Before an ETL release that renames or removes one,
the ETL team adds the new column first, this repo switches to it (save, pull request, deploy), and only then the ETL
removes the old one. After every ETL release, run **rebenchmark-prod**.
