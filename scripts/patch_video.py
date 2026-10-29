"""Hash-pinned, idempotent video-ad patches for the supplied Bilibili APK.

Only advertising entry points are changed. Player, account and entitlement
methods are untouched. Run after apktool d -r into work/decoded.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
DECODED = ROOT / 'work' / 'decoded'
MARKER = '# chiyang001: video advertisements disabled'


def patch_class(relative, descriptor, expected_sha256, methods):
    path = DECODED / relative
    raw = path.read_bytes()
    content = raw.decode('utf-8').replace('\r\n', '\n')
    assert re.search(r'^\.class[^\n]* ' + re.escape(descriptor) + r'$', content, re.M), path
    before = hashlib.sha256(raw).hexdigest()
    if MARKER not in content:
        assert before == expected_sha256, f'Unexpected original class: {path}: {before}'
    changed = []
    for signature, locals_count, code in methods:
        pattern = re.compile(r'(^\.method[^\n]* ' + re.escape(signature) + r'\n)(.*?)(^\.end method)', re.M | re.S)
        matches = list(pattern.finditer(content))
        assert len(matches) == 1, (path, signature, len(matches))
        m = matches[0]
        old = m.group(2)
        # Preserve method and parameter annotations, including Nullable contracts.
        prefix = old.split('    .line 1\n', 1)[0]
        prefix = re.sub(r'    \.locals \d+\n', f'    .locals {locals_count}\n', prefix, count=1)
        if MARKER in old:
            continue
        assert '    .line 1\n' in old, (path, signature)
        body = prefix + f'    {MARKER}\n' + code + '\n'
        content = content[:m.start()] + m.group(1) + body + m.group(3) + content[m.end():]
        changed.append(signature)
    if changed:
        path.write_text(content, encoding='utf-8', newline='\n')
    return {'class': descriptor, 'file': str(path.relative_to(DECODED)),
            'original_sha256': expected_sha256,
            'patched_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'methods': [x[0] for x in methods]}


def main():
    result = []
    result.append(patch_class(
        'smali_classes10/P10/q$e.smali', 'LP10/q$e;',
        '14e8e597f8ccd8a8461068db8ddbadc1acff830318e3b81ecf313e4faf3304b7',
        [
            ('getUpperAdView(Landroid/view/ViewGroup;Ljava/util/List;Lcom/bilibili/gripper/api/ad/biz/videodetail/underplayer/AdUpperBridge;Lcom/bilibili/gripper/api/ad/biz/videodetail/underplayer/AdUpperConfig;Ljava/util/List;Ljava/util/List;Lcom/bilibili/adcommon/data/model/AdUpperExtraDataDto;)Lcom/bilibili/gripper/api/ad/biz/videodetail/underplayer/IAdUnderPlayerCallback;',
             1, '    const/4 v0, 0x0\n    return-object v0'),
            ('showCmHalfPanel(Landroid/content/Context;Lcom/bilibili/gripper/api/ad/biz/videodetail/panel/VideoDetailPanelRequest;)V',
             0, '    return-void'),
        ]))
    result.append(patch_class(
        'smali_classes22/kntr/app/ad/biz/videodetail/pausedpage/a.1.smali',
        'Lkntr/app/ad/biz/videodetail/pausedpage/a;',
        '85783a17c00818e29282d90d2b96ec486326641e90b859f1066ce34cd0553f9a',
        [
            ('b([B)Lkntr/app/ad/biz/videodetail/pausedpage/AdPausedPageData;',
             1, '    const/4 v0, 0x0\n    return-object v0'),
            ('c(JJLcom/bapis/bilibili/app/viewunite/v1/KTabType;Ljava/lang/String;IJJIILjava/util/List;ILjava/lang/String;Ljava/lang/String;Lkotlin/jvm/functions/Function2;Lkotlin/coroutines/jvm/internal/ContinuationImpl;)Ljava/lang/Object;',
             7,
             '    new-instance v0, Lkntr/app/ad/biz/videodetail/pausedpage/a$b;\n'
             '    const/4 v1, 0x0\n'
             '    sget-object v2, Lkntr/app/ad/base/protocol/biz/vd/pausedpage/IAdPausedPageRequestResult$ResultType;->NO_AD:Lkntr/app/ad/base/protocol/biz/vd/pausedpage/IAdPausedPageRequestResult$ResultType;\n'
             '    const/4 v3, 0x0\n    const/4 v4, 0x0\n    const/4 v5, 0x0\n    const/4 v6, 0x0\n'
             '    invoke-direct/range {v0 .. v6}, Lkntr/app/ad/biz/videodetail/pausedpage/a$b;-><init>(Lkntr/app/ad/biz/videodetail/pausedpage/AdPausedPageData;Lkntr/app/ad/base/protocol/biz/vd/pausedpage/IAdPausedPageRequestResult$ResultType;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V\n'
             '    return-object v0'),
        ]))
    result.append(patch_class(
        'smali_classes32/com/bapis/bilibili/app/viewunite/v1/ViewReply.smali',
        'Lcom/bapis/bilibili/app/viewunite/v1/ViewReply;',
        'f5f36cb6786235455cf940f8aee6902ce15ae0e5a84b04335e81c58841e8ee7a',
        [
            ('getCm()Lcom/bapis/bilibili/app/viewunite/v1/CM;', 1,
             '    invoke-static {}, Lcom/bapis/bilibili/app/viewunite/v1/CM;->getDefaultInstance()Lcom/bapis/bilibili/app/viewunite/v1/CM;\n'
             '    move-result-object v0\n    return-object v0'),
            ('hasCm()Z', 1, '    const/4 v0, 0x0\n    return v0'),
        ]))
    result.append(patch_class(
        'smali_classes32/com/bapis/bilibili/app/viewunite/v1/KViewReply.smali',
        'Lcom/bapis/bilibili/app/viewunite/v1/KViewReply;',
        '608c1c4b0760fbb26a5cb481ad86c90f66fdb450510abf900eb3e6776cc9ce2a',
        [('getCm()Lcom/bapis/bilibili/app/viewunite/v1/KCM;', 1,
          '    const/4 v0, 0x0\n    return-object v0')]))
    (ROOT / 'analysis' / 'video_patch_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
