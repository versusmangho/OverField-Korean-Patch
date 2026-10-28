# 오버필드 비공식 한국어 패치

스토리·아이템·스킬·장비 설명과 미니게임 안내를 한국어로 개선하는 팬 패치입니다.

## v1.1.0 — 번역 교정본

[최신 릴리스 다운로드](https://github.com/versusmangho/OverField-Korean-Patch/releases/latest)

Table **1, 7, 17, 20, 46, 63**의 번역 필드 **3,413개**를 수정하고 화자 메타데이터 **2,509개**를 통일했습니다. 잘린 대사, 인명·말투·용어, 스킬 조건·수치·회복 기준, 치환자 서식 등을 교정했습니다.

전체 문장을 전수 윤문한 완료본은 아닙니다. 추가 검토 후보 252건은 오탐과 원문 자체의 임시 설명을 포함합니다. 게임·런처 실제 실행 검증은 생략했으며, 번역 데이터 대조와 EXE 빌드만 확인했습니다. 향후 게임 업데이트에 따른 번들 구조 호환성은 별도로 확인해야 합니다.

- [인물별 특징·말투·용어 기준](translation_review/CHARACTER_STYLE.md)
- [원문 대사 근거](translation_review/speaker_evidence.md)
- [테이블별 교정 범위와 확인 내역](translation_review/review_report.md)
- [행별 변경 기록](translation_review/changes.json)
- [추가 검토 후보](translation_review/needs_review.json)
- [변경 이력](CHANGELOG.md)

## 설치 — 다운로드형 런처 (현재 로컬 개발본)

`OverFieldLauncher.exe` 하나만 게임 폴더와 별도 폴더에 두고 실행합니다. 번역 데이터는 내장하지 않고 GitHub 최신 정식 릴리스에서 내려받습니다. 최초 실행에는 인터넷이 필요합니다.

설정과 검증된 다운로드 캐시는 `%LOCALAPPDATA%/OverFieldKoreanPatch`에 저장합니다. EXE 옆의 `patch_payload.dat`와 `launcher_config.json`은 읽지 않습니다. 자동 업데이트를 끄면 마지막 다운로드 캐시를 사용하며, 캐시가 없을 때는 처음 한 번 다운로드합니다.

게임 경로는 Steam에서 감지하거나 직접 지정할 수 있습니다. 게임을 종료한 뒤 패치를 적용하세요. 로컬 교정본은 GitHub에 별도로 게시하기 전까지 다운로드 대상에 포함되지 않습니다.

위 설명은 현재 소스의 미게시 변경입니다. 기존 v1.1.0 배포 EXE의 동작과 구별해 주세요.

## 설치 — 수동 복사

릴리스의 `OverField_Korean_Patch_review_2026-10-28.zip`을 압축 해제하고, 게임을 종료한 상태에서 포함된 `launcher_Data`를 게임 설치 폴더에 복사합니다.

기본 설치 위치는 Steam의 `steamapps/common/OverField`입니다.

수동 패키지에는 번역 기준과 교정 내역도 포함되어 있습니다. 각 파일의 SHA-256은 릴리스의 `SHA256SUMS.txt`에서 확인할 수 있습니다.

## 번역 편집 및 개발

번역 원본은 `translations.json`입니다. 수정 전에 [번역 기준](translation_review/CHARACTER_STYLE.md)과 [AGENTS.md](AGENTS.md)를 읽어 주세요. 실제 번들의 `String_Japanese`와 편집용 `ja`가 다른 경우 번들 원문을 우선합니다. 인물의 정체나 미완성 스킬 효과를 추측해 채우지 않습니다.

```powershell
python -m pip install -r requirements-build.txt
python translator_gui.py
```

편집기는 번역 JSON을 저장합니다. 번들 적용 버튼은 설치된 게임 파일을 변경하므로 작업 전 백업을 유지해 주세요. 이전 CSV/XLSX를 다시 가져오면 교정 내용이 되돌아갈 수 있습니다.

### 런처 빌드

릴리스에서 `patch_payload.dat`를 내려받아 소스 루트에 둔 뒤 빌드합니다.

```powershell
python -m PyInstaller --noconfirm OverFieldLauncher.spec
```

결과는 `dist/OverFieldLauncher.exe`입니다. EXE·패치 페이로드·수동 설치 ZIP은 GitHub Releases에서 배포하며 소스 트리에는 중복 보관하지 않습니다.

### 이번 교정 과정 재현

릴리스의 선택적 개발 자료 `translation_review_baseline_2026-10-28.zip`을 저장소 루트에 압축 해제합니다. 작업 직전 JSON과 페이로드가 `translation_review`에 들어갑니다.

```powershell
python translation_review/apply_review.py
python translation_review/build_reviewed_payload.py
python translation_review/audit_review.py
```

이 도구들은 JSON 교정, 페이로드 생성 및 정적 데이터 대조를 수행하며 게임이나 GUI 런처를 실행하지 않습니다. `apply_review.py`는 작업 직전 백업을 기준으로 재생성하므로 이후 수작업 수정이 있다면 먼저 따로 보관해야 합니다. 생성한 `reviewed_payload.dat`를 자동으로 게임에 설치하지는 않습니다.

## Steam 시작 옵션 — 선택 사항

게임 설치 경로에 맞게 `"게임 설치 폴더/OverFieldLauncher.exe" %command%`를 지정할 수 있습니다. 런처는 원래 게임 실행 파일을 직접 호출해 Steam 시작 옵션으로 다시 진입하는 순환을 피합니다.

## 안내 및 권리

- 본 패치는 비공식 팬 메이드 프로젝트이며 무료로 배포됩니다.
- 게임과 리소스의 권리는 원 개발사 EKONEKO Studio에 있습니다.
- 본 패치의 상업적 이용, 유료 판매 및 재배포를 금지합니다.
- 권리사의 요청이 있으면 배포를 중단할 수 있습니다.
- 초기 번역·코드에 Gemini를 사용했으며, 이번 교정과 런처 정리에는 Codex를 사용했습니다.
