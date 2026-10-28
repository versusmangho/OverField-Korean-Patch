# 한글패치 작업 규칙

- 실제 프로그램을 돌려 검증하는 것은 사용자의 명시적 지시가 없는 한 생략한다.
- 실제 동작을 검증하지 않은 변경은 로컬 Git 커밋까지만 허용한다. 푸시하거나 GitHub 릴리스를 생성·수정하지 않는다. 사용자가 실행 검증과 게시를 명시적으로 요청하면 검증이 통과한 결과만 게시한다.
- Table 1, 7, 17, 20, 46, 63의 번역을 수정하기 전에 `translation_review/CHARACTER_STYLE.md`를 읽는다. 화자별 원문 근거는 `translation_review/speaker_evidence.md`에 있다.
- 실제 번들의 `String_Japanese`를 원문 기준으로 삼고 `translations.json`의 `ja`와 대조한다. 일부는 중국어다. 원문 차이는 `translation_review/source_overrides.json`에 기록한다. 기존 한국어만 보고 윤문하지 않는다.
- 인물 설정·정체·호칭을 추측하지 않는다. 효과 수치·고정값/비율·조건·주체와 치환자·태그를 보존한다.
- `original_ko` 및 다른 테이블, 키·UID·인덱스를 변경하지 않는다. 번역 본문 변경 시 `modified`를 설정한다.
- 번역 원본 JSON과 변경 전 백업을 보존한다. 이름/용어 자동 통일과 직접 문장 검토를 구분해 보고한다.
- 기존 스프레드시트는 이번 교정 이전 버전일 수 있다. 덮어쓰기 가져오기 전에 JSON과 차이를 확인한다.
- 한글패치 작업 위치는 `C:\Program Files (x86)\Steam\steamapps\common\OverField-Korean-Patch\작업자료`이다. 게임 폴더에는 패치 소스·배포 파일을 다시 만들지 않는다. 사용자 실행 파일은 그 상위 폴더의 `OverFieldLauncher.exe` 하나이며 번역은 GitHub에서 받는다.
