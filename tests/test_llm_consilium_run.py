from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'llm-consilium-run.py'


def load_runner():
    loader = importlib.machinery.SourceFileLoader('llm_consilium_run', str(SCRIPT))
    spec = importlib.util.spec_from_loader('llm_consilium_run', loader)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules['llm_consilium_run'] = module
    spec.loader.exec_module(module)
    return module


def test_default_config_is_generic_and_model_agnostic():
    r = load_runner()
    config = r.load_consilium_config()
    assert config['modes']['fast']['default_candidates'] == ['candidate-a', 'candidate-b']
    assert config['modes']['full']['default_candidates'] == ['candidate-a', 'candidate-b', 'candidate-c']
    specs = r.all_candidate_specs()
    assert set(specs) == {'candidate-a', 'candidate-b', 'candidate-c'}
    assert all(spec.route == 'custom' for spec in specs.values())
    assert all(spec.prompt_transport == 'stdin' for spec in specs.values())


def test_output_classifier_distinguishes_reasoning_only_json():
    r = load_runner()
    reasoning_only = '{"type":"step_start"}\n{"type":"reasoning","text":"thinking..."}\n'
    assert r.classify_output(0, reasoning_only, '') == 'no_final_output'
    assert r.classify_output(0, 'Final answer', '') == 'ok'
    assert r.classify_output(0, '', '') == 'empty_output'
    assert r.classify_output(1, 'some text', '') == 'failed'
    assert r.classify_output(0, 'thinking: initial note\n## Position\nFinal answer', '') == 'ok'


def test_preflight_skips_candidate_when_marker_missing(tmp_path: Path):
    r = load_runner()
    spec = r.CandidateSpec(
        id='bad', label='bad', route='fake',
        command=['python3', '-c', 'print("WRONG")'],
        prompt_transport='stdin', timeout=5,
    )
    workspace = tmp_path / 'w'
    workspace.mkdir()
    result = r.run_preflight(spec, workspace, timeout=5, dry_run=False)
    assert result['status'] == 'skipped_preflight'


def test_dry_run_creates_isolated_artifacts_and_hash(tmp_path: Path):
    r = load_runner()
    q = tmp_path / 'question.md'
    q.write_text('Should we use a deterministic runner?', encoding='utf-8')
    out_root = tmp_path / 'runs'
    code = r.main([
        'test-consilium', '--question-file', str(q), '--run-root', str(out_root),
        '--mode', 'fast', '--candidates', 'candidate-a,candidate-b,candidate-c', '--dry-run',
    ])
    assert code == 0
    runs = list(out_root.glob('test-consilium-*'))
    assert len(runs) == 1
    run = runs[0]
    manifest = json.loads((run / 'council_run.json').read_text(encoding='utf-8'))
    assert manifest['prompt_sha256']
    assert len(manifest['candidates']) == 3
    assert all(c['status'] == 'dry_run' for c in manifest['candidates'])
    for c in manifest['candidates']:
        candidate_dir = Path(c['workspace'])
        assert candidate_dir.exists()
        assert (candidate_dir / 'prompt.md').exists()
        assert str(candidate_dir).startswith(str(run / 'inputs'))
    status = json.loads((run / 'route_status.json').read_text(encoding='utf-8'))
    assert set(status) == {'candidate-a', 'candidate-b', 'candidate-c'}
    assert (run / 'final.md').exists()


def test_synthesize_creates_claims_reports_and_final(tmp_path: Path):
    r = load_runner()
    run = tmp_path / 'sample-run'
    for sub in ['raw', 'analysis', 'graphs', 'reviews', 'logs']:
        (run / sub).mkdir(parents=True)
    (run / 'question.md').write_text('What should we do?', encoding='utf-8')
    manifest = {
        'kind': 'llm-consilium-run', 'version': 2, 'mode': 'fast',
        'run_dir': str(run), 'prompt_sha256': 'abc',
        'candidates': [
            {'id': 'model-a', 'status': 'ok', 'raw_path': str(run / 'raw' / 'model-a.md')},
            {'id': 'model-b', 'status': 'ok', 'raw_path': str(run / 'raw' / 'model-b.md')},
            {'id': 'model-c', 'status': 'failed', 'raw_path': str(run / 'raw' / 'model-c.md')},
        ],
    }
    (run / 'council_run.json').write_text(json.dumps(manifest), encoding='utf-8')
    (run / 'raw' / 'model-a.md').write_text('''## Position\nUse a deterministic runner.\n\n## Main arguments\n- It preserves prompt hashes.\n- It saves raw outputs.\n\n## Risks / caveats\n- It does not verify facts.\n''', encoding='utf-8')
    (run / 'raw' / 'model-b.md').write_text('''## Position\nUse a deterministic runner.\n\n## Main arguments\n- It preserves prompt hashes.\n- It makes failures auditable.\n\n## Risks / caveats\n- It does not verify facts.\n''', encoding='utf-8')
    result = r.synthesize_run(run)
    claims = json.loads((run / 'analysis' / 'claims.json').read_text(encoding='utf-8'))
    report = json.loads((run / 'analysis' / 'repetition_report.json').read_text(encoding='utf-8'))
    ledger = json.loads((run / 'analysis' / 'evidence_ledger.json').read_text(encoding='utf-8'))
    final = (run / 'final.md').read_text(encoding='utf-8')
    assert result['ok_candidates'] == ['model-a', 'model-b']
    assert claims['claims']
    assert report['claims']
    assert ledger['mode'] == 'model-consistency-only'
    assert '## Consensus' in final
    assert 'model-consistency-only' in final


def test_make_run_dir_avoids_same_second_collisions(tmp_path: Path):
    r = load_runner()
    first = r.make_run_dir(tmp_path, 'same-slug')
    second = r.make_run_dir(tmp_path, 'same-slug')
    assert first != second
    assert first.exists()
    assert second.exists()


def test_order_results_preserves_configured_candidate_order():
    r = load_runner()
    desired = ['a', 'b', 'c']
    unordered = [{'id': 'b'}, {'id': 'c'}, {'id': 'a'}]
    assert [x['id'] for x in r.order_candidate_results(unordered, desired)] == desired


def test_preflight_logs_stdout_and_stderr(tmp_path: Path):
    r = load_runner()
    bad = r.CandidateSpec(
        id='bad-preflight-log', label='bad', route='fake',
        command=['python3', '-c', 'import sys; print("OUT"); print("ERR", file=sys.stderr)'],
        prompt_transport='stdin', timeout=5, preflight_timeout=5,
    )
    workspace = tmp_path / 'w'
    workspace.mkdir()
    result = r.run_preflight(bad, workspace, timeout=5, dry_run=False)
    assert result['status'] == 'skipped_preflight'
    assert (workspace / 'preflight_attempt_1.stdout').read_text(encoding='utf-8').strip() == 'OUT'
    assert (workspace / 'preflight_attempt_1.stderr').read_text(encoding='utf-8').strip() == 'ERR'
