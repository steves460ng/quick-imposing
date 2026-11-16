# 리팩토링 제안

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-16 |
| 기준 | main `5d4b8d9` (버전 0.5.1) |
| 상태 | **제안**. 사용자가 범위를 정하기 전에는 착수하지 않는다 |
| 개정 | 2026-11-16 코드 대조 검토 반영: R1 범위(CFF 오류) 추가, R2 우선순위 · 동작 변화 정정, R3 발생 경로 명시, R5 `reason` 언어 규칙, R8 완료 기준 범위, R10 주석 처리 범위, R12 별도 변경으로 분리 |
| 대상 독자 | 이 저장소에서 리팩토링을 맡는 다음 세션(사람 또는 에이전트) |
| 관련 문서 | `docs/SPEC.md`(배치 · 비변형 규칙), `docs/TEMPLATE-REQUIREMENTS.md`(요구사항), `docs/DEVELOPMENT.md`(실행 · 테스트), `docs/HANDOFF-2026-11-13.md`(현재 상태 · 빌드 절차), `PR/004-gui.md`(GUI 변경 기록) |

이 문서만 읽고 작업을 시작할 수 있도록 배경, 위치, 완료 기준, 검증 방법을 함께 적는다. 줄 번호는 기준 커밋 기준이며 바뀔 수 있으니 함수 이름으로 찾는다.

---

## 0. 배경과 원칙

### 프로젝트 요약

베이스 PDF 위에 카드 PDF(화면 용어 "데이터", 코드 · 내부 문서 용어 "B")를 템플릿의 셀에 배치해 인쇄용 판 PDF를 만드는 Windows 프로그램이다. 구성은 다음과 같다.

| 계층 | 파일 | 역할 |
|---|---|---|
| 형식 검사 · 셀 계산 | `imposing/model.py` | `template@2` · `project@1` 검사, 셀 좌표 |
| PDF 엔진 | `imposing/engine.py`, `imposing/pdf.py`, `imposing/fonts.py` | 배치 · 클리핑 · 텍스트 삽입 · 저장 · 검사 |
| 자동 배열 | `imposing/autofill.py` | 정렬, 채움 순서, 명령행 자동 배열 |
| 화면 없는 계층 | `imposing/store.py`, `imposing/session.py` | 템플릿 폴더 관리, 작업 편집 상태 |
| GUI | `imposing/gui/common.py`, `work.py`, `editor.py` | 미리보기, 작업 프로그램, 템플릿 편집기 |
| 명령행 | `imposing/__main__.py` | `create-template`, `build`, `autofill` |
| 배포 | `packaging/`, `.github/workflows/windows.yml` | PyInstaller 빌드, Windows 검증 |

### 지켜야 할 것

1. **PDF 결과가 바뀌면 안 된다.** 배치 행렬, `/BBox`, 원본 스트림 보존(SPEC R1~R11)은 3-1차 · 3-2차에서 독립 계산한 기대값으로 검증한 부분이다. 리팩토링 전후로 테스트 실행기 결과가 같아야 한다.
2. **파일 형식을 바꾸지 않는다.** `template@2`, `project@1`과 저장된 파일은 그대로 읽혀야 한다. 리포트(`.report.json`)는 사람이 읽는 기록이지만, 코드나 필드를 바꾸면 SPEC §6.4 · §9.3에 반영한다.
3. **화면 동작이 바뀌면 안 된다.** 사용자가 1차 베타(직접 사용 테스트)를 하고 있다. 동작이 바뀌는 변경은 리팩토링과 섞지 않고 따로 합의한다.
4. **한 번에 한 항목.** 항목마다 따로 커밋하고, 가능하면 따로 병합한다.

### 손대지 말 것

- `engine.geometry`(회전 · 중심 맞춤 행렬, `/BBox` 역변환)와 B 페이지를 Form XObject로 옮기는 처리. 4번을 하더라도 계산식은 옮기기만 하고 고치지 않는다.
- `template@2` · `project@1`의 키와 의미.

---

## 1. 제안 목록

| # | 항목 | 우선 | 동작 변화 | 규모 |
|---|---|---|---|---|
| R1 | 오류 종류를 영문 문장으로 구분하는 부분 | 높음 | 리포트 오류 코드 추가 | 작음 |
| R2 | 저장할 때 임시 프로젝트 파일을 거치는 구조 | 중간 | 리포트 `inputs` 목록에서 임시 파일 경로가 빠짐 | 중간 |
| R3 | 상대경로 계산이 세 군데에 따로 있음 | 높음(명령행 기준) | 다른 드라이브 오류 코드 통일 | 작음 |
| R4 | `engine.generate` 한 함수가 약 280줄 | 중간 | 없음 | 큼 |
| R5 | 리포트 오류 항목 형식이 두 가지 | 중간 | 리포트 필드 통일 | 작음 |
| R6 | 글꼴 폴더를 두 번 따로 훑음 | 중간 | 없음(편집기 글꼴 목록 로딩이 빨라질 수 있음) | 작음 |
| R7 | 외부 도구 실행 함수의 반환 타입이 상황마다 다름 | 중간 | 없음 | 작음 |
| R8 | 작업 프로그램 창 클래스에 판단 로직이 섞여 있음 | 중간 | 없음 | 중간 |
| R9 | 테스트 실행기가 저장소 최상단에 있음 | 낮음 | 없음 | 작음 |
| R10 | 코드 · 메시지에 남은 "B" 용어 | 낮음 | 영문 메시지 문구 | 작음 |
| R11 | 셀 행 · 열 계산이 두 군데 | 낮음 | 없음 | 작음 |
| R12 | 프로그램 화면에 버전이 안 보임 | 낮음 | 창 제목 · 도움말에 버전 표시 | 작음 |

R12는 리팩토링이 아니라 화면 기능 추가다. 0장 원칙 3에 따라 리팩토링 작업과 섞지 않고 별도 변경으로 다룬다. 이 문서에는 발견한 과제로만 남긴다.

---

## 2. 항목별 상세

### R1. 오류 종류를 영문 문장으로 구분하는 부분

- **위치**: `imposing/fonts.py` `embed()`의 `FontError` 세 곳(빠진 글자, 임베드 금지, 이름 기반 CFF 미지원), `imposing/engine.py` `generate()`의 글꼴 임베드 단계 `except fonts.FontError` → `SCHEMA_INVALID`, `imposing/gui/work.py` `describe_error()`. 글꼴 찾기 단계의 `FontError`는 이미 `FONT_NOT_FOUND`로 기록되므로 대상이 아니다.
- **문제**: 글꼴에 없는 글자, 임베드 금지 글꼴, 지원하지 않는 이름 기반(Name-keyed) CFF 글꼴이 모두 `SCHEMA_INVALID` 하나로 리포트된다. 작업 프로그램은 사유 문장에 `"lacks characters"`, `"prohibits embedding"`이 들어 있는지 문자열로 검사해 한국어 안내를 고른다. 엔진 쪽 문장을 바꾸면 안내가 경고 없이 일반 오류("입력을 처리할 수 없습니다")로 바뀐다.
- **제안**:
  - `FontError`에 `code` 속성을 두고 `FONT_GLYPH_MISSING`(빠진 글자 목록 포함), `FONT_EMBED_FORBIDDEN`, `FONT_UNSUPPORTED`(이름 기반 CFF)를 낸다.
  - `generate()`는 그 코드를 그대로 리포트에 기록한다.
  - `describe_error()`는 코드로만 문구를 고른다. `ERROR_TEXT` 표에 세 코드를 추가한다. `FONT_UNSUPPORTED` 문구는 "TrueType 또는 CID 방식 글꼴을 고르세요" 취지로 한다.
- **문서 반영**: SPEC §6.4 예외 처리 표에 세 코드 추가.
- **완료 기준**: `describe_error` 안에 영문 문장 검사가 없다. 세 경우 각각 리포트 코드와 화면 문구를 확인하는 테스트가 있다(이름 기반 CFF 글꼴 표본이 없으면 `fonts.embed`를 바꿔 끼워 흉내 낸다).

### R2. 저장할 때 임시 프로젝트 파일을 거치는 구조

- **위치**: `imposing/session.py` `Session.save()`, `imposing/engine.py` `generate()`
- **문제**: `generate()`가 프로젝트 파일 경로만 받기 때문에, 작업 프로그램은 저장할 때 프로젝트를 출력 폴더에 임시 파일 `~<이름>.<pid>.input.json`으로 쓰고 `generate()`가 그것을 다시 읽는다.
  - 주된 문제: 입력 해시 목록(`report["inputs"]`)에 사용자에게 의미 없는 임시 파일 경로가 기록된다.
  - 부수 문제: 임시 파일은 `finally`에서 지우므로 평소에는 남지 않는다. 저장 도중 프로그램이 강제 종료될 때만 사용자 폴더에 남는다.
- **동작 변화**: 작업 프로그램이 만든 리포트의 `inputs`에서 임시 파일 경로가 빠진다. PDF · 프로젝트 · 미리보기는 같다. 리포트 필드 설명이 있으면 SPEC §9.3에 반영한다.
- **제안**:
  - `generate_from(project, project_dir, templates_root, output, font_dirs)`를 새로 만든다. `project`는 이미 읽은 dict, `project_dir`은 B 상대경로의 기준 폴더다.
  - 기존 `generate(project_file, …)`는 파일을 읽어 `generate_from`을 부르는 얇은 함수로 바꾼다. 명령행과 테스트 실행기는 그대로 동작한다.
  - `Session.save()`는 임시 파일 없이 `generate_from`을 부른다.
  - 입력 보존 검사(R9 해시)는 파일로 들어온 경우에만 프로젝트 파일을 포함한다.
- **완료 기준**: `Session.save()`가 출력 폴더에 임시 파일을 만들지 않는다. 3-1차 · 3-2차 실행기 결과가 같다.

### R3. 상대경로 계산이 세 군데에 따로 있음

- **위치**: `imposing/autofill.py` `autofill()`(기존 배정과 새 파일 경로 재계산), `imposing/engine.py` `generate()` 끝부분(저장할 프로젝트의 경로 재계산), `imposing/session.py` `Session.to_project()`
- **문제**: "B 경로를 새 프로젝트 위치 기준 상대경로로 다시 계산"을 세 곳이 각자 구현한다. Windows에서 B와 저장 위치가 다른 드라이브면 상대경로를 만들 수 없는데, 처리가 제각각이다.

  | 위치 | 다른 드라이브일 때 |
  |---|---|
  | `autofill()` | `SCHEMA_INVALID` + 파이썬 예외 문장 |
  | `Session.to_project()` | 한국어 안내, 코드 `DIFFERENT_DRIVE` |
  | `generate()` | 처리 없음. 저장 직전에 `ValueError`가 그대로 올라감 |

  `generate()` 쪽 문제는 사실상 명령행 `build`에서만 생긴다. 작업 프로그램은 `Session.to_project()`가 먼저 다른 드라이브를 검사해 막기 때문이다. 우선순위 "높음"은 명령행 사용자 기준이다.

- **제안**: `imposing/model.py`에 `relative_file(path, folder)`를 두고 세 곳이 쓴다. 다른 드라이브면 `PathError(code="DIFFERENT_DRIVE")`를 낸다. `generate()`와 `autofill()`은 이 코드를 리포트에 기록하고 PDF · 프로젝트를 만들지 않는다.
- **문서 반영**: SPEC §6.4에 `DIFFERENT_DRIVE` 추가. `docs/DEVELOPMENT.md`의 명령행 설명.
- **완료 기준**: 경로 재계산 코드가 한 곳이다. 세 경로 각각에 다른 드라이브 테스트가 있다(Linux에서는 `os.path.relpath`를 바꿔 끼워 흉내 낸다).

### R4. `engine.generate` 한 함수가 약 280줄

- **위치**: `imposing/engine.py` `generate()`
- **문제**: 입력 검사, 템플릿 · B 열기, OCG 병합, 카드 배치, 글꼴 준비, 텍스트 삽입, Illustrator 데이터 제거, 임시 저장 · qpdf 검사 · 미리보기, 출력 이동, 리포트가 한 함수에 있다. 리포트는 함수 안 여러 곳에서 dict를 직접 고친다. 한 단계만 따로 테스트하거나 고치기 어렵다.
- **제안**: 단계별 함수로 나누고 `generate()`는 순서만 정한다. 예:
  `load_inputs` → `merge_ocgs` → `place_cards` → `prepare_fonts` → `draw_texts` → `finalize`(R11 제거, 저장, 검사, 미리보기, 출력 이동). 리포트는 작은 클래스(오류 · 경고 · 정보 추가 메서드)로 감싼다.
- **주의**: 가장 많이 검증된 부분이다. 계산식과 PDF 객체를 만드는 순서를 바꾸지 않는다. XObject 이름(`/Card1`…), 폰트 리소스 이름(`/Text1`…), 콘텐츠 스트림 순서가 같아야 결과 PDF가 같다.
- **완료 기준**: 같은 입력으로 리팩토링 전후 결과 PDF를 만들어 **qpdf `--qdf --object-streams=disable`로 정규화한 내용이 같다**(타임스탬프 · ID 제외). 실행기 전체 통과.
- **시점**: 1차 베타가 끝난 뒤 별도 작업으로 권한다.

### R5. 리포트 오류 항목 형식이 두 가지

- **위치**: `imposing/model.py` `template_errors()` · `project_errors()`(`{code, field}`), 그 밖의 오류(`{code, reason, …}`)
- **문제**: 화면과 테스트가 두 형식을 모두 다뤄야 한다(`describe_error`의 `entry.get("reason") or entry.get("field")`). 자동 배열 리포트는 `model` 오류를 `reason="Invalid field: …"`로 다시 감싼다.
- **제안**: 모든 오류 항목을 `{code, reason, field?(선택), 그 밖의 맥락}`으로 통일한다. `model`의 검사 함수가 `reason`도 채운다(예: `"grid.pitch_mm: negative value not allowed"`).
- **언어 규칙**: 리포트의 `reason`은 지금처럼 영문으로 쓴다(개발 · 진단용 기록). 사용자에게 보이는 한국어 문구는 화면 쪽(`describe_error`의 `ERROR_TEXT`)이 `code`로 고른다.
- **완료 기준**: 리포트의 모든 오류 항목에 영문 `reason`이 있다. 기존 `field` 키는 남긴다(하위 호환).

### R6. 글꼴 폴더를 두 번 따로 훑음

- **위치**: `imposing/fonts.py` `catalogue()`(엔진이 이름으로 글꼴을 찾을 때), `imposing/store.py` `usable_fonts()` · `_embeddable()`(편집기의 글꼴 목록)
- **문제**: 같은 폴더들을 두 함수가 각자 열어 이름표를 읽는다. 규칙이 따로 구현되어 있어 "편집기 목록에는 있는데 저장할 때 못 찾음"이 생길 수 있다. 편집기는 글꼴 수가 많은 PC에서 목록을 처음 열 때 느릴 수 있다.
- **제안**: `fonts.py`가 한 번 훑으면서 이름별 위치, 표시 이름, 임베드 가능 여부를 함께 만든다. `usable_fonts()`는 그 결과를 거르기만 한다.
- **완료 기준**: 글꼴 파일을 여는 코드가 `fonts.py` 한 곳이다. `tests/test_font_selection.py` 통과, 편집기 글꼴 목록에 `Noto Sans CJK KR`(테스트 환경) · `Malgun Gothic`(Windows)이 나온다.

### R7. 외부 도구 실행 함수의 반환 타입이 상황마다 다름

- **위치**: `imposing/pdf.py` `invoke()`
- **문제**: 허용 종료 코드가 하나면 출력 문자열을, 여럿이면 `CompletedProcess`를 돌려준다(qpdf 경고 처리 때 추가). 부르는 쪽이 어느 쪽인지 알아야 한다.
- **제안**: 항상 `CompletedProcess`를 돌려주고, 출력만 필요한 곳(`pdffonts` 등)은 `.stdout`을 꺼낸다. 또는 `run()`(결과 객체)과 `output()`(문자열) 두 함수로 나눈다.
- **영향 범위**: `test03_runner.py`, `test32_runner.py`도 `invoke`를 쓴다.
- **완료 기준**: 반환 타입이 하나다. 전체 테스트 통과.

### R8. 작업 프로그램 창 클래스에 판단 로직이 섞여 있음

- **위치**: `imposing/gui/work.py` `WorkWindow`(약 720줄)
- **문제**: 화면과 함께 판단이 들어 있다. 예: 붙여넣기 확인 문구의 개수 계산, 템플릿이 바뀌었을 때 다시 불러오기(`_reload_changed_template`, 함수 안 `from ..model import cells`), 파일 검사, 자동 배열 막힘 문구 만들기. 화면 없이 테스트하려면 대화상자를 가짜로 바꿔야 한다.
- **제안**: 판단은 `Session`(또는 새 `JobController`)으로 옮기고, 창은 결과를 표시만 한다. 예: `Session.reload_template()`이 "없어진 셀 목록"을 돌려주고 창은 그 목록으로 문구만 만든다.
- **완료 기준**: `WorkWindow` 클래스 안에 함수 안 import가 없다. 모듈 함수 `main()`의 `from .common import self_test`는 `--selftest`에서만 불러오는 의도된 지연 import이므로 대상이 아니다. 옮긴 판단은 화면 없는 테스트(`tests/test_store_session.py`)로 확인한다.
- **시점**: 1차 베타가 끝난 뒤 권한다.

### R9. 테스트 실행기가 저장소 최상단에 있음

- **위치**: `test03_runner.py`, `test32_runner.py`. `tests/test_project.py`와 `tests/test_autofill.py`가 이를 import한다.
- **제안**: `tests/runners/`로 옮기고, 최상단에는 같은 이름의 얇은 실행 파일만 남겨 문서의 명령(`python test03_runner.py`)이 그대로 동작하게 한다. Windows 워크플로의 명령도 확인한다.
- **완료 기준**: 문서 · 워크플로의 명령이 그대로 동작한다.

### R10. 코드 · 메시지에 남은 "B" 용어

- **배경**: 2026-11-13 사용자 결정으로 화면 용어는 "데이터"로 바꿨다(0.4.3). "B"는 초기 설명용 이름이다.
- **남은 곳**: `imposing/autofill.py`의 영문 오류 문장(`Select at least one B file`, `B file does not exist…`), `imposing/__main__.py` 도움말, 주석과 docstring.
- **제안**: 명령행 메시지의 "B file"을 "data file"로 바꾼다. 리포트 코드(`B_FILE_MISSING`)와 SPEC · 작업 지시서의 "B"는 그대로 둔다(기록 · 검증 문서와의 대응을 위해).
- **주석 · docstring**: 같은 작업에서 "B file"을 "data file"로 바꾼다. 다만 SPEC · 리포트 코드를 가리키는 맥락(예: `B_FILE_MISSING` 설명, SPEC 조항 인용)은 그대로 둔다.
- **완료 기준**: 사용자가 볼 수 있는 문장과 `imposing/`의 주석 · docstring에 "B file"이 없다(위 예외 제외).

### R11. 셀 행 · 열 계산이 두 군데

- **위치**: `imposing/model.py` `cells()`, `imposing/gui/editor.py` `cell_position()`(0.5.1에서 추가)
- **제안**: `model.py`에 `cell_rect(template, cell)`(행, 열, 좌상단, 크기)를 두고 편집기와 미리보기가 쓴다.
- **완료 기준**: 행 · 열 계산식이 한 곳이다. `test_editor_shows_cell_coordinates` 통과.

### R12. 프로그램 화면에 버전이 안 보임

- **배경**: 버전은 `pyproject.toml`의 `version` 하나이고, 배포 폴더의 `VERSION.txt`로만 확인할 수 있다. 사용자 테스트 중 문제를 보고할 때 버전을 알기 어렵다.
- **제안**: `importlib.metadata.version("quick-imposing")`로 읽어 두 프로그램의 창 제목 끝이나 `도움말 → 정보`에 표시한다. 읽지 못하면 `VERSION.txt`, 그것도 없으면 표시하지 않는다.
- **주의**: 화면이 바뀌는 기능 추가다. 리팩토링 브랜치 · PR과 섞지 않고 별도 변경으로 진행한다. 표시 위치는 사용자에게 확인한다.
- **완료 기준**: 배포 exe에서 버전이 보인다(`build.ps1`의 시작 점검 후 화면 캡처 또는 테스트).

---

## 3. 권하는 순서

| 단계 | 항목 | 이유 |
|---|---|---|
| 1 | R1 → R3 → R5 | 오류 코드와 경로 처리를 정리한다. 사용자 테스트에서 오류가 나왔을 때 원인을 바로 볼 수 있다. 세 항목 모두 리포트 오류 형식과 `describe_error`를 건드리므로 한 PR로 묶어도 된다(커밋은 항목별) |
| 2 | R2 → R7 → R6 | 엔진 입출력을 정리한다. R2는 R3의 경로 함수를 쓴다 |
| 3 | R4, R8 | 큰 구조 정리. 1차 베타가 끝난 뒤 별도 작업 |
| 수시 | R9 ~ R11 | 위 작업과 함께 |
| 별도 | R12 | 화면 기능 추가. 리팩토링과 분리해 사용자 확인 후 진행 |

---

## 4. 작업 방법

### 환경

`docs/DEVELOPMENT.md`의 설치 절차를 따른다. Linux에서는 다음이 필요하다.

```sh
python -m venv .venv && . .venv/bin/activate
python -m pip install -e '.[test,gui]'
# qpdf, poppler-utils, Noto Sans CJK KR 글꼴 (Debian/Ubuntu: apt-get install qpdf poppler-utils fonts-noto-cjk)
# GUI 테스트를 화면 없이 돌리려면: libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3 등
```

### 매 항목 검증

```sh
python -m pytest -q                         # 기준 커밋에서 99 passed (작성 시점 기록, 착수 전 재확인)
python test03_runner.py --out out/r-31      # 10/10 PASS
python test32_runner.py --out out/r-32      # 11/11 PASS (+ 3-1차 회귀 10/10)
ruff check --select F imposing tests        # 문제 없음
```

R4처럼 PDF 생성 경로를 건드리면 위에 더해 **리팩토링 전 커밋과 후 커밋으로 같은 프로젝트를 빌드해 결과 PDF를 비교**한다.

```sh
qpdf --qdf --object-streams=disable --static-id before.pdf before.qdf
qpdf --qdf --object-streams=disable --static-id after.pdf after.qdf
diff before.qdf after.qdf    # 차이가 없어야 한다 (/CreationDate 등 제외)
```

### 브랜치 · 병합 · Windows 검증

- 작업 브랜치에 커밋하고 push한다. main 반영은 GitHub PR로 한다. 기록은 `PR/004-gui.md`의 "수정 내역"에 이어 적는다(또는 새 번호 `PR/005-refactoring.md`).
- 작업 브랜치에 push하면 GitHub Actions `windows` 워크플로가 Windows에서 pytest, 두 실행기, 배포 빌드(`packaging/build.ps1`)와 시작 점검을 돈다(약 6분). **통과를 확인한 뒤 병합한다.**
- 동작이 바뀌는 항목(R1 · R3 · R5의 리포트 코드, R2의 리포트 `inputs`, R10 문구, R12 화면)은 사용자에게 먼저 알린다.
- 리팩토링으로 버전을 올릴 필요는 없다. 화면이나 리포트가 바뀌는 항목을 병합할 때는 `pyproject.toml`의 셋째 자리를 올린다.

---

## 5. 진행 상황

| # | 상태 | 커밋 · PR | 비고 |
|---|---|---|---|
| R1 | 제안 | — | |
| R2 | 제안 | — | |
| R3 | 제안 | — | |
| R4 | 제안 | — | 베타 뒤 |
| R5 | 제안 | — | |
| R6 | 제안 | — | |
| R7 | 제안 | — | |
| R8 | 제안 | — | 베타 뒤 |
| R9 | 제안 | — | |
| R10 | 제안 | — | |
| R11 | 제안 | — | |
| R12 | 제안 | — | 별도 변경(기능 추가), 사용자 확인 필요 |

항목을 끝내면 이 표의 상태를 `완료`로 바꾸고 커밋 · PR 번호를 적는다.
