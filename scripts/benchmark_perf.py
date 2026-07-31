import os
import re
import time
from uuid import uuid4
from contextlib import contextmanager

os.environ.setdefault('DATABASE_URL', 'sqlite:///./data/perf_bench.db')
os.environ.setdefault('SEED_DEMO_DATA', 'true')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('STARTUP_VALIDATE_MIGRATIONS', 'false')

from sqlalchemy import event
from fastapi.testclient import TestClient

from app.main import app
from app.db import engine


@contextmanager
def query_counter():
    count = {'value': 0}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        count['value'] += 1

    event.listen(engine, 'before_cursor_execute', before_cursor_execute)
    try:
        yield count
    finally:
        event.remove(engine, 'before_cursor_execute', before_cursor_execute)


client = TestClient(app)


def csrf_token() -> str:
    page = client.get('/login')
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match is not None
    return match.group(1)


def post_with_csrf(path, data=None):
    payload = dict(data or {})
    payload['csrf_token'] = csrf_token()
    return client.post(path, data=payload, follow_redirects=False)


def auth():
    response = post_with_csrf('/login', {'email': 'admin@politis.local', 'password': 'PolitisDemo!'})
    client.cookies.update(response.cookies)


def benchmark_endpoint(path: str, rounds: int = 40):
    with query_counter() as qc:
        start = time.perf_counter()
        for _ in range(rounds):
            response = client.get(path)
            assert response.status_code == 200, (path, response.status_code)
        elapsed = time.perf_counter() - start
    avg_ms = (elapsed / rounds) * 1000
    avg_queries = qc['value'] / rounds
    return {'path': path, 'avg_ms': round(avg_ms, 3), 'avg_queries': round(avg_queries, 2)}


def main():
    with client:
        auth()
        # Ensure a participant exists for detail page benchmark.
        reference = f"PERF-{uuid4().hex[:8].upper()}"
        create = post_with_csrf('/participants', {
            'reference': reference,
            'name': 'Perf User',
            'email': 'perf.user@example.org',
            'phone': '',
            'status_value': 'prospective',
            'consent_status': 'pending',
            'communication_preference': 'email',
            'tags': '',
            'notes': '',
        })
        assert create.status_code == 303
        participant_path = create.headers['location']

        targets = ['/', '/studies', '/projects', participant_path]
        rows = [benchmark_endpoint(path) for path in targets]

    print('PERF_BASELINE_START')
    for row in rows:
        print(f"{row['path']} avg_ms={row['avg_ms']} avg_queries={row['avg_queries']}")
    print('PERF_BASELINE_END')


if __name__ == '__main__':
    main()
