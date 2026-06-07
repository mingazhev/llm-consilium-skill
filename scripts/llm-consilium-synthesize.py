#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import sys
import os
from pathlib import Path

DEFAULT_RUNNER = Path(__file__).resolve().parent / 'llm-consilium-run.py'
WORKSPACE_RUNNER = Path(os.environ.get('LLM_CONSILIUM_RUNNER_BIN', 'llm-consilium-run'))


def runner_path() -> Path:
    # Prefer sibling skill script for package self-containment; allow explicit override for deployed workspace wrappers.
    import os
    override = os.environ.get('LLM_CONSILIUM_RUNNER')
    if override:
        return Path(override)
    return DEFAULT_RUNNER if DEFAULT_RUNNER.exists() else WORKSPACE_RUNNER


def load_runner():
    loader = importlib.machinery.SourceFileLoader('llm_consilium_run', str(runner_path()))
    spec = importlib.util.spec_from_loader('llm_consilium_run', loader)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules['llm_consilium_run'] = module
    spec.loader.exec_module(module)
    return module


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Deterministic synthesis for an LLM consilium run')
    ap.add_argument('run_dir', type=Path)
    args = ap.parse_args(argv)
    runner = load_runner()
    result = runner.synthesize_run(args.run_dir)
    print(f"FINAL={result['final_path']}")
    print(f"CLAIMS={result['claim_count']} CONSENSUS={result['consensus_count']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
