# -*- coding: utf-8 -*-
"""
오버필드 (OverField) 비공식 한국어 런처 & 자동 패처
- 내장/로컬 패치 지원 및 선택적 GitHub 업데이트
- 게임사 핫픽스 감지 시 자동으로 번역 재주입 및 YooAsset CRC32 통과
- 다운로드 진행도 실시간 표시 및 원클릭 게임 실행
"""

import os
import sys
import glob
import json
import zlib
import struct
import binascii
import urllib.request
import subprocess
import winreg
import tempfile
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QTextEdit,
    QMessageBox, QFrame, QProgressBar, QCheckBox, QDialog,
    QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QTextCursor

STEAM_APP_ID = "3879660"
DEFAULT_GITHUB_REPO = "versusmangho/OverField-Korean-Patch"
CONFIG_FILE = "launcher_config.json"
PAYLOAD_FILENAME = "patch_payload.dat"

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def atomic_write(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".overfield-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_bundle(data):
    if not data.startswith(b"UnityFS\x00"):
        raise ValueError("유효한 UnityFS 패치 번들이 아닙니다.")
    return data


def load_config():
    default_config = {
        "game_path": "",
        "github_repo": DEFAULT_GITHUB_REPO,
        "auto_update": True,
        "auto_launch": False,
        "close_launcher_on_game_start": True,
        "current_patch_version": "0.0.0"
    }
    config_path = os.path.join(get_base_dir(), CONFIG_FILE)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    default_config.update(saved)
        except Exception:
            pass
    return default_config

def save_config(config):
    config_path = os.path.join(get_base_dir(), CONFIG_FILE)
    atomic_write(config_path, json.dumps(config, indent=4, ensure_ascii=False).encode("utf-8"))


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
                data = open(manifests[0], "rb").read()
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

def apply_bundle_to_game(game_dir, bundle_bytes):
    validate_bundle(bundle_bytes)
    info = detect_yooasset_cache(game_dir)
    data_path = info["data_file"]
    info_path = info["info_file"]
    streaming_path = info["streaming_bundle"]

    os.makedirs(info["cache_dir"], exist_ok=True)

    # 순정 백업 생성
    if os.path.exists(data_path) and not os.path.exists(data_path + ".clean_orig"):
        open(data_path + ".clean_orig", "wb").write(open(data_path, "rb").read())
    if os.path.exists(info_path) and not os.path.exists(info_path + ".clean_orig"):
        open(info_path + ".clean_orig", "wb").write(open(info_path, "rb").read())
    if os.path.exists(streaming_path) and not os.path.exists(streaming_path + ".bak"):
        open(streaming_path + ".bak", "wb").write(open(streaming_path, "rb").read())

    # 캐시 번들 작성
    atomic_write(data_path, bundle_bytes)

    # YooAsset 검증 통과용 CRC32 + 파일크기 info 작성 (18 bytes)
    crc = binascii.crc32(bundle_bytes) & 0xFFFFFFFF
    crc_hex = f"{crc:08x}"
    file_size = len(bundle_bytes)
    info_bytes = struct.pack('<H', 8) + crc_hex.encode('ascii') + struct.pack('<q', file_size)
    atomic_write(info_path, info_bytes)

    # StreamingAssets 업데이트
    if os.path.exists(os.path.dirname(streaming_path)):
        atomic_write(streaming_path, bundle_bytes)

    # steam_appid.txt 보장
    appid_path = os.path.join(game_dir, "steam_appid.txt")
    if not os.path.exists(appid_path):
        open(appid_path, "w", encoding="ascii").write(f"{STEAM_APP_ID}\n")

    return crc_hex, file_size

class LauncherWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, config, mode="startup"):
        super().__init__()
        self.config = config
        self.mode = mode

    def run(self):
        try:
            game_dir = self.config.get("game_path")
            if not game_dir or not os.path.exists(os.path.join(game_dir, "launcher.exe")):
                self.log_signal.emit("❌ 게임 폴더를 찾을 수 없습니다. 경로를 지정해주세요.")
                self.status_signal.emit("게임 경로 필요", "#ff6b6b")
                self.finished_signal.emit(False, "NO_PATH")
                return

            if self.mode == "startup":
                self.do_startup(game_dir)
            elif self.mode == "force_patch":
                self.do_force_patch(game_dir)
            elif self.mode == "restore":
                self.do_restore(game_dir)
        except Exception as e:
            self.log_signal.emit(f"❌ 오류 발생: {str(e)}")
            self.status_signal.emit("오류 발생", "#ff6b6b")
            self.finished_signal.emit(False, str(e))

    def do_startup(self, game_dir):
        self.log_signal.emit("🔍 게임 상태 및 GitHub 최신 패치 확인 중...")
        self.progress_signal.emit(15)

        repo = self.config.get("github_repo", DEFAULT_GITHUB_REPO).strip()
        local_payload_file = os.path.join(get_base_dir(), PAYLOAD_FILENAME)

        bundle_bytes = None
        new_version_downloaded = False

        # 1. GitHub에서 최신 릴리즈 확인 및 다운로드
        if self.config.get("auto_update", True) and repo and "/" in repo:
            self.log_signal.emit(f"🌐 GitHub에서 최신 번역 데이터 확인 중... ({repo})")
            remote_data, remote_tag = self.fetch_github_patch(repo)
            if remote_data:
                bundle_bytes = remote_data
                new_version_downloaded = True
                self.log_signal.emit(f"✨ GitHub에서 최신 패치(v{remote_tag}) 다운로드 완료!")
                # 로컬에 캐싱 보관
                try:
                    atomic_write(local_payload_file, zlib.compress(bundle_bytes, 9))
                except Exception:
                    pass

        self.progress_signal.emit(50)

        if bundle_bytes is None and not os.path.exists(local_payload_file):
            bundled = os.path.join(getattr(sys, "_MEIPASS", get_base_dir()), PAYLOAD_FILENAME)
            if os.path.exists(bundled):
                bundle_bytes = validate_bundle(zlib.decompress(open(bundled, "rb").read()))

        # 2. GitHub 연결 실패 시 로컬 캐시된 패치 페이로드 확인
        if bundle_bytes is None:
            if os.path.exists(local_payload_file):
                self.log_signal.emit("📦 로컬에 저장된 번역 패치 데이터를 로드합니다.")
                bundle_bytes = validate_bundle(zlib.decompress(open(local_payload_file, "rb").read()))
            else:
                fallback = os.path.join(game_dir, "OverField_Korean_Patch", "launcher_Data", "StreamingAssets", "yoo", "DefaultPackage", "d36af905d36461838e80ed5db5090c65.bundle")
                if os.path.exists(fallback):
                    self.log_signal.emit("📦 기본 디렉토리의 패치 번들을 로드합니다.")
                    bundle_bytes = open(fallback, "rb").read()

        if bundle_bytes is None:
            raise FileNotFoundError("사용 가능한 패치 데이터가 없습니다. 패치 파일 또는 GitHub 설정을 확인해주세요.")
        validate_bundle(bundle_bytes)

        # 3. 게임 YooAsset 캐시 점검 및 패치 적용
        cache_info = detect_yooasset_cache(game_dir)
        data_file = cache_info["data_file"]
        info_file = cache_info["info_file"]

        need_apply = new_version_downloaded

        if not os.path.exists(data_file):
            self.log_signal.emit("⚠️ YooAsset 캐시가 비어있어 패치 주입이 필요합니다.")
            need_apply = True
        elif bundle_bytes is not None:
            current_size = os.path.getsize(data_file)
            if current_size != len(bundle_bytes):
                self.log_signal.emit(f"⚡ 게임 핫픽스/업데이트 감지됨! (캐시 크기: {current_size:,} -> 패치 크기: {len(bundle_bytes):,})")
                self.log_signal.emit("💡 핫픽스로 초기화된 텍스트를 감지하여 한글 패치를 자동 재적용합니다.")
                need_apply = True
            elif not os.path.exists(info_file):
                need_apply = True
            else:
                # CRC 일치 확인
                expected_crc = f"{binascii.crc32(bundle_bytes) & 0xFFFFFFFF:08x}"
                if (expected_crc.encode('ascii') not in open(info_file, 'rb').read()
                        or binascii.crc32(open(data_file, 'rb').read()) & 0xFFFFFFFF != binascii.crc32(bundle_bytes) & 0xFFFFFFFF):
                    self.log_signal.emit("⚠️ YooAsset __info 메타데이터 불일치 감지. 자동 재동기화 진행.")
                    need_apply = True

        streaming_file = cache_info["streaming_bundle"]
        if not os.path.exists(streaming_file) or open(streaming_file, "rb").read() != bundle_bytes:
            need_apply = True

        self.progress_signal.emit(75)

        if need_apply:
            if bundle_bytes is None:
                self.log_signal.emit("❌ 다운로드할 패치 데이터가 없으며 로컬 캐시도 없습니다. GitHub 연결을 확인해주세요.")
                self.status_signal.emit("패치 다운로드 실패", "#ff6b6b")
                self.finished_signal.emit(False, "NO_PAYLOAD")
                return

            crc_hex, fsize = apply_bundle_to_game(game_dir, bundle_bytes)
            self.log_signal.emit(f"✅ 한글 패치 주입 및 YooAsset CRC32({crc_hex.upper()}) 동기화 성공!")

        if new_version_downloaded:
            self.config["current_patch_version"] = remote_tag
            save_config(self.config)
        self.progress_signal.emit(100)
        self.status_signal.emit(f"● 한글 패치 적용 확인 (v{self.config.get('current_patch_version', '1.0')})", "#43b581")
        self.log_signal.emit("🟢 모든 점검 완료! [게임 시작] 버튼을 누르시면 오버필드가 실행됩니다.")
        self.finished_signal.emit(True, "READY")

    def do_force_patch(self, game_dir):
        self.log_signal.emit("🚀 최신 한글 패치 강제 다운로드 및 재적용 시작...")
        self.progress_signal.emit(20)

        repo = self.config.get("github_repo", DEFAULT_GITHUB_REPO).strip()
        bundle_bytes, remote_tag = self.fetch_github_patch(repo, force=True)

        if bundle_bytes is None:
            local_payload_file = os.path.join(get_base_dir(), PAYLOAD_FILENAME)
            if os.path.exists(local_payload_file):
                bundle_bytes = validate_bundle(zlib.decompress(open(local_payload_file, "rb").read()))
            else:
                self.log_signal.emit("❌ 패치 데이터를 가져올 수 없습니다.")
                self.finished_signal.emit(False, "FAIL")
                return

        self.progress_signal.emit(70)
        crc_hex, fsize = apply_bundle_to_game(game_dir, bundle_bytes)
        atomic_write(os.path.join(get_base_dir(), PAYLOAD_FILENAME), zlib.compress(bundle_bytes, 9))
        if remote_tag:
            self.config["current_patch_version"] = remote_tag
            save_config(self.config)
        self.progress_signal.emit(100)
        self.log_signal.emit(f"✅ 패치 재적용 및 CRC32 동기화 완료! (CRC={crc_hex.upper()})")
        self.status_signal.emit("● 한글 패치 완료 (실행 준비됨)", "#43b581")
        self.finished_signal.emit(True, "MANUAL_DONE")

    def do_restore(self, game_dir):
        self.log_signal.emit("🔄 적용 전 백업 복구 시작...")
        self.progress_signal.emit(30)
        cache_info = detect_yooasset_cache(game_dir)
        data_path = cache_info["data_file"]
        info_path = cache_info["info_file"]
        streaming_path = cache_info["streaming_bundle"]

        paths = [data_path, info_path, streaming_path]
        backups = [data_path + ".clean_orig", info_path + ".clean_orig", streaming_path + ".bak"]
        if not all(os.path.isfile(path) for path in backups):
            raise FileNotFoundError("완전한 원본 백업이 없습니다. Steam 파일 무결성 검사로 복구해주세요.")
        for target, backup in zip(paths, backups):
            atomic_write(target, open(backup, "rb").read())
        self.progress_signal.emit(100)
        self.log_signal.emit("백업 파일 복구 완료. 백업이 순정인지 여부는 Steam 무결성 검사로 확인할 수 있습니다.")
        self.status_signal.emit("● 패치 적용 전 백업으로 복구됨", "#f0b232")
        self.finished_signal.emit(True, "RESTORE_DONE")

    def fetch_github_patch(self, repo, force=False):
        try:
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "OverFieldLauncher"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                rel = json.loads(resp.read().decode())
                tag = rel.get("tag_name", "").lstrip("v")
                current = self.config.get("current_patch_version", "0.0.0").lstrip("v")

                # 로컬에 패치 파일이 없거나 새 버전이 올라온 경우
                local_payload = os.path.join(get_base_dir(), PAYLOAD_FILENAME)
                need_download = force or (tag != current) or (not os.path.exists(local_payload))

                if need_download:
                    for asset in rel.get("assets", []):
                        if asset.get("name") in [PAYLOAD_FILENAME, "patch.dat", "patch_data.dat"]:
                            download_url = asset.get("browser_download_url")
                            size = asset.get("size", 0)
                            self.log_signal.emit(f"⬇️ GitHub에서 새 번역 패치(v{tag}) 다운로드 시작 ({size:,} bytes)...")

                            # 다운로드 진행도 처리
                            with urllib.request.urlopen(download_url, timeout=30) as d_resp:
                                total_size = int(d_resp.headers.get('Content-Length', size))
                                downloaded = 0
                                chunks = []
                                chunk_size = 64 * 1024
                                while True:
                                    chunk = d_resp.read(chunk_size)
                                    if not chunk:
                                        break
                                    chunks.append(chunk)
                                    downloaded += len(chunk)
                                    pct = min(100, int(downloaded / max(total_size, 1) * 50) + 20)
                                    self.progress_signal.emit(pct)

                                comp_data = b"".join(chunks)
                                decomp = zlib.decompress(comp_data)
                                return validate_bundle(decomp), tag
                else:
                    self.log_signal.emit(f"ℹ️ 현재 버전(v{current})이 GitHub 최신 버전과 일치합니다.")
                    return None, tag
        except Exception as e:
            self.log_signal.emit(f"ℹ️ GitHub 확인 스킵/오프라인: {str(e)}")
        return None, None

class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("런처 환경설정")
        self.setFixedSize(480, 310)
        self.setStyleSheet("""
            QDialog { background-color: #1a1b24; color: #ffffff; }
            QLabel { color: #d0d2de; font-family: 'Malgun Gothic'; }
            QLineEdit { background-color: #101117; border: 1px solid #36394c; color: #ffffff; padding: 6px; border-radius: 4px; }
            QCheckBox { color: #e0e2ec; font-family: 'Malgun Gothic'; }
            QPushButton { background-color: #383c52; color: #ffffff; border-radius: 4px; padding: 7px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #484d69; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        self.repo_edit = QLineEdit(self.config.get("github_repo", DEFAULT_GITHUB_REPO))
        self.repo_edit.setPlaceholderText("예: versusmangho/OverField-Korean-Patch")
        form.addRow("GitHub 배포 저장소:", self.repo_edit)

        self.auto_update_chk = QCheckBox("시작 시 GitHub에서 최신 패치 자동 확인/다운로드")
        self.auto_update_chk.setChecked(self.config.get("auto_update", True))
        form.addRow("", self.auto_update_chk)

        self.auto_launch_chk = QCheckBox("무결성 점검 통과 시 즉시 오버필드 자동 실행 (Fast Boot)")
        self.auto_launch_chk.setChecked(self.config.get("auto_launch", False))
        form.addRow("", self.auto_launch_chk)

        self.close_on_start_chk = QCheckBox("게임 실행 후 런처 자동 닫기 (메모리 절약)")
        self.close_on_start_chk.setChecked(self.config.get("close_launcher_on_game_start", True))
        form.addRow("", self.close_on_start_chk)

        layout.addLayout(form)

        shortcut_btn = QPushButton("📌 바탕화면에 '오버필드 (한국어)' 바로가기 생성")
        shortcut_btn.clicked.connect(self.create_shortcut)
        layout.addWidget(shortcut_btn)

        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.save_and_close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def create_shortcut(self):
        try:
            desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
            lnk_path = os.path.join(desktop, "OverField (한국어).lnk")
            exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
            work_dir = os.path.dirname(exe_path)

            ps_cmd = f"$ws = New-Object -COM WScript.Shell; $s = $ws.CreateShortcut('{lnk_path}'); $s.TargetPath = '{exe_path}'; $s.WorkingDirectory = '{work_dir}'; $s.Save()"
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)
            QMessageBox.information(self, "완료", "바탕화면에 바로가기가 성공적으로 생성되었습니다!")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"바로가기 생성 실패: {str(e)}")

    def save_and_close(self):
        self.config["github_repo"] = self.repo_edit.text().strip()
        self.config["auto_update"] = self.auto_update_chk.isChecked()
        self.config["auto_launch"] = self.auto_launch_chk.isChecked()
        self.config["close_launcher_on_game_start"] = self.close_on_start_chk.isChecked()
        save_config(self.config)
        self.accept()

class OverFieldLauncherApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.init_ui()
        self.run_startup_sequence()

    def init_ui(self):
        self.setWindowTitle("오버필드 (OverField) 비공식 한국어 런처")
        self.setFixedSize(720, 560)
        self.setStyleSheet("""
            QMainWindow { background-color: #14151c; }
            QLabel { color: #e0e2ec; font-family: 'Malgun Gothic', 'Noto Sans KR', sans-serif; }
            QFrame.card {
                background-color: #1e202b;
                border: 1px solid #2d3040;
                border-radius: 8px;
                padding: 12px;
            }
            QLineEdit {
                background-color: #101117;
                border: 1px solid #323547;
                border-radius: 5px;
                color: #f0f0f5;
                padding: 7px 10px;
                font-size: 12px;
            }
            QPushButton {
                font-family: 'Malgun Gothic', sans-serif;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 13px;
            }
            QPushButton.game_start {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00b4db, stop:1 #0083b0);
                color: #ffffff;
                font-size: 18px;
                font-weight: 900;
                border: none;
                border-radius: 8px;
            }
            QPushButton.game_start:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #05c3ec, stop:1 #0294c7);
            }
            QPushButton.game_start:disabled {
                background-color: #323545;
                color: #72768d;
            }
            QPushButton.action_btn {
                background-color: #2b2e3d;
                color: #d1d4e3;
                border: 1px solid #3d4156;
            }
            QPushButton.action_btn:hover {
                background-color: #373b4e;
            }
            QTextEdit {
                background-color: #0d0e13;
                border: 1px solid #242633;
                border-radius: 6px;
                color: #9da2b8;
                font-family: 'Consolas', 'Malgun Gothic', monospace;
                font-size: 12px;
                padding: 8px;
            }
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #101117;
                height: 8px;
            }
            QProgressBar::chunk {
                background-color: #00b4db;
                border-radius: 4px;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(22, 22, 22, 22)
        main_layout.setSpacing(14)

        # 1. 헤더 & 타이틀
        header_card = QFrame()
        header_card.setProperty("class", "card")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(16, 12, 16, 12)

        title_vbox = QVBoxLayout()
        title_label = QLabel("OVERFIELD LAUNCHER")
        title_label.setFont(QFont("Malgun Gothic", 17, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #ffffff; letter-spacing: 1px;")

        ver_text = f"저장소: {self.config.get('github_repo', DEFAULT_GITHUB_REPO)} | 핫픽스 자동 대응 & CRC 바이패스"
        sub_label = QLabel(ver_text)
        sub_label.setStyleSheet("color: #7d8299; font-size: 11px;")
        title_vbox.addWidget(title_label)
        title_vbox.addWidget(sub_label)

        self.status_badge = QLabel("상태 점검 중...")
        self.status_badge.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        self.status_badge.setStyleSheet("background-color: #272936; color: #a0a5ba; padding: 6px 14px; border-radius: 14px;")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        settings_btn = QPushButton("⚙️ 설정")
        settings_btn.setProperty("class", "action_btn")
        settings_btn.clicked.connect(self.open_settings)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        header_layout.addWidget(self.status_badge)
        header_layout.addWidget(settings_btn)
        main_layout.addWidget(header_card)

        # 2. 게임 설치 경로
        path_card = QFrame()
        path_card.setProperty("class", "card")
        path_layout = QHBoxLayout(path_card)
        path_layout.setContentsMargins(14, 8, 14, 8)
        path_layout.setSpacing(10)

        path_label = QLabel("설치 경로:")
        path_label.setStyleSheet("font-weight: bold; color: #a0a4b8;")
        self.path_edit = QLineEdit(self.config.get("game_path", ""))
        self.path_edit.setPlaceholderText("OverField 게임 설치 폴더를 지정해주세요...")

        browse_btn = QPushButton("찾아보기...")
        browse_btn.setProperty("class", "action_btn")
        browse_btn.clicked.connect(self.browse_path)

        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_edit, 5)
        path_layout.addWidget(browse_btn, 1)
        main_layout.addWidget(path_card)

        # 3. 진행도 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 4. 실시간 상태 로그 창
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        main_layout.addWidget(self.log_box, 3)

        # 5. 하단 버튼 바 (게임 시작 + 부가 기능)
        bottom_box = QHBoxLayout()
        bottom_box.setSpacing(12)

        self.reapply_btn = QPushButton("🔄 패치 다운로드 / 재적용")
        self.reapply_btn.setProperty("class", "action_btn")
        self.reapply_btn.setFixedHeight(52)
        self.reapply_btn.clicked.connect(self.force_patch)

        self.restore_btn = QPushButton("⏪ 적용 전 백업 복구")
        self.restore_btn.setProperty("class", "action_btn")
        self.restore_btn.setFixedHeight(52)
        self.restore_btn.clicked.connect(self.restore_original)

        self.start_btn = QPushButton("🎮 게임 시작 (GAME START)")
        self.start_btn.setProperty("class", "game_start")
        self.start_btn.setFixedHeight(52)
        self.start_btn.clicked.connect(self.launch_game)
        self.start_btn.setEnabled(False)

        bottom_box.addWidget(self.reapply_btn, 2)
        bottom_box.addWidget(self.restore_btn, 2)
        bottom_box.addWidget(self.start_btn, 4)
        main_layout.addLayout(bottom_box)

    def log(self, message):
        self.log_box.append(message)
        self.log_box.moveCursor(QTextCursor.MoveOperation.End)

    def set_badge(self, text, color):
        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(f"background-color: #1e202b; color: {color}; border: 1px solid {color}; padding: 6px 14px; border-radius: 14px;")

    def browse_path(self):
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            return
        folder = QFileDialog.getExistingDirectory(self, "OverField 설치 폴더 선택", self.path_edit.text() or "C:\\")
        if folder:
            self.path_edit.setText(folder)
            self.config["game_path"] = folder
            save_config(self.config)
            self.run_startup_sequence()

    def open_settings(self):
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            return
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.log("⚙️ 설정이 저장되었습니다.")

    def run_startup_sequence(self):
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            return
        if self.is_game_running():
            self.log("게임 실행 중에는 패치를 변경하지 않습니다. 게임 종료 후 런처를 다시 열어주세요.")
            return
        game_path = self.path_edit.text().strip()
        if not game_path or not os.path.exists(os.path.join(game_path, "launcher.exe")):
            detected = find_steam_game_path()
            if detected:
                self.path_edit.setText(detected)
                self.config["game_path"] = detected
                save_config(self.config)
                game_path = detected

        if not game_path:
            self.set_badge("● 게임 경로 필요", "#ff6b6b")
            self.log("⚠️ OverField 설치 경로를 감지하지 못했습니다. [찾아보기]를 눌러 게임 폴더를 선택해주세요.")
            return

        self.start_btn.setEnabled(False)
        self.reapply_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)

        self.path_edit.setEnabled(False)
        self.worker = LauncherWorker(self.config, mode="startup")
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.status_signal.connect(self.set_badge)
        self.worker.finished_signal.connect(self.on_startup_finished)
        self.worker.start()

    def on_startup_finished(self, success, action):
        self.path_edit.setEnabled(True)
        self.reapply_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)
        if success:
            self.start_btn.setEnabled(True)
            if self.config.get("auto_launch"):
                self.log("🚀 'Fast Boot' 옵션 활성화: 1.5초 후 오버필드를 자동 실행합니다...")
                QTimer.singleShot(1500, lambda: self.launch_game() if self.start_btn.isEnabled() else None)
        else:
            self.start_btn.setEnabled(False)

    def set_busy(self, busy):
        self.start_btn.setEnabled(not busy)
        self.reapply_btn.setEnabled(not busy)
        self.restore_btn.setEnabled(not busy)
        self.path_edit.setEnabled(not busy)

    def start_operation(self, mode):
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            return
        if self.is_game_running():
            QMessageBox.warning(self, "게임 실행 중", "게임을 종료한 뒤 패치 또는 복구해주세요.")
            return
        self.config["game_path"] = self.path_edit.text().strip()
        save_config(self.config)
        self.set_busy(True)
        self.worker = LauncherWorker(self.config, mode=mode)
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.status_signal.connect(self.set_badge)
        self.worker.finished_signal.connect(self.on_operation_finished)
        self.worker.start()

    def on_operation_finished(self, success, action):
        self.set_busy(False)
        self.start_btn.setEnabled(success)

    def force_patch(self):
        self.start_operation("force_patch")

    def restore_original(self):
        reply = QMessageBox.question(
            self, "순정 복구 확인", "게임을 원본 백업으로 복구하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.start_operation("restore")

    def closeEvent(self, event):
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            self.log("패치 작업이 끝난 뒤 런처를 종료해주세요.")
            event.ignore()
            return
        super().closeEvent(event)

    def is_game_running(self):
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-Process -Name 'launcher' -ErrorAction SilentlyContinue"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            return len(res.stdout.strip()) > 0
        except Exception:
            return False

    def launch_game(self):
        game_dir = self.path_edit.text().strip()
        exe = os.path.join(game_dir, "launcher.exe")

        if not os.path.exists(exe):
            self.log(f"❌ 게임 실행 파일({exe})을 찾을 수 없습니다.")
            QMessageBox.warning(self, "실행 오류", "launcher.exe를 찾을 수 없습니다.")
            return

        if self.is_game_running():
            self.log("ℹ️ 오버필드가 이미 실행 중입니다.")
            QMessageBox.information(self, "알림", "오버필드가 이미 실행 중입니다.")
            return

        self.log("🚀 오버필드(OverField) 게임을 실행합니다...")
        self.start_btn.setEnabled(False)
        self.start_btn.setText("실행 중...")

        appid_file = os.path.join(game_dir, "steam_appid.txt")
        if not os.path.exists(appid_file):
            open(appid_file, "w", encoding="ascii").write(f"{STEAM_APP_ID}\n")

        try:
            subprocess.Popen([exe, *sys.argv[2:]] if len(sys.argv) > 1 and os.path.basename(sys.argv[1]).lower() == "launcher.exe" else [exe], cwd=game_dir)
            self.log("🎮 오버필드 실행 요청을 전달했습니다!")
        except Exception as e:
            self.log(f"⚠️ 스팀 프로토콜 실패, 직접 실행: {str(e)}")
            try:
                subprocess.Popen([exe], cwd=game_dir)
                self.log(f"🎮 {exe} 직접 실행 완료!")
            except Exception as e2:
                self.log(f"❌ 게임 실행 실패: {str(e2)}")
                self.start_btn.setEnabled(True)
                self.start_btn.setText("🎮 게임 시작 (GAME START)")
                return

        if self.config.get("close_launcher_on_game_start", True):
            self.log("⏱️ 게임 실행 확인 후 3초 뒤 런처를 종료합니다...")
            QTimer.singleShot(3000, self.close)

def main():
    app = QApplication(sys.argv)
    win = OverFieldLauncherApp()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
