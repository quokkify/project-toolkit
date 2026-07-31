#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []

def check(condition: bool, message: str) -> None:
    if not condition: ERRORS.append(message)

def run(cmd: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print('+', ' '.join(cmd), f'(cwd={cwd.relative_to(ROOT) if cwd.is_relative_to(ROOT) else cwd})')
    subprocess.run(cmd, cwd=cwd, env=env, check=True)

for path in sorted([*ROOT.rglob('*.yml'), *ROOT.rglob('*.yaml')]):
    if '.git' in path.parts or 'templates/project/template' in path.as_posix(): continue
    try: yaml.safe_load(path.read_text())
    except Exception as exc: ERRORS.append(f'{path.relative_to(ROOT)}: YAML: {exc}')

for path in sorted(ROOT.rglob('*.json')):
    if 'templates/project/template' in path.as_posix(): continue
    try: json.loads(path.read_text())
    except Exception as exc: ERRORS.append(f'{path.relative_to(ROOT)}: JSON: {exc}')
for path in sorted(ROOT.rglob('*.json5')):
    try: json.loads(path.read_text())
    except Exception as exc: ERRORS.append(f'{path.relative_to(ROOT)}: JSON5 subset: {exc}')

uses_re = re.compile(r'^\s*uses:\s*([^\s#]+)', re.M)
sha_re = re.compile(r'^[0-9a-f]{40}$')
for path in sorted([*ROOT.rglob('*.yml'), *ROOT.rglob('*.yaml')]):
    for use in uses_re.findall(path.read_text()):
        if use.startswith('./'): continue
        target, sep, ref = use.rpartition('@')
        check(bool(sep), f'{path.relative_to(ROOT)}: action without ref: {use}')
        if target.startswith('ylazakovich/project-toolkit/.github/workflows/'):
            check(bool(re.fullmatch(r'v\d+\.\d+\.\d+', ref)), f'{path.relative_to(ROOT)}: toolkit workflow must use exact SemVer: {use}')
        else:
            check(bool(sha_re.fullmatch(ref)), f'{path.relative_to(ROOT)}: external action is not SHA-pinned: {use}')

link_re = re.compile(r'(?<!!)\[[^]]+\]\(([^)]+)\)')
for path in sorted(ROOT.rglob('*.md')):
    for link in link_re.findall(path.read_text()):
        if re.match(r'^(https?://|mailto:|#)', link): continue
        target = (path.parent / link.split('#', 1)[0]).resolve()
        check(target.exists() and (target == ROOT or ROOT in target.parents), f'{path.relative_to(ROOT)}: broken/escaping local link: {link}')

poly = (ROOT / 'examples/polyglot-ci.yml').read_text()
for job in ('python:', 'node:', 'java:', 'integration:'):
    check(re.search(rf'^  {re.escape(job)}$', poly, re.M) is not None, f'polyglot example missing independent {job[:-1]} job')
check("needs: [changes, python, node, java]" in poly, 'polyglot integration job must depend on component checks')

docker = yaml.safe_load((ROOT / '.github/workflows/docker-build.yml').read_text())
on_key = next((k for k in docker if str(k).lower() in ('on', 'true')), None)
call = docker[on_key]['workflow_call']
check(call['inputs']['push']['default'] is False, 'Docker push default must be false')
release = yaml.safe_load((ROOT / '.github/workflows/release-please.yml').read_text())
check(release.get('permissions') == {'contents': 'write', 'pull-requests': 'write'}, 'Release workflow permissions must be exactly contents:write and pull-requests:write')

secret_patterns = [
    r'ghp_[A-Za-z0-9]{20,}',
    r'github_pat_[A-Za-z0-9_]{20,}',
    '/ho' + r'me/[^/\s]+',
    r'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY',
]
for path in sorted(p for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.parts):
    try: text = path.read_text()
    except UnicodeDecodeError: continue
    for pattern in secret_patterns:
        if re.search(pattern, text): ERRORS.append(f'{path.relative_to(ROOT)}: prohibited secret/personal-path pattern: {pattern}')

if ERRORS:
    print('\n'.join('ERROR: ' + e for e in ERRORS), file=sys.stderr)
    raise SystemExit(1)

run([sys.executable, '-m', 'compileall', '-q', 'src'], ROOT / 'tests/fixtures/python')
run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], ROOT / 'tests/fixtures/python')
(ROOT / 'tests/fixtures/python/dist').mkdir(exist_ok=True)
run([sys.executable, '-m', 'zipapp', 'src', '-o', 'dist/app.pyz', '-m', 'app:main'], ROOT / 'tests/fixtures/python')
run(['npm', 'run', 'lint'], ROOT / 'tests/fixtures/node')
run(['npm', 'test'], ROOT / 'tests/fixtures/node')
run(['npm', 'run', 'build'], ROOT / 'tests/fixtures/node')
java = ROOT / 'tests/fixtures/java'
(java / 'build/classes').mkdir(parents=True, exist_ok=True)
(java / 'build/test-classes').mkdir(parents=True, exist_ok=True)
run(['javac', '-Xlint:all', '-d', 'build/classes', 'src/toolkit/App.java'], java)
run(['javac', '-Xlint:all', '-cp', 'build/classes', '-d', 'build/test-classes', 'test/toolkit/AppTest.java'], java)
run(['java', '-cp', 'build/classes:build/test-classes', 'toolkit.AppTest'], java)
run(['jar', '--create', '--file', 'build/toolkit-java-fixture.jar', '-C', 'build/classes', '.'], java)

copier = shutil.which('copier')
check(copier is not None, 'copier executable is required')
actionlint = shutil.which('actionlint')
check(actionlint is not None, 'actionlint executable is required')
if ERRORS:
    print('\n'.join('ERROR: ' + e for e in ERRORS), file=sys.stderr); raise SystemExit(1)
assert copier is not None and actionlint is not None
with tempfile.TemporaryDirectory(prefix='project-toolkit-validation-') as tmp:
    tmp_path = Path(tmp)
    for scenario in ('python', 'node', 'java', 'polyglot'):
        dest = tmp_path / scenario
        run([copier, 'copy', '--trust', '--defaults', '--vcs-ref', 'HEAD', '--data-file', str(ROOT / f'tests/scenarios/{scenario}.yml'), str(ROOT), str(dest)])
        run([actionlint, str(dest / '.github/workflows/ci.yml')])
        check((dest / '.copier-answers.yml').exists(), f'{scenario}: missing .copier-answers.yml')
        if scenario == 'polyglot':
            generated = (dest / '.github/workflows/ci.yml').read_text()
            for name in ('python-ci.yml', 'node-ci.yml', 'java-ci.yml', 'docker-build.yml'):
                check(name in generated, f'polyglot generated workflow missing {name}')
        if scenario == 'python':
            run(['git', 'init', '-q'], dest)
            run(['git', 'config', 'user.email', 'fixture@example.invalid'], dest)
            run(['git', 'config', 'user.name', 'Fixture'], dest)
            run(['git', 'add', '.'], dest)
            run(['git', 'commit', '-qm', 'fixture'], dest)
            run([copier, 'update', '--trust', '--defaults'], dest)
            status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=dest, text=True)
            check(status == '', f'copier update was not idempotent: {status}')
if ERRORS:
    print('\n'.join('ERROR: ' + e for e in ERRORS), file=sys.stderr); raise SystemExit(1)
print('validation: OK')
