"""Accuracy gate. Every number that appears on screen, in captions or in the
post text must be either:
  - a sourced fact   (spec["facts"][*]["value"], with source + url), or
  - a computed value (spec["checks"][*], recomputed here in code), or
  - an explained constant (spec["allowed_numbers"][*], with a reason).
Any other number fails the run.

spec["checks"] = [{"expr": "round(payoff(1000, 22.36, 100)['interest'])", "expect": 117,
                  "why": "interest at $100/mo"}, ...]
  expr is evaluated with the functions in moneymath.py.

Usage: python verify.py <episode_dir>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moneymath  # noqa: E402

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def nums(text):
    out = []
    for m in NUM.findall(text or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("value", "count_to", "decimals", "at", "reveal_at", "bar"):
                continue  # numeric layout/data fields, checked separately
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def main(ep):
    ep = Path(ep)
    spec = json.loads((ep / "spec.json").read_text())
    errors = []

    allowed = set()
    for f in spec.get("facts", []):
        for k in ("source", "url", "value"):
            if not f.get(k):
                errors.append(f"fact missing {k}: {f}")
        allowed.update(nums(f.get("value", "")))
        allowed.update(nums(f.get("claim", "")))
        allowed.update(nums(f.get("source", "")))
    env = {k: getattr(moneymath, k) for k in dir(moneymath) if not k.startswith("_")}
    env["round"] = round
    for c in spec.get("checks", []):
        got = eval(c["expr"], {"__builtins__": {}}, env)  # expressions are ours, in the repo
        if abs(float(got) - float(c["expect"])) > 1e-9:
            errors.append(f"MATH MISMATCH {c['expr']} = {got}, spec says {c['expect']}")
        allowed.add(float(c["expect"]))
    for a in spec.get("allowed_numbers", []):
        if not a.get("why"):
            errors.append(f"allowed number without reason: {a}")
        allowed.add(float(a["n"]))

    def ok(x):
        return any(abs(x - a) < 1e-9 for a in allowed)

    seen = []
    for where, block in (("sentences", spec["sentences"]), ("scenes", spec["scenes"]),
                         ("thumbnail", spec.get("thumbnail", {})), ("metadata", spec.get("metadata", {}))):
        for s in strings(block):
            if s.startswith("http"):
                continue
            for x in nums(s):
                seen.append(x)
                if not ok(x):
                    errors.append(f"UNVERIFIED NUMBER {x:g} in {where}: {s[:90]!r}")
    for sc in spec["scenes"]:
        if "count_to" in sc and not ok(float(sc["count_to"])):
            errors.append(f"UNVERIFIED count_to {sc['count_to']}")
        for r in sc.get("rows", []):
            if not ok(round(r["value"], 2)) and not ok(r["value"]):
                errors.append(f"UNVERIFIED bar value {r['value']}")

    md = spec.get("metadata", {})
    for k in ("description", "tiktok_caption"):
        if md and not md.get(k, "").rstrip().endswith("Not financial advice."):
            errors.append(f"{k} must end with 'Not financial advice.'")
        if md and "Source" not in md.get(k, ""):
            errors.append(f"{k} must list sources")

    if errors:
        print("\n".join(errors))
        raise SystemExit("VERIFY FAILED - fix or cut the number")
    print(f"verify ok: {len(seen)} numbers checked against {len(allowed)} sourced/computed values")


if __name__ == "__main__":
    main(sys.argv[1])
