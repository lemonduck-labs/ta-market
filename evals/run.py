"""Run the Move forward planner evals as CI does, and fail if a score is below its bar.

    python evals/run.py screen                      plan_screen on the shared cases (no model); bar 1.0
    python evals/run.py pipeline                    plan_live on the stand-in drafter, one epoch; bar 1.0
    python evals/run.py live --model anthropic/<model> [--epochs 3]
                                                    plan_live on a real model; reports, no bar

Logs go to evals/logs (not in git), or to --log-dir; `inspect view --log-dir evals/logs` shows them.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fake_drafter  # noqa: E402,F401  registers fakedrafter before any model is resolved
from plan_evals import plan_live, plan_screen  # noqa: E402
from inspect_ai import eval as inspect_eval  # noqa: E402


def scores(log) -> dict[str, float]:
    out = {}
    for s in (log.results.scores if log.results else []):
        for name, m in s.metrics.items():
            out[f"{s.name}/{s.reducer + '/' if s.reducer else ''}{name}"] = m.value
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("which", choices=["screen", "pipeline", "live"])
    ap.add_argument("--model")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--log-dir", default=str(HERE / "logs"))
    a = ap.parse_args(argv)
    if a.which == "screen":
        task, model, bar = plan_screen(), "mockllm/model", 1.0
    elif a.which == "pipeline":
        task, model, bar = plan_live(epochs=1), "fakedrafter/plan", 1.0
    else:
        if not a.model:
            ap.error("live needs --model")
        task, model, bar = plan_live(epochs=a.epochs), a.model, None
    log = inspect_eval(task, model=model, log_dir=a.log_dir, display="plain")[0]
    got = scores(log)
    print(f"samples: {log.results.total_samples if log.results else 0}")
    for k, v in got.items():
        print(f"{k}: {v:.3f}")
    if log.status != "success":
        print(f"the eval did not finish: {log.status} {log.error.message if log.error else ''}")
        return 1
    if bar is not None:
        low = {k: v for k, v in got.items() if k.endswith("accuracy") and not v >= bar}
        if low:
            print("below the bar: " + ", ".join(f"{k} {v:.3f}" for k, v in low.items()))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
