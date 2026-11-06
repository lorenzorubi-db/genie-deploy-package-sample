"""Benchmark gate on the deployed agents: score at or above the threshold and no regression against the dev result.

Usage: python ci/benchmark_gate.py --target prod [--keys cx_insights,...]
Space ids come from `databricks bundle summary`. Failed questions are re-run once (Genie is non-deterministic).
Eval Run API is Beta: if it is unavailable, run the benchmarks in the UI and record the score in the pull request.
"""
import argparse
import json
import os
import subprocess
import sys
import time

TERMINAL = ("DONE", "EVALUATION_FAILED", "EVALUATION_CANCELLED", "EVALUATION_TIMEOUT")


def decide(now, baseline, threshold):
    """now/baseline: {benchmark id: assessment}, scored benchmarks only. Pass = score >= threshold and nothing GOOD in baseline is not GOOD now."""
    total = len(now)
    score = sum(1 for a in now.values() if a == "GOOD") / total if total else 0.0
    regressions = sorted(q for q, a in baseline.items() if a == "GOOD" and q in now and now[q] != "GOOD")
    return (score >= threshold and not regressions), score, regressions


def evaluate(w, space_id, question_ids=None):
    base = f"/api/2.0/genie/spaces/{space_id}/eval-runs"
    run = w.api_client.do("POST", base, body={"benchmark_question_ids": question_ids} if question_ids else {})
    rid = run["eval_run_id"]
    while run["eval_run_status"] not in TERMINAL:
        time.sleep(30)
        run = w.api_client.do("GET", f"{base}/{rid}")
    if run["eval_run_status"] != "DONE":
        raise RuntimeError(f"benchmark run {rid} ended {run['eval_run_status']}")
    results, token = [], None
    while True:
        page = w.api_client.do("GET", f"{base}/{rid}/results", query={"page_token": token} if token else None)
        results += page.get("eval_results", [])
        token = page.get("next_page_token")
        if not token:
            break
    out = {}
    for r in results:
        d = w.api_client.do("GET", f"{base}/{rid}/results/{r['result_id']}")
        out[r.get("benchmark_question_id") or r.get("question")] = (r.get("question", ""), d.get("assessment", "UNKNOWN"))
    return rid, out


if __name__ == "__main__":
    import yaml
    from databricks.sdk import WorkspaceClient

    p = argparse.ArgumentParser()
    p.add_argument("--target", default="prod")
    p.add_argument("--keys", default="")
    p.add_argument("--profile", help="~/.databrickscfg profile (local runs); CI uses the DATABRICKS_* env vars")
    a = p.parse_args()
    with open("settings.yml", encoding="utf-8") as f:
        s = yaml.safe_load(f)
    summary = json.loads(subprocess.run(["databricks", "bundle", "summary", "-t", a.target, "-o", "json"]
                                        + (["-p", a.profile] if a.profile else []),
                                        check=True, capture_output=True, text=True).stdout)
    spaces = summary["resources"]["genie_spaces"]
    keys = [k for k in (a.keys.split(",") if a.keys else spaces) if k]
    w = WorkspaceClient(profile=a.profile) if a.profile else WorkspaceClient()
    failed = []
    for key in keys:
        sid = spaces[key]["id"]
        with open(os.path.join("src", f"{key}.geniespace.json"), encoding="utf-8") as f:
            qs = json.load(f).get("benchmarks", {}).get("questions", [])
        unscored = {q["id"] for q in qs if not any(x.get("content") for x in q.get("answer") or [])}
        with open(os.path.join("benchmarks", f"{key}.json"), encoding="utf-8") as f:
            dev = {qid: q["assessment"] for qid, q in json.load(f)["questions"].items() if qid not in unscored}
        rid, res = evaluate(w, sid)
        retry = [qid for qid, (_, a_) in res.items() if a_ != "GOOD" and qid not in unscored]
        if retry:
            _, again = evaluate(w, sid, retry)
            res.update({qid: v for qid, v in again.items() if v[1] == "GOOD"})
        now = {qid: a_ for qid, (_, a_) in res.items() if qid not in unscored}
        ok, score, regressions = decide(now, dev, float(s.get("threshold", 0.8)))
        print(f"{key}: {score:.0%} on {len(now)} scored benchmarks (run {rid}) → {'PASS' if ok else 'FAIL'}")
        for qid, (question, a_) in res.items():
            if a_ != "GOOD":
                print(f"    {a_ if qid not in unscored else 'not scored':12} {question[:100]}")
        for qid in regressions:
            print(f"    REGRESSION   {res[qid][0][:100]}")
        if not ok:
            failed.append(key)
    sys.exit(1 if failed else 0)
