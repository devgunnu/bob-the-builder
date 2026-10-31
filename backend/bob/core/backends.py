"""Backend selection by BOB_ENV (CONTRACTS section 7). Owner: A1.

local (default): LocalBlobs, LocalStore, LocalEventLog, LocalRunner.
aws: bob.aws.* (A5), imported lazily so local mode never needs AWS credentials. Expected names (zero-arg
constructors that read get_settings()): bob.aws.blobs.S3Blobs, bob.aws.store.DynamoStore,
bob.aws.events.DynamoEventLog, bob.aws.runner.EcsRunner.
One instance per process.
"""

from __future__ import annotations

from functools import lru_cache

from bob.config import get_settings
from bob.core.blobs import Blobs, LocalBlobs
from bob.core.events import EventLog, LocalEventLog
from bob.core.runner import LocalRunner, Runner
from bob.core.store import LocalStore, Store


def _aws() -> bool:
    return get_settings().env == "aws"


@lru_cache
def get_blobs() -> Blobs:
    if _aws():
        from bob.aws.blobs import S3Blobs  # type: ignore[import-not-found]

        return S3Blobs()
    return LocalBlobs(get_settings().runs_dir)


@lru_cache
def get_store() -> Store:
    if _aws():
        from bob.aws.store import DynamoStore  # type: ignore[import-not-found]

        return DynamoStore()
    return LocalStore()


@lru_cache
def get_events() -> EventLog:
    if _aws():
        from bob.aws.events import DynamoEventLog  # type: ignore[import-not-found]

        return DynamoEventLog()
    return LocalEventLog()


@lru_cache
def get_runner() -> Runner:
    if _aws():
        from bob.aws.runner import EcsRunner  # type: ignore[import-not-found]

        return EcsRunner()
    return LocalRunner()
