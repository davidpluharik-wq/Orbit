import json
from pathlib import Path
import tempfile
import io
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web_app as app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='.test-', dir=app.ROOT)
        cls.original_db = app.store.DB
        app.store.DB = Path(cls.temp.name) / 'test.sqlite3'
        app.store.initialize()

    @classmethod
    def tearDownClass(cls):
        app.store.DB = cls.original_db
        cls.temp.cleanup()

    def raw_request(self, path, method='GET', body=None, origin=None):
        payload = json.dumps(body).encode() if body is not None else b''
        headers = f'{method} {path} HTTP/1.0\r\nHost: 127.0.0.1:8765\r\nContent-Length: {len(payload)}\r\n'
        if origin:
            headers += f'Origin: {origin}\r\n'
        class Connection:
            def makefile(self, mode, *args):
                return io.BytesIO(headers.encode() + b'\r\n' + payload)
            def sendall(self, content):
                output.write(content)
        output = io.BytesIO()
        app.Handler(Connection(), ('127.0.0.1', 12345), None)
        head, content = output.getvalue().split(b'\r\n\r\n', 1)
        return int(head.split()[1]), content

    def request(self, path, method='GET', body=None, origin=None):
        status, content = self.raw_request('/api/' + path, method, body, origin)
        return status, json.loads(content)

    def setUp(self):
        self.request('import', 'POST', {t: [] for t in ('projects', 'tasks', 'notes', 'sessions')})

    def test_full_lifecycle_and_foreign_keys(self):
        status, data = self.request('projects', 'POST', {'name': 'Launch'})
        self.assertEqual(status, 200)
        pid = data['projects'][0]['id']
        _, data = self.request('tasks', 'POST', {'title': 'Ship it', 'project_id': pid, 'priority': 'high'})
        tid = data['tasks'][0]['id']
        _, data = self.request('tasks/' + str(tid), 'PATCH', {'status': 'done'})
        self.assertEqual(data['tasks'][0]['status'], 'done')
        self.request('sessions', 'POST', {'task_id': tid, 'minutes': 25})
        self.request('projects/' + str(pid), 'DELETE')
        _, data = self.request('state')
        self.assertIsNone(data['tasks'][0]['project_id'])
        _, data = self.request('tasks/' + str(tid), 'DELETE')
        self.assertIsNone(data['sessions'][0]['task_id'])

    def test_backup_round_trip_and_rollback(self):
        self.request('notes', 'POST', {'title': 'Idea', 'body': 'Hello\nworld'})
        _, backup = self.request('export')
        self.assertEqual(self.request('import', 'POST', backup), (200, backup))
        invalid = dict(backup, tasks=[{'id': 1, 'title': 'Bad task', 'project_id': 9999, 'created': app.store.now()}])
        self.assertEqual(self.request('import', 'POST', invalid)[0], 400)
        self.assertEqual(self.request('state')[1], backup)

    def test_validation(self):
        for body in ({'title': ''}, {'title': 'X', 'status': 'unknown'}, {'title': 'X', 'due': 'tomorrow'}, {'title': 'X', 'project_id': 'oops'}):
            self.assertEqual(self.request('tasks', 'POST', body)[0], 400)
        self.assertEqual(self.request('sessions', 'POST', {'minutes': -1})[0], 400)
        self.assertEqual(self.request('tasks/9999', 'PATCH', {'title': 'X'})[0], 404)
        self.assertEqual(self.request('tasks', 'POST', {'title': 'X'}, 'https://example.com')[0], 403)
        self.assertEqual(self.request('state')[1]['tasks'], [])

    def test_static_assets(self):
        for path in ('/', '/app.js', '/style.css'):
            status, content = self.raw_request(path)
            self.assertEqual(status, 200)
            self.assertGreater(len(content), 100)


if __name__ == '__main__':
    unittest.main()
