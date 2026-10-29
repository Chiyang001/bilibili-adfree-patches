"""Non-destructive smoke test of the installed, already-authorized test build.

Does not install/uninstall, log in, purchase, post, like, follow, or collect
credentials. Uses one public video and only playback/navigation controls.
"""
from pathlib import Path
import argparse
import datetime
import json
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'tv.danmaku.bili'
VIDEO = 'bilibili://video/BV1GJ411x7h7'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser()
    p.add_argument('--serial', required=True)
    args = p.parse_args()
    output = ROOT / 'work/runtime/final'
    output.mkdir(parents=True, exist_ok=True)

    def adb(*command, timeout=45):
        r = subprocess.run(['adb', '-s', args.serial, *command], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout, check=True)
        return r.stdout

    def text(*command):
        return adb(*command).decode('utf-8', 'replace')

    def shot(name):
        focus = text('shell', 'dumpsys', 'window')
        current = [line for line in focus.splitlines() if 'mCurrentFocus=' in line]
        assert current and PACKAGE + '/' in current[0], 'Bilibili is not foreground'
        png = adb('exec-out', 'screencap', '-p')
        assert png.startswith(b'\x89PNG')
        (output / (name + '.png')).write_bytes(png)

    def state():
        s = text('shell', 'dumpsys', 'media_session')
        sessions = re.split(r'(?m)^\s*package=', s)[1:]
        sessions = [block for block in sessions if block.splitlines()[0].strip() == PACKAGE]
        for block in sessions:
            if not re.search(r'(?m)^\s*active=true\s*$', block):
                continue
            m = re.search(r'state=PlaybackState \{state=([A-Z_]+)\((\d+)\), position=(\d+)', block)
            metadata = re.search(r'(?m)^\s*metadata:.*description=(.*)$', block)
            if m and metadata and 'never gonna give you up' in metadata.group(1).lower():
                return dict(state=m.group(1), code=int(m.group(2)), position_ms=int(m.group(3)),
                            metadata=metadata.group(1))
        raise AssertionError('No active Bilibili session for the selected test video')

    report = {'started_at': datetime.datetime.now().astimezone().isoformat(),
              'status': 'running', 'serial': args.serial, 'package': PACKAGE, 'tests': {}}
    def save(stage):
        report['stage'] = stage
        (ROOT / 'analysis/runtime_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    save('device_check')
    report.update(android=text('shell', 'getprop', 'ro.build.version.release').strip(),
                  model=text('shell', 'getprop', 'ro.product.model').strip(),
                  abi=text('shell', 'getprop', 'ro.product.cpu.abilist').strip())
    power = text('shell', 'dumpsys', 'power')
    policy = text('shell', 'dumpsys', 'window', 'policy')
    awake = bool(re.search(r'mWakefulness=Awake\b', power))
    keyguard = bool(re.search(r'(?m)^\s*showing=true\s*$', policy))
    report['device_preflight'] = {'awake': awake, 'keyguard_showing': keyguard}
    save('device_preflight')
    if not awake or keyguard:
        raise RuntimeError('Device is asleep or locked; manual unlock is required before UI testing')
    built = json.loads((ROOT / 'analysis/build_report.json').read_text(encoding='utf-8'))
    path = text('shell', 'pm', 'path', PACKAGE).strip().removeprefix('package:')
    installed_hash = text('shell', 'sha256sum', path).split()[0]
    assert installed_hash == built['output_sha256'], 'Installed APK is not the final artifact'
    report['tested_apk_sha256'] = installed_hash
    uid = re.search(r'uid:(\d+)', text('shell', 'pm', 'list', 'packages', '-U', PACKAGE)).group(1)
    since = text('shell', 'date', '+%s').strip() + '.000'
    report['logcat_since_epoch'] = since
    save('cold_start')
    adb('shell', 'am', 'force-stop', PACKAGE)
    launch = text('shell', 'am', 'start', '-W', '-n', PACKAGE + '/.MainActivityV2')
    assert 'Status: ok' in launch
    report['tests']['cold_start'] = {'passed': True, 'am_start': launch.strip()}
    time.sleep(4)
    shot('01-home')
    save('video_playback')
    video_launch = text('shell', 'am', 'start', '-W', '-a', 'android.intent.action.VIEW', '-d', VIDEO, '-p', PACKAGE)
    assert 'Status: ok' in video_launch and 'UnitedBizDetailsActivity' in video_launch
    time.sleep(4)
    playing = state()
    assert playing['code'] == 3, playing
    shot('02-playing')
    report['tests']['video_playback'] = {'passed': True, 'state': playing}
    save('pause_12_seconds')
    adb('shell', 'input', 'keyevent', '127')
    time.sleep(1)
    paused = state()
    assert paused['code'] == 2, paused
    time.sleep(12)
    still = state()
    assert still['code'] == 2 and abs(still['position_ms'] - paused['position_ms']) < 500, still
    shot('03-paused-12-seconds')
    report['tests']['pause_12_seconds'] = {'passed': True, 'initial': paused, 'after_12_seconds': still}
    save('resume')
    adb('shell', 'input', 'keyevent', '126')
    time.sleep(3)
    resumed = state()
    assert resumed['code'] == 3, resumed
    shot('04-resumed')
    report['tests']['resume'] = {'passed': True, 'state': resumed}
    save('search_open')
    adb('shell', 'input', 'keyevent', '127')
    search = text('shell', 'am', 'start', '-W', '-a', 'android.intent.action.VIEW',
                  '-d', 'bilibili://search?keyword=bilibili', '-p', PACKAGE)
    assert 'BiliMainSearchActivity' in search
    time.sleep(4)
    shot('05-search')
    report['tests']['search_open'] = {'passed': True, 'am_start': search.strip()}
    save('background_return')
    adb('shell', 'input', 'keyevent', '3')
    time.sleep(3)
    warm = text('shell', 'am', 'start', '-W', '-n', PACKAGE + '/.MainActivityV2')
    assert 'Status: ok' in warm
    time.sleep(3)
    shot('06-background-return')
    report['tests']['background_return'] = {'passed': True, 'am_start': warm.strip()}
    save('fatal_log_scan')
    log = text('logcat', '-d', '--uid=' + uid, '-v', 'epoch', '-T', since)
    fatal = [line for line in log.splitlines() if re.search(
        r'FATAL EXCEPTION|Fatal signal', line)]
    suspicious = [line for line in log.splitlines() if re.search(
        r'VerifyError|NoSuchMethodError|IllegalAccessError|ExceptionInInitializerError|UnsatisfiedLinkError', line)]
    (output / 'fatal-log-lines.txt').write_text('\n'.join(fatal), encoding='utf-8')
    (output / 'suspicious-log-lines.txt').write_text('\n'.join(suspicious), encoding='utf-8')
    report['tests']['fatal_log_scan'] = {'passed': not fatal, 'matching_lines': len(fatal),
                                       'suspicious_lines_to_review': len(suspicious),
                                       'scope': 'Bilibili UID logcat since this test started'}
    assert not fatal, fatal
    exits = text('shell', 'dumpsys', 'activity', 'exit-info', PACKAGE)
    (output / 'process-exit-info.txt').write_text(exits, encoding='utf-8')
    report['limits'] = ['Visual advertisement absence requires screenshot review.',
                        'Not an exhaustive test of all accounts, pages, devices, or server ad variants.',
                        'Fullscreen, paid content, downloading, publishing, and external sharing are not verified by this script.']
    report['finished_at'] = datetime.datetime.now().astimezone().isoformat()
    report['status'] = 'automated_smoke_passed_visual_review_pending'
    save('visual_review_pending')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        target = ROOT / 'analysis/runtime_report.json'
        if target.exists():
            partial = json.loads(target.read_text(encoding='utf-8'))
            partial.update(status='requires_device_unlock' if 'manual unlock is required' in str(exc) else 'failed',
                           error=repr(exc), finished_at=datetime.datetime.now().astimezone().isoformat())
            target.write_text(json.dumps(partial, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        raise
