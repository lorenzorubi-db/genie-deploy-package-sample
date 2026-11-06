"""Pull-request check: every agent has a benchmark result for exactly the definition being merged, at or above the threshold.

Usage: python ci/check_benchmarks.py [--threshold 0.8]   (threshold defaults to settings.yml)
"""
import argparse
import hashlib
import json
import os
import sys


def _sha(path):
    with open(path, encoding="utf-8") as f:
        return hashlib.sha256(f.read().encode("utf-8")).hexdigest()


def check(root, threshold):
    errors = []
    src = os.path.join(root, "src")
    keys = sorted(f.removesuffix(".geniespace.json") for f in os.listdir(src) if f.endswith(".geniespace.json"))
    if not keys:
        errors.append("no agent definitions in src/")
    for key in keys:
        res = os.path.join(root, "benchmarks", f"{key}.json")
        if not os.path.exists(res):
            errors.append(f"{key}: no benchmark result (run save_and_benchmark in dev)")
            continue
        with open(res, encoding="utf-8") as f:
            r = json.load(f)
        if r.get("definition_sha256") != _sha(os.path.join(src, f"{key}.geniespace.json")):
            errors.append(f"{key}: benchmark result is stale (the definition changed after the run): run save_and_benchmark again")
        elif r.get("score", 0) < threshold:
            errors.append(f"{key}: score {r.get('score', 0):.0%} is below the threshold {threshold:.0%}")
    return errors


if __name__ == "__main__":
    import yaml

    p = argparse.ArgumentParser()
    p.add_argument("--threshold", type=float)
    a = p.parse_args()
    with open("settings.yml", encoding="utf-8") as f:
        threshold = a.threshold if a.threshold is not None else float(yaml.safe_load(f).get("threshold", 0.8))
    errs = check(".", threshold)
    for e in errs:
        print("FAIL", e)
    print("benchmark results OK" if not errs else f"{len(errs)} problem(s)")
    sys.exit(1 if errs else 0)
