"""Reject accidental non-ad method or class-metadata edits in planned classes."""
import re
from pathlib import Path

METHOD = re.compile(r'^\.method[^\n]*\n.*?^\.end method', re.M | re.S)
MARKERS = ('AD_PATCH_SPLASH:', '# chiyang001:')


def methods(text):
    return {m.group().splitlines()[0].split()[-1]: m.group()
            for m in METHOD.finditer(text)}


def planned_methods(path):
    return {signature for signature, body in methods(Path(path).read_text(encoding='utf-8')).items()
            if any(marker in body for marker in MARKERS)}


def audit(before, after, expected):
    old = methods(before)
    new = methods(after)
    assert old.keys() == new.keys(), 'Existing class method inventory changed'
    assert METHOD.sub('', before).strip() == METHOD.sub('', after).strip(), 'Class metadata/fields changed'
    changed = {signature for signature in old if old[signature] != new[signature]}
    assert changed == expected, f'Unexpected method edits: actual={sorted(changed)}, planned={sorted(expected)}'
    return sorted(changed)
