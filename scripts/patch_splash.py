"""Disable legacy and KMP business splash orders; preserve KMP lifecycle events.

Version-specific, fail-closed, idempotent smali patch. No activities, startup
initializers, classes, resources, or methods are removed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
METHOD = re.compile(r"(?ms)^\.method [^\n]*\n.*?^\.end method")


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def null_getter(original):
    # Retain signature and nullability; allocate one register for the null value.
    header = original.splitlines()[0]
    return (header + "\n    .locals 1\n"
            "    .annotation build Lorg/jetbrains/annotations/Nullable;\n"
            "    .end annotation\n\n"
            "    # AD_PATCH_SPLASH: normal no-order result\n"
            "    const/4 v0, 0x0\n    return-object v0\n.end method")


def keep_lifecycle(original):
    needle = "    :goto_5\n    if-nez v3, :cond_c"
    assert original.count(needle) == 1, "KMP selection merge point changed"
    # v3 is the nullable selected SplashOrder. Null it before no-order reporting
    # and the existing do1.a.h / do1.a.f state events; both events remain intact.
    patched = original.replace(needle,
        "    :goto_5\n"
        "    # AD_PATCH_SPLASH: choose no business splash, retain state cleanup\n"
        "    const/4 v3, 0x0\n\n"
        "    if-nez v3, :cond_c")
    assert patched.count("Lkntr/srcs/app/splash/core/vm/BusinessSplashViewModel;->d(Lao1/a;)V") == 2
    return patched


def false_popup_gate(original):
    return (original.splitlines()[0] + "\n    .locals 1\n\n"
            "    # AD_PATCH_SPLASH: decline promotional home popup\n"
            "    const/4 v0, 0x0\n    return v0\n.end method")


PATCHES = [
    ("smali_classes28/tv/danmaku/bili/ui/main/opdialog/OpBizDialogHelper.smali",
     "a(Ltv/danmaku/bili/MainActivityV2;Ltv/danmaku/bili/ui/main/opdialog/OpBizDialogHelper$OpDialogInfo;)Z",
     "235998f6ef9c946371e0fd50085d7fa000088cf29c40c612c884d83a1c251c68", false_popup_gate,
     "Decline the /x/resource/pop/up promotional home popup before image fetch and dialog queue registration."),
    ("smali_classes27/tv/danmaku/bili/splash/ad/core/SplashOrderSelectComponentKt.smali",
     "b(Ltv/danmaku/bili/splash/ad/model/SplashListResponse;Ljava/util/List;Ltv/danmaku/bili/splash/ad/model/SplashSource;Ljava/lang/String;ZLtv/danmaku/bili/splash/ad/core/SelectMode;)Ltv/danmaku/bili/splash/ad/model/SplashOrder;",
     "9bf812b14da58a45f400ef821ace54fa163bc9fd4cf53fb2883ec4062f016229", null_getter,
     "Legacy real-time/local strategy selection returns no order, covering direct real-time cache reads."),
    ("smali_classes27/tv/danmaku/bili/splash/ad/core/SplashManager.smali",
     "b(ZLtv/danmaku/bili/splash/ad/model/SplashSource;)Ltv/danmaku/bili/splash/ad/model/SplashOrder;",
     "2e087e4b2193b9099eee6c73284e44814b3d5504e130a43a668694fe9bd3f145", null_getter,
     "Legacy cold, hot and deep-link business splash selection returns no order."),
    ("smali_classes26/kntr/srcs/app/splash/core/vm/BusinessSplashViewModel.smali",
     "a(Lkntr/srcs/app/splash/model/SplashSource;)Lfo1/q;",
     "83573c6271d24108fdb05c63f46148c6e30d85cdc4e455ac0fc0618f98e0b099", keep_lifecycle,
     "KMP splash returns no order and dispatches its existing selection/cleanup state events."),
    ("smali_classes26/kntr/srcs/app/splash/core/vm/BusinessSplashViewModel.smali",
     "c()Lfo1/q;",
     "464ba82cf55ca6aac20bd2041e8223bd7871c2d9be87bd6425820919aab12e2d", null_getter,
     "KMP hot splash preparation returns no cached or live order."),
]

PATCHED_HASHES = {
    "235998f6ef9c946371e0fd50085d7fa000088cf29c40c612c884d83a1c251c68": "5251e9155c0c9802a516892b9dd91ae04b832aea7d720a42c6440b28910b05c8",
    "9bf812b14da58a45f400ef821ace54fa163bc9fd4cf53fb2883ec4062f016229": "09c14541dd946eda2b71bff7251ea7422039331f82fe64acaf5e3d3f75c77463",
    "2e087e4b2193b9099eee6c73284e44814b3d5504e130a43a668694fe9bd3f145": "4e2a92280f83d14db312c18c52047e6e57b8ad6213d5e94d7c24e93de8f44316",
    "83573c6271d24108fdb05c63f46148c6e30d85cdc4e455ac0fc0618f98e0b099": "10db460bc5fe46ec9759cc42ba5c8bf3b4e0ad687864c756438e1cbe5c506df0",
    "464ba82cf55ca6aac20bd2041e8223bd7871c2d9be87bd6425820919aab12e2d": "ff56d890a3e0d4a3a1fda578dab2a1ea8a5a63ed47eb87ec39263a834196adfb",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("decoded", nargs="?", type=Path, default=ROOT / "work/decoded")
    args = parser.parse_args()
    report = []
    pending = {}
    for rel, sig, expected, transform, reason in PATCHES:
        path = args.decoded / rel
        text = pending.get(path, path.read_text(encoding="utf-8"))
        matches = [m for m in METHOD.finditer(text)
                   if m.group(0).splitlines()[0].endswith(" " + sig)]
        assert len(matches) == 1, f"Expected one method: {rel}: {sig}"
        match = matches[0]
        original = match.group(0)
        if "# AD_PATCH_SPLASH:" in original:
            assert digest(original) == PATCHED_HASHES[expected], f"Patched method hash mismatch: {rel}: {sig}"
            status = "already_patched"
            patched = original
        else:
            assert digest(original) == expected, f"Original method hash mismatch: {rel}: {sig}"
            patched = transform(original)
            assert digest(patched) == PATCHED_HASHES[expected], f"Unexpected transform result: {rel}: {sig}"
            text = text[:match.start()] + patched + text[match.end():]
            pending[path] = text
            status = "patched"
        report.append(dict(file=rel, method=sig, original_sha256=expected,
                           patched_sha256=digest(patched), status=status, reason=reason))
    # Validate every target before writing anything.
    for path, text in pending.items():
        path.write_text(text, encoding="utf-8", newline="\n")
    out = ROOT / "analysis/splash_patch_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
