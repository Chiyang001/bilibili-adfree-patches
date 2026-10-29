"""Reproduce this version-specific ad patch; replace DEX only, then sign locally."""
from pathlib import Path
import argparse
import concurrent.futures
import difflib
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib
from audit_changes import audit, planned_methods

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'iBiliPlayer-bili.apk'
SOURCE_SHA256 = '5c4cda22b7d8cf2b9a56d2f175b80402fc07fbdb726f1cab0893cd5820bea3a7'
ART = Path(os.environ.get('ANDROID_REVERSE_TOOLS', r'C:\Program Files\AndroidReverseTool'))
SDK = Path(os.environ.get('ANDROID_HOME', str(Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk')))
TOOLS = SDK / 'build-tools/37.0.0'
JAVA = ART / 'jdk/bin/java.exe'
JAVAC = ART / 'jdk/bin/javac.exe'
KEYTOOL = ART / 'jdk/bin/keytool.exe'
JAR = ART / 'apktool/apktool.jar'
WORK = ROOT / 'work'
DIST = ROOT / 'dist'
ANALYSIS = ROOT / 'analysis'
CP = str(WORK / 'java') + os.pathsep + str(JAR)
PATCH_NAMES = ('splash', 'video', 'common', 'search_legacy', 'video_relate', 'traffic_promo')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(command, log):
    p = subprocess.run([str(c) for c in command], cwd=ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = p.stdout.decode('utf-8', errors='replace')
    (ANALYSIS / log).write_text(output, encoding='utf-8')
    if p.returncode:
        raise RuntimeError(f'{command[0]} failed; see analysis/{log}\n{output[-6000:]}')
    return output


def dex_integrity(data):
    assert data[:8] == b'dex\n037\x00', 'DEX format must remain 037 / Android 7+'
    assert struct.unpack_from('<I', data, 32)[0] == len(data), 'DEX file size'
    assert struct.unpack_from('<I', data, 8)[0] == zlib.adler32(data[12:]) & 0xffffffff, 'DEX Adler32'
    assert data[12:32] == hashlib.sha1(data[32:]).digest(), 'DEX SHA1'
    for name, offset in (('type', 64), ('proto', 72), ('field', 80), ('method', 88)):
        assert struct.unpack_from('<I', data, offset)[0] <= 65536, f'DEX {name} reference limit'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reuse-assembled', action='store_true',
                        help='Only use when no smali changed after the last assembly')
    parser.add_argument('--rebuild-dex', action='append', default=[],
                        help='Rebuild this DEX while checking cached recipes for other DEX files')
    args = parser.parse_args()
    ANALYSIS.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)
    (WORK / 'java').mkdir(parents=True, exist_ok=True)
    assert sha(SOURCE.read_bytes()) == SOURCE_SHA256, 'Input APK differs from analyzed 9.17.0'
    assert (WORK / 'decoded/apktool.yml').exists(), 'First finish apktool d -r -o work/decoded iBiliPlayer-bili.apk'
    for name in PATCH_NAMES:
        command = [sys.executable, ROOT / f'scripts/patch_{name}.py']
        if name == 'search_legacy':
            command.append('--apply')
        run(command, f'patch_{name}.log')
    allowed = {}
    planned = {}
    for name in PATCH_NAMES:
        entries = json.loads((ANALYSIS / f'{name}_patch_report.json').read_text(encoding='utf-8'))
        for entry in entries:
            relative = entry.get('file') or entry.get('path')
            if not relative:
                continue
            p = WORK / 'decoded' / relative
            text = p.read_text(encoding='utf-8')
            match = re.search(r'^\.class[^\n]* (L[^\s]+;)$', text, re.M)
            assert match, p
            directory = Path(relative).parts[0]
            dexname = directory.replace('smali_', '') + '.dex' if directory != 'smali' else 'classes.dex'
            allowed.setdefault(dexname, set()).add(match.group(1))
            planned[(dexname, match.group(1))] = planned_methods(p)
    run([JAVAC, '-encoding', 'UTF-8', '-cp', JAR, '-d', WORK / 'java',
         ROOT / 'scripts/AssembleDex.java', ROOT / 'scripts/CompareDex.java'], 'javac.log')
    run([JAVA, '-cp', CP, 'CompareDex', '--selftest'], 'exception_comparison_selftest.log')

    def assemble(dexname):
        output = WORK / 'rebuilt' / dexname
        smali = 'smali' if dexname == 'classes.dex' else 'smali_' + dexname.removesuffix('.dex')
        # Cache is tied to the exact planned patched classes, not just APK version.
        recipe = hashlib.sha256()
        report_paths = set()
        for report_name in PATCH_NAMES:
            for item in json.loads((ANALYSIS / f'{report_name}_patch_report.json').read_text(encoding='utf-8')):
                rel = item.get('file') or item.get('path')
                if rel and Path(rel).parts[0] == smali:
                    report_paths.add(str(Path(rel)))
        for rel in sorted(report_paths):
            recipe.update(rel.encode('utf-8'))
            recipe.update((WORK / 'decoded' / rel).read_bytes())
        recipe_hash = recipe.hexdigest()
        stamp = output.with_suffix('.source-sha256')
        if args.reuse_assembled and dexname not in args.rebuild_dex:
            assert stamp.exists() and stamp.read_text().strip() == recipe_hash, f'Stale assembly for {dexname}; rerun without --reuse-assembled'
        else:
            run([JAVA, '-Xmx2048m', '-cp', CP, 'AssembleDex', WORK / 'decoded' / smali, output], f'assemble_{dexname}.log')
            stamp.write_text(recipe_hash + '\n', encoding='ascii')
        dex_integrity(output.read_bytes())
        print(f'Assembled and checked {dexname}', flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(assemble, sorted(allowed)))

    reviews = []
    checks = []
    method_checks = []
    try_equivalences = []
    for dexname, types in sorted(allowed.items()):
        allowfile = WORK / f'{dexname}.allowed.txt'
        allowfile.write_text('\n'.join(sorted(types)) + '\n', encoding='utf-8')
        reviewdir = WORK / 'review' / dexname
        output = run([JAVA, '-Xmx1536m', '-cp', CP, 'CompareDex', SOURCE, dexname,
                      WORK / 'rebuilt' / dexname, allowfile, reviewdir], f'compare_{dexname}.log')
        for line in output.splitlines():
            if line.startswith('NORMALIZED_TRY_BLOCKS\t'):
                _, normalized_dex, normalized_class = line.split('\t')
                try_equivalences.append(dict(dex=normalized_dex, class_name=normalized_class,
                    verification='Identical instructions/debug data/metadata and identical exception coverage, handler targets and handler order; adjacent ranges merged by assembler'))
            elif line.startswith('CHANGED\t'):
                _, classname, number = line.split('\t')
                a = (reviewdir / f'{number}.before.smali').read_text(encoding='utf-8')
                b = (reviewdir / f'{number}.after.smali').read_text(encoding='utf-8')
                if a:
                    changed_methods = audit(a, b, planned[(dexname, classname)])
                    method_checks.append(dict(dex=dexname, class_name=classname, methods=changed_methods))
                else:
                    assert classname in {'Lcom/chiyang001/adfree/FeedFilter;', 'Lcom/chiyang001/adfree/RelateFilter;'}, 'Unexpected new class'
                reviews.extend(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                               fromfile=f'{dexname}/{classname}/original', tofile=f'{dexname}/{classname}/patched'))
            elif line.startswith('VERIFIED\t'):
                _, _, total, changed = line.split('\t')
                checks.append(dict(dex=dexname, classes_checked=int(total), classes_changed=int(changed)))
        print(output.strip().splitlines()[-1], flush=True)
    (ANALYSIS / 'patches.diff').write_text(''.join(reviews), encoding='utf-8')
    unsigned = WORK / 'adfree-unsigned.apk'
    with zipfile.ZipFile(SOURCE) as source, zipfile.ZipFile(unsigned, 'w') as output:
        for info in source.infolist():
            if info.filename.upper().startswith('META-INF/') and info.filename.upper().endswith(('.SF', '.RSA', '.DSA', '.EC', 'MANIFEST.MF')):
                continue
            replacement = WORK / 'rebuilt' / info.filename
            data = replacement.read_bytes() if info.filename in allowed else source.read(info.filename)
            output.writestr(info, data)
    aligned = WORK / 'adfree-aligned.apk'
    run([TOOLS / 'zipalign.exe', '-f', '-P', '16', '4', unsigned, aligned], 'zipalign_build.log')
    keys = ROOT / 'keys'
    keys.mkdir(exist_ok=True)
    password = keys / 'signing-password.txt'
    keystore = keys / 'chiyang001-adfree.p12'
    if not keystore.exists():
        password.write_text(secrets.token_urlsafe(32), encoding='ascii')
        run([KEYTOOL, '-genkeypair', '-keystore', keystore, '-storetype', 'PKCS12',
             '-storepass:file', password, '-keypass:file', password, '-alias', 'adfree',
             '-keyalg', 'RSA', '-keysize', '3072', '-validity', '10000',
             '-dname', 'CN=Chiyang001,OU=Personal APK Modification'], 'keytool.log')
    assert password.exists(), 'Signing password file missing'
    final = DIST / 'Bilibili-9.17.0-adfree-experimental-arm64.apk'
    signer_base = [JAVA, '-Dfile.encoding=UTF-8', '-jar', TOOLS / 'lib/apksigner.jar']
    signer = signer_base + ['sign', '--ks', str(keystore), '--ks-key-alias', 'adfree',
              '--ks-pass', 'file:' + str(password),
              '--v1-signing-enabled', 'false', '--v2-signing-enabled', 'true',
              '--v3-signing-enabled', 'true', '--v4-signing-enabled', 'false',
              '--out', str(final), str(aligned)]
    run(signer, 'sign.log')
    run(signer_base + ['verify', '--verbose', '--print-certs', final], 'signature_verify.log')
    run([TOOLS / 'zipalign.exe', '-c', '-P', '16', '4', final], 'zipalign_verify.log')
    # Every non-replaced ZIP entry must have identical uncompressed bytes.
    unchanged = 0
    with zipfile.ZipFile(SOURCE) as source, zipfile.ZipFile(final) as output:
        assert source.namelist() == output.namelist(), 'Unexpected added/removed archive entries'
        for info in source.infolist():
            if info.filename in allowed:
                assert output.read(info.filename) == (WORK / 'rebuilt' / info.filename).read_bytes()
            else:
                assert sha(source.read(info.filename)) == sha(output.read(info.filename)), info.filename
                unchanged += 1
        for dexname in allowed:
            dex_integrity(output.read(dexname))
    report = dict(input=str(SOURCE.name), input_sha256=SOURCE_SHA256,
                  output=str(final.relative_to(ROOT)), output_sha256=sha(final.read_bytes()),
                  output_bytes=final.stat().st_size, replaced_dex=sorted(allowed),
                  canonical_dex_comparisons=checks, unchanged_zip_entries=unchanged,
                  verified_method_changes=method_checks,
                  equivalent_exception_range_encodings=try_equivalences,
                  manifest_resources_native_libraries='byte-identical to supplied APK',
                  apk_signature='v2/v3 verified; local certificate differs from official certificate',
                  zip_alignment='16 KiB native library ZIP alignment verified',
                  runtime_test='NOT RUN by this static build pipeline; consult runtime_report.json if available')
    (ANALYSIS / 'build_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (DIST / 'SHA256SUMS.txt').write_text(report['output_sha256'] + '  ' + final.name + '\n', encoding='ascii')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    main()
