"""Database dump archives - what the dialects write and :mod:`grunt.backups` keeps.

A leaf: the dialects dump and restore (``Dialect.dump`` / ``restore``), the
backups package orchestrates them - both take the compression settings and the
error from here, so a dialect never imports the backups package.
"""

import os
from compression import zstd

# zstd 9: ~40% smaller than gzip 6 and faster; 19 squeezes more at ~25× the time.
DEFAULT_COMPRESSION_LEVEL = 9
MAX_COMPRESSION_LEVEL = 19


class BackupError(RuntimeError):
    pass


def zstd_options(level: int) -> dict:
    """Compression *level* (clamped) on half the cores - the site keeps serving meanwhile."""
    options = {
        zstd.CompressionParameter.compression_level: min(max(level, 1), MAX_COMPRESSION_LEVEL)
    }
    workers = max((os.cpu_count() or 1) // 2, 1)
    if workers > 1 and zstd.CompressionParameter.nb_workers.bounds()[1] > 0:
        options[zstd.CompressionParameter.nb_workers] = workers
    return options
