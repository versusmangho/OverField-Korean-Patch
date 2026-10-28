# -*- coding: utf-8 -*-
"""
오버필드 (OverField) 비공식 한국어 런처 & 자동 패처
- GitHub 패치 다운로드 및 사용자 데이터 폴더 캐시
- 게임사 핫픽스 감지 시 자동으로 번역 재주입 및 YooAsset CRC32 통과
- 다운로드 진행도 실시간 표시 및 원클릭 게임 실행
"""

import os
from pathlib import Path
import sys
import json
import struct
import binascii
import subprocess
from game_paths import find_steam_game_path, detect_yooasset_cache
from launcher_data import atomic_write, validate_bundle, config_path, obtain_patch
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


def validate_game_executable(path):
    """Reject text fixtures and legacy DOS/16-bit files before asking Windows to run them."""
    with open(path, "rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ValueError("유효한 Windows 게임 실행 파일이 아닙니다.")
        pe_offset = struct.unpack_from("<I", header, 60)[0]
        if pe_offset < 64:
            raise ValueError("Windows 실행 파일 헤더가 손상되었습니다.")
        stream.seek(pe_offset)
        if stream.read(4) != b"PE\x00\x00":
            raise ValueError("지원되는 Windows 실행 파일 형식이 아닙니다.")


def load_config():
    default_config = {
        "game_path": "",
        "github_repo": DEFAULT_GITHUB_REPO,
        "auto_update": True,
        "auto_launch": False,
        "close_launcher_on_game_start": True,
        "current_patch_version": "0.0.0"
    }
    settings_file = config_path()
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    default_config.update(saved)
        except Exception:
            pass
    return default_config

def save_config(config):
    settings_file = config_path()
    atomic_write(settings_file, json.dumps(config, indent=4, ensure_ascii=False).encode("utf-8"))


def apply_bundle_to_game(game_dir, bundle_bytes):
    validate_bundle(bundle_bytes)
    info = detect_yooasset_cache(game_dir)
    data_path = info["data_file"]
    info_path = info["info_file"]
    streaming_path = info["streaming_bundle"]

    os.makedirs(info["cache_dir"], exist_ok=True)

    # 순정 백업 생성
    if os.path.exists(data_path) and not os.path.exists(data_path + ".clean_orig"):
        atomic_write(data_path + ".clean_orig", Path(data_path).read_bytes())
    if os.path.exists(info_path) and not os.path.exists(info_path + ".clean_orig"):
        atomic_write(info_path + ".clean_orig", Path(info_path).read_bytes())
    if os.path.exists(streaming_path) and not os.path.exists(streaming_path + ".bak"):
        atomic_write(streaming_path + ".bak", Path(streaming_path).read_bytes())

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
        Path(appid_path).write_text(f"{STEAM_APP_ID}\n", encoding="ascii")

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
        bundle_bytes, remote_tag = obtain_patch(
            repo, check_updates=self.config.get("auto_update", True),
            log=self.log_signal.emit, progress=self.progress_signal.emit)
        self.progress_signal.emit(50)

        # 3. 게임 YooAsset 캐시 점검 및 패치 적용
        cache_info = detect_yooasset_cache(game_dir)
        data_file = cache_info["data_file"]
        info_file = cache_info["info_file"]

        need_apply = False

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
                if (expected_crc.encode('ascii') not in Path(info_file).read_bytes()
                        or binascii.crc32(Path(data_file).read_bytes()) & 0xFFFFFFFF != binascii.crc32(bundle_bytes) & 0xFFFFFFFF):
                    self.log_signal.emit("⚠️ YooAsset __info 메타데이터 불일치 감지. 자동 재동기화 진행.")
                    need_apply = True

        streaming_file = cache_info["streaming_bundle"]
        if not os.path.exists(streaming_file) or Path(streaming_file).read_bytes() != bundle_bytes:
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

        self.config["current_patch_version"] = remote_tag.lstrip("v")
        save_config(self.config)
        self.progress_signal.emit(100)
        self.status_signal.emit(f"● 한글 패치 적용 확인 (v{self.config.get('current_patch_version', '1.0')})", "#43b581")
        self.log_signal.emit("🟢 모든 점검 완료! [게임 시작] 버튼을 누르시면 오버필드가 실행됩니다.")
        self.finished_signal.emit(True, "READY")

    def do_force_patch(self, game_dir):
        self.log_signal.emit("🚀 최신 한글 패치 강제 다운로드 및 재적용 시작...")
        self.progress_signal.emit(20)

        repo = self.config.get("github_repo", DEFAULT_GITHUB_REPO).strip()
        bundle_bytes, remote_tag = obtain_patch(
            repo, force=True, log=self.log_signal.emit, progress=self.progress_signal.emit)
        self.progress_signal.emit(70)
        crc_hex, fsize = apply_bundle_to_game(game_dir, bundle_bytes)
        self.config["current_patch_version"] = remote_tag.lstrip("v")
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
            atomic_write(target, Path(backup).read_bytes())
        self.progress_signal.emit(100)
        self.log_signal.emit("백업 파일 복구 완료. 백업이 순정인지 여부는 Steam 무결성 검사로 확인할 수 있습니다.")
        self.status_signal.emit("● 패치 적용 전 백업으로 복구됨", "#f0b232")
        self.finished_signal.emit(True, "RESTORE_DONE")

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

        try:
            validate_game_executable(exe)
        except (OSError, ValueError) as error:
            self.log(f"❌ 게임 실행 파일 확인 실패: {error}")
            QMessageBox.warning(self, "실행 오류", f"{error}\n게임 설치 경로와 Steam 파일 무결성을 확인해주세요.")
            return

        if self.is_game_running():
            self.log("ℹ️ 오버필드가 이미 실행 중입니다.")
            QMessageBox.information(self, "알림", "오버필드가 이미 실행 중입니다.")
            return

        self.log("🚀 오버필드(OverField) 게임을 실행합니다...")
        self.start_btn.setEnabled(False)
        self.start_btn.setText("실행 중...")

        try:
            appid_file = os.path.join(game_dir, "steam_appid.txt")
            if not os.path.exists(appid_file):
                with open(appid_file, "w", encoding="ascii") as stream:
                    stream.write(f"{STEAM_APP_ID}\n")
            subprocess.Popen([exe, *sys.argv[2:]] if len(sys.argv) > 1 and os.path.basename(sys.argv[1]).lower() == "launcher.exe" else [exe], cwd=game_dir)
            self.log("🎮 오버필드 실행 요청을 전달했습니다!")
        except Exception as e:
            self.log(f"❌ 게임 실행 실패: {e}")
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
