"""Rebuild deterministic, licensed skill bundles from immutable upstream archives.

Build-time network only. Never imports or executes upstream code.
"""
import hashlib
import io
import json
from pathlib import Path
import stat
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / '.agents/skills/spec-team'
PINS = {
    'superpowers': ('obra/superpowers', 'b739a8af570e10a95898f2bdf6cec97467fa6c12'),
    'ui-ux-pro-max': ('nextlevelbuilder/ui-ux-pro-max-skill', '56ea9cf174ed86786187daa9de0e6247cb0747e4'),
    'ponytail': ('DietrichGebert/ponytail', '09c434ab73ca43761c5d8b0c5d341926c2fba710'),
}


def build():
    families = []
    notices = ['# Third-party notices', '', 'Bundled dependencies are MIT licensed. Full original license text is retained in each exported skill directory. No upstream hooks, plugin configuration, or package-manager state is installed.', '', 'Superpowers includes all 15 skill siblings to keep internal skill references available (including writing-skills and diagnosing-superpowers). UI/UX Pro Max materializes canonical src scripts/data and retains its pristine upstream skill and references. Its upstream examples use CLAUDE_PLUGIN_ROOT; resolve the actual directory containing its SKILL.md and invoke Python with the absolute path to scripts/search.py instead. No plugin environment variable is required for the bundled search scripts. Ponytail exports its six skills only.', '']
    (DEST / 'bundles').mkdir(parents=True, exist_ok=True)
    for family, (repo, revision) in PINS.items():
        url = f'https://codeload.github.com/{repo}/zip/{revision}'
        raw = urllib.request.urlopen(url, timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            source = {}
            for i in z.infolist():
                if i.is_dir():
                    continue
                relative = i.filename.split('/', 1)[1]
                if relative.startswith('/') or '..' in relative.split('/'):
                    raise ValueError('unsafe upstream archive')
                if stat.S_IFMT(i.external_attr >> 16) not in (0, stat.S_IFREG):
                    continue  # Upstream aliases are excluded; only canonical regular files are bundled.
                source[relative] = z.read(i)
        license_text = source['LICENSE']
        assert b'MIT' in license_text and b'Permission is hereby granted' in license_text
        files = {}
        if family in ('superpowers', 'ponytail'):
            names = sorted(p.split('/')[1] for p in source if p.startswith('skills/') and p.endswith('/SKILL.md'))
            for name in names:
                prefix = f'skills/{name}/'
                files.update({p[len('skills/'):]: data for p, data in source.items() if p.startswith(prefix)})
        else:
            names = [family]
            prefix = '.claude/skills/ui-ux-pro-max/'
            files.update({family + '/' + p[len(prefix):]: data for p, data in source.items() if p.startswith(prefix) and (p.endswith('/SKILL.md') or '/references/' in p)})
            prefix = 'src/ui-ux-pro-max/'
            files.update({family + '/' + p[len(prefix):]: data for p, data in source.items() if p.startswith(prefix) and ('/data/' in p or '/scripts/' in p) and '/tests/' not in p})
        for name in names:
            files[f'{name}/LICENSE'] = license_text
        if family == 'ponytail':
            files['ponytail-gain/README.md'] = source['README.md']
            files['ponytail-gain/benchmarks/results/2026-10-07-agentic.md'] = source['benchmarks/results/2026-10-07-agentic.md']
        archive = DEST / f'bundles/{family}.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, data, compresslevel=9)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        families.append({'name': family, 'repository': f'https://github.com/{repo}', 'revision': revision, 'license': 'MIT', 'archive': f'bundles/{family}.zip', 'sha256': digest, 'upstream_archive_sha256': hashlib.sha256(raw).hexdigest(), 'skills': {name: name for name in names}})
        notices.extend([f'## {family}', '', f'Source: https://github.com/{repo}/tree/{revision}', '', f'Bundled SHA-256: `{digest}`', '', license_text.decode('utf-8').strip(), ''])
        print(f'{family}: {len(files)} files, {sum(map(len, files.values()))} unpacked bytes, {archive.stat().st_size} archive bytes; {len(names)} skills')
    (DEST / 'dependencies.lock.json').write_text(json.dumps({'schema_version': 1, 'families': families}, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'THIRD_PARTY_NOTICES.md').write_text('\n'.join(notices), encoding='utf-8')


if __name__ == '__main__':
    build()
