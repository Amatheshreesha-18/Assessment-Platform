"""Authoritative scoring primitives. No network, clock, or model calls are allowed here."""
from dataclasses import dataclass
import hashlib
import json
import random

@dataclass(frozen=True)
class TestCase:
    input: object
    expected: object
    points: float

def seeded_cases(seed: dict, cases: list[dict]) -> list[TestCase]:
    raw = json.dumps(seed, sort_keys=True, separators=(",", ":"))
    rng = random.Random(int(hashlib.sha256(raw.encode()).hexdigest()[:16], 16))
    result=[]
    for case in cases:
        expected=case.get("expected")
        if expected == "$seeded_int": expected=rng.randint(0, 1000)
        result.append(TestCase(case.get("input"), expected, float(case.get("points", 1))))
    return result

def score_results(results: list[dict], max_score: float = 100.0) -> dict:
    total=sum(float(r.get("points", 0)) for r in results)
    earned=sum(float(r.get("points", 0)) for r in results if r.get("passed") is True)
    score=round((earned/total)*max_score, 2) if total else 0.0
    return {"score": score, "passed": sum(1 for r in results if r.get("passed") is True), "total": len(results), "normalized": results}
