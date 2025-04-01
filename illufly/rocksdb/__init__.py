from .index import IndexedRocksDB
from .base_rocksdb import BaseRocksDB
from .cache.cache_rocksdb import CachedRocksDB

import tempfile

default_rocksdb = IndexedRocksDB(
    path=tempfile.mkdtemp(prefix="ILLUFLY_ROCKSDB_")
)
