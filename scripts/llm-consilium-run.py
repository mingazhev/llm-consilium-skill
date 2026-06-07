#!/usr/bin/env python3
"""Deterministic multi-LLM consilium runner.

Creates isolated candidate workspaces, records prompt hashes/routes/statuses,
runs preflight and candidate commands, and writes raw artifacts + manifests.
This is intentionally conservative: route execution is deterministic and auditable, while factual verification remains a separate layer.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable


DEFAULT_RUN_ROOT = Path(os.environ.get("LLM_CONSILIUM_RUN_ROOT", "./artifacts/llm-consilium"))
DEFAULT_CONFIG = Path(os.environ.get("LLM_CONSILIUM_CONFIG", "./llm-consilium.json"))
PACKAGE_CONFIG = Path(__file__).resolve().parent.parent / "templates" / "llm-consilium.json"
PREFLIGHT_MARKER = "PREFLIGHT_OK"


@dataclasses.dataclass(frozen=True)
class CandidateSpec:
    id: str
    label: str
    route: str
    command: list[str]
    timeout: int = 600
    preflight: bool = True
    preflight_timeout: int = 90
    explicit_reasoning: str = "unknown"
    notes: str = ""
    # argv: replace {PROMPT}; stdin: send prompt to stdin; opencode_file: attach prompt.md via -f/{PROMPT_FILE}
    prompt_transport: str = "argv"


def slugify(value: str) -> str:
    out = re.sub(r"[^\w\-]+", "-", value.lower(), flags=re.UNICODE).strip("-")
    out = re.sub(r"-+", "-", out)
    return out or "consilium"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_candidate_prompt(question: str) -> str:
    return f"""You are an independent participant in a multi-model council. Reply in the user's language. Be concise and practical.

Task:
{question.strip()}

Do not guess other models' opinions. Do not refer to consensus. Provide an independent position.

Return this structure:
## Position
...

## Main arguments
- ...

## Risks / caveats
- ...

## Confidence
low|medium|high — why

## What could change the conclusion
- ...
"""


def _replace_tokens(cmd: Iterable[str], *, prompt: str, workspace: Path, prompt_file: Path) -> list[str]:
    out: list[str] = []
    for part in cmd:
        if part == "{PROMPT}":
            out.append(prompt)
        elif part == "{WORKSPACE}":
            out.append(str(workspace))
        elif part == "{PROMPT_FILE}":
            out.append(str(prompt_file))
        else:
            out.append(part)
    return out


def load_consilium_config(config_path: Path | None = None) -> dict:
    if config_path:
        path = config_path
    elif DEFAULT_CONFIG.exists():
        path = DEFAULT_CONFIG
    elif PACKAGE_CONFIG.exists():
        path = PACKAGE_CONFIG
    else:
        path = DEFAULT_CONFIG
    return json.loads(path.read_text(encoding="utf-8"))


def _config_command(command: list[str]) -> list[str]:
    return list(command)


def all_candidate_specs(config_path: Path | None = None) -> dict[str, CandidateSpec]:
    config = load_consilium_config(config_path)
    specs: dict[str, CandidateSpec] = {}
    for cid, raw in config.get("candidates", {}).items():
        specs[cid] = CandidateSpec(
            id=cid,
            label=raw.get("label", cid),
            route=raw["route"],
            command=_config_command(list(raw["command"])),
            timeout=int(raw.get("timeout", 600)),
            preflight=bool(raw.get("preflight", True)),
            preflight_timeout=int(raw.get("preflight_timeout", 90)),
            explicit_reasoning=raw.get("explicit_reasoning", "unknown"),
            notes=raw.get("notes", ""),
            prompt_transport=raw.get("prompt_transport", "argv"),
        )
    return specs


def default_candidate_ids(mode: str, config_path: Path | None = None) -> list[str]:
    config = load_consilium_config(config_path)
    try:
        return list(config["modes"][mode]["default_candidates"])
    except KeyError as e:
        raise SystemExit(f"unknown mode in config: {mode}") from e


def default_candidates(mode: str) -> list[CandidateSpec]:
    specs = all_candidate_specs()
    ids = default_candidate_ids(mode)
    missing = [i for i in ids if i not in specs]
    if missing:
        raise SystemExit(f"config mode {mode} references unknown candidates: {', '.join(missing)}")
    return [specs[i] for i in ids]

def classify_output(returncode: int | None, stdout: str, stderr: str) -> str:
    if returncode is None:
        return "timeout"
    if returncode != 0:
        return "failed"
    text = stdout.strip()
    if not text:
        return "empty_output"
    nonempty_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if nonempty_lines and all(re.match(r"(?i)^(>?\s*build\s*·|thinking:\s*)", line) for line in nonempty_lines):
        return "no_final_output"
    lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    parsed = []
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            parsed = []
            break
        if isinstance(obj, dict):
            parsed.append(obj)
    if parsed:
        event_types = {str(o.get("type") or o.get("part") or "").lower() for o in parsed}
        text_values = [str(o.get("text") or o.get("content") or "").strip() for o in parsed]
        has_finalish_text = any(t for t in text_values) and any(t in event_types for t in {"text", "message", "assistant_message", "response"})
        if event_types and event_types.issubset({"step_start", "step_finish", "reasoning", "thinking"}) and not has_finalish_text:
            return "no_final_output"
    return "ok"


def _to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def build_command(spec: CandidateSpec, prompt: str, workspace: Path, prompt_file: Path) -> tuple[list[str], str | None]:
    if spec.prompt_transport == "stdin":
        cmd = _replace_tokens(spec.command, prompt="", workspace=workspace, prompt_file=prompt_file)
        return cmd, prompt
    if spec.prompt_transport == "opencode_file":
        cmd = _replace_tokens(spec.command, prompt="", workspace=workspace, prompt_file=prompt_file)
        return cmd, None
    cmd = _replace_tokens(spec.command, prompt=prompt, workspace=workspace, prompt_file=prompt_file)
    return cmd, None


def run_command(spec: CandidateSpec, prompt: str, workspace: Path, timeout: int, dry_run: bool) -> tuple[str, str, int | None, float]:
    prompt_file = workspace / "prompt.md"
    cmd, stdin_text = build_command(spec, prompt, workspace, prompt_file)
    if dry_run:
        return "", "", 0, 0.0
    env = os.environ.copy()
    env.setdefault("CODEX_HOME", str(Path.home() / ".codex"))
    started = time.monotonic()
    print(f"START {spec.id} route={spec.route} timeout={timeout}s", flush=True)
    try:
        p = subprocess.run(
            cmd, cwd=str(workspace), env=env, text=True, input=stdin_text,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
        )
        return _to_text(p.stdout), _to_text(p.stderr), p.returncode, time.monotonic() - started
    except subprocess.TimeoutExpired as e:
        stdout = _to_text(e.stdout)
        stderr = _to_text(e.stderr) + f"\nTIMEOUT after {timeout}s\n"
        return stdout, stderr, None, time.monotonic() - started


def _opencode_model_from_command(command: list[str]) -> str | None:
    try:
        return command[command.index("--model") + 1]
    except (ValueError, IndexError):
        return None


def run_preflight(spec: CandidateSpec, workspace: Path, timeout: int, dry_run: bool) -> dict:
    if dry_run or not spec.preflight:
        return {"status": "dry_run" if dry_run else "skipped", "marker": PREFLIGHT_MARKER}
    prompt = f"Reply exactly {PREFLIGHT_MARKER}"
    write_text(workspace / "preflight_prompt.md", prompt)
    env = os.environ.copy()
    env.setdefault("CODEX_HOME", str(Path.home() / ".codex"))
    attempts = []
    for attempt in range(1, 3):
        started = time.monotonic()
        try:
            if spec.route == "opencode-cli":
                model = _opencode_model_from_command(spec.command)
                cmd = [os.environ.get("LLM_CONSILIUM_OPENCODE", "opencode"), "run", prompt]
                if model:
                    cmd += ["--model", model, "--variant", "max"]
                stdin_text = None
            else:
                cmd, stdin_text = build_command(spec, prompt, workspace, workspace / "preflight_prompt.md")
            print(f"PREFLIGHT {spec.id} route={spec.route} attempt={attempt}", flush=True)
            p = subprocess.run(
                cmd, cwd=str(workspace), env=env, text=True, input=stdin_text,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(timeout, spec.preflight_timeout),
            )
            stdout, stderr, returncode = _to_text(p.stdout), _to_text(p.stderr), p.returncode
        except subprocess.TimeoutExpired as e:
            stdout, stderr, returncode = _to_text(e.stdout), _to_text(e.stderr) + f"\nPREFLIGHT TIMEOUT after {min(timeout, spec.preflight_timeout)}s\n", None
        write_text(workspace / f"preflight_attempt_{attempt}.stdout", stdout)
        write_text(workspace / f"preflight_attempt_{attempt}.stderr", stderr)
        duration = time.monotonic() - started
        status = classify_output(returncode, stdout, stderr)
        attempts.append({
            "attempt": attempt,
            "returncode": returncode,
            "duration_sec": round(duration, 3),
            "stdout_chars": len(stdout),
            "stderr_chars": len(stderr),
            "classifier_status": status,
        })
        if status == "ok" and PREFLIGHT_MARKER in stdout:
            return {"status": "ok", "marker": PREFLIGHT_MARKER, "attempts": attempts, **attempts[-1]}
        time.sleep(1)
    return {"status": "skipped_preflight", "marker": PREFLIGHT_MARKER, "attempts": attempts, **attempts[-1]}


def make_run_dir(root: Path, slug: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = root / f"{slugify(slug)}-{stamp}"
    run = base
    suffix = 2
    while run.exists():
        run = Path(f"{base}-{suffix}")
        suffix += 1
    for sub in ["prompts", "inputs", "raw", "logs", "analysis", "graphs", "reviews"]:
        (run / sub).mkdir(parents=True, exist_ok=False)
    return run


def order_candidate_results(items: list[dict], desired_ids: list[str]) -> list[dict]:
    order = {cid: idx for idx, cid in enumerate(desired_ids)}
    return sorted(items, key=lambda item: order.get(item.get("id"), len(order)))


SECTION_ALIASES = {
    "Position": ["Position", "Позиция", "Answer", "Verdict", "Итог", "Вердикт"],
    "Main arguments": ["Main arguments", "Arguments", "Key arguments", "Главные аргументы", "Аргументы", "Ключевые аргументы"],
    "Risks / caveats": ["Risks / caveats", "Risks", "Caveats", "Limitations", "Риски / caveats", "Риски", "Ограничения"],
    "What could change the conclusion": ["What could change the conclusion", "What would change the answer", "Conditions for revision", "Что могло бы изменить вывод", "Что изменит вывод"],
}


def _section_text(text: str, section: str) -> str:
    for alias in SECTION_ALIASES.get(section, [section]):
        pattern = rf"(?is)^##\s*{re.escape(alias)}\s*\n(.*?)(?=^##\s+|\Z)"
        m = re.search(pattern, text, flags=re.MULTILINE)
        if m:
            return m.group(1).strip()
    return ""


def _clean_claim(line: str) -> str:
    line = re.sub(r"^\s*[-*•]\s*", "", line).strip()
    line = re.sub(r"\s+", " ", line)
    return line.strip(" .;—-")


def _claim_key(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    stop = {"и", "в", "во", "на", "с", "со", "что", "это", "как", "но", "или", "а", "по", "из", "для", "без", "не"}
    words = [w for w in text.split() if len(w) > 2 and w not in stop]
    return " ".join(words[:14])


def _token_set(text: str) -> set[str]:
    return set(_claim_key(text).split())


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / max(1, min(len(ta), len(tb))) >= 0.72


def extract_candidate_claims(candidate_id: str, text: str) -> list[dict]:
    claims: list[dict] = []
    position = _clean_claim(_section_text(text, "Position").splitlines()[0] if _section_text(text, "Position") else "")
    if position:
        claims.append({"candidate": candidate_id, "type": "position", "text": position, "section": "Position"})
    for section, claim_type in [("Main arguments", "argument"), ("Risks / caveats", "risk"), ("What could change the conclusion", "uncertainty")]:
        body = _section_text(text, section)
        for line in body.splitlines():
            claim = _clean_claim(line)
            if claim and len(claim) > 8:
                claims.append({"candidate": candidate_id, "type": claim_type, "text": claim, "section": section})
    return claims


def synthesize_run(run: Path) -> dict:
    manifest_path = run / "council_run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ok_items = [c for c in manifest.get("candidates", []) if c.get("status") == "ok"]
    ok_ids = [c["id"] for c in ok_items]
    failed = [c for c in manifest.get("candidates", []) if c.get("status") != "ok"]

    per_candidate_claims: dict[str, list[dict]] = {}
    extraction_warnings: list[dict] = []
    flat: list[dict] = []
    for c in ok_items:
        raw_path = Path(c.get("raw_path") or run / "raw" / f"{c['id']}.md")
        text = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
        claims = extract_candidate_claims(c["id"], text)
        if not claims:
            extraction_warnings.append({
                "candidate": c["id"],
                "raw_path": str(raw_path),
                "warning": "ok candidate produced zero structured claims; check headings/schema before excluding from synthesis",
            })
        per_candidate_claims[c["id"]] = claims
        flat.extend(claims)

    groups: list[dict] = []
    for claim in flat:
        placed = False
        for group in groups:
            if _similar(_claim_key(claim["text"]), group["key"]):
                group["mentions"].append(claim)
                placed = True
                break
        if not placed:
            groups.append({"id": f"C{len(groups)+1}", "key": _claim_key(claim["text"]), "text": claim["text"], "type": claim["type"], "mentions": [claim]})

    stance_rows: list[dict] = []
    for group in groups:
        stances: dict[str, str] = {}
        supporters: list[str] = []
        for cid in ok_ids:
            candidate_claims = per_candidate_claims.get(cid, [])
            supports = any(_similar(_claim_key(cc["text"]), group["key"]) for cc in candidate_claims)
            stances[cid] = "support" if supports else "not_addressed"
            if supports:
                supporters.append(cid)
        support_count = len(supporters)
        support_ratio = support_count / len(ok_ids) if ok_ids else 0.0
        agreement_level = "high" if support_ratio >= 0.75 else "medium" if support_ratio >= 0.4 else "low"
        evidence_status = "cross-model-repeated" if support_count >= 2 else "single-model-only"
        if support_count == len(ok_ids) and ok_ids:
            evidence_status = "all-models-repeated"
        stance_rows.append({
            "id": group["id"],
            "text": group["text"],
            "type": group["type"],
            "stances": stances,
            "supporters": supporters,
            "support_count": support_count,
            "support_ratio": round(support_ratio, 3),
            "evidence_status": evidence_status,
            "agreement_level": agreement_level,
            "confidence": agreement_level,  # backward-compatible alias; not composite confidence
        })

    consensus = [r for r in stance_rows if r["support_count"] >= 2]
    single_source = [r for r in stance_rows if r["support_count"] == 1]
    unresolved = [r for r in stance_rows if r["type"] in {"risk", "uncertainty"}]

    analysis_dir = run / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    claims_doc = {"run_dir": str(run), "ok_candidates": ok_ids, "claims": stance_rows, "extraction_warnings": extraction_warnings}
    stance_doc = {
        "run_dir": str(run),
        "candidates": ok_ids,
        "semantics": "repetition-report; stances are support/not_addressed only unless a separate contradiction detector is added",
        "claims": stance_rows,
        "extraction_warnings": extraction_warnings,
    }
    ledger = {
        "run_dir": str(run),
        "mode": "model-consistency-only",
        "note": "No external evidence checks were executed by the deterministic synthesizer; statuses reflect cross-model repetition only, not verified truth.",
        "checked_claims": [],
        "extraction_warnings": extraction_warnings,
    }
    write_text(analysis_dir / "claims.json", json.dumps(claims_doc, ensure_ascii=False, indent=2))
    report_json = json.dumps(stance_doc, ensure_ascii=False, indent=2)
    write_text(analysis_dir / "repetition_report.json", report_json)
    write_text(analysis_dir / "stance_matrix.json", report_json)  # compatibility filename
    write_text(analysis_dir / "evidence_ledger.json", json.dumps(ledger, ensure_ascii=False, indent=2))

    lines = [
        "# Синтез LLM-консилиума", "",
        f"Прогон: `{run}`",
        f"Режим: `{manifest.get('mode', 'unknown')}`",
        f"Статус evidence: `model-consistency-only` — deterministic stage did not perform web/source verification.", "",
        "## Successful candidates",
    ]
    lines += [f"- {cid}" for cid in ok_ids] or ["- none"]
    lines += ["", "## Consensus"]
    lines += [f"- **{r['id']}** ({r['support_count']}/{len(ok_ids)}): {r['text']}" for r in consensus[:12]] or ["- No repeated consensus found."]
    lines += ["", "## Single-source / слабые claims"]
    lines += [f"- **{r['id']}** ({', '.join(r['supporters'])}): {r['text']}" for r in single_source[:12]] or ["- none"]
    lines += ["", "## Risks / unresolved"]
    lines += [f"- **{r['id']}**: {r['text']}" for r in unresolved[:10]] or ["- none"]
    lines += ["", "## Stance matrix / repetition report"]
    for r in stance_rows[:20]:
        compact = "; ".join(f"{cid}: {stance}" for cid, stance in r["stances"].items())
        lines.append(f"- **{r['id']}** {r['text']} — {compact}")
    if extraction_warnings:
        lines += ["", "## Extraction warnings"]
        lines += [f"- {w['candidate']}: {w['warning']}" for w in extraction_warnings]
    if failed:
        lines += ["", "## Failed / excluded candidates"]
        lines += [f"- {c.get('id')}: {c.get('status')}" for c in failed]
    lines += ["", "## Next layer", "For factual questions, run a separate evidence-checking/source/tool pass; this file does not prove claim truth."]
    final = "\n".join(lines) + "\n"
    write_text(run / "final.md", final)
    write_text(analysis_dir / "summary.md", final)
    result = {"ok_candidates": ok_ids, "claim_count": len(stance_rows), "consensus_count": len(consensus), "final_path": str(run / "final.md")}
    write_text(analysis_dir / "synthesis_result.json", json.dumps(result, ensure_ascii=False, indent=2))
    return result


def build_final_stub(run: Path, manifest: dict) -> str:
    ok = [c["id"] for c in manifest["candidates"] if c["status"] == "ok"]
    bad = [c for c in manifest["candidates"] if c["status"] != "ok"]
    lines = [
        "# LLM Consilium Run", "",
        f"Прогон: `{run}`",
        f"Mode: `{manifest['mode']}`",
        f"Prompt SHA256: `{manifest['prompt_sha256']}`", "",
        "## Successful candidates",
    ]
    lines += [f"- {x}" for x in ok] or ["- none"]
    lines += ["", "## Failed / excluded candidates"]
    lines += [f"- {c['id']}: {c['status']}" for c in bad] or ["- none"]
    lines += ["", "## Next", "Run `llm-consilium-synthesize <run-dir>` for deterministic claim extraction, repetition report, and synthesis."]
    return "\n".join(lines) + "\n"

def command_for_log(spec: CandidateSpec, workspace: Path) -> list[str]:
    return _replace_tokens(spec.command, prompt="<PROMPT>", workspace=workspace, prompt_file=workspace / "prompt.md")


def run_candidate(spec: CandidateSpec, prompt: str, prompt_hash: str, run: Path, timeout: int, dry_run: bool, do_preflight: bool) -> dict:
    workspace = run / "inputs" / spec.id
    workspace.mkdir(parents=True, exist_ok=True)
    write_text(workspace / "prompt.md", prompt)
    preflight_result = {"status": "disabled"}
    if do_preflight and spec.preflight:
        preflight_result = run_preflight(spec, workspace, timeout, dry_run)
        if preflight_result["status"] == "skipped_preflight":
            stdout, stderr, returncode, duration = "", "", None, preflight_result.get("duration_sec", 0.0)
            status = "skipped_preflight"
        else:
            stdout, stderr, returncode, duration = run_command(spec, prompt, workspace, timeout, dry_run)
            status = "dry_run" if dry_run else classify_output(returncode, stdout, stderr)
    else:
        stdout, stderr, returncode, duration = run_command(spec, prompt, workspace, timeout, dry_run)
        status = "dry_run" if dry_run else classify_output(returncode, stdout, stderr)

    raw_path = run / "raw" / f"{spec.id}.md"
    err_path = run / "logs" / f"{spec.id}.err"
    write_text(raw_path, stdout)
    write_text(err_path, stderr)
    cmd_for_log = command_for_log(spec, workspace)
    item = {
        "id": spec.id,
        "label": spec.label,
        "route": spec.route,
        "explicit_reasoning": spec.explicit_reasoning,
        "prompt_transport": spec.prompt_transport,
        "preflight_timeout": spec.preflight_timeout,
        "preflight": preflight_result,
        "status": status,
        "workspace": str(workspace),
        "raw_path": str(raw_path),
        "stderr_path": str(err_path),
        "prompt_sha256": prompt_hash,
        "command": cmd_for_log,
        "command_shell": shlex.join(cmd_for_log),
        "timeout": timeout,
        "returncode": returncode,
        "duration_sec": round(float(duration), 3),
        "stdout_chars": len(stdout),
        "stderr_chars": len(stderr),
        "notes": spec.notes,
    }
    print(f"{spec.id}: {status} chars={len(stdout)} raw={raw_path}", flush=True)
    return item


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic LLM consilium runner")
    ap.add_argument("slug", help="run slug/name")
    q = ap.add_mutually_exclusive_group(required=True)
    q.add_argument("--question", help="question text")
    q.add_argument("--question-file", type=Path, help="markdown/text question file")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    ap.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    ap.add_argument("--config", type=Path, default=None, help="consilium route/mode config JSON; defaults to LLM_CONSILIUM_CONFIG or package template")
    ap.add_argument("--candidates", help="comma-separated candidate IDs; default depends on mode")
    ap.add_argument("--timeout", type=int, default=None, help="override per-candidate timeout seconds")
    ap.add_argument("--concurrency", type=int, default=2, help="max concurrent candidate runs")
    ap.add_argument("--no-preflight", action="store_true", help="skip route marker preflight")
    ap.add_argument("--dry-run", action="store_true", help="create artifacts and route manifest without calling models")
    ap.add_argument("--no-synthesize", action="store_true", help="do not run deterministic synthesis after candidates")
    args = ap.parse_args(argv)

    question = args.question if args.question is not None else args.question_file.read_text(encoding="utf-8")
    prompt = build_candidate_prompt(question)
    prompt_hash = sha256_text(prompt)
    specs_by_id = all_candidate_specs(args.config)
    if args.candidates:
        ids = [x.strip() for x in args.candidates.split(",") if x.strip()]
        unknown = [x for x in ids if x not in specs_by_id]
        if unknown:
            raise SystemExit(f"unknown candidates: {', '.join(unknown)}; available: {', '.join(sorted(specs_by_id))}")
        specs = [specs_by_id[i] for i in ids]
    else:
        ids = default_candidate_ids(args.mode, args.config)
        missing = [i for i in ids if i not in specs_by_id]
        if missing:
            raise SystemExit(f"config mode {args.mode} references unknown candidates: {', '.join(missing)}")
        specs = [specs_by_id[i] for i in ids]

    run = make_run_dir(args.run_root, args.slug)
    write_text(run / "question.md", question)
    write_text(run / "prompts" / "candidate.md", prompt)

    manifest = {
        "kind": "llm-consilium-run",
        "version": 2,
        "mode": args.mode,
        "run_dir": str(run),
        "created_at": dt.datetime.now().isoformat(),
        "prompt_sha256": prompt_hash,
        "dry_run": bool(args.dry_run),
        "preflight": not args.no_preflight,
        "concurrency": max(1, int(args.concurrency)),
        "candidates": [],
    }
    route_status: dict[str, dict] = {}

    def persist() -> None:
        write_text(run / "council_run.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        write_text(run / "route_status.json", json.dumps(route_status, ensure_ascii=False, indent=2))

    max_workers = 1 if args.dry_run else max(1, int(args.concurrency))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = []
        for spec in specs:
            timeout = args.timeout or spec.timeout
            futures.append(pool.submit(run_candidate, spec, prompt, prompt_hash, run, timeout, args.dry_run, not args.no_preflight))
        completed_items = []
        for fut in as_completed(futures):
            item = fut.result()
            completed_items.append(item)
            manifest["candidates"] = order_candidate_results(completed_items, ids)
            route_status.clear()
            route_status.update({c["id"]: c for c in manifest["candidates"]})
            persist()

    manifest["candidates"] = order_candidate_results(manifest["candidates"], ids)
    route_status.clear()
    route_status.update({c["id"]: c for c in manifest["candidates"]})
    write_text(run / "final.md", build_final_stub(run, manifest))
    persist()
    if not args.no_synthesize:
        synthesize_run(run)
    print(f"RUN_DIR={run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
