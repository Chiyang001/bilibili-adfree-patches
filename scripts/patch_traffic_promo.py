"""Suppress optional free-data package promotion in old/new video players.

The two tryToShowFreeDataGuideToast methods and the older service's marketing-only
eligibility branch are changed. Network permission/charge alerts, free-data
entitlement queries, URL transformation, playback and retry stay intact.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
DECODED = ROOT / 'work/decoded'
MARKER = '# chiyang001: suppress optional free-data package promotion'
METHOD = re.compile(r'^\.method[^\n]*\n.*?^\.end method', re.M | re.S)
SPECS = [
    {
        'file': 'smali_classes16/com/bilibili/ship/theseus/united/player/mediaplay/network/m.smali',
        'class': 'Lcom/bilibili/ship/theseus/united/player/mediaplay/network/m;',
        'method': 'f(Lkotlin/coroutines/jvm/internal/ContinuationImpl;)Ljava/lang/Object;',
        'original_sha256': '355885cd58ad7528aecb400e71fc09f0670dd2cb8c37352f9edad9d02d92b521',
        'patched_sha256': 'f8a5cef8820d6204deff3a9f962940891e225c38a37180f533e682cc790370f0',
        'original_method_sha256': '898d74ffa567963dbd498e6982097a9f359a5163566d237bbbd9ec1388bbfb47',
        'patched_method_sha256': 'f2373156bf3921e85fcd978a5887eeab98d9d924b0325e717e1e8f111db314db',
    },
    {
        'file': 'smali_classes17/com/bilibili/ship/theseus2/united/player/mediaplay/network/NetworkShowToastService.smali',
        'class': 'Lcom/bilibili/ship/theseus2/united/player/mediaplay/network/NetworkShowToastService;',
        'method': 'g(Lkotlin/coroutines/jvm/internal/ContinuationImpl;)Ljava/lang/Object;',
        'original_sha256': '6789f63cd7a9ee563812dd7b90f283dc7b9864da17bd2923a51e55b0a044f327',
        'patched_sha256': 'd6c6f1d1414f86ff34571b16113fb7030b4d28145903dcd16a9d1ce85086eef8',
        'original_method_sha256': '420900ab8e72f51e000ed968b7144cfe04ac161a7ba86ae4e3af9d29af429290',
        'patched_method_sha256': '961943d1562b710d0bcec530ee55be084b1d9854ab181b53086076dbd9010cb9',
    },
    {
        'file': 'smali_classes14/com/bilibili/playerbizcommon/features/network/PlayerNetworkService.smali',
        'class': 'Lcom/bilibili/playerbizcommon/features/network/PlayerNetworkService;',
        'method': 'l(Lcom/bilibili/playerbizcommon/features/network/VideoEnvironment;Landroid/content/Context;)V',
        'operation': 'skip_common_guide_branch',
        'original_sha256': '5ab5694b33d83c72f52d683e0ffb6700e4eb14cf641a328fb942cab11d717a6c',
        'patched_sha256': '316bcfbdf66293e7c214d64bf69040dfc9875fd06e104e2f8f14f52fb5d8a5a9',
        'original_method_sha256': 'ebc6243ba29a4f0b647956b75341e4b4e81677f85bf9a5bce30505cd62af06c7',
        'patched_method_sha256': 'c81eb93b9531806c15407fb9f4ae54d03b24f2a99fce79555e39140346136efc',
    },
]


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def main():
    pending = []
    report = []
    for spec in SPECS:
        path = DECODED / spec['file']
        text = path.read_text(encoding='utf-8')
        actual = digest(text)
        assert actual in (spec['original_sha256'], spec['patched_sha256']), ('Unknown class edits/version', spec['file'], actual)
        assert re.search(r'^\.class[^\n]* ' + re.escape(spec['class']) + r'$', text, re.M)
        matches = [m for m in METHOD.finditer(text) if m.group().splitlines()[0].endswith(' ' + spec['method'])]
        assert len(matches) == 1, (spec['file'], spec['method'])
        match = matches[0]
        old = match.group()
        if actual == spec['patched_sha256']:
            assert digest(old) == spec['patched_method_sha256']
            result = text
            already = True
        else:
            assert digest(old) == spec['original_method_sha256']
            if spec.get('operation') == 'skip_common_guide_branch':
                needle = '    :cond_e\n    :goto_5\n    if-eqz v2, :cond_11'
                assert old.count(needle) == 1
                replacement = old.replace(needle,
                    '    :cond_e\n    :goto_5\n'
                    '    # chiyang001: skip optional free-data marketing, retain actual fee warning and cleanup\n'
                    '    goto/16 :cond_11')
                for preserved_call in ('->m(Ljava/lang/String;ZZ)V', '->a()V', '->q()V'):
                    assert old.count(preserved_call) == replacement.count(preserved_call) > 0
            else:
                assert 'tryToShowFreeDataGuideToast' in old
                assert 'player.player.network-freeflow-toast.show.player' in old
                assert 'not china sim user, skip free data guide toast' in old
                assert 'new user should not show free data guide toast' in old
                header, body = old.split('\n', 1)
                assert '    .line 1\n' in body
                prefix = body.split('    .line 1\n', 1)[0]
                prefix, count = re.subn(r'    \.locals \d+\n', '    .locals 1\n', prefix, count=1)
                assert count == 1
                replacement = (header + '\n' + prefix + '    ' + MARKER + '\n'
                               '    sget-object v0, Lkotlin/Unit;->INSTANCE:Lkotlin/Unit;\n'
                               '    return-object v0\n.end method')
            assert digest(replacement) == spec['patched_method_sha256']
            result = text[:match.start()] + replacement + text[match.end():]
            already = False
        assert digest(result) == spec['patched_sha256']
        pending.append((path, result))
        report.append({**spec, 'already_applied': already,
                       'behavior': ('Skip only the optional promotion eligibility branch; keep prior fee warnings and a()/q() cleanup.'
                                    if spec.get('operation') == 'skip_common_guide_branch' else
                                    'Synchronously complete the optional free-data promotion with kotlin.Unit; no guide request or toast.'),
                       'runtime_verified': False})
    # No mutations until every input and exact final result passes validation.
    for path, result in pending:
        if path.read_text(encoding='utf-8') != result:
            path.write_text(result, encoding='utf-8', newline='\n')
    out = ROOT / 'analysis/traffic_promo_patch_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
