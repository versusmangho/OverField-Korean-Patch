# 교정본 사용 안내

- 루트 patch_payload.dat는 reviewed_payload.dat와 같은 교정본입니다.
- OverFieldLauncher.exe에도 교정본을 내장하도록 다시 빌드합니다. 다음 실행 시 캐시를 비교해 적용합니다.
- 게임 설치 캐시와 StreamingAssets 파일은 이번 번역 작업에서 직접 덮어쓰지 않았습니다.
- 원격 릴리스가 로컬 교정본을 되돌리지 않도록 launcher_config.json의 auto_update를 false로 설정했습니다. 이전 설정은 launcher_config.before-review.json에 있습니다.
- 런처의 수동 다운로드/재적용 버튼은 원격 릴리스를 받을 수 있으므로 로컬 교정본 유지 시 사용하지 마세요. 로컬 교정본은 translation_review/reviewed_payload.dat에 보관되어 있습니다.
- 수동 설치 패키지: OverField_Korean_Patch_review_2026-10-28.zip. 게임 종료 후 패키지의 launcher_Data를 게임 폴더에 복사해도 됩니다.
- 이전 수동 설치 ZIP과 이전 EXE는 _patch_archive/2026-10-28에 보존했습니다. 작업 직전 페이로드는 patch_payload.before-review.dat에 있습니다.
- 기존 XLSX/CSV는 교정 이전 버전입니다. 재가져오기 전에 JSON과 비교해야 합니다.
- 게임·런처를 실제 실행한 검증은 생략했습니다.

## GitHub 게시 이후

v1.1.0을 정식 최신 릴리스로 게시했습니다. 로컬 설정은 current_patch_version=1.1.0, auto_update=true로 갱신했습니다. 위의 자동 업데이트 중지 안내는 공개 전 로컬 교정 단계의 기록입니다. 현재 원격 최신 페이로드는 이 교정본과 해시가 같습니다.

릴리스: https://github.com/versusmangho/OverField-Korean-Patch/releases/tag/v1.1.0
