"""
OverField 한국어/일본어 번역 및 한글패치 제작 GUI 툴 (PyQt6)
- 원클릭 DeepL / 자동 번역 연동 및 게임 공식 고유명사 치환 지원
"""

import os
import sys
import json
import re
import webbrowser
import urllib.parse
import requests

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTableView, QTextEdit, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QMessageBox, QStatusBar, QHeaderView, QFrame,
    QInputDialog
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QFont, QColor, QKeySequence, QShortcut

import patch_core

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

# OverField 공식 고유명사 자동 보정 사전
GAME_GLOSSARY = {
    "サルベージャー": "프론티어",
    "살베이저": "프론티어",
    "샐비저": "프론티어",
    "ロータラボラトリー": "로타 연구소",
    "ロータラボ": "로타 연구소",
    "ロータ": "로타",
    "로타연구소": "로타 연구소",
    "灰物": "변이체",
    "하이부츠": "변이체",
    "잿물": "변이체",
    "フェイ": "페이",
    "詩": "시",
    "ファンティーヌ": "팡틴",
    "エテリウム": "에테리움",
    "インリウム": "인리움",
    "イン元素": "인리움",
    "シュタイン": "슈타인",
    "ステイン": "스테인",
    "異変": "변이",
    "ラプラスツリー": "스타 트리"
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"deepl_api_key": ""}

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("설정 저장 실패:", e)

class TranslationTableModel(QAbstractTableModel):
    HEADERS = ["#", "테이블", "ID / 키", "화자 (JA)", "일본어 원문 (Reference)", "한국어 번역 (Translation)", "수정됨"]

    def __init__(self, items=None):
        super().__init__()
        self.all_items = items or []
        self.filtered_items = []
        self.apply_filter("", "전체", True, False)

    def rowCount(self, parent=QModelIndex()):
        return len(self.filtered_items)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        item = self.filtered_items[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(row + 1)
            elif col == 1:
                return f"T{item['table_id']}"
            elif col == 2:
                return item.get('key') or str(item['entry_id'])
            elif col == 3:
                return item.get('speaker_ja') or "-"
            elif col == 4:
                ja_preview = item.get('ja', '').replace('\n', ' ')
                return ja_preview[:80] + ("..." if len(ja_preview) > 80 else "")
            elif col == 5:
                ko_preview = item.get('ko', '').replace('\n', ' ')
                return ko_preview[:80] + ("..." if len(ko_preview) > 80 else "")
            elif col == 6:
                return "● 수정됨" if item.get('modified') else ""

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 6 and item.get('modified'):
                return QColor("#4CAF50")
            elif col == 4:
                return QColor("#BBDEFB")
            elif col == 5:
                return QColor("#FFFFFF")
            elif col in (1, 2, 3):
                return QColor("#B0BEC5")

        elif role == Qt.ItemDataRole.BackgroundRole:
            if item.get('modified'):
                return QColor("#1E382B")

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1, 6):
                return Qt.AlignmentFlag.AlignCenter

        return None

    def apply_filter(self, search_text, table_filter, hide_keys, only_modified):
        self.beginResetModel()
        search_lower = search_text.strip().lower()
        
        results = []
        for it in self.all_items:
            if table_filter and table_filter != "전체":
                m = re.search(r'Table\s*(\d+)', table_filter)
                if m:
                    t_id = int(m.group(1))
                    if it['table_id'] != t_id:
                        continue

            if hide_keys and it.get('is_key'):
                continue

            if only_modified and not it.get('modified'):
                continue

            if search_lower:
                match = (
                    search_lower in str(it['entry_id']) or
                    search_lower in it.get('key', '').lower() or
                    search_lower in it.get('speaker_ja', '').lower() or
                    search_lower in it.get('speaker_ko', '').lower() or
                    search_lower in it.get('ja', '').lower() or
                    search_lower in it.get('ko', '').lower()
                )
                if not match:
                    continue

            results.append(it)

        self.filtered_items = results
        self.endResetModel()

    def update_item_ko(self, row, new_ko):
        if 0 <= row < len(self.filtered_items):
            item = self.filtered_items[row]
            item['ko'] = new_ko
            item['modified'] = (item['ko'] != item['original_ko'])
            left = self.index(row, 5)
            right = self.index(row, 6)
            self.dataChanged.emit(left, right)
            return item
        return None

class TranslationEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OverField 한글패치 제작 & 일본어 대조 편집기")
        self.resize(1350, 870)
        self.current_row = -1
        self.settings = load_settings()

        self.init_data()
        self.init_ui()
        self.apply_dark_theme()

    def init_data(self):
        self.items = patch_core.load_translations_from_json()
        if not self.items:
            self.items = []
            QMessageBox.warning(self, "번역 데이터 필요", "translations.json 파일을 편집기와 같은 폴더에 넣어주세요.")

        for it in self.items:
            it['modified'] = (it.get('ko') != it.get('original_ko'))

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. 상단 툴바
        top_bar = QHBoxLayout()
        
        self.btn_save = QPushButton("💾 작업 저장 (Ctrl+S)")
        self.btn_save.clicked.connect(self.action_save)
        top_bar.addWidget(self.btn_save)

        self.btn_pack = QPushButton("🚀 게임에 적용 (번들 패킹)")
        self.btn_pack.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_pack.clicked.connect(self.action_pack)
        top_bar.addWidget(self.btn_pack)

        top_bar.addStretch()

        self.btn_api_settings = QPushButton("⚙️ DeepL API 키 설정")
        self.btn_api_settings.clicked.connect(self.action_configure_deepl)
        top_bar.addWidget(self.btn_api_settings)

        self.lbl_stats = QLabel(self.get_stats_text())
        self.lbl_stats.setStyleSheet("font-size: 13px; font-weight: bold; color: #4CAF50;")
        top_bar.addWidget(self.lbl_stats)

        main_layout.addLayout(top_bar)

        # 2. 필터 및 검색 바
        filter_bar = QHBoxLayout()
        
        filter_bar.addWidget(QLabel("테이블:"))
        self.combo_table = QComboBox()
        self.combo_table.setMinimumWidth(260)
        self.populate_tables()
        self.combo_table.currentIndexChanged.connect(self.on_filter_changed)
        filter_bar.addWidget(self.combo_table)

        filter_bar.addWidget(QLabel("검색:"))
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("ID, 화자, 일본어 또는 한국어 텍스트 검색...")
        self.edit_search.textChanged.connect(self.on_filter_changed)
        filter_bar.addWidget(self.edit_search)

        self.chk_hide_keys = QCheckBox("식별자(Key) 숨기기")
        self.chk_hide_keys.setChecked(True)
        self.chk_hide_keys.stateChanged.connect(self.on_filter_changed)
        filter_bar.addWidget(self.chk_hide_keys)

        self.chk_only_mod = QCheckBox("수정된 항목만")
        self.chk_only_mod.stateChanged.connect(self.on_filter_changed)
        filter_bar.addWidget(self.chk_only_mod)

        main_layout.addLayout(filter_bar)

        # 3. 메인 스플리터 (좌: 목록 테이블, 우: 상세 편집기)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 좌측: 목록 테이블
        self.model = TranslationTableModel(self.items)
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.setColumnWidth(0, 50)
        self.table_view.setColumnWidth(1, 60)
        self.table_view.setColumnWidth(2, 130)
        self.table_view.setColumnWidth(3, 90)
        self.table_view.setColumnWidth(4, 280)
        self.table_view.setColumnWidth(5, 280)
        self.table_view.setColumnWidth(6, 80)
        self.table_view.selectionModel().currentRowChanged.connect(self.on_row_selected)
        splitter.addWidget(self.table_view)

        # 우측: 상세 편집 패널
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(6)

        self.lbl_info = QLabel("항목을 선택하세요.")
        self.lbl_info.setStyleSheet("font-size: 13px; font-weight: bold; color: #90CAF9;")
        right_layout.addWidget(self.lbl_info)

        # 일본어 원문 섹션
        ja_header = QHBoxLayout()
        ja_header.addWidget(QLabel("🇯🇵 일본어 원문 (Reference):"))
        ja_header.addStretch()
        
        self.btn_copy_ja = QPushButton("일본어 복사")
        self.btn_copy_ja.clicked.connect(self.action_copy_ja)
        ja_header.addWidget(self.btn_copy_ja)

        self.btn_deepl_web = QPushButton("웹 DeepL 열기")
        self.btn_deepl_web.clicked.connect(self.action_open_deepl_web)
        ja_header.addWidget(self.btn_deepl_web)
        right_layout.addLayout(ja_header)

        self.text_ja = QTextEdit()
        self.text_ja.setReadOnly(True)
        self.text_ja.setStyleSheet("background-color: #1e2630; color: #E0E0E0; font-size: 14px; line-height: 1.4;")
        self.text_ja.setMaximumHeight(150)
        right_layout.addWidget(self.text_ja)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        right_layout.addWidget(line)

        # 한국어 편집 섹션 & 원클릭 번역 버튼
        ko_header = QHBoxLayout()
        ko_header.addWidget(QLabel("🇰🇷 한국어 번역 (Korean Edit):"))
        ko_header.addStretch()

        self.btn_fetch_trans = QPushButton("⚡ 원클릭 번역 가져오기 (Ctrl+T)")
        self.btn_fetch_trans.setStyleSheet("background-color: #0288D1; color: white; font-weight: bold; padding: 4px 10px;")
        self.btn_fetch_trans.clicked.connect(self.action_fetch_translation)
        ko_header.addWidget(self.btn_fetch_trans)

        self.btn_revert = QPushButton("원문 복구")
        self.btn_revert.clicked.connect(self.action_revert)
        ko_header.addWidget(self.btn_revert)
        right_layout.addLayout(ko_header)

        self.text_ko = QTextEdit()
        self.text_ko.setStyleSheet("background-color: #21252b; color: #FFFFFF; font-size: 14px; line-height: 1.4;")
        self.text_ko.textChanged.connect(self.on_ko_text_edited)
        right_layout.addWidget(self.text_ko)

        # 하단 작업 버튼
        btn_action_layout = QHBoxLayout()
        self.btn_prev = QPushButton("▲ 이전 (Alt+Up)")
        self.btn_prev.clicked.connect(self.action_prev_row)
        btn_action_layout.addWidget(self.btn_prev)

        self.btn_apply_next = QPushButton("✓ 저장 후 다음으로 (Ctrl+Enter)")
        self.btn_apply_next.setStyleSheet("background-color: #1565C0; color: white; font-weight: bold; padding: 8px;")
        self.btn_apply_next.clicked.connect(self.action_apply_and_next)
        btn_action_layout.addWidget(self.btn_apply_next)

        self.btn_next = QPushButton("▼ 다음 (Alt+Down)")
        self.btn_next.clicked.connect(self.action_next_row)
        btn_action_layout.addWidget(self.btn_next)

        right_layout.addLayout(btn_action_layout)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)
        main_layout.addWidget(splitter)

        # 상태바
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("준비 완료. [Ctrl+T]로 원클릭 번역을 가져오거나 [Ctrl+Enter]로 이동하세요.")

        # 단축키 설정
        QShortcut(QKeySequence("Ctrl+S"), self, self.action_save)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.action_apply_and_next)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self.action_apply_and_next)
        QShortcut(QKeySequence("Ctrl+T"), self, self.action_fetch_translation)
        QShortcut(QKeySequence("Alt+Up"), self, self.action_prev_row)
        QShortcut(QKeySequence("Alt+Down"), self, self.action_next_row)

        if self.model.rowCount() > 0:
            self.table_view.selectRow(0)

    def populate_tables(self):
        self.combo_table.clear()
        self.combo_table.addItem("전체")
        
        table_counts = {}
        for it in self.items:
            table_counts[it['table_id']] = table_counts.get(it['table_id'], 0) + 1

        table_descs = {
            46: "★ 메인스토리 & 퀘스트 대화 / 나레이션 (수정 필수)",
            1: "아이템 / 스탯 / 재화 도감 (품질 양호)",
            7: "스킬 및 버프 설명 (품질 양호)",
            14: "친구 / 소셜 시스템",
            17: "UI 시스템 텍스트",
            20: "공지 및 편지",
            23: "미션 및 업적",
            30: "가챠 / 상점",
            33: "생활 및 필드 오브젝트",
            57: "튜토리얼 및 안내",
            63: "미니게임 이벤트 안내 (중국어 잔존)"
        }

        for t_id in sorted(table_counts.keys()):
            desc = table_descs.get(t_id, "기타 텍스트")
            self.combo_table.addItem(f"Table {t_id:02d} ({desc}) [{table_counts[t_id]:,}개]")

        # 기본 선택을 Table 46 (스토리 대화)로 설정
        for idx in range(self.combo_table.count()):
            if "Table 46" in self.combo_table.itemText(idx):
                self.combo_table.setCurrentIndex(idx)
                break

    def get_stats_text(self):
        total = len(self.items)
        modified = sum(1 for x in self.items if x.get('modified'))
        return f"전체: {total:,}개 | 수정됨: {modified:,}개"

    def update_stats(self):
        self.lbl_stats.setText(self.get_stats_text())

    def on_filter_changed(self):
        search = self.edit_search.text()
        tbl = self.combo_table.currentText()
        hide_keys = self.chk_hide_keys.isChecked()
        only_mod = self.chk_only_mod.isChecked()
        self.model.apply_filter(search, tbl, hide_keys, only_mod)
        if self.model.rowCount() > 0:
            self.table_view.selectRow(0)
        else:
            self.clear_editor()

    def on_row_selected(self, current, previous):
        if not current.isValid():
            return
        row = current.row()
        self.current_row = row
        item = self.model.filtered_items[row]

        spk_ja = item.get('speaker_ja') or "없음"
        spk_ko = item.get('speaker_ko') or "없음"
        key_name = item.get('key') or str(item['entry_id'])
        self.lbl_info.setText(
            f"테이블: Table {item['table_id']} | 식별자: {key_name} | "
            f"화자: {spk_ja} ({spk_ko})"
        )

        self.text_ja.setPlainText(item.get('ja', ''))

        self.text_ko.blockSignals(True)
        self.text_ko.setPlainText(item.get('ko', ''))
        self.text_ko.blockSignals(False)

        status_mod = "수정됨" if item.get('modified') else "원본 유지"
        self.status_bar.showMessage(f"선택: #{row+1} / {self.model.rowCount()} [{status_mod}]")

    def on_ko_text_edited(self):
        if self.current_row < 0 or self.current_row >= len(self.model.filtered_items):
            return
        new_text = self.text_ko.toPlainText()
        self.model.update_item_ko(self.current_row, new_text)
        self.update_stats()

    def clear_editor(self):
        self.current_row = -1
        self.lbl_info.setText("표시할 항목이 없습니다.")
        self.text_ja.clear()
        self.text_ko.blockSignals(True)
        self.text_ko.clear()
        self.text_ko.blockSignals(False)

    def action_fetch_translation(self):
        """
        현재 선택된 일본어 텍스트를 DeepL / 고속 번역 엔진으로 가져와 한국어 입력창에 적용합니다.
        공식 게임 고유명사 치환 규칙을 자동 적용합니다.
        """
        if self.current_row < 0 or self.current_row >= len(self.model.filtered_items):
            return

        ja_text = self.text_ja.toPlainText().strip()
        if not ja_text:
            return

        api_key = self.settings.get("deepl_api_key", "").strip()
        self.status_bar.showMessage("번역 요청 중...")
        QApplication.processEvents()

        translated = ""
        engine_name = "DeepL" if api_key else "자동 번역기"

        # 1. DeepL API 키가 있으면 DeepL 우선 시도
        if api_key:
            try:
                from deep_translator import DeeplTranslator
                is_free = api_key.endswith(":fx")
                translator = DeeplTranslator(api_key=api_key, source="ja", target="ko", use_free_api=is_free)
                translated = translator.translate(ja_text)
            except Exception as e:
                self.status_bar.showMessage(f"DeepL API 오류: {e} (무료 엔진으로 전환)")
                translated = ""

        # 2. DeepL 실패 또는 키가 없으면 고속 무료 엔진 사용
        if not translated:
            try:
                url = "https://translate.googleapis.com/translate_a/single"
                params = {"client": "gtx", "sl": "ja", "tl": "ko", "dt": "t", "q": ja_text}
                headers = {"User-Agent": "Mozilla/5.0"}
                r = requests.get(url, params=params, headers=headers, timeout=5)
                translated = "".join(x[0] for x in r.json()[0])
            except Exception as e:
                QMessageBox.warning(self, "번역 실패", f"번역 엔진 연결 오류: {e}")
                return

        # 3. 고유명사 사전 자동 치환
        for src, dst in GAME_GLOSSARY.items():
            translated = translated.replace(src, dst)

        # 4. 한국어 텍스트박스에 반영
        self.text_ko.setPlainText(translated)
        self.on_ko_text_edited()
        self.status_bar.showMessage(f"[{engine_name}] 번역 완료 (고유명사 보정 적용됨)", 3000)

    def action_configure_deepl(self):
        cur_key = self.settings.get("deepl_api_key", "")
        key, ok = QInputDialog.getText(
            self, "DeepL API 키 설정",
            "DeepL API 인증키를 입력하세요:\n(무료 키는 뒷자리가 :fx로 끝납니다. 비워두면 기본 무료 엔진으로 동작합니다)",
            QLineEdit.EchoMode.Normal, cur_key
        )
        if ok:
            self.settings["deepl_api_key"] = key.strip()
            save_settings(self.settings)
            msg = "DeepL API 키가 저장되었습니다!" if key.strip() else "API 키가 해제되어 기본 무료 엔진을 사용합니다."
            QMessageBox.information(self, "설정 저장", msg)

    def action_apply_and_next(self):
        self.action_next_row()

    def action_prev_row(self):
        if self.current_row > 0:
            self.table_view.selectRow(self.current_row - 1)

    def action_next_row(self):
        if self.current_row < self.model.rowCount() - 1:
            self.table_view.selectRow(self.current_row + 1)

    def action_revert(self):
        if self.current_row < 0 or self.current_row >= len(self.model.filtered_items):
            return
        item = self.model.filtered_items[self.current_row]
        orig = item.get('original_ko', '')
        self.text_ko.setPlainText(orig)
        self.on_ko_text_edited()
        self.status_bar.showMessage("원문으로 되돌렸습니다.")

    def action_copy_ja(self):
        ja = self.text_ja.toPlainText()
        if ja:
            QApplication.clipboard().setText(ja)
            self.status_bar.showMessage("일본어 원문이 클립보드에 복사되었습니다.", 2000)

    def action_open_deepl_web(self):
        ja = self.text_ja.toPlainText()
        if not ja:
            return
        url = f"https://www.deepl.com/translator#ja/ko/{urllib.parse.quote(ja)}"
        webbrowser.open(url)

    def action_save(self):
        patch_core.save_translations_to_json(self.items)
        self.update_stats()
        self.status_bar.showMessage(f"저장 완료: translations.json ({len(self.items):,}개 항목)", 3000)
        QMessageBox.information(self, "저장 완료", "작업 내용이 translations.json에 저장되었습니다.")

    def action_pack(self):
        patch_core.save_translations_to_json(self.items)
        reply = QMessageBox.question(
            self, "게임 번들 적용",
            "현재 작업한 한국어 번역을 게임 번들에 적용하시겠습니까?\n"
            "(원본 번들 파일은 .bundle.bak으로 자동 백업됩니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                mod_count = patch_core.pack_translations_to_bundle(self.items)
                QMessageBox.information(
                    self, "패킹 완료",
                    f"총 {mod_count:,}개의 수정된 문장이 게임 번들에 성공적으로 적용되었습니다!\n\n"
                    "게임을 실행하여 확인해보세요."
                )
            except Exception as e:
                QMessageBox.critical(self, "오류", f"번들 패킹 실패: {e}")

    def apply_dark_theme(self):
        dark_qss = """
        QMainWindow, QWidget {
            background-color: #1e1e24;
            color: #dcdcdc;
            font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
        }
        QTableView {
            background-color: #16161a;
            alternate-background-color: #1b1b20;
            gridline-color: #2b2b36;
            selection-background-color: #2b4c7e;
            selection-color: #ffffff;
            border: 1px solid #333340;
            font-size: 13px;
        }
        QHeaderView::section {
            background-color: #262630;
            color: #cfd8dc;
            padding: 5px;
            border: 1px solid #333340;
            font-weight: bold;
        }
        QLineEdit, QComboBox, QTextEdit {
            background-color: #262630;
            color: #ffffff;
            border: 1px solid #3d3d4d;
            border-radius: 4px;
            padding: 5px;
        }
        QLineEdit:focus, QTextEdit:focus {
            border: 1px solid #2196F3;
        }
        QPushButton {
            background-color: #2d3748;
            color: #ffffff;
            border: 1px solid #4a5568;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #3b475a;
        }
        QPushButton:pressed {
            background-color: #1a202c;
        }
        QCheckBox {
            spacing: 5px;
        }
        QStatusBar {
            background-color: #16161a;
            color: #9e9e9e;
            border-top: 1px solid #2b2b36;
        }
        """
        self.setStyleSheet(dark_qss)

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    window = TranslationEditorWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
