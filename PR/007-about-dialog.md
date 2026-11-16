# PR 007: 작업 프로그램 "프로그램 정보" (버전 · 저장소 링크)

| 항목 | 내용 |
|---|---|
| 상태 | 병합됨 (2026-11-16, GitHub PR #16, 사용자 지시: Windows 검증 통과 시 병합) |
| 브랜치 | `claude/about-dialog` → `main` |
| 기준 커밋 | main `b91be82` (0.6.0) |
| 최신 커밋 | 브랜치 최신 |
| 관련 문서 | [README](../README.md) §알아 둘 것, [REFACTORING](../docs/REFACTORING.md) R12 |

> **작성 경위**: 2026-11-16 사용자 요청. "퀵 임포징 도구 메뉴에 프로그램 정보 항목을 추가하고, 클릭했을 때 뜨는 창에 버전 정보와 저장소 주소 링크." 리팩토링 제안서 R12(화면에 버전이 안 보임)를 이 기능으로 처리했다. 버전 0.7.0.

## 구현 요약

- 작업 프로그램 `도구(&T)` 메뉴 맨 아래(구분선 뒤)에 `프로그램 정보(&A)…`.
- 창 내용: 프로그램 아이콘, "퀵 임포징 — 작업", `버전 <버전>`, 저장소 링크 `https://github.com/steves460ng/quick-imposing`(누르면 기본 브라우저로 열림).
- 버전 찾는 순서(`common.app_version`):
  1. 배포본(exe): exe 옆 `VERSION.txt`(`build.ps1`이 `pyproject.toml`의 버전으로 씀)
  2. 소스 실행: 저장소의 `pyproject.toml`(버전을 올리고 다시 설치하지 않아도 맞게 나온다)
  3. 설치된 패키지 정보
  4. 모두 없으면 "알 수 없음"
- 템플릿 편집기에는 메뉴가 없어 넣지 않았다.

## 실행 방법 · 결과 요약

| 검증 | 결과 |
|---|---|
| `python -m pytest -q` | **131 passed** (기준 126, 새 테스트 5: `tests/test_about.py`) |
| `ruff check --select F imposing tests` | 문제 없음 |
| 화면 캡처 | 확인함 |

새 테스트: 소스 실행 버전 = `pyproject.toml`, 배포본은 `VERSION.txt`(`sys.frozen` 흉내), 버전을 못 찾으면 "알 수 없음", 창의 제목 · 버전 · 링크 · 링크 클릭 가능 설정, 메뉴 항목으로 창이 뜸.

Windows 검증 통과 (2026-11-16): [실행 43832325979](https://github.com/steves460ng/quick-imposing/actions/runs/43832325979)(`19ce58b`) 전 단계 성공(pytest, 실행기, 한글 경로, GUI 시작 점검, 배포 빌드와 시작 점검, PowerShell 5.1). 배포본에서 `VERSION.txt`를 실제로 읽는지는 배포 폴더에서 메뉴를 눌러 확인할 항목이다(시작 점검은 메뉴를 열지 않는다).

## 질문

없음.

---

## 검토

## 수정 내역
