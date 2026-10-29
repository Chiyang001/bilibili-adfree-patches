"""Capture only the authorized Bilibili test surface on the connected phone."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('--serial', required=True)
    parser.add_argument('--xml', action='store_true')
    args = parser.parse_args()
    output = ROOT / 'work/runtime'
    output.mkdir(parents=True, exist_ok=True)

    def adb(*command, timeout=35):
        return subprocess.run(['adb', '-s', args.serial, *command], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout, check=True).stdout

    focus = adb('shell', 'dumpsys', 'window').decode('utf-8', 'replace')
    current = [line.strip() for line in focus.splitlines() if 'mCurrentFocus=' in line]
    print('\n'.join(current))
    assert current and 'tv.danmaku.bili/' in current[0], 'Bilibili is not foreground; skip screenshot'
    png = adb('exec-out', 'screencap', '-p')
    assert png.startswith(b'\x89PNG'), 'Invalid screenshot'
    path = output / f'{args.label}.png'
    path.write_bytes(png)
    print(path)
    if args.xml:
        remote = '/data/local/tmp/bili-adfree-ui.xml'
        adb('shell', 'rm', '-f', remote)
        status = adb('shell', 'uiautomator', 'dump', remote).decode('utf-8', 'replace')
        if 'dumped to:' not in status:
            print(status)
            return
        raw = adb('exec-out', 'cat', remote)
        root = ET.fromstring(raw)
        nodes = []
        for node in root.iter('node'):
            if not (node.get('text') or node.get('content-desc')):
                continue
            if node.get('class') == 'android.widget.EditText':
                continue
            nodes.append({k: node.get(k) for k in ('text', 'content-desc', 'resource-id', 'clickable', 'bounds')})
        (output / f'{args.label}.nodes.json').write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(nodes, ensure_ascii=False))


if __name__ == '__main__':
    main()
