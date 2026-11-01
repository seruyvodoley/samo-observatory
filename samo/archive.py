"""Bounded, transactional scientific recorder. Not exposed to organism programs."""
import json
import os
import sqlite3
import zlib
from pathlib import Path
from .genome import canonical, digest, validate

ARCHIVE_LIMIT = 64_000_000
SCHEMA = '''
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
 ordinal INTEGER NOT NULL, payload TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES runs(id));
CREATE TABLE IF NOT EXISTS artifacts(hash TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
 payload TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES runs(id));
CREATE INDEX IF NOT EXISTS event_run ON events(run_id, ordinal);
'''


class Archive:
    def __init__(self, path, limit=ARCHIVE_LIMIT, read_only=False):
        self.path = Path(path)
        self.limit = limit
        if read_only:
            self.db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
            self.db.execute('BEGIN')
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        self.db = sqlite3.connect(str(path))
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript(SCHEMA)
        self.db.execute('PRAGMA max_page_count=' + str(max(1, limit // 4096)))

    def close(self):
        self.db.close()

    def check_capacity(self, extra=0):
        # Account for rollback journal duplication and conservative record overhead.
        size = self.path.stat().st_size if self.path.exists() else 0
        if 2 * size + extra * 2 + 65536 > self.limit:
            raise RuntimeError('archive quota; collection stopped, no pruning')

    def put_artifact(self, g):
        validate(g)
        h = digest(g)
        self.check_capacity(len(canonical(g)))
        self.db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?)', (h, canonical(g).decode()))
        return h

    def run(self, run):
        self.check_capacity(len(canonical(run)))
        with self.db:
            self.db.execute('INSERT INTO runs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                            (run['id'], canonical(run).decode()))

    def record(self, run, event, genome, evidence):
        self.check_capacity(sum(len(canonical(x)) for x in (run, event, genome, evidence)))
        with self.db:
            self.put_artifact(genome)
            self.db.execute('INSERT INTO events VALUES(?,?,?,?)',
                            (event['id'], run['id'], event['ordinal'], canonical(event).decode()))
            self.db.execute('INSERT INTO evidence VALUES(?,?,?)',
                            (evidence['id'], run['id'], zlib.compress(canonical(evidence), 6)))
            self.db.execute('UPDATE runs SET payload=? WHERE id=?', (canonical(run).decode(), run['id']))

    def all(self, table):
        if table not in ('runs', 'events', 'evidence', 'artifacts'):
            raise ValueError('table')
        order = 'run_id, ordinal' if table == 'events' else 'rowid'
        return list(self.iter_records(table))

    def iter_records(self, table):
        if table not in ('runs', 'events', 'evidence', 'artifacts'):
            raise ValueError('table')
        order = 'run_id, ordinal' if table == 'events' else 'rowid'
        for (payload,) in self.db.execute(f'SELECT payload FROM {table} ORDER BY {order}'):
            if isinstance(payload, bytes):
                inflater = zlib.decompressobj()
                payload = inflater.decompress(payload, 1_000_000)
                if not inflater.eof or inflater.unused_data:
                    raise ValueError('compressed evidence limit or trailing data')
            yield json.loads(payload)

    def artifact(self, h):
        row = self.db.execute('SELECT payload FROM artifacts WHERE hash=?', (h,)).fetchone()
        if not row:
            raise ValueError('missing artifact')
        g = json.loads(row[0])
        if digest(g) != h:
            raise ValueError('artifact hash mismatch')
        return validate(g)
