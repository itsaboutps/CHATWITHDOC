"""Bulk document uploader & ingestion monitor.

Usage inside backend container (after stack up & migrations):

python -m scripts.bulk_upload --dir /data/docs --email user@example.com --password Secret123 --pattern .pdf .txt .docx --concurrency 4

Outside container (host): ensure you have requests installed and BACKEND_URL accessible.

Environment variables:
  BACKEND_URL (default http://localhost:8000)
  API_KEY (optional if using API key auth)

If no user exists, the script will register; otherwise it logs in.
"""
from __future__ import annotations
import argparse, os, time, sys, threading
from pathlib import Path
import requests
from typing import List, Tuple

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY")

def register_or_login(email: str, password: str) -> str:
    session = requests.Session()
    # Try login first
    r = session.post(f"{BACKEND}/auth/login", json={"email": email, "password": password})
    if r.status_code == 401:
        r = session.post(f"{BACKEND}/auth/register", json={"email": email, "password": password})
    r.raise_for_status()
    token = r.json()["access_token"]
    return token

def iter_files(root: Path, patterns: List[str]) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        if not patterns:
            files.append(p)
        else:
            if any(p.name.lower().endswith(ext.lower()) for ext in patterns):
                files.append(p)
    return files

def upload_file(path: Path, headers: dict) -> Tuple[int, str]:
    with path.open('rb') as f:
        r = requests.post(f"{BACKEND}/upload", files={'file': (path.name, f)}, headers=headers, timeout=300)
    r.raise_for_status()
    data = r.json()
    return data['document_id'], data['task_id']

def poll_task(task_id: str, headers: dict, interval=2, timeout=1800):
    start = time.time()
    while True:
        r = requests.get(f"{BACKEND}/tasks/{task_id}", headers=headers, timeout=30)
        if r.status_code == 404:
            time.sleep(interval)
            continue
        js = r.json()
        status = js.get('status')
        if status in ('SUCCESS', 'FAILURE', 'REVOKED') or (time.time() - start) > timeout:
            return js
        time.sleep(interval)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True, help='Directory containing documents')
    ap.add_argument('--email', required=True)
    ap.add_argument('--password', required=True)
    ap.add_argument('--pattern', nargs='*', default=['.pdf', '.txt', '.docx'])
    ap.add_argument('--concurrency', type=int, default=3)
    ap.add_argument('--sync', action='store_true', help='If set and SYNC_INGEST true, skip polling tasks.')
    args = ap.parse_args()

    token = register_or_login(args.email, args.password)
    headers = {'Authorization': f'Bearer {token}'}
    if API_KEY:
        headers['x-api-key'] = API_KEY

    root = Path(args.dir)
    if not root.exists():
        print(f"Directory not found: {root}", file=sys.stderr)
        sys.exit(1)
    files = iter_files(root, args.pattern)
    if not files:
        print('No matching files found.')
        return
    print(f"Discovered {len(files)} files. Starting uploads (concurrency={args.concurrency})...")

    lock = threading.Lock()
    queue = files.copy()
    results: List[Tuple[Path, int, str]] = []

    def worker():
        while True:
            with lock:
                if not queue:
                    return
                path = queue.pop()
            try:
                doc_id, task_id = upload_file(path, headers)
                with lock:
                    results.append((path, doc_id, task_id))
                print(f"Uploaded {path.name} -> doc {doc_id} task {task_id}")
            except Exception as e:
                print(f"Error uploading {path}: {e}", file=sys.stderr)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.concurrency)]
    for t in threads: t.start()
    for t in threads: t.join()

    if args.sync:
        print('SYNC mode assumed, skipping task polling.')
        return

    print('Polling tasks...')
    completed = 0
    for path, doc_id, task_id in results:
        info = poll_task(task_id, headers)
        status = info.get('status')
        print(f"Task {task_id} ({path.name}) -> {status}")
        completed += 1
    print(f"All tasks polled: {completed}/{len(results)}")

if __name__ == '__main__':
    main()
