"""外置或 <repo>/.local/ 下、按内容寻址的追加缓存；不保存联系身份或持仓。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from product.mcp.provenance import canonical_json, content_hash, iso_utc


class SnapshotCache:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        repo = Path(__file__).resolve().parents[3]
        # Allowed: outside the repository, or inside the git-ignored <repo>/.local/ tree.
        local = repo / ".local"
        if (self.root == repo or repo in self.root.parents) and local not in self.root.parents:
            raise ValueError("LIVE_CACHE_MUST_BE_EXTERNAL_OR_UNDER_DOT_LOCAL")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, kind: str, digest: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("CACHE_HASH_INVALID")
        directory = self.root / kind
        directory.mkdir(exist_ok=True, mode=0o700)
        if directory.resolve().parent != self.root:
            raise ValueError("CACHE_PATH_ESCAPE")
        path = directory / digest
        if path.is_symlink():
            raise ValueError("CACHE_SYMLINK_REJECTED")
        return path

    def _append(self, path: Path, raw: bytes) -> None:
        # 先写临时文件，再以硬链接原子发布；现有版本绝不覆盖。
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(name, path)
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise ValueError("CACHE_CONTENT_COLLISION")
        finally:
            os.unlink(name)

    # Key index: keys/<key_hash> lists the record hashes stored for that key, so a lookup reads only
    # those records instead of scanning every record (the cache holds tens of thousands).
    def _index_path(self, key_hash: str) -> Path:
        return self._path("keys", key_hash)

    def _index_add(self, key_hash: str, record_hash: str) -> None:
        fd = os.open(self._index_path(key_hash), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a") as handle:
            handle.write(record_hash + "\n")

    def _mark_checked(self, key_hash: str, at: str) -> None:
        path = self._path("keys", key_hash).with_suffix(".checked")
        tmp = path.with_suffix(".checked.tmp")
        tmp.write_text(iso_utc(at))
        tmp.replace(path)

    def _checked_at(self, key_hash: str) -> str | None:
        path = self._path("keys", key_hash).with_suffix(".checked")
        return path.read_text().strip() if path.exists() else None

    def _ensure_index(self) -> None:
        marker = self.root / "keys" / ".built"
        if marker.exists():
            return
        import fcntl
        (self.root / "keys").mkdir(exist_ok=True, mode=0o700)
        with open(self.root / "keys" / ".lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not marker.exists():
                records = self.root / "records"
                records.mkdir(exist_ok=True, mode=0o700)
                by_key: dict[str, list[str]] = {}
                for path in records.iterdir():
                    if path.name.startswith(".pending-") or path.is_symlink():
                        continue
                    by_key.setdefault(json.loads(path.read_bytes())["key_hash"], []).append(path.name)
                for key_hash, hashes in by_key.items():
                    existing = set(self._index_path(key_hash).read_text().split()) \
                        if self._index_path(key_hash).exists() else set()
                    for record_hash in hashes:
                        if record_hash not in existing:
                            self._index_add(key_hash, record_hash)
                marker.write_text("1\n")
            fcntl.flock(lock, fcntl.LOCK_UN)

    def store(self, key: dict, raw: bytes, *, retrieved_at: str) -> dict:
        digest = hashlib.sha256(raw).hexdigest()
        key_hash = content_hash(key)
        # 同请求、同内容只保存第一次实际获取时间。
        old = self.lookup(key, raw_hash=digest)
        if old:
            # Same content again: keep the first retrieval time on the record, but note that it was re-verified
            # now, so freshness checks do not re-download unchanged data on every call.
            self._mark_checked(key_hash, retrieved_at)
            return dict(old, checked_at=iso_utc(retrieved_at))
        record = {"schema_version": "live-cache/1.0.0", "key": key,
                  "key_hash": key_hash, "raw_content_hash": digest,
                  "retrieved_at": iso_utc(retrieved_at)}
        self._append(self._path("objects", digest), raw)
        record_hash = content_hash(record)
        self._append(self._path("records", record_hash), canonical_json(record).encode())
        self._index_add(key_hash, record_hash)
        return dict(record, record_hash=record_hash)

    def repair_verified(self, key: dict, raw: bytes, *, retrieved_at: str) -> dict:
        """Repair a missing/corrupt object only after the provider returned its bytes.

        Ordinary reads remain fail-closed.  This narrow recovery path is used for
        immutable provider documents whose stable identity can be fetched again.
        A matching content digest is restored atomically; unrelated cache records
        and objects are never removed or rewritten.
        """

        digest = hashlib.sha256(raw).hexdigest()
        path = self._path("objects", digest)
        if path.exists() and (path.is_symlink() or path.read_bytes() != raw):
            fd, name = tempfile.mkstemp(dir=path.parent, prefix=".repair-")
            temporary = Path(name)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        elif not path.exists():
            self._append(path, raw)

        # If a matching record already existed, restoring the object makes the
        # normal verified lookup usable again.  Otherwise publish a new record.
        matching = self.lookup(key, raw_hash=digest)
        if matching is not None:
            return matching
        return self.store(key, raw, retrieved_at=retrieved_at)

    def lookup(self, key: dict, *, raw_hash: str | None = None) -> dict | None:
        self._ensure_index()
        index = self._index_path(content_hash(key))
        names = set(index.read_text().split()) if index.exists() else set()
        directory = self._path("records", "0" * 64).parent
        matches = []
        for path in (directory / name for name in sorted(names)):
            if not path.exists() or path.name.startswith(".pending-"):
                continue
            if path.is_symlink():
                raise ValueError("CACHE_SYMLINK_REJECTED")
            record = json.loads(path.read_bytes())
            if content_hash(record) != path.name:
                raise ValueError("CACHE_RECORD_HASH_MISMATCH")
            if record["key_hash"] != content_hash(record["key"]):
                raise ValueError("CACHE_KEY_HASH_MISMATCH")
            if record["key"] == key and (raw_hash is None or record["raw_content_hash"] == raw_hash):
                iso_utc(record["retrieved_at"])
                self.read(record)
                matches.append(dict(record, record_hash=path.name))
        if not matches:
            return None
        latest = max(matches, key=lambda item: item["retrieved_at"])
        checked = self._checked_at(content_hash(key))
        if checked and checked > latest["retrieved_at"]:
            latest = dict(latest, checked_at=checked)
        return latest

    def read(self, record: dict) -> bytes:
        raw = self._path("objects", record["raw_content_hash"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["raw_content_hash"]:
            raise ValueError("CACHE_OBJECT_HASH_MISMATCH")
        return raw
