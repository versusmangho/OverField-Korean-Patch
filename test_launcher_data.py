import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

import launcher_data as data


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.headers = {'Content-Length': str(len(payload))}


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.bundle = b'UnityFS\x00test translation bundle'
        self.payload = zlib.compress(self.bundle)
        self.repo = 'owner/patch'
        self.release = {
            'tag_name': 'v1.2.0', 'published_at': '2026-10-28T00:00:00Z',
            'assets': [{'name': 'patch_payload.dat', 'size': len(self.payload),
                        'digest': 'sha256:' + hashlib.sha256(self.payload).hexdigest(),
                        'browser_download_url': 'https://github.com/owner/patch/releases/download/v1.2.0/patch_payload.dat'}],
        }
        self.urls = []

    def opener(self, request, timeout):
        self.urls.append(request.full_url)
        return Response(json.dumps(self.release).encode() if 'api.github.com' in request.full_url else self.payload)

    def download(self, **kwargs):
        return data.obtain_patch(self.repo, opener=self.opener, **kwargs)

    def seed(self):
        return data.store_cache(self.repo, self.payload, 'v1.2.0', '2026-10-28T00:00:00Z')

    def test_first_download_even_with_auto_updates_off(self):
        self.assertEqual(self.download(check_updates=False), (self.bundle, 'v1.2.0'))
        self.assertEqual(len(self.urls), 2)
        self.assertEqual(data.load_cache(self.repo)[0], self.bundle)

    def test_disabled_updates_use_valid_cache_without_network(self):
        self.seed()
        self.assertEqual(self.download(check_updates=False)[0], self.bundle)
        self.assertFalse(self.urls)

    def test_same_release_checks_metadata_only(self):
        self.seed()
        self.assertEqual(self.download()[0], self.bundle)
        self.assertEqual(len(self.urls), 1)

    def test_replaced_asset_with_same_tag_is_detected(self):
        self.seed()
        self.payload = zlib.compress(b'UnityFS\x00replacement')
        self.release['assets'][0].update(size=len(self.payload), digest='sha256:' + hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(self.download()[0], b'UnityFS\x00replacement')
        self.assertEqual(len(self.urls), 2)

    def test_corrupt_cache_is_redownloaded(self):
        self.seed()
        file = next(data.cache_dir(self.repo).glob('*.dat'))
        file.write_bytes(b'corrupt')
        self.assertEqual(self.download()[0], self.bundle)
        self.assertEqual(len(self.urls), 2)

    def test_offline_falls_back_to_verified_cache(self):
        self.seed()
        with patch.object(data.urllib.request, 'urlopen', side_effect=OSError('offline')):
            self.assertEqual(data.obtain_patch(self.repo), (self.bundle, 'v1.2.0'))

    def test_offline_first_launch_fails_instead_of_reporting_ready(self):
        with self.assertRaisesRegex(RuntimeError, '최초 실행'):
            data.obtain_patch(self.repo, opener=lambda *args, **kwargs: (_ for _ in ()).throw(OSError('offline')))

    def test_digest_mismatch_preserves_previous_cache(self):
        self.seed()
        self.release['tag_name'] = 'v1.3.0'
        self.release['assets'][0]['digest'] = 'sha256:' + '0' * 64
        self.assertEqual(self.download(), (self.bundle, 'v1.2.0'))
        self.assertEqual(data.load_cache(self.repo)[1]['tag'], 'v1.2.0')

    def test_truncated_download_has_no_ready_cache(self):
        self.release['assets'][0]['size'] += 1
        with self.assertRaisesRegex(RuntimeError, '끊겼습니다'):
            self.download()
        self.assertEqual(data.load_cache(self.repo), (None, None))

    def test_repository_change_cannot_reuse_previous_repository_cache(self):
        self.seed()
        self.assertEqual(data.load_cache('another/patch'), (None, None))

    def test_older_release_does_not_downgrade_cache(self):
        self.seed()
        self.release.update(tag_name='v1.0.0', published_at='2026-10-01T00:00:00Z')
        self.assertEqual(self.download(force=True), (self.bundle, 'v1.2.0'))
        self.assertEqual(len(self.urls), 1)

    def test_rejects_non_bundle_payload(self):
        self.payload = zlib.compress(b'not a bundle')
        self.release['assets'][0].update(size=len(self.payload), digest='sha256:' + hashlib.sha256(self.payload).hexdigest())
        with self.assertRaisesRegex(RuntimeError, 'UnityFS'):
            self.download()

    def test_missing_asset_fails_without_creating_cache(self):
        self.release['assets'] = []
        with self.assertRaisesRegex(RuntimeError, '없습니다'):
            self.download()

    def test_config_uses_local_appdata(self):
        self.assertEqual(data.config_path(), Path(self.temp.name) / 'OverFieldKoreanPatch' / 'launcher_config.json')


if __name__ == '__main__':
    unittest.main()
