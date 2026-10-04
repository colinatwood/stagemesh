"""Cross-platform advisory locks for StageMesh-owned lock files."""
from __future__ import annotations

from contextlib import contextmanager
import os


if os.name == "nt":
    import msvcrt
else:
    import fcntl


@contextmanager
def exclusive_file_lock(lock):
    """Hold an exclusive lock on the first byte of an open lock file."""
    if os.name == "nt":
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write("\0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
