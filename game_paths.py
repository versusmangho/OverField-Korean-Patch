"""Game discovery and YooAsset paths shared by the launcher and editor."""
import glob
import json
import os
from pathlib import Path
import sys
import winreg
from launcher_data import config_path


def get_base_dir():
    return os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))


def find_steam_game_path():
    exe_dir = get_base_dir()
    if os.path.exists(os.path.join(exe_dir, "launcher.exe")):
        return exe_dir

    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, "launcher.exe")):
        return cwd

    default_path = r"C:\Program Files (x86)\Steam\steamapps\common\OverField"
    if os.path.exists(os.path.join(default_path, "launcher.exe")):
        return default_path

    try:
        hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_path, _ = winreg.QueryValueEx(hkey, "SteamPath")
        winreg.CloseKey(hkey)

        cand = os.path.join(steam_path, "steamapps", "common", "OverField")
        if os.path.exists(os.path.join(cand, "launcher.exe")):
            return cand

        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf_path):
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                import re
                paths = re.findall(r'"path"\s+"([^"]+)"', content)
                for p in paths:
                    cand = os.path.join(p.replace(r"\\", "\\"), "steamapps", "common", "OverField")
                    if os.path.exists(os.path.join(cand, "launcher.exe")):
                        return cand
    except Exception:
        pass

    return ""


def detect_yooasset_cache(game_dir):
    manifest_dir = os.path.join(game_dir, "launcher_Data", "yoo", "DefaultPackage", "ManifestFiles")
    cache_base = os.path.join(game_dir, "launcher_Data", "yoo", "DefaultPackage", "CacheFiles")

    cache_hash = "68a9e72732e99edf100d6e4a6f692583"

    if os.path.exists(manifest_dir):
        manifests = glob.glob(os.path.join(manifest_dir, "PackageManifest_*.bytes"))
        if manifests:
            manifests.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            try:
                data = Path(manifests[0]).read_bytes()
                idx = data.find(b"pbstaticconfigure")
                if idx != -1:
                    import re
                    m = re.search(rb"([0-9a-f]{32})", data[idx:idx+200])
                    if m:
                        cache_hash = m.group(1).decode("ascii")
            except Exception:
                pass

    prefix = cache_hash[:2]
    target_cache_dir = os.path.join(cache_base, prefix, cache_hash)
    data_file = os.path.join(target_cache_dir, "__data")
    info_file = os.path.join(target_cache_dir, "__info")
    streaming_bundle = os.path.join(game_dir, "launcher_Data", "StreamingAssets", "yoo", "DefaultPackage", "d36af905d36461838e80ed5db5090c65.bundle")

    return {
        "cache_hash": cache_hash,
        "cache_dir": target_cache_dir,
        "data_file": data_file,
        "info_file": info_file,
        "streaming_bundle": streaming_bundle
    }



def configured_game_dir():
    try:
        with open(config_path(), encoding='utf-8') as stream:
            candidate = json.load(stream).get('game_path', '')
        if candidate and os.path.isfile(os.path.join(candidate, 'launcher.exe')):
            return candidate
    except (OSError, ValueError, TypeError):
        pass
    candidate = find_steam_game_path()
    if not candidate:
        raise FileNotFoundError('게임 설치 경로를 찾을 수 없습니다. 먼저 런처에서 경로를 설정해주세요.')
    return candidate
