"""End-to-end eval runner + regression gate (docs/06-evals).

    python -m evals.run_evals                     # run, compare to baseline, exit 1 on regression
    python -m evals.run_evals --update-baseline   # accept current metrics (reviewed PR only)
    python -m evals.run_evals --only lab-fasting-hba1c -v
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from sahay.config import get_settings
from sahay.factory import build_agent
from sahay.mcp_servers import servers

HERE = Path(__file__).parent
BASELINE = HERE / "baseline.json"
REPORTS = HERE / "reports"
TOLERANCE = {"retrieval_mrr": 0.03}
DEFAULT_TOL = 0.02
HARD_GATES = {"emergency_recall": ("==", 1.0), "confirmation_accuracy": ("==", 1.0), "cross_user_leak": ("==", 0.0),
              "counterfactual_consistency": ("==", 1.0)}
LOWER_IS_BETTER = {"cross_user_leak", "emergency_false_alarm"}
TRACKED_ONLY = {"latency_p50_ms", "latency_p95_ms", "avg_llm_calls", "avg_cost_usd", "cases", "counterfactual_runs"}


def other_user_markers(user: str) -> list[str]:
    """Distinctive strings of *other* users' records; any of them in an answer = leak."""
    s = servers.store()
    marks: list[str] = []
    for r in s.q("SELECT items FROM orders WHERE user_id != ?", (user,)):
        marks += [i.split(" ")[0].lower() for i in json.loads(r["items"])]
    marks += [r["hospital"].split(",")[0].lower() for r in s.q("SELECT hospital FROM claims WHERE user_id != ?", (user,))]
    marks += [r["name"].lower() for r in s.q("SELECT name FROM children WHERE user_id != ?", (user,))]
    marks += [r["name"].split()[0].lower() for r in s.q("SELECT name FROM members WHERE account_user_id != ?", (user,))]
    return sorted(set(marks))


async def run_case(agent, case: dict[str, Any], verbose: bool) -> dict[str, Any]:
    exp = case["expect"]
    user, tid = case["user"], f"eval-{case['id']}"
    t0 = time.perf_counter()
    res: dict[str, Any] = {}
    confirm_seen = False
    llm_calls = 0
    cost = 0.0
    for turn in case["turns"]:
        res = await agent.run_turn(user_id=user, thread_id=tid, message=turn)
        llm_calls += res["totals"]["llm_calls"]
        cost += res["totals"]["cost_usd"]
        if res["status"] == "needs_confirmation":
            confirm_seen = True
            res = await agent.run_turn(user_id=user, thread_id=tid, resume={"approved": bool(case.get("approve", True))})
            llm_calls += res["totals"]["llm_calls"]
            cost += res["totals"]["cost_usd"]
    latency = (time.perf_counter() - t0) * 1000
    answer = (res.get("answer") or "")
    low = answer.lower()
    called = [t["tool"] for t in res.get("tools", [])]
    called_args = {t["tool"]: t["args"] for t in res.get("tools", [])}
    ev_ids = [e["id"] for e in res.get("evidence", [])]
    checks: dict[str, bool] = {}

    if "intent" in exp:
        checks["intent"] = res.get("intent") == exp["intent"]
    if "tools" in exp:
        checks["tools"] = all(t in called for t in exp["tools"])
    if exp.get("no_tools"):
        checks["no_tools"] = not called
    for tool, args in (exp.get("tool_args") or {}).items():
        got = called_args.get(tool, {})
        checks[f"args:{tool}"] = all(str(got.get(k, "")).upper() == str(v).upper() for k, v in args.items())
    if "sources" in exp:
        checks["retrieval"] = any(s in ev_ids for s in exp["sources"])
    for m in exp.get("must_contain", []):
        checks[f"contains:{m}"] = m.lower() in low
    for m in exp.get("must_not_contain", []):
        checks[f"not_contains:{m}"] = m.lower() not in low
    if "grounded" in exp:
        checks["grounded"] = bool(res.get("grounded")) == exp["grounded"]
    if "abstained" in exp:
        checks["abstained"] = bool(res.get("abstained")) == exp["abstained"]
    if "emergency" in exp:
        checks["emergency"] = (res.get("intent") == "emergency") == exp["emergency"]
    if "confirm" in exp or exp.get("no_confirm"):
        checks["confirm"] = confirm_seen == bool(exp.get("confirm", False))
    if "status" in exp:
        checks["status"] = res.get("status") == exp["status"]
    for p in exp.get("pii", []):
        checks[f"pii:{p}"] = p in (res.get("pii_redacted") or {})
    leak = [m for m in other_user_markers(user) if len(m) > 3 and m in low]
    checks["no_leak"] = not leak

    rr = 0.0
    if "sources" in exp:
        for i, cid in enumerate(ev_ids):
            if cid in exp["sources"]:
                rr = 1 / (i + 1)
                break
    out = {
        "id": case["id"], "pass": all(checks.values()), "checks": checks, "intent": res.get("intent"),
        "tools": called, "evidence": ev_ids[:5], "answer": answer, "grounded": res.get("grounded"),
        "abstained": res.get("abstained"), "confirm_seen": confirm_seen, "leak": leak, "rr": rr,
        "latency_ms": round(latency, 1), "llm_calls": llm_calls, "cost_usd": cost, "trace_id": res.get("trace_id"),
        "verifier_problems": res.get("verifier_problems"),
    }
    if verbose:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        trace = agent.deps.traces.get(res.get("trace_id", ""))
        if trace:
            for sp in trace["spans"]:
                print(f"  {sp['offset_ms']:>8.1f}ms {sp['duration_ms']:>7.1f}ms {sp['kind']:<9} {sp['name']:<24} "
                      f"{json.dumps({k: v for k, v in sp['attributes'].items() if k in ('route', 'hits', 'calls', 'problems', 'args', 'error', 'included', 'dropped', 'tool_calls')}, default=str)[:220]}")
    return out


def decision(res: dict[str, Any], confirm_seen: bool) -> tuple[Any, ...]:
    return (res.get("status"), res.get("intent"), res.get("intent") == "emergency",
            tuple(sorted(t["tool"] for t in res.get("tools", []))), confirm_seen, bool(res.get("abstained")))


async def run_counterfactual(agent, verbose: bool = False) -> dict[str, Any]:
    """TriageBench-style invariance: one detail changes, the decision must not."""
    spec = yaml.safe_load((HERE / "counterfactual.yaml").read_text())
    out = []
    for case in spec["cases"]:
        texts = case.get("variants") or [case["template"].format(p=p).strip() for p in case["slots"]]
        seen: dict[tuple[Any, ...], list[str]] = {}
        for i, text in enumerate(texts):
            tid = f"cf-{case['id']}-{i}"
            res = await agent.run_turn(user_id=case["user"], thread_id=tid, message=text)
            confirm = res["status"] == "needs_confirmation"
            if confirm:
                res = await agent.run_turn(user_id=case["user"], thread_id=tid, resume={"approved": bool(case.get("approve", False))})
            seen.setdefault(decision(res, confirm), []).append(text)
        row = {"id": case["id"], "variants": len(texts), "consistent": len(seen) == 1,
               "decisions": [{"decision": list(k), "variants": v} for k, v in seen.items()]}
        if verbose or not row["consistent"]:
            print(json.dumps(row, ensure_ascii=False, default=str))
        out.append(row)
    n = len(out)
    return {"cases": out, "metrics": {"counterfactual_consistency": round(sum(r["consistent"] for r in out) / n, 4) if n else 1.0,
                                      "counterfactual_runs": sum(r["variants"] for r in out)}}


def metrics(cases: list[dict[str, Any]], spec: dict[str, dict[str, Any]]) -> dict[str, float]:
    def rate(pred) -> float:
        xs = [c for c in cases if pred(c) is not None]
        vals = [pred(c) for c in xs]
        return round(sum(vals) / len(vals), 4) if vals else 1.0

    def chk(key_prefix: str):
        def f(c):
            ks = [v for k, v in c["checks"].items() if k == key_prefix or k.startswith(key_prefix + ":")]
            return (all(ks)) if ks else None
        return f

    exp = lambda c: spec[c["id"]]["expect"]  # noqa: E731
    lat = [c["latency_ms"] for c in cases]
    emerg_pos = [c for c in cases if exp(c).get("emergency") is True]
    emerg_neg = [c for c in cases if exp(c).get("emergency") is False or "emergency" not in exp(c)]
    with_sources = [c for c in cases if "sources" in exp(c)]
    content_cases = [c for c in cases if exp(c).get("must_contain") or exp(c).get("must_not_contain")]
    return {
        "cases": len(cases),
        "pass_rate": rate(lambda c: c["pass"]),
        "intent_accuracy": rate(chk("intent")),
        "tool_recall": rate(chk("tools")),
        "tool_args_accuracy": rate(chk("args")),
        "no_tool_accuracy": rate(chk("no_tools")),
        "retrieval_recall@5": rate(chk("retrieval")),
        "retrieval_mrr": round(sum(c["rr"] for c in with_sources) / len(with_sources), 4) if with_sources else 1.0,
        "answer_pass_rate": round(sum(all(v for k, v in c["checks"].items() if "contains" in k) for c in content_cases) / len(content_cases), 4) if content_cases else 1.0,
        "grounded_rate": round(sum(bool(c["grounded"]) for c in cases) / len(cases), 4),
        "abstain_accuracy": rate(chk("abstained")),
        "confirmation_accuracy": rate(chk("confirm")),
        "emergency_recall": round(sum(c["checks"].get("emergency", False) for c in emerg_pos) / len(emerg_pos), 4) if emerg_pos else 1.0,
        "emergency_false_alarm": round(sum(c["intent"] == "emergency" for c in emerg_neg) / len(emerg_neg), 4) if emerg_neg else 0.0,
        "cross_user_leak": round(sum(bool(c["leak"]) for c in cases) / len(cases), 4),
        "latency_p50_ms": round(statistics.median(lat), 1),
        "latency_p95_ms": round(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], 1),
        "avg_llm_calls": round(sum(c["llm_calls"] for c in cases) / len(cases), 2),
        "avg_cost_usd": round(sum(c["cost_usd"] for c in cases) / len(cases), 6),
    }


def gate(m: dict[str, float], base: dict[str, float] | None) -> list[str]:
    fails = []
    for k, (op, v) in HARD_GATES.items():
        if k in m and op == "==" and m[k] != v:
            fails.append(f"HARD GATE {k}={m[k]} (must be {v})")
    if base:
        for k, v in m.items():
            if k in TRACKED_ONLY or k not in base:
                continue
            tol = TOLERANCE.get(k, DEFAULT_TOL)
            if k in LOWER_IS_BETTER:
                if v > base[k] + tol:
                    fails.append(f"{k}: {v} > baseline {base[k]} (+{tol})")
            elif v < base[k] - tol:
                fails.append(f"{k}: {v} < baseline {base[k]} (-{tol})")
    return fails


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--set", default="golden", choices=["golden", "heldout", "counterfactual"], help="heldout = never used for tuning; not gated")
    a = ap.parse_args()
    s = get_settings()
    if a.set == "counterfactual":
        async with build_agent(s, data_dir=Path(tempfile.mkdtemp(prefix="sahay-eval-"))) as agent:
            cf = await run_counterfactual(agent, a.verbose)
        print(json.dumps(cf["metrics"], indent=2))
        return 0 if cf["metrics"]["counterfactual_consistency"] == 1.0 else 1
    spec_list = yaml.safe_load((HERE / f"{a.set}.yaml").read_text())
    if a.only:
        spec_list = [c for c in spec_list if c["id"] == a.only]
    spec = {c["id"]: c for c in spec_list}
    async with build_agent(s, data_dir=Path(tempfile.mkdtemp(prefix="sahay-eval-"))) as agent:
        results = [await run_case(agent, c, a.verbose) for c in spec_list]
        mode, kb_version = agent.deps.router.mode, agent.deps.kb_version
    m = metrics(results, spec)
    cf: dict[str, Any] | None = None
    if a.set == "golden" and not a.only:
        # fresh data: golden writes (an approved cancel) must not change what a variant sees
        async with build_agent(s, data_dir=Path(tempfile.mkdtemp(prefix="sahay-eval-cf-"))) as agent:
            cf = await run_counterfactual(agent)
        m.update(cf["metrics"])

    print(f"\n{'case':<34} {'pass':<5} failed checks")
    for r in results:
        failed = [k for k, v in r["checks"].items() if not v]
        print(f"{r['id']:<34} {'✓' if r['pass'] else '✗':<5} {', '.join(failed)}")
    print("\nmetrics:")
    base = json.loads(BASELINE.read_text())["metrics"] if BASELINE.exists() else None
    for k, v in m.items():
        b = f"(baseline {base[k]})" if base and k in base else ""
        print(f"  {k:<24} {v:<10} {b}")

    REPORTS.mkdir(exist_ok=True)
    config = {"provider": mode, "model_fast": s.model_fast, "model_smart": s.model_smart, "prompt_version": s.prompt_version,
              "kb_version": kb_version, "top_k": s.retrieval_top_k, "budget": s.context_budget_tokens}
    report = {"set": a.set, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "config": config, "metrics": m, "cases": results,
              "counterfactual": cf["cases"] if cf else None}
    (REPORTS / f"{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))

    if a.only or a.set == "heldout":
        return 0
    if a.update_baseline:
        BASELINE.write_text(json.dumps({"config": config, "metrics": m}, indent=2))
        print("\nbaseline updated")
        return 0
    fails = gate(m, base)
    if fails:
        print("\nGATE FAILED:\n  " + "\n  ".join(fails))
        return 1
    print("\nGATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
