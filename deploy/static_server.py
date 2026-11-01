#!/usr/bin/python3
"""Read-only VPS origin for the static observatory; never executes uploaded content."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import mimetypes

ROOT = Path('/srv/samo/site').resolve()


class Handler(BaseHTTPRequestHandler):
    server_version = 'SAMOOrigin/1'
    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        target = (ROOT / path.lstrip('/')).resolve()
        if target != ROOT and ROOT not in target.parents:
            self.send_error(404); return None
        if not target.is_file():
            target = ROOT / 'index.html'
        try:
            info = target.stat()
            size = info.st_size
            if size > 4_000_000:
                self.send_error(413); return None
            live_snapshot = path == '/data/ecosystem.json'
            etag = f'"{info.st_mtime_ns:x}-{size:x}"' if live_snapshot else None
            if live_snapshot and self.headers.get('If-None-Match') == etag:
                self.send_response(304)
                self.send_header('ETag', etag)
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return None
            stream = target.open('rb')
        except OSError:
            self.send_error(404); return None
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(size))
        self.send_header('Cache-Control', 'no-cache' if target.name == 'index.html' or '/data/' in path else 'public, max-age=31536000, immutable')
        if path == '/data/ecosystem.json':
            self.send_header('ETag', etag)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        return stream
    def do_GET(self):
        stream = self.send_head()
        if stream:
            with stream:
                self.wfile.write(stream.read(4_000_001))
    def do_HEAD(self):
        stream = self.send_head()
        if stream: stream.close()
    def do_POST(self): self.send_error(405)
    def do_PUT(self): self.send_error(405)
    def do_DELETE(self): self.send_error(405)
    def log_message(self, fmt, *args): pass


ThreadingHTTPServer(('127.0.0.1', 4180), Handler).serve_forever()
