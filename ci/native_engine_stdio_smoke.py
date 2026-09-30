"""Exercise the actual native dispatcher without authorizing any output."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
engine = root / 'build' / 'native' / ('Release/stagemesh_engine.exe' if os.name == 'nt' else 'stagemesh_engine')
token = 'stagemesh-ci-stdio-dispatch-fixture'


def fields(line: str) -> dict[str, str]:
    values = {}
    for part in line.split()[1:]:
        if '=' in part:
            key, value = part.split('=', 1)
            values[key] = value
    return values


def require_prefix(line: str, prefix: str) -> None:
    if not line.startswith(prefix):
        raise RuntimeError(f'native stdio expected {prefix!r}, got {line!r}')


def valid_identity_token(value: str, *, midi: bool = False) -> bool:
    pattern = (
        r'backend=(?:windows-midi|coremidi);'
        if midi else r''
    ) + r'native=sha256:[0-9a-f]{64};persistent=sha256:[0-9a-f]{64};strength=(?:volatile|installation-snapshot|os-stable-endpoint);auto=[01]'
    return re.fullmatch(pattern, value or '') is not None


with tempfile.TemporaryDirectory(prefix='stagemesh-stdio-') as temporary:
    env = {k: v for k, v in os.environ.items() if not k.startswith('STAGEMESH_')}
    env.update(STAGEMESH_IPC_TOKEN=token, STAGEMESH_DATA_DIR=temporary)
    process = subprocess.Popen(
        [str(engine), '--stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1, env=env)

    def transact(command: str) -> str:
        if process.stdin is None or process.stdout is None:
            raise RuntimeError('native stdio pipes unavailable')
        process.stdin.write(command + '\n')
        process.stdin.flush()
        line = process.stdout.readline().strip()
        if not line:
            raise RuntimeError(f'native engine exited during {command!r}: code={process.poll()}')
        return line

    require_prefix(transact('PING'), 'ERR code=permission')
    require_prefix(transact('AUTH wrong'), 'ERR code=permission')
    require_prefix(transact('AUTH ' + token), 'OK authenticated=1')
    require_prefix(transact('HELLO'), 'OK engineVersion=')
    require_prefix(transact('PING'), 'OK pong=1')
    status_line = transact('STATUS')
    require_prefix(status_line, 'OK ')
    if 'lightingNetworkArmed=0' not in status_line:
        raise RuntimeError('native status did not confirm disarmed lighting')

    audio_scan = transact('AUDIO_SCAN')
    require_prefix(audio_scan, 'OK count=')
    audio_count = int(fields(audio_scan).get('count', '0'))
    audio_devices = []
    for index in range(max(0, min(audio_count, 64))):
        line = transact(f'AUDIO_DEVICE {index}')
        require_prefix(line, 'OK ')
        audio_devices.append(fields(line))

    midi_scan = transact('MIDI_SCAN')
    require_prefix(midi_scan, 'OK count=')
    midi_count = int(fields(midi_scan).get('count', '0'))
    midi_devices = []
    for index in range(max(0, min(midi_count, 32))):
        line = transact(f'MIDI_DEVICE {index}')
        require_prefix(line, 'OK ')
        midi_devices.append(fields(line))

    system = platform.system()
    target_audio = [item for item in audio_devices if item.get('backend') in {'wasapi', 'coreaudio'}]
    for item in target_audio:
        if not valid_identity_token(item.get('address', '')):
            raise RuntimeError(f'target audio endpoint leaked or malformed identity metadata: {item!r}')
    target_midi = [item for item in midi_devices if item.get('path', '').startswith('backend=')]
    for item in target_midi:
        if not valid_identity_token(item.get('path', ''), midi=True):
            raise RuntimeError(f'target MIDI endpoint leaked or malformed identity metadata: {item!r}')
    if system == 'Darwin' and not any(item.get('backend') == 'coreaudio' for item in target_audio):
        raise RuntimeError('hosted macOS full engine did not expose any CoreAudio endpoint through AUDIO_SCAN')
    if system == 'Windows' and any(item.get('backend') not in {'null', 'wasapi'} for item in audio_devices):
        raise RuntimeError(f'Windows full engine exposed unexpected audio backend: {audio_devices!r}')

    require_prefix(transact('NO_SUCH_COMMAND'), 'ERR code=unsupported')
    require_prefix(transact('QUIT'), 'OK bye=1')
    process.wait(timeout=20)
    stderr = process.stderr.read() if process.stderr else ''
    if process.returncode != 0:
        raise RuntimeError(f'native stdio contract failed: exit={process.returncode}, stderr={stderr[:1000]!r}')

report = {
    'documentType':'org.upp.native-engine-stdio-smoke', 'schemaVersion':2,
    'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
    'githubRunId':os.environ.get('GITHUB_RUN_ID'), 'hostOs':platform.system(),
    'binarySha256':hashlib.sha256(engine.read_bytes()).hexdigest(),
    'status':'passed', 'unauthenticatedRejected':True, 'wrongTokenRejected':True,
    'authenticatedCommands':True, 'unknownCommandRejected':True, 'quitCompleted':True,
    'audioDeviceCount':audio_count, 'targetOsAudioDeviceCount':len(target_audio),
    'midiInputDeviceCount':midi_count, 'targetOsMidiInputDeviceCount':len(target_midi),
    'targetOsIdentityTokensHashOnly':all(valid_identity_token(item.get('address','')) for item in target_audio)
        and all(valid_identity_token(item.get('path',''), midi=True) for item in target_midi),
    'physicalOutputsArmed':False, 'physicalHardwareQualified':False,
    'audioStreamingQualified':False, 'midiInputQualified':False,
}
Path('native-engine-smoke.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report, indent=2))
