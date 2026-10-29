"""Remove only explicit commercial cards from video recommendations.

The Java protobuf list/count/index/OrBuilder accessors use the same filtered
view. Ordinary videos, live rooms, and other unmarked recommendations retain
their original order. No account, player or entitlement methods are changed.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
DECODED = ROOT / 'work' / 'decoded'
BASE = Path('smali_classes32/com/bapis/bilibili/app/viewunite/common')
MARKER = '# chiyang001: exclude explicit commercial recommendation cards'
PROTO = 'Lcom/bapis/bilibili/app/viewunite/common/Relates;'
CARD = 'Lcom/bapis/bilibili/app/viewunite/common/RelateCard;'
HELPER = Path('smali_classes32/com/chiyang001/adfree/RelateFilter.smali')
PATCHED = {
    'Relates.smali': '0158e39dc1924f904255d8c34d900f16e14fc9e076eedce9858ed7b30e08067a',
    'KRelates.smali': 'b1bb96ad20f3fc999e171f8aacd43c760b7bdeb872f320f9d2600de5eec8cf35',
}

HELPER_SOURCE = '''.class public final Lcom/chiyang001/adfree/RelateFilter;
.super Ljava/lang/Object;

# CM is the official commercial-card enum (value 5). Payload checks also
# handle incomplete type metadata without treating ordinary AV cards as ads.
.method public static isCommercial(Ljava/lang/Object;)Z
    .locals 2
    instance-of v0, p0, Lcom/bapis/bilibili/app/viewunite/common/RelateCard;
    if-eqz v0, :kotlin_card
    check-cast p0, Lcom/bapis/bilibili/app/viewunite/common/RelateCard;
    invoke-virtual {p0}, Lcom/bapis/bilibili/app/viewunite/common/RelateCard;->hasCm()Z
    move-result v0
    if-nez v0, :commercial
    invoke-virtual {p0}, Lcom/bapis/bilibili/app/viewunite/common/RelateCard;->getRelateCardTypeValue()I
    move-result v0
    const/4 v1, 0x5
    if-eq v0, v1, :commercial
    goto :ordinary
    :kotlin_card
    instance-of v0, p0, Lcom/bapis/bilibili/app/viewunite/common/KRelateCard;
    if-eqz v0, :ordinary
    check-cast p0, Lcom/bapis/bilibili/app/viewunite/common/KRelateCard;
    invoke-virtual {p0}, Lcom/bapis/bilibili/app/viewunite/common/KRelateCard;->getCard()Lcom/bapis/bilibili/app/viewunite/common/KRelateCard$b;
    move-result-object v0
    instance-of v0, v0, Lcom/bapis/bilibili/app/viewunite/common/KRelateCard$h;
    if-nez v0, :commercial
    invoke-virtual {p0}, Lcom/bapis/bilibili/app/viewunite/common/KRelateCard;->getRelateCardType()Lcom/bapis/bilibili/app/viewunite/common/KRelateCardType;
    move-result-object v0
    if-eqz v0, :ordinary
    invoke-virtual {v0}, Lcom/bapis/bilibili/app/viewunite/common/KRelateCardType;->getValue()I
    move-result v0
    const/4 v1, 0x5
    if-eq v0, v1, :commercial
    :ordinary
    const/4 v0, 0x0
    return v0
    :commercial
    const/4 v0, 0x1
    return v0
.end method

.method public static filter(Ljava/util/List;)Ljava/util/List;
    .locals 4
    if-eqz p0, :original
    new-instance v0, Ljava/util/ArrayList;
    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V
    invoke-interface {p0}, Ljava/util/List;->iterator()Ljava/util/Iterator;
    move-result-object v1
    :next
    invoke-interface {v1}, Ljava/util/Iterator;->hasNext()Z
    move-result v2
    if-eqz v2, :complete
    invoke-interface {v1}, Ljava/util/Iterator;->next()Ljava/lang/Object;
    move-result-object v2
    invoke-static {v2}, Lcom/chiyang001/adfree/RelateFilter;->isCommercial(Ljava/lang/Object;)Z
    move-result v3
    if-nez v3, :next
    invoke-virtual {v0, v2}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z
    goto :next
    :complete
    invoke-virtual {v0}, Ljava/util/ArrayList;->size()I
    move-result v1
    invoke-interface {p0}, Ljava/util/List;->size()I
    move-result v2
    if-eq v1, v2, :original
    invoke-static {v0}, Ljava/util/Collections;->unmodifiableList(Ljava/util/List;)Ljava/util/List;
    move-result-object v0
    return-object v0
    :original
    return-object p0
.end method
'''


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def replace_methods(content, methods):
    for signature, code in methods:
        pattern = re.compile(r'(^\.method[^\n]* ' + re.escape(signature) + r'\n)(.*?)(^\.end method)', re.M | re.S)
        matches = list(pattern.finditer(content))
        assert len(matches) == 1, (signature, len(matches))
        m = matches[0]
        body = m.group(2)
        if MARKER in body:
            assert body.endswith('    ' + MARKER + '\n' + code + '\n'), signature
            continue
        assert '    .line 1\n' in body, signature
        prefix = body.split('    .line 1\n', 1)[0]
        # All replacements only use one local and preserve existing annotations.
        prefix = re.sub(r'    \.locals \d+\n', '    .locals 1\n', prefix, count=1)
        replacement = prefix + '    ' + MARKER + '\n' + code + '\n'
        content = content[:m.start()] + m.group(1) + replacement + m.group(3) + content[m.end():]
    return content


def main():
    specs = [
        (BASE / 'Relates.smali', PROTO,
         'e14f2172abf5b6cbe72d716093618e16f7403a949dac09deee1178c20f83b8fb', [
            ('getCardsList()Ljava/util/List;',
             f'    iget-object v0, p0, {PROTO}->cards_:Lcom/google/protobuf/Internal$ProtobufList;\n'
             '    invoke-static {v0}, Lcom/chiyang001/adfree/RelateFilter;->filter(Ljava/util/List;)Ljava/util/List;\n'
             '    move-result-object v0\n    return-object v0'),
            (f'getCards(I){CARD}',
             f'    invoke-virtual {{p0}}, {PROTO}->getCardsList()Ljava/util/List;\n'
             '    move-result-object v0\n    invoke-interface {v0, p1}, Ljava/util/List;->get(I)Ljava/lang/Object;\n'
             f'    move-result-object v0\n    check-cast v0, {CARD}\n    return-object v0'),
            ('getCardsCount()I',
             f'    invoke-virtual {{p0}}, {PROTO}->getCardsList()Ljava/util/List;\n'
             '    move-result-object v0\n    invoke-interface {v0}, Ljava/util/List;->size()I\n'
             '    move-result v0\n    return v0'),
            ('getCardsOrBuilder(I)Lcom/bapis/bilibili/app/viewunite/common/K1;',
             f'    invoke-virtual {{p0, p1}}, {PROTO}->getCards(I){CARD}\n'
             '    move-result-object v0\n    return-object v0'),
            ('getCardsOrBuilderList()Ljava/util/List;',
             f'    invoke-virtual {{p0}}, {PROTO}->getCardsList()Ljava/util/List;\n'
             '    move-result-object v0\n    return-object v0'),
         ]),
        (BASE / 'KRelates.smali', 'Lcom/bapis/bilibili/app/viewunite/common/KRelates;',
         '8d54cd214994f3577c0e0af2bf0ae0415afdbd75f1c0f9e1e91901350c333251', [
             ('getCards()Ljava/util/List;',
              '    iget-object v0, p0, Lcom/bapis/bilibili/app/viewunite/common/KRelates;->a:Ljava/util/List;\n'
              '    invoke-static {v0}, Lcom/chiyang001/adfree/RelateFilter;->filter(Ljava/util/List;)Ljava/util/List;\n'
              '    move-result-object v0\n    return-object v0'),
         ]),
    ]
    planned = []
    for relative, descriptor, original_sha, methods in specs:
        p = DECODED / relative
        raw = p.read_bytes()
        content = raw.decode('utf-8').replace('\r\n', '\n')
        assert re.search(r'^\.class[^\n]* ' + re.escape(descriptor) + r'$', content, re.M), relative
        assert hash_bytes(raw) in {original_sha, PATCHED[relative.name]}, (relative, 'Unexpected source hash')
        result = replace_methods(content, methods)
        assert hash_bytes(result.encode('utf-8')) == PATCHED[relative.name], (relative, 'Unexpected patched hash')
        planned.append((p, result, {'file': str(relative), 'class': descriptor,
                        'original_sha256': original_sha, 'patched_sha256': hash_bytes(result.encode('utf-8')),
                        'methods': [m[0] for m in methods]}))
    helper = DECODED / HELPER
    if helper.exists():
        assert helper.read_text(encoding='utf-8') == HELPER_SOURCE, 'Unexpected helper edits'
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(HELPER_SOURCE, encoding='utf-8', newline='\n')
    for p, result, _ in planned:
        p.write_text(result, encoding='utf-8', newline='\n')
    reports = [x[2] for x in planned]
    reports.append({'file': str(HELPER), 'class': 'Lcom/chiyang001/adfree/RelateFilter;',
                    'original_sha256': None, 'patched_sha256': hash_bytes(HELPER_SOURCE.encode('utf-8')),
                    'methods': ['isCommercial(Ljava/lang/Object;)Z', 'filter(Ljava/util/List;)Ljava/util/List;']})
    (ROOT / 'analysis' / 'video_relate_patch_report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
