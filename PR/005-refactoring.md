# PR 005: 리팩토링 1단계 (R1 · R3 · R5 오류 코드 · 경로 · 오류 형식 정리)

| 항목 | 내용 |
|---|---|
| 상태 | 검토 대기 |
| 브랜치 | `claude/refactor-stage1` → `main` |
| 기준 커밋 | `aadc2e6` (`docs/REFACTORING.md` 개정판, main `552c033` 기준) |
| 최신 커밋 | 브랜치 최신 (이 문서 기록 커밋 포함) |
| 관련 문서 | [REFACTORING](../docs/REFACTORING.md) §2 R1 · R3 · R5, [SPEC v0.6.2](../docs/SPEC.md) §6.4 · §9.3, [DEVELOPMENT](../docs/DEVELOPMENT.md) |

> **작성 경위**: 2026-11-16 사용자가 리팩토링 제안서 1단계 진행을 지시했다. 별도 브랜치로 작업했고 main에는 병합하지 않았다. 구현자(Claude)의 자기 점검만 거쳤으며, 독립 검토와 병합 승인은 사용자 몫이다.

## 구현 요약

항목별로 커밋을 나눴다.

| 커밋 | 항목 | 내용 |
|---|---|---|
| `65c2119` | R1 | `FontError`에 `code` · `context`를 둔다. 빠진 글자 → `FONT_GLYPH_MISSING`(빠진 글자를 `missing`에 기록), 임베드 금지 → `FONT_EMBED_FORBIDDEN`, 이름 기반 CFF → `FONT_UNSUPPORTED`. 엔진은 코드를 그대로 기록하고, 작업 프로그램 `describe_error`는 영문 문장 검사 없이 코드로 문구를 고른다 |
| `1c739a6` | R3 | `model.relative_file(path, folder)` 하나로 자동 배열 · `generate()` · `Session.to_project()`의 상대경로 계산을 합쳤다. 다른 드라이브면 `PathError("DIFFERENT_DRIVE")`. `build` · `autofill`은 이 코드를 기록하고 PDF · 프로젝트를 만들지 않는다 |
| `78c1be9` | R5 | 모든 오류 항목을 `{code, reason, field?, …}`로 통일. 형식 검사 오류의 `reason`은 `"<field>: <규칙>"` 영문. `generate()`의 `fail()`이 `reason`을 필수로 받아 `TEMPLATE_NOT_FOUND` · `CELL_NOT_IN_TEMPLATE` · `INPUT_CHANGED`에도 사유가 붙는다. 자동 배열은 `model` 오류를 다시 감싸지 않고 그대로 쓴다 |
| (기록 커밋) | — | 버전 0.5.2, SPEC v0.6.2 변경 이력, `REFACTORING.md` 진행 상황, 이 문서 |

## 동작 변화

화면 흐름과 PDF 결과는 바뀌지 않는다. 바뀌는 것은 리포트 내용과 오류 안내 문구 일부다.

| 대상 | 이전 | 이후 |
|---|---|---|
| 글꼴에 없는 글자 · 임베드 금지 글꼴(리포트) | `SCHEMA_INVALID` + 영문 사유 | `FONT_GLYPH_MISSING` / `FONT_EMBED_FORBIDDEN` + `font`(, `missing`) |
| 이름 기반 CFF 글꼴(리포트 · 화면) | `SCHEMA_INVALID`, 화면은 "입력을 처리할 수 없습니다" + 영문 | `FONT_UNSUPPORTED`, 화면은 "지원하지 않는 형식의 글꼴입니다 … TrueType 또는 CID 방식 글꼴로 바꾸세요" |
| 빠진 글자 · 임베드 금지(화면) | 같은 한국어 문구 | 같음 |
| 다른 드라이브: 명령행 `autofill` | `SCHEMA_INVALID` + 파이썬 예외 문장 | `DIFFERENT_DRIVE` |
| 다른 드라이브: 명령행 `build` | 처리 안 된 `ValueError`로 종료(리포트 없음) | `DIFFERENT_DRIVE` 리포트, 종료 코드 1 |
| 다른 드라이브: 작업 프로그램 | 한국어 안내 | 같음 |
| 형식 검사 오류 항목 | `{code, field}` | `{code, reason, field}` (`field` 유지) |
| 자동 배열 형식 오류 `reason` | `"Invalid field: <field>"` | `"<field>: <규칙>"` |

파일 형식(`template@2` · `project@1`)은 바뀌지 않았다.

## 실행 방법 · 결과 요약

Linux(Python 3.13, qpdf, poppler-utils, Noto Sans CJK KR, Qt offscreen)에서 실행했다.

| 검증 | 기준 커밋 | 이 브랜치 |
|---|---|---|
| `python -m pytest -q` | 99 passed | **113 passed** (추가 14) |
| `python test03_runner.py` | 10/10 PASS | 10/10 PASS |
| `python test32_runner.py` | 11/11 PASS, 회귀 10/10 | 11/11 PASS, 회귀 10/10 |
| `ruff check --select F imposing tests` | 문제 없음 | 문제 없음 |
| 결과 PDF 비교(두 실행기가 만든 PDF 29개, `qpdf --qdf --object-streams=disable --static-id` 정규화, `CreationDate` 제외) | — | **29개 모두 같음** |

추가한 테스트:
- `tests/test_font_errors.py`: fontTools로 만든 표본 글꼴(글자 부족, `fsType` 2, 이름 기반 CFF)로 `fonts.embed`의 코드, `generate()` 리포트 코드, 화면 문구를 확인한다.
- `tests/test_different_drive.py`: `os.path.relpath`를 Windows처럼 실패하는 함수로 바꿔 끼워 `relative_file`, `generate()`, `autofill()`, `Session.to_project()` · `save()`를 확인한다.
- `tests/test_project.py`: 형식 검사 오류 전부에 `field` · `reason`이 있는지, 엔진 오류(`TEMPLATE_NOT_FOUND`, `CELL_NOT_IN_TEMPLATE`)에 `reason`이 있는지.

**Windows 검증은 아직 하지 않았다.** `windows` 워크플로는 push 대상이 `ccr-**` · `release/**` 브랜치뿐이라 이 브랜치(`claude/…`) push로는 돌지 않는다. 병합 전에 GitHub Actions에서 이 브랜치를 골라 수동 실행(`workflow_dispatch`)하고 통과를 확인한다.

## 문서와 다르게 처리한 부분

- `describe_error`의 빠진 글자 · 임베드 금지 문구는 기존 한국어 문장을 그대로 썼다. 리포트에 `missing`(빠진 글자)이 생겼지만, 화면에 보여 주는 것은 화면 동작 변경이라 넣지 않았다.
- `DIFFERENT_DRIVE` 화면 문구를 `ERROR_TEXT`에 추가했다. 작업 프로그램은 `to_project()`에서 먼저 막으므로 지금은 쓰이지 않는 방어용이다.
- `generate()`의 다른 드라이브 검사는 원래 위치(PDF를 임시 폴더에 만든 뒤, 출력으로 옮기기 전)에 두었다. 앞으로 옮기면 실패가 빨라지지만 처리 순서가 바뀌므로 R4에서 함께 판단한다.
- `FONT_NOT_FOUND`를 내는 `fonts.resolve()`의 `FontError`에도 코드를 붙였다. 리포트 결과는 같다.

## 질문

1. 리포트에 기록하는 `missing`(빠진 글자)을 오류 안내 문구에도 보여 줄지. 보여 주면 사용자가 어떤 글자가 문제인지 바로 알 수 있다(화면 변경이라 별도 합의 필요).

---

## 검토

## 수정 내역
