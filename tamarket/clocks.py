"""Statutory clocks on synthetic records: when a notice is due, when a family in bed and
breakfast reaches 6 weeks, and when a review decision is due. The reference for
tamarket/spec/clocks.mjs; both must give the answers in tamarket/spec/clocks.json's cases.

A period of N days "beginning with" a day ends on that day plus N - 1 (s.208(4), s.213AA and
SI 2018/223 reg. 9 all count this way; 6 weeks in B&B are counted the same way from the placement). Dates are ISO strings (YYYY-MM-DD), compared as text.
Dates for an officer to act on; the officer decides and records what was done.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

SPEC = Path(__file__).resolve().parent / "spec" / "clocks.json"


def load_rules(path: Path = SPEC) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["rules"]


def add_days(iso: str, n: int) -> str:
    return (dt.date.fromisoformat(iso) + dt.timedelta(days=n)).isoformat()


def last_day(start: str, days: int) -> str:
    """The last day of a period of `days` days beginning with `start`."""
    return add_days(start, days - 1)


def _state(due: str, today: str, done_on: str | None, soon_days: int, done_words=("sent_on_time", "sent_late")) -> str:
    if done_on:
        return done_words[0] if done_on <= due else done_words[1]
    if today > due:
        return "overdue"
    return "due" if today >= add_days(due, -soon_days) else "later"


def s208(record: dict, today: str, sent_on: str | None = None, rules: dict | None = None) -> dict:
    rules = rules or load_rules()
    if not record.get("placed_in_another_district"):
        return {"applies": False, "due": None, "state": "not_applicable"}
    due = last_day(record["placed_on"], rules["s208"]["days"])
    return {"applies": True, "due": due, "state": _state(due, today, sent_on, rules["soon_days"])}


YOUNG_APPLICANT = "applicant aged 16 or 17"


def child_scope(record: dict, rules: dict | None = None) -> dict:
    """Whether s.213AA applies to the placement, for how many children, and whether one of them is
    a 16 or 17 year old applicant (a child under the section, asked instead of a parent, s.213AA(3))."""
    rules = rules or load_rules()
    young = record.get("priority_need") == YOUNG_APPLICANT
    n = int(record.get("children") or 0) + (1 if young else 0)
    if not n:
        return {"applies": False, "reason": "no_child", "children": 0, "young_applicant": False}
    # An application comes before the placement, so a placement before the section came into
    # force means the application was before it too. A later placement may still follow an
    # earlier application: the officer checks the application date.
    if record["placed_on"] < rules["child"]["in_force"]:
        return {"applies": False, "reason": "before_commencement", "children": n, "young_applicant": young}
    return {"applies": True, "reason": "check_application_date", "children": n, "young_applicant": young}


def child_due(placed_on: str, agreed_on: str | None, info_on: str | None, rules: dict | None = None) -> str | None:
    """The last day for one body's notice: 14 days beginning with the latest of the agreement, the
    information about that body and the placement (s.213AA(4)). None until both have been received."""
    rules = rules or load_rules()
    if not agreed_on or not info_on:
        return None
    return last_day(max(placed_on, agreed_on, info_on), rules["child"]["days"])


def bnb(record: dict, today: str, rules: dict | None = None) -> dict:
    """The day a family in B&B must move by: the last day of 6 weeks beginning with the day of the
    placement (the placement day plus 41). From the next day 6 weeks are reached ("past")."""
    rules = rules or load_rules()
    if "bnb-family-limit" not in (record.get("suitability_checks") or []):
        return {"applies": False, "limit": None, "state": "not_applicable"}
    limit = last_day(record["placed_on"], rules["bnb_family"]["days"])
    state = "past" if today > limit else "soon" if today >= add_days(limit, -rules["soon_days"]) else "later"
    return {"applies": True, "limit": limit, "state": state}


def review(requested_on: str, today: str, decided_on: str | None = None, agreed_to: str | None = None,
           rules: dict | None = None) -> dict:
    rules = rules or load_rules()
    due = agreed_to or last_day(requested_on, rules["review"]["days"])
    return {"due": due, "state": _state(due, today, decided_on, rules["soon_days"], ("decided", "decided_late"))}


def run_case(c: dict, rules: dict | None = None) -> dict:
    rules = rules or load_rules()
    f = c["fn"]
    if f == "s208":
        return s208(c["record"], c["today"], c.get("sent_on"), rules)
    if f == "child_scope":
        return child_scope(c["record"], rules)
    if f == "child_due":
        return {"due": child_due(c["placed_on"], c.get("agreed_on"), c.get("info_on"), rules)}
    if f == "bnb":
        return bnb(c["record"], c["today"], rules)
    if f == "review":
        return review(c["requested_on"], c["today"], c.get("decided_on"), c.get("agreed_to"), rules)
    raise ValueError("no such clock: " + f)
