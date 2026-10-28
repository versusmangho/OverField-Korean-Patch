# 오버필드 한글패치 작업 폴더

사용자 실행 파일은 상위 폴더의 `OverFieldLauncher.exe` 하나다. 게임 설치 폴더와 분리해서 사용한다.

## 다운로드형 런처

- 번역 데이터는 EXE에 내장하지 않는다. 최초 실행 때 GitHub 최신 정식 릴리스의 `patch_payload.dat`를 받는다.
- 설정은 `%LOCALAPPDATA%/OverFieldKoreanPatch/launcher_config.json`에 보관한다.
- 패치는 같은 사용자 폴더 아래 저장소별 캐시에 SHA-256으로 구분해 보관한다.
- EXE 옆의 JSON/DAT, 작업 폴더의 DAT, 예전 수동 패치 폴더는 읽지 않는다.
- 자동 업데이트를 꺼도 캐시가 없으면 최초 다운로드가 필요하다. 통신 실패 시 검증된 이전 다운로드 캐시가 있으면 사용한다.
- GitHub 태그와 SHA-256을 함께 확인하므로 같은 태그의 교체된 에셋도 구별한다. 게시 시점이 더 오래된 릴리스로는 자동으로 되돌리지 않는다.
- 게임 경로는 Steam에서 감지하거나 런처 설정에서 지정한다. 편집 도구도 이 게임 경로와 현재 YooAsset 캐시 경로를 사용한다.

## 소스와 백업

이 폴더에는 소스, 번역 JSON, 검토 기록, 기존 배포본, 구형 EXE 및 백업을 보존한다. 예전 EXE는 보관용으로 확장자를 `.disabled`로 바꾼다.
`translation_review`의 교정본은 작업 자료이며 GitHub에 게시되기 전까지 다운로드형 런처에 배포되지 않는다.
과거 일회성 파이프라인은 `_patch_archive`에 보존하며 현재 설치 절차로 사용하지 않는다.

## 빌드와 확인

```powershell
python -m unittest test_launcher_data test_launcher_flow -v
python -m PyInstaller --clean --noconfirm OverFieldLauncher.spec
```

생성 결과는 `dist/OverFieldLauncher.exe` 한 파일이다. `patch_payload.dat`와 `launcher_config.json`을 함께 복사하지 않는다.
단위 테스트는 임시 폴더에서 다운로드·캐시·버전·적용·복구 코드를 확인하며 Qt 창이나 게임을 실행하지 않는다.
이번 작업에서는 실제 GitHub v1.1.0 다운로드도 임시 폴더에서 확인했다. EXE 창과 게임을 실행한 검증은 하지 않았다.
실제 동작을 검증하지 않은 변경은 GitHub에 푸시하거나 릴리스하지 않는다.

## 진행 중 번역 표본 검토

`translation_review/ten_by_five/status.json`에 10개씩 검사하고 5회 연속 무오류일 때 중단하는 진행 상태를 보존했다.
다운로드형 런처 정리 요청으로 전환되기 전 1회차에서 8건의 오류를 발견했다. 연속 통과는 0/5이며 완료 상태가 아니다.
