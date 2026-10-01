"""User-triggered GitHub release updates. Credentials never leave GitHub's API."""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
import paths
from version import APP_VERSION

REPO = 'Ijtihed/flow-local'
API = f'https://api.github.com/repos/{REPO}'
RELEASES = f'https://github.com/{REPO}/releases/latest'
PUBLISH = f'https://github.com/{REPO}/actions/workflows/release.yml'
MAX_BYTES = 600 * 1024 * 1024


class UpdateError(RuntimeError):
    pass


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise UpdateError('This release has an unsupported version number.')
    return tuple(map(int, value.lstrip('v').split('.')))


def token():
    """Explicit saved access, or the user's existing GitHub CLI sign-in."""
    file = paths.DATA / 'update-key'
    if file.exists():
        data = file.read_bytes()
        if os.name == 'nt':
            from speech_api import _dpapi
            data = _dpapi(data, decrypt=True)
        return data.decode()
    if shutil.which('gh'):
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        try:
            result = subprocess.run(['gh', 'auth', 'token', '--hostname', 'github.com'],
                                    capture_output=True, text=True, timeout=5, **options)
            return result.stdout.strip() if result.returncode == 0 else ''
        except (OSError, subprocess.TimeoutExpired):
            pass
    return ''


def save_token(value):
    value = str(value).strip()
    if not value or len(value) > 8192 or any(c.isspace() for c in value):
        raise ValueError('Enter a GitHub access token without spaces.')
    paths.DATA.mkdir(parents=True, exist_ok=True)
    data = value.encode()
    if os.name == 'nt':
        from speech_api import _dpapi
        data = _dpapi(data)
    target = paths.DATA / 'update-key'
    tmp = target.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
    if os.name != 'nt':
        tmp.chmod(0o600)
    tmp.replace(target)


def headers(access, binary=False):
    result = {'Accept': 'application/octet-stream' if binary else 'application/vnd.github+json',
              'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': f'Flow/{APP_VERSION}'}
    if access:
        result['Authorization'] = 'Bearer ' + access
    return result


def status_error(response):
    if response.status_code in (401, 404):
        raise UpdateError('This private release needs GitHub access. Connect an account with access to Flow.')
    if response.status_code == 403:
        raise UpdateError('GitHub denied access or its request limit was reached. Check access and try again later.')
    if response.status_code != 200:
        raise UpdateError(f'GitHub returned HTTP {response.status_code}. Try again later.')


def latest(access):
    with requests.get(API + '/releases/latest', headers=headers(access), timeout=(10, 30), allow_redirects=False) as response:
        status_error(response)
        release = response.json()
    if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
        raise UpdateError('No stable update is available yet.')
    release_version = version(release.get('tag_name'))
    if release_version <= version(APP_VERSION):
        return None
    name = 'FlowSetup.exe' if sys.platform == 'win32' else 'Flow-x86_64.AppImage'
    asset = next((a for a in release.get('assets', []) if a.get('name') == name), None)
    if not asset or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or ''):
        raise UpdateError('The release is still being prepared. Try again when its verified download is ready.')
    if (type(asset.get('id')) is not int or asset['id'] <= 0 or type(asset.get('size')) is not int
            or not 0 < asset['size'] <= MAX_BYTES or asset.get('state') != 'uploaded'):
        raise UpdateError('The release download is incomplete.')
    return {'version': '.'.join(map(str, release_version)), 'id': asset['id'], 'name': name,
            'size': asset['size'], 'sha256': asset['digest'][7:]}


def publisher(access):
    if not access:
        return False
    try:
        with requests.get(API, headers=headers(access), timeout=(5, 10), allow_redirects=False) as response:
            return response.status_code == 200 and response.json().get('permissions', {}).get('push') is True
    except (requests.RequestException, ValueError):
        return False


def download(asset, access, progress):
    folder = paths.DATA / 'updates' / asset['version']
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / asset['name']
    temporary = target.with_suffix('.partial')
    if target.is_file() and target.stat().st_size == asset['size']:
        cached = hashlib.sha256()
        with target.open('rb') as stream:
            for chunk in iter(lambda: stream.read(256 * 1024), b''):
                cached.update(chunk)
        if cached.hexdigest() == asset['sha256']:
            progress(asset['size'], asset['size'])
            return target
    digest, received = hashlib.sha256(), 0
    try:
        response = requests.get(API + f"/releases/assets/{asset['id']}", headers=headers(access, True),
                                stream=True, timeout=(10, 60), allow_redirects=False)
        with response:
            if response.status_code == 302:
                location = response.headers.get('Location', '')
                parsed = urlsplit(location)
                if (parsed.scheme != 'https' or parsed.hostname not in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com')
                        or parsed.username or parsed.password or parsed.port not in (None, 443)):
                    raise UpdateError('GitHub returned an unexpected download address.')
                # Never forward the GitHub token to signed asset-storage URLs.
                response = requests.get(location, stream=True, timeout=(10, 60), allow_redirects=False)
                with response:
                    status_error(response)
                    received = _write(response, temporary, digest, asset['size'], progress)
            else:
                status_error(response)
                received = _write(response, temporary, digest, asset['size'], progress)
        if received != asset['size'] or digest.hexdigest() != asset['sha256']:
            raise UpdateError('The update failed its integrity check. Your installed app has not changed.')
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def _write(response, temporary, digest, expected, progress):
    received = 0
    with temporary.open('wb') as stream:
        for chunk in response.iter_content(256 * 1024):
            received += len(chunk)
            if received > expected:
                raise UpdateError('The update download was larger than expected.')
            stream.write(chunk)
            digest.update(chunk)
            progress(received, expected)
    return received


def windows_script(installer, executable, startup, expected=''):
    # Literal PowerShell paths; no command construction from release notes/tags.
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    task = '/TASKS=startup' if startup else '/TASKS='
    return f'''$ErrorActionPreference = 'Stop'
$flowExe = {quote(executable)}
$flowRoot = [IO.Path]::GetFullPath([IO.Path]::GetDirectoryName($flowExe))
try {{
$flowDeadline = [DateTime]::UtcNow.AddSeconds(60)
do {{
  $flowRunning = @(Get-CimInstance Win32_Process -Filter "Name='Flow.exe'" | Where-Object {{ $_.ExecutablePath -eq $flowExe }})
  if ($flowRunning.Count -eq 0) {{ break }}
  Start-Sleep -Milliseconds 250
}} while ([DateTime]::UtcNow -lt $flowDeadline)
if ($flowRunning.Count -gt 0) {{ throw 'Flow did not close. Reopen Flow and try the update again.' }}
$flowSetup = Start-Process -FilePath {quote(installer)} -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',{quote(task)},('/DIR="' + $flowRoot + '"') -WindowStyle Hidden -Wait -PassThru
if ($flowSetup.ExitCode -ne 0) {{ Start-Process -FilePath $flowExe -WindowStyle Hidden; throw 'The installer did not complete.' }}
if ({quote(expected)} -ne '' -and (Get-Item -LiteralPath $flowExe).VersionInfo.ProductVersion -ne {quote(expected)}) {{ throw 'The installed version did not match the update.' }}
}} catch {{
  @{{phase='error';message='The installer could not finish. Check for updates and try again.'}} | ConvertTo-Json | Set-Content -LiteralPath {quote(installer.parent.parent / 'install-result.json')} -Encoding utf8
  if (Test-Path -LiteralPath $flowExe) {{ Start-Process -FilePath $flowExe -ArgumentList '--window' -WindowStyle Hidden }}
  exit 1
}}
@{{phase='current';version={quote(expected)};message='Flow was updated successfully.'}} | ConvertTo-Json | Set-Content -LiteralPath {quote(installer.parent.parent / 'install-result.json')} -Encoding utf8
Start-Process -FilePath $flowExe -WindowStyle Hidden
Start-Process -FilePath $flowExe -ArgumentList '--window' -WindowStyle Hidden
'''


def linux_replace(downloaded, target):
    """Replace a writable AppImage atomically; keep the old image for rollback."""
    target = Path(target)
    if target.suffix != '.AppImage' or not target.is_file() or target.is_symlink():
        raise UpdateError('Run Flow from a writable AppImage to install updates.')
    temporary = target.with_name(target.name + '.update')
    backup = target.with_name(target.name + '.previous')
    try:
        shutil.copyfile(downloaded, temporary)
        temporary.chmod(target.stat().st_mode | 0o100)
        shutil.copy2(target, backup)
        os.replace(temporary, target)
    except OSError:
        raise UpdateError('This AppImage location is not writable. Move it to your home folder and try again.') from None
    finally:
        temporary.unlink(missing_ok=True)


def install(downloaded):
    if sys.platform == 'win32':
        if not paths.FROZEN:
            raise UpdateError('Run the installed Flow app to install an update.')
        from system import startup_enabled
        script = downloaded.parent / 'install.ps1'
        script.write_text(windows_script(downloaded, Path(sys.executable).resolve(), startup_enabled(), downloaded.parent.name), 'utf-8-sig')
        launch_windows(script)
    else:
        target = os.environ.get('APPIMAGE')
        if not target:
            raise UpdateError('Run the AppImage to install an update. Source installs update through git.')
        linux_replace(downloaded, target)
        # The old process must release the single-instance lock before restart.
        subprocess.Popen(['/bin/sh', '-c', 'while kill -0 "$1" 2>/dev/null; do sleep 0.2; done; "$2" & "$2" --window',
                          'Flow update', str(os.getpid()), target], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch_windows(script):
    # DETACHED_PROCESS makes Windows PowerShell exit successfully without
    # running its script. A hidden process with valid handles runs reliably.
    return subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-WindowStyle', 'Hidden', '-File', str(script)],
                            creationflags=subprocess.CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Manager:
    def __init__(self):
        self.lock = threading.Lock()
        self.asset = None
        self.state = {'phase': 'idle', 'current': APP_VERSION, 'publisher': False}
        try:
            import json
            report = json.loads((paths.DATA / 'updates/install-result.json').read_text('utf-8-sig'))
            if report.get('phase') == 'error':
                self.state.update(phase='error', message='The installer could not finish. Check for updates and try again.')
            elif report.get('phase') == 'current' and report.get('version') == APP_VERSION:
                self.state.update(phase='current', message='Flow was updated successfully.')
        except (OSError, ValueError, AttributeError):
            pass

    def status(self):
        with self.lock:
            return dict(self.state)

    def _set(self, **values):
        with self.lock:
            self.state.update(values)

    def _start(self, phase, work):
        with self.lock:
            if self.state['phase'] in ('checking', 'downloading', 'installing'):
                return False
            self.state.update(phase=phase, message='', progress=0)
            if phase == 'checking':
                self.state['check_id'] = self.state.get('check_id', 0) + 1
        def worker():
            try:
                work()
            except UpdateError as error:
                self._set(phase='error', message=str(error))
            except requests.RequestException:
                self._set(phase='error', message='Could not reach GitHub. Check your connection and try again.')
            except Exception:
                self._set(phase='error', message='The update could not complete. Your saved data is unchanged. Try again.')
        threading.Thread(target=worker, daemon=True).start()
        return True

    def check(self):
        def work():
            access = token()
            self.asset = latest(access)
            self._set(phase='available' if self.asset else 'current',
                      latest=self.asset['version'] if self.asset else APP_VERSION, publisher=publisher(access))
        return self._start('checking', work)

    def apply(self, on_install, can_install=None):
        import control
        runtime = control.state()
        if runtime.get('recording') or runtime.get('busy'):
            message = 'Finish your current dictation before updating Flow.'
            self._set(message=message)
            raise UpdateError(message)
        if not self.asset or self.status()['phase'] != 'available':
            raise UpdateError('Check for an available update first.')
        def work():
            file = download(self.asset, token(), lambda done, total: self._set(progress=round(done / total * 100)))
            runtime = control.state()
            if runtime.get('recording') or runtime.get('busy'):
                self._set(phase='available', message='Download ready. Finish your dictation, then click Update again.')
                return
            if can_install is not None and not can_install():
                self._set(phase='available', message='Download ready. Flow will update when you finish using it.')
                return
            self._set(phase='installing', progress=100)
            install(file)
            on_install()
        return self._start('downloading', work)


class Automatic:
    """One scheduler in the tray process; windows share its status and commands."""
    def __init__(self, manager, on_install, reserve):
        self.manager, self.on_install, self.reserve = manager, on_install, reserve
        self.next_check = time.monotonic()
        self.idle_since = time.monotonic()
        self.previous = 'idle'

    def tick(self, enabled, idle, now=None):
        now = time.monotonic() if now is None else now
        if not idle:
            self.idle_since = now
        phase = self.manager.status()['phase']
        if phase != self.previous:
            if phase == 'error':
                self.next_check = now + 15 * 60
            elif phase in ('available', 'current') and self.previous == 'checking':
                self.next_check = now + 6 * 60 * 60
            self.previous = phase
        if not enabled:
            self.idle_since = now
        if enabled and phase == 'available' and idle and now - self.idle_since >= 60:
            self.manager.apply(self.on_install, can_install=lambda: self.reserve(True))
        elif phase not in ('checking', 'downloading', 'installing', 'available') and now >= self.next_check:
            self.next_check = now + 6 * 60 * 60
            self.manager.check()


class Remote:
    """Keep manual and automatic requests on the same tray-owned updater."""
    def status(self):
        import control
        return control.state().get('updates', {'phase': 'idle', 'current': APP_VERSION, 'publisher': False})

    def check(self):
        import control
        control.send('update_check')
        return True

    def apply(self, on_install):
        import control
        runtime = control.state()
        if runtime.get('recording') or runtime.get('busy'):
            raise UpdateError('Finish your current dictation before updating Flow.')
        if self.status().get('phase') != 'available':
            raise UpdateError('Check for an available update first.')
        control.send('update_install')
        return True
