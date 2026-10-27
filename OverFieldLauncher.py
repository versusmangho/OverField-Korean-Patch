# -*- coding: utf-8 -*-
"""
오버필드 (OverField) 공식 한국어 런처 & 자동 패처
- 핫픽스/업데이트 자동 감지 및 1초 한글 패치 자동 재동기화
- YooAsset CRC32 무결성 통과 자동화 (__info 생성)
- 깃허브 릴리즈(GitHub Releases) 기반 새 번역 패치 자동 확인 및 다운로드
- 원클릭 게임 실행 및 바탕화면 바로가기 지원
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
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QTextEdit,
    QMessageBox, QFrame, QProgressBar, QCheckBox, QDialog,
    QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QTextCursor

STEAM_APP_ID = "3879660"
DEFAULT_GITHUB_REPO = "" # 사용자 지정 가능 (예: username/OverField-Korean-Patch)
CONFIG_FILE = "launcher_config.json"
PATCH_SIZE_SIGNATURE = 10292773 # v1.0 패치 번들 파일 크기

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', get_base_dir())
    target = os.path.join(base_path, relative_path)
    if os.path.exists(target):
        return target
    cwd_target = os.path.join(os.getcwd(), relative_path)
    if os.path.exists(cwd_target):
        return cwd_target
    return target

def load_config():
    default_config = {
        "game_path": "",
        "github_repo": DEFAULT_GITHUB_REPO,
        "auto_update": True,
        "auto_launch": False,
        "close_launcher_on_game_start": True,
        "current_patch_version": "1.0.0"
    }
    config_path = os.path.join(get_base_dir(), CONFIG_FILE)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_config.update(saved)
        except Exception:
            pass
    return default_config

def save_config(config):
    config_path = os.path.join(get_base_dir(), CONFIG_FILE)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

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
    open(data_path, "wb").write(bundle_bytes)

    # YooAsset 검증 통과용 CRC32 + 파일크기 info 작성 (18 bytes)
    crc = binascii.crc32(bundle_bytes) & 0xFFFFFFFF
    crc_hex = f"{crc:08x}"
    file_size = len(bundle_bytes)
    info_bytes = struct.pack('<H', 8) + crc_hex.encode('ascii') + struct.pack('<q', file_size)
    open(info_path, "wb").write(info_bytes)

    # StreamingAssets 업데이트
    if os.path.exists(os.path.dirname(streaming_path)):
        open(streaming_path, "wb").write(bundle_bytes)

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
        self.log_signal.emit("🔍 게임 무결성 및 패치 상태 점검 중...")
        self.progress_signal.emit(20)

        cache_info = detect_yooasset_cache(game_dir)
        data_file = cache_info["data_file"]
        info_file = cache_info["info_file"]

        need_patch = False
        hotfix_detected = False

        if not os.path.exists(data_file):
            self.log_signal.emit("⚠️ YooAsset 캐시가 비어있습니다. 한글 패치 주입이 필요합니다.")
            need_patch = True
        else:
            current_size = os.path.getsize(data_file)
            if abs(current_size - PATCH_SIZE_SIGNATURE) > 500:
                self.log_signal.emit(f"⚡ 게임 핫픽스/업데이트 감지됨! (현재 번들: {current_size:,} bytes)")
                self.log_signal.emit("💡 핫픽스로 초기화된 번들을 감지하여 자동으로 한글 패치 및 CRC를 동기화합니다.")
                hotfix_detected = True
                need_patch = True
            else:
                if os.path.exists(info_file):
                    raw_info = open(info_file, "rb").read()
                    data_bytes = open(data_file, "rb").read()
                    actual_crc = f"{binascii.crc32(data_bytes) & 0xFFFFFFFF:08x}"
                    if actual_crc.encode('ascii') not in raw_info:
                        self.log_signal.emit("⚠️ YooAsset __info 메타데이터 불일치 감지. 자동 복구 진행.")
                        need_patch = True
                else:
                    need_patch = True

        self.progress_signal.emit(40)

        # GitHub 릴리즈 업데이트 확인
        repo = self.config.get("github_repo", "").strip()
        if self.config.get("auto_update") and repo and "/" in repo:
            self.log_signal.emit(f"🌐 GitHub 릴리즈 확인 중... ({repo})")
            remote_bundle = self.check_github_update(repo)
            if remote_bundle:
                self.log_signal.emit("✨ GitHub에서 다운로드한 최신 패치를 적용합니다.")
                apply_bundle_to_game(game_dir, remote_bundle)
                need_patch = False

        self.progress_signal.emit(75)

        if need_patch:
            self.log_signal.emit("🚀 패치 바이너리 주입 및 YooAsset CRC32 동기화 중...")
            payload_path = get_resource_path("patch_payload.dat")
            if os.path.exists(payload_path):
                bundle_bytes = zlib.decompress(open(payload_path, "rb").read())
            else:
                fallback = os.path.join(game_dir, "OverField_Korean_Patch", "launcher_Data", "StreamingAssets", "yoo", "DefaultPackage", "d36af905d36461838e80ed5db5090c65.bundle")
                if os.path.exists(fallback):
                    bundle_bytes = open(fallback, "rb").read()
                else:
                    raise FileNotFoundError("패치 리소스(patch_payload.dat)를 찾을 수 없습니다.")

            crc_hex, fsize = apply_bundle_to_game(game_dir, bundle_bytes)
            self.log_signal.emit(f"✅ 한글 패치 적용 및 CRC32({crc_hex.upper()}) 동기화 성공!")
            if hotfix_detected:
                self.log_signal.emit("🎉 핫픽스 무결성 검증 통과 완료! 바로 한글로 플레이하실 수 있습니다.")

        self.progress_signal.emit(100)
        self.status_signal.emit("● 한글 패치 완료 (실행 준비됨)", "#43b581")
        self.log_signal.emit("🟢 점검 완료! 게임 시작 버튼을 누르시면 오버필드가 실행됩니다.")
        self.finished_signal.emit(True, "READY")

    def do_force_patch(self, game_dir):
        self.log_signal.emit("🚀 최신 한글 패치 수동 재적용 시작...")
        self.progress_signal.emit(30)
        payload_path = get_resource_path("patch_payload.dat")
        if os.path.exists(payload_path):
            bundle_bytes = zlib.decompress(open(payload_path, "rb").read())
        else:
            fallback = os.path.join(game_dir, "OverField_Korean_Patch", "launcher_Data", "StreamingAssets", "yoo", "DefaultPackage", "d36af905d36461838e80ed5db5090c65.bundle")
            bundle_bytes = open(fallback, "rb").read()
        self.progress_signal.emit(70)
        crc_hex, fsize = apply_bundle_to_game(game_dir, bundle_bytes)
        self.progress_signal.emit(100)
        self.log_signal.emit(f"✅ 패치 재적용 및 CRC32 동기화 완료! (CRC={crc_hex.upper()})")
        self.status_signal.emit("● 한글 패치 완료 (실행 준비됨)", "#43b581")
        self.finished_signal.emit(True, "MANUAL_DONE")

    def do_restore(self, game_dir):
        self.log_signal.emit("🔄 순정 원본 복구 시작...")
        self.progress_signal.emit(30)
        cache_info = detect_yooasset_cache(game_dir)
        data_path = cache_info["data_file"]
        info_path = cache_info["info_file"]
        streaming_path = cache_info["streaming_bundle"]

        restored = False
        if os.path.exists(data_path + ".clean_orig"):
            open(data_path, "wb").write(open(data_path + ".clean_orig", "rb").read())
            restored = True
        if os.path.exists(info_path + ".clean_orig"):
            open(info_path, "wb").write(open(info_path + ".clean_orig", "rb").read())
            restored = True
        if os.path.exists(streaming_path + ".bak"):
            open(streaming_path, "wb").write(open(streaming_path + ".bak", "rb").read())
            restored = True

        self.progress_signal.emit(100)
        if restored:
            self.log_signal.emit("✨ 순정 원본으로 복구되었습니다.")
            self.status_signal.emit("● 순정 원본 상태 (미패치)", "#f0b232")
            self.finished_signal.emit(True, "RESTORE_DONE")
        else:
            self.log_signal.emit("⚠️ 순정 원본 백업 파일(.clean_orig)을 찾을 수 없습니다.")
            self.finished_signal.emit(False, "NO_BACKUP")

    def check_github_update(self, repo):
        try:
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "OverFieldLauncher"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                rel = json.loads(resp.read().decode())
                tag = rel.get("tag_name", "").lstrip("v")
                current = self.config.get("current_patch_version", "1.0.0").lstrip("v")
                if tag and tag != current:
                    self.log_signal.emit(f"📢 GitHub에서 새 패치 발견: v{tag} (현재: v{current})")
                    for asset in rel.get("assets", []):
                        if asset.get("name") in ["patch_payload.dat", "patch.dat"]:
                            download_url = asset.get("browser_download_url")
                            self.log_signal.emit(f"⬇️ 최신 패치 바이너리 다운로드 중 ({asset.get('size'):,} bytes)...")
                            with urllib.request.urlopen(download_url, timeout=20) as d_resp:
                                comp_data = d_resp.read()
                                decomp = zlib.decompress(comp_data)
                                self.config["current_patch_version"] = tag
                                save_config(self.config)
                                return decomp
        except Exception as e:
            self.log_signal.emit(f"ℹ️ GitHub 업데이트 확인 통과: {str(e)}")
        return None

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
        self.repo_edit = QLineEdit(self.config.get("github_repo", ""))
        self.repo_edit.setPlaceholderText("예: your-username/OverField-Korean-Patch")
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
        self.setWindowTitle("오버필드 (OverField) 공식 한국어 런처")
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
        
        ver_text = f"패치 버전: v{self.config.get('current_patch_version', '1.0.0')} | 핫픽스 자동 대응 & CRC 바이패스 탑재"
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

        self.reapply_btn = QPushButton("🔄 한글 패치 강제 재적용")
        self.reapply_btn.setProperty("class", "action_btn")
        self.reapply_btn.setFixedHeight(52)
        self.reapply_btn.clicked.connect(self.force_patch)

        self.restore_btn = QPushButton("⏪ 순정 원본 복구")
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
        folder = QFileDialog.getExistingDirectory(self, "OverField 설치 폴더 선택", self.path_edit.text() or "C:\\")
        if folder:
            self.path_edit.setText(folder)
            self.config["game_path"] = folder
            save_config(self.config)
            self.run_startup_sequence()

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.log("⚙️ 설정이 저장되었습니다.")

    def run_startup_sequence(self):
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

        self.worker = LauncherWorker(self.config, mode="startup")
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.status_signal.connect(self.set_badge)
        self.worker.finished_signal.connect(self.on_startup_finished)
        self.worker.start()

    def on_startup_finished(self, success, action):
        self.reapply_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)
        if success:
            self.start_btn.setEnabled(True)
            if self.config.get("auto_launch"):
                self.log("🚀 'Fast Boot' 옵션 활성화: 1.5초 후 오버필드를 자동 실행합니다...")
                QTimer.singleShot(1500, self.launch_game)
        else:
            self.start_btn.setEnabled(False)

    def force_patch(self):
        self.start_btn.setEnabled(False)
        self.worker = LauncherWorker(self.config, mode="force_patch")
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.status_signal.connect(self.set_badge)
        self.worker.finished_signal.connect(lambda s, a: self.start_btn.setEnabled(s))
        self.worker.start()

    def restore_original(self):
        reply = QMessageBox.question(
            self, "순정 복구 확인",
            "한글 패치를 해제하고 게임을 순정 원본 상태로 복구하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.start_btn.setEnabled(False)
            self.worker = LauncherWorker(self.config, mode="restore")
            self.worker.log_signal.connect(self.log)
            self.worker.progress_signal.connect(self.progress_bar.setValue)
            self.worker.status_signal.connect(self.set_badge)
            self.worker.finished_signal.connect(lambda s, a: self.start_btn.setEnabled(s))
            self.worker.start()

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

        # 중복 실행 방지
        if self.is_game_running():
            self.log("ℹ️ 오버필드가 이미 실행 중입니다.")
            QMessageBox.information(self, "알림", "오버필드가 이미 실행 중입니다.")
            return

        self.log("🚀 오버필드(OverField) 게임을 실행합니다...")
        self.start_btn.setEnabled(False)
        self.start_btn.setText("실행 중...")

        # 1. steam_appid.txt 확인
        appid_file = os.path.join(game_dir, "steam_appid.txt")
        if not os.path.exists(appid_file):
            open(appid_file, "w", encoding="ascii").write(f"{STEAM_APP_ID}\n")

        # 2. 게임 프로세스 실행 (스팀 프로토콜 우선, fallback 직접 실행)
        try:
            os.startfile(f"steam://rungameid/{STEAM_APP_ID}")
            self.log("🎮 스팀 프로토콜을 통해 오버필드가 실행되었습니다!")
        except Exception as e:
            self.log(f"⚠️ 스팀 프로토콜 실행 실패, 직접 실행 시도: {str(e)}")
            try:
                subprocess.Popen([exe], cwd=game_dir)
                self.log(f"🎮 {exe} 직접 실행 완료!")
            except Exception as e2:
                self.log(f"❌ 게임 실행 실패: {str(e2)}")
                self.start_btn.setEnabled(True)
                self.start_btn.setText("🎮 게임 시작 (GAME START)")
                return

        # 3. 옵션: 게임 실행 후 런처 종료
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
