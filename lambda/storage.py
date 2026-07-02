"""
storage.py — S3-backed persistence for the tournament Lambda.

Key layout (single bucket, env CAMEL_BUCKET — the site's CDN asset bucket):
  images/camel-up/leaderboard.json    public via CloudFront /images/* behavior
  images/camel-up/status/{id}.json    public, no-cache (submission polling)
  camel-up/bots/{Name}.py             accepted bot source (not CDN-served)
  camel-up/bots/{Name}.json           accepted bot metadata (author, date, id)

CI's `aws s3 sync` of public/images/ does NOT pass --delete, so Lambda-written
files under images/camel-up/ survive site deploys. Never move these under
assets/ — that sync prunes unknown keys.

Set CAMEL_LOCAL_DIR to use a local directory instead of S3 (tests).
"""

import json
import os

LEADERBOARD_KEY = "images/camel-up/leaderboard.json"
STATUS_PREFIX = "images/camel-up/status/"
BOTS_PREFIX = "camel-up/bots/"


class Storage:
    def __init__(self):
        self.local_dir = os.environ.get("CAMEL_LOCAL_DIR")
        if not self.local_dir:
            import boto3
            self.bucket = os.environ["CAMEL_BUCKET"]
            self.s3 = boto3.client("s3")

    # ── raw ────────────────────────────────────────────────────────────────

    def put(self, key, body, content_type="application/json", cache_control=None):
        if self.local_dir:
            path = os.path.join(self.local_dir, key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(body)
            return
        extra = {"ContentType": content_type}
        if cache_control:
            extra["CacheControl"] = cache_control
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body.encode("utf-8"), **extra)

    def get(self, key):
        """Returns the object body as str, or None if it doesn't exist."""
        if self.local_dir:
            path = os.path.join(self.local_dir, key)
            if not os.path.exists(path):
                return None
            with open(path) as f:
                return f.read()
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read().decode("utf-8")
        except self.s3.exceptions.NoSuchKey:
            return None

    def list(self, prefix):
        if self.local_dir:
            base = os.path.join(self.local_dir, prefix)
            if not os.path.isdir(base):
                return []
            return [prefix + name for name in sorted(os.listdir(base))]
        keys = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    # ── typed helpers ──────────────────────────────────────────────────────

    def write_status(self, submission_id, status):
        self.put(
            STATUS_PREFIX + f"{submission_id}.json",
            json.dumps(status),
            cache_control="no-cache",
        )

    def write_leaderboard(self, leaderboard):
        self.put(
            LEADERBOARD_KEY,
            json.dumps(leaderboard, indent=1),
            cache_control="public,max-age=30",
        )

    def read_leaderboard(self):
        raw = self.get(LEADERBOARD_KEY)
        return json.loads(raw) if raw else None

    def save_accepted_bot(self, name, code, meta):
        self.put(BOTS_PREFIX + f"{name}.py", code, content_type="text/x-python")
        self.put(BOTS_PREFIX + f"{name}.json", json.dumps(meta))

    def load_accepted_bots(self):
        """Returns [(name, code, meta), ...] for all previously accepted bots."""
        bots = []
        for key in self.list(BOTS_PREFIX):
            if not key.endswith(".py"):
                continue
            name = key[len(BOTS_PREFIX):-len(".py")]
            code = self.get(key)
            meta_raw = self.get(BOTS_PREFIX + f"{name}.json")
            meta = json.loads(meta_raw) if meta_raw else {}
            if code:
                bots.append((name, code, meta))
        return bots
