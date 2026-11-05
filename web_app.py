"""Orbit — a private, local project and focus workspace. Python 3.10+."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import argparse
import json
import mimetypes
import sqlite3
import threading
import webbrowser

from orbit import storage as store

ROOT = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, value, status=200):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ('/api/state', '/api/export'):
            with store.connect() as con:
                self.reply(store.state(con))
            return
        files = {'/': 'index.html', '/style.css': 'style.css', '/app.js': 'app.js'}
        if path not in files:
            self.send_error(404)
            return
        file = ROOT / 'static' / files[path]
        payload = file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(str(file))[0] + '; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self.mutate('POST')

    def do_PATCH(self):
        self.mutate('PATCH')

    def do_DELETE(self):
        self.mutate('DELETE')

    def mutate(self, method):
        # Reject cross-origin browser requests to this local service.
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            self.reply({'error': 'Cross-origin request rejected.'}, 403)
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 <= length <= 5_000_000:
                raise ValueError('Backup or request is too large (5 MB maximum).')
            data = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            parts = self.path.strip('/').split('/')
            with store.connect() as con:
                if parts == ['api', 'import'] and method == 'POST':
                    self.restore(con, data)
                else:
                    if len(parts) not in (2, 3) or parts[0] != 'api' or parts[1] not in ('projects', 'tasks', 'notes', 'sessions'):
                        self.reply({'error': 'Unknown endpoint.'}, 404)
                        return
                    table = parts[1]
                    if method == 'POST' and len(parts) == 2:
                        values = store.clean(table, data)
                        required = {'projects': 'name', 'tasks': 'title', 'notes': 'title', 'sessions': 'minutes'}[table]
                        if required not in values:
                            raise ValueError(f'{required} is required.')
                        if table in ('tasks', 'sessions'):
                            values['created'] = store.now()
                        if table == 'notes':
                            values['updated'] = store.now()
                        keys = ','.join(values)
                        con.execute(f'INSERT INTO {table} ({keys}) VALUES ({",".join("?" for _ in values)})', list(values.values()))
                    elif method in ('PATCH', 'DELETE') and len(parts) == 3:
                        ident = int(parts[2])
                        if not con.execute(f'SELECT id FROM {table} WHERE id=?', (ident,)).fetchone():
                            self.reply({'error': 'Record not found.'}, 404)
                            return
                        if method == 'DELETE':
                            con.execute(f'DELETE FROM {table} WHERE id=?', (ident,))
                        else:
                            values = store.clean(table, data)
                            if table == 'notes':
                                values['updated'] = store.now()
                            if values:
                                con.execute(f'UPDATE {table} SET {",".join(k+"=?" for k in values)} WHERE id=?', [*values.values(), ident])
                    else:
                        raise ValueError('Unsupported operation.')
                snapshot = store.state(con)
            self.reply(snapshot)
        except (ValueError, TypeError, KeyError, sqlite3.IntegrityError) as exc:
            self.reply({'error': str(exc)}, 400)

    def restore(self, con, data):
        store.restore_backup(con, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    store.initialize()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Orbit is running at {url}\nPress Ctrl+C to stop.', flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nOrbit stopped. Your work is saved.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
