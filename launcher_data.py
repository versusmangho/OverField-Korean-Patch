"""GitHub patch downloads and per-user storage, independent of the GUI."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request
import zlib

PAYLOAD_FILENAME = 'patch_payload.dat'


def user_data_dir():
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
    return Path(base) / 'OverFieldKoreanPatch'


def config_path():
    return user_data_dir() / 'launcher_config.json'


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.overfield-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_bundle(data):
    if not data.startswith(b'UnityFS\x00'):
        raise ValueError('유효한 UnityFS 패치 번들이 아닙니다.')
    return data


def cache_dir(repo):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('GitHub 저장소는 소유자/저장소 형식으로 입력해주세요.')
    return user_data_dir() / 'patches' / hashlib.sha256(repo.lower().encode()).hexdigest()[:20]


def load_cache(repo):
    directory = cache_dir(repo)
    manifest = directory / 'current.json'
    if not manifest.exists():
        return None, None
    metadata = json.loads(manifest.read_text(encoding='utf-8'))
    digest = metadata['sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('캐시 해시가 올바르지 않습니다.')
    compressed = (directory / f'{digest}.dat').read_bytes()
    if hashlib.sha256(compressed).hexdigest() != digest:
        raise ValueError('다운로드 캐시의 무결성 검사에 실패했습니다.')
    return validate_bundle(zlib.decompress(compressed)), metadata


def store_cache(repo, compressed, tag, published_at):
    bundle = validate_bundle(zlib.decompress(compressed))
    digest = hashlib.sha256(compressed).hexdigest()
    directory = cache_dir(repo)
    metadata = {'tag': tag, 'published_at': published_at, 'sha256': digest}
    # Publish the pointer last; an interrupted download cannot replace a valid cache.
    atomic_write(directory / f'{digest}.dat', compressed)
    atomic_write(directory / 'current.json', json.dumps(metadata).encode('utf-8'))
    return bundle, metadata


def obtain_patch(repo, check_updates=True, force=False, log=lambda message: None,
                 progress=lambda percent: None, opener=None):
    opener = opener or urllib.request.urlopen
    cached = metadata = None
    try:
        cached, metadata = load_cache(repo)
    except (OSError, ValueError, KeyError, zlib.error) as error:
        log(f'⚠️ 저장된 패치 캐시를 사용할 수 없습니다: {error}')
    if cached is not None and not check_updates and not force:
        log(f'📦 GitHub에서 받은 캐시 사용: {metadata["tag"]}')
        return cached, metadata['tag']
    try:
        request = urllib.request.Request(
            f'https://api.github.com/repos/{repo}/releases/latest',
            headers={'User-Agent': 'OverFieldLauncher'})
        with opener(request, timeout=10) as response:
            release = json.loads(response.read().decode('utf-8'))
        tag = release['tag_name']
        published = release.get('published_at') or ''
        asset = next((a for a in release.get('assets', [])
                      if a.get('name') == PAYLOAD_FILENAME), None)
        if asset is None:
            raise ValueError('최신 GitHub 릴리스에 patch_payload.dat가 없습니다.')
        if cached is not None:
            if published and metadata.get('published_at') and published < metadata['published_at']:
                log('ℹ️ GitHub 게시본이 저장된 버전보다 오래되어 기존 캐시를 유지합니다.')
                return cached, metadata['tag']
            digest = asset.get('digest')
            same_asset = not digest or digest == 'sha256:' + metadata['sha256']
            if not force and tag == metadata['tag'] and same_asset:
                log(f'ℹ️ GitHub 최신 게시본과 캐시가 일치합니다: {tag}')
                return cached, tag
        url = asset['browser_download_url']
        if not url.startswith('https://'):
            raise ValueError('GitHub 다운로드 URL이 HTTPS가 아닙니다.')
        log(f'⬇️ GitHub 게시본 다운로드: {tag}')
        with opener(urllib.request.Request(url, headers={'User-Agent': 'OverFieldLauncher'}), timeout=30) as response:
            total = int(response.headers.get('Content-Length', asset.get('size', 0)))
            chunks, received = [], 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
                progress(min(70, 20 + int(received / max(total, 1) * 50)))
        compressed = b''.join(chunks)
        if asset.get('size') and len(compressed) != asset['size']:
            raise ValueError('GitHub 패치 다운로드가 중간에 끊겼습니다.')
        if asset.get('digest') and asset['digest'] != 'sha256:' + hashlib.sha256(compressed).hexdigest():
            raise ValueError('GitHub 패치의 SHA-256이 일치하지 않습니다.')
        bundle, metadata = store_cache(repo, compressed, tag, published)
        return bundle, metadata['tag']
    except Exception as error:
        if cached is not None:
            log(f'ℹ️ GitHub 확인 실패. 마지막 다운로드 캐시({metadata["tag"]}) 사용: {error}')
            return cached, metadata['tag']
        raise RuntimeError(f'최초 실행에는 GitHub 패치 다운로드가 필요합니다: {error}') from error
