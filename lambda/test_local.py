#!/usr/bin/env python3
"""
test_local.py — end-to-end exercise of the tournament Lambda, no AWS needed.

    python3 lambda/test_local.py

Runs the handler against a local directory (CAMEL_LOCAL_DIR) with a small
game count and a fake Lambda context whose clock drains fast enough to force
self-invoke chunking. Covers: acceptance, chunk continuation, leaderboard
publishing, roster persistence, and the rejection paths (banned import,
per-move timeout, name collision).
"""

import json
import os
import shutil
import sys
import tempfile

WORK = tempfile.mkdtemp(prefix="camel-lambda-test-")
os.environ["CAMEL_LOCAL_DIR"] = WORK
os.environ["CAMEL_TOTAL_GAMES"] = "8"
os.environ["CAMEL_SMOKE_GAMES"] = "1"
os.environ["CAMEL_MOVE_LIMIT_S"] = "0.5"
os.environ["CAMEL_WORKERS"] = "2"  # exercises the fork-parallel round path
os.environ["CAMEL_GAMES_PER_WORKER_ROUND"] = "2"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "lambda"))

import handler  # noqa: E402
from storage import Storage  # noqa: E402

GOOD_BOT = """
from playerinterface import PlayerInterface
import random

class UnitCamel(PlayerInterface):
    def move(player, g):
        if random.random() < 0.5:
            return [2, random.choice(g.camel_colors)]
        return [0]
"""

BAD_IMPORT_BOT = """
import os

class SneakyCamel:
    def move(player, g):
        os.system("echo pwned")
        return [0]
"""

TIMEOUT_BOT = """
import time

class SlowCamel:
    def move(player, g):
        time.sleep(2)
        return [0]
"""


class FakeContext:
    """Drains 25s of 'remaining time' per check to force chunking."""

    invoked_function_arn = "arn:aws:lambda:local:0:function:camel-up-tournament"

    def __init__(self, start_ms=200_000):
        self.remaining = start_ms

    def get_remaining_time_in_millis(self):
        self.remaining -= 25_000
        return self.remaining


def run_to_completion(payload):
    chunks = 0
    while True:
        result = handler.handler(payload, FakeContext())
        if isinstance(result, dict) and "continue" in result:
            payload = result["continue"]
            chunks += 1
            continue
        return result, chunks


def read_status(sid):
    with open(os.path.join(WORK, f"images/camel-up/status/{sid}.json")) as f:
        return json.load(f)


failures = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        failures.append(label)


print("1. valid bot is accepted, tournament chunks, leaderboard published")
result, chunks = run_to_completion(
    {"id": "sub-1", "botName": "UnitCamel", "author": "tester", "code": GOOD_BOT}
)
status = read_status("sub-1")
board = Storage().read_leaderboard()
names = [b["name"] for b in board["bots"]] if board else []
check("completes", result.get("status") == "complete", str(result))
check("chunked at least once", chunks >= 1, f"chunks={chunks}")
check("status complete w/ rank", status["phase"] == "complete" and status.get("rank"), str(status))
check("leaderboard has UnitCamel + builtins", board and "UnitCamel" in names and "tb-FabelFelix" in names)
check("accepted bot persisted", os.path.exists(os.path.join(WORK, "camel-up/bots/UnitCamel.py")))
check("full game count", status["gamesDone"] == 8, str(status["gamesDone"]))

print("2. banned import is rejected")
result, _ = run_to_completion(
    {"id": "sub-2", "botName": "SneakyCamel", "author": "tester", "code": BAD_IMPORT_BOT}
)
status = read_status("sub-2")
check("rejected", result.get("status") == "rejected", str(result))
check("reason mentions import", "import" in status.get("reason", ""), status.get("reason"))

print("3. slow bot is disqualified on move time")
result, _ = run_to_completion(
    {"id": "sub-3", "botName": "SlowCamel", "author": "tester", "code": TIMEOUT_BOT}
)
status = read_status("sub-3")
check("rejected", result.get("status") == "rejected", str(result))
check("reason mentions time limit", "time limit" in status.get("reason", ""), status.get("reason"))

print("4. duplicate name is rejected (existing accepted bot)")
result, _ = run_to_completion(
    {"id": "sub-4", "botName": "UnitCamel", "author": "tester", "code": GOOD_BOT}
)
check("rejected", result.get("status") == "rejected", str(result))

print("5. builtin name is rejected")
result, _ = run_to_completion(
    {"id": "sub-5", "botName": "tb-FabelFelix", "author": "tester", "code": GOOD_BOT}
)
check("rejected", result.get("status") == "rejected", str(result))

print("6. rerun rebuilds leaderboard including accepted UnitCamel")
result, _ = run_to_completion({"op": "rerun", "id": "rerun-1"})
board = Storage().read_leaderboard()
names = [b["name"] for b in board["bots"]]
check("completes", result.get("status") == "complete", str(result))
check("roster includes accepted bot", "UnitCamel" in names, str(names))

shutil.rmtree(WORK, ignore_errors=True)
if failures:
    print(f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("\nall checks passed")
