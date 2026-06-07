#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', '.venv', 'venv'}
SKIP_SUFFIXES = {'.pyc', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf'}

PATTERNS = [
    ('github_token', re.compile(r'gh[pousr]_[A-Za-z0-9_]{20,}')),
    ('openai_key', re.compile(r'sk-[A-Za-z0-9]{20,}')),
    ('anthropic_key', re.compile(r'sk-ant-[A-Za-z0-9_-]{20,}')),
    ('generic_secret_assignment', re.compile(r'(?i)(api[_-]?key|token|secret|password)\s*=\s*[^\s#]{12,}')),
    ('private_key', re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----')),
]

ALLOW_SNIPPETS = [
    'GITHUB_TOKEN',
    '<token>',
    '<THEIR_TOKEN>',
    'your-secret-value',
    'API_KEY',
    'api_key|token|secret|password',
]

findings = []
for path in ROOT.rglob('*'):
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    if not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue
    for name, pattern in PATTERNS:
        for match in pattern.finditer(text):
            line = text.count('\n', 0, match.start()) + 1
            snippet = match.group(0)[:120]
            if any(allowed in snippet for allowed in ALLOW_SNIPPETS):
                continue
            findings.append((str(path.relative_to(ROOT)), line, name, snippet))

if findings:
    print('Potential secrets found:', file=sys.stderr)
    for file, line, name, snippet in findings:
        print(f'{file}:{line}: {name}: {snippet}', file=sys.stderr)
    sys.exit(1)

print('secret_scan: ok')
