"""Create or replace the metric views on the target schema, before the agents are deployed.

Usage: python ci/apply_metric_views.py --target prod   (catalog.schema and warehouse from settings.yml)
Auth: DATABRICKS_HOST + service principal OAuth (DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET).
"""
import argparse
import os
import sys
import time


def statements(folder, catalog, schema):
    out = []
    for fn in sorted(os.listdir(folder)):
        if fn.endswith(".sql"):
            with open(os.path.join(folder, fn), encoding="utf-8") as f:
                sql = f.read().replace("<catalog>.<schema>", f"{catalog}.{schema}")
            sql = "\n".join(ln for ln in sql.splitlines() if not ln.startswith("-- ")).strip().rstrip(";").strip()
            out.append((fn.removesuffix(".sql"), sql))
    return out


def run(w, warehouse_id, sql):
    r = w.api_client.do("POST", "/api/2.0/sql/statements",
                        body={"statement": sql, "warehouse_id": warehouse_id, "wait_timeout": "50s"})
    while r["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(5)
        r = w.api_client.do("GET", f"/api/2.0/sql/statements/{r['statement_id']}")
    if r["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(r["status"].get("error", {}).get("message", r["status"]["state"]))


if __name__ == "__main__":
    import yaml
    from databricks.sdk import WorkspaceClient

    p = argparse.ArgumentParser()
    p.add_argument("--target", default="prod", choices=["dev", "prod"])
    p.add_argument("--profile", help="~/.databrickscfg profile (local runs); CI uses the DATABRICKS_* env vars")
    a = p.parse_args()
    with open("settings.yml", encoding="utf-8") as f:
        s = yaml.safe_load(f)
    catalog, schema = s[f"{a.target}_schema"].split(".")
    w = WorkspaceClient(profile=a.profile) if a.profile else WorkspaceClient()
    for name, sql in statements("metric_views", catalog, schema):
        run(w, s[f"{a.target}_warehouse_id"], sql)
        print("applied", f"{catalog}.{schema}.{name}")
    sys.exit(0)
