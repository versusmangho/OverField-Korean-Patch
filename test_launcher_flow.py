"""Exercise worker logic on temporary bundles without importing Qt or starting apps."""
import ast
import binascii
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from game_paths import detect_yooasset_cache
from launcher_data import atomic_write, config_path, validate_bundle


class Signal:
    def __init__(self):
        self.events = []

    def emit(self, *args):
        self.events.append(args)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.game = Path(self.temp.name) / 'game'
        self.paths = detect_yooasset_cache(str(self.game))
        Path(self.paths['cache_dir']).mkdir(parents=True)
        Path(self.paths['streaming_bundle']).parent.mkdir(parents=True)
        self.old = b'UnityFS\x00old-translation'
        self.new = b'UnityFS\x00new-translation'
        self.old_info = struct.pack('<H', 8) + f'{binascii.crc32(self.old) & 0xffffffff:08x}'.encode() + struct.pack('<q', len(self.old))
        for key in ('data_file', 'streaming_bundle'):
            Path(self.paths[key]).write_bytes(self.old)
        Path(self.paths['info_file']).write_bytes(self.old_info)
        tree = ast.parse(Path('OverFieldLauncher.py').read_text(encoding='utf-8'))
        selected = [n for n in tree.body if getattr(n, 'name', '') in {
            'validate_game_executable', 'load_config', 'save_config', 'apply_bundle_to_game', 'LauncherWorker'}]
        self.scope = dict(Path=Path, os=os, struct=struct, binascii=binascii, json=json,
                          QThread=object, pyqtSignal=lambda *args: Signal(),
                          DEFAULT_GITHUB_REPO='owner/patch', STEAM_APP_ID='3879660',
                          detect_yooasset_cache=detect_yooasset_cache,
                          atomic_write=atomic_write, config_path=config_path,
                          validate_bundle=validate_bundle,
                          obtain_patch=lambda *args, **kwargs: (self.new, 'v1.2.0'))
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'OverFieldLauncher.py', 'exec'), self.scope)
        self.worker = self.scope['LauncherWorker']({'game_path': str(self.game), 'github_repo': 'owner/patch'})
        for name in ('log_signal', 'progress_signal', 'status_signal', 'finished_signal'):
            setattr(self.worker, name, Signal())

    def test_startup_applies_download_and_records_actual_version(self):
        self.worker.do_startup(str(self.game))
        self.assertEqual(Path(self.paths['data_file']).read_bytes(), self.new)
        self.assertEqual(Path(self.paths['streaming_bundle']).read_bytes(), self.new)
        info = Path(self.paths['info_file']).read_bytes()
        self.assertEqual(info[2:10], f'{binascii.crc32(self.new) & 0xffffffff:08x}'.encode())
        self.assertEqual(struct.unpack('<q', info[10:])[0], len(self.new))
        self.assertEqual(json.loads(config_path().read_text(encoding='utf-8'))['current_patch_version'], '1.2.0')
        self.assertEqual(self.worker.finished_signal.events[-1], (True, 'READY'))
        self.assertFalse((self.game / 'patch_payload.dat').exists())
        self.assertEqual(Path(self.paths['data_file'] + '.clean_orig').read_bytes(), self.old)

    def test_same_size_corruption_is_repaired_and_backups_restore(self):
        self.assertEqual(len(self.old), len(self.new))
        self.worker.do_startup(str(self.game))
        self.worker.do_restore(str(self.game))
        self.assertEqual(Path(self.paths['data_file']).read_bytes(), self.old)
        self.assertEqual(Path(self.paths['streaming_bundle']).read_bytes(), self.old)
        self.assertEqual(Path(self.paths['info_file']).read_bytes(), self.old_info)

    def test_current_data_not_rewritten(self):
        self.worker.do_startup(str(self.game))
        timestamp = Path(self.paths['data_file']).stat().st_mtime_ns
        self.worker.do_startup(str(self.game))
        self.assertEqual(Path(self.paths['data_file']).stat().st_mtime_ns, timestamp)

    def test_failed_first_download_does_not_apply_or_mark_ready(self):
        self.scope['obtain_patch'] = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('offline'))
        # run() first checks the game executable's presence, but never executes it.
        (self.game / 'launcher.exe').write_bytes(b'fixture, not executable')
        self.worker.run()
        self.assertFalse(self.worker.finished_signal.events[-1][0])
        self.assertEqual(Path(self.paths['data_file']).read_bytes(), self.old)

    def test_settings_do_not_use_exe_adjacent_json(self):
        config = self.scope['load_config']()
        self.assertEqual(config['current_patch_version'], '0.0.0')
        self.assertEqual(config['game_path'], '')


if __name__ == '__main__':
    unittest.main()
