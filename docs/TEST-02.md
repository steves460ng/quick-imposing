# 2차 테스트 명세: JSON 템플릿 기반 배치

> **대체됨 (2026-11-11)**: 이 문서는 완료된 2차 테스트의 기록이다. 형식 `quick-imposing/template@1`과 아래 오류 규칙은 현행 구현에 적용하지 않는다. 현행 규칙은 `docs/SPEC.md` v0.6, `docs/TEMPLATE-REQUIREMENTS.md`, `docs/TASK-03-1.md` §2·§3을 따른다. 본문 중 "SPEC §…" 참조는 SPEC v0.5(커밋 `1e22e14`)의 절 번호다.
>
> | 이 문서 (2차) | 현행 |
> |---|---|
> | 템플릿 JSON 하나에 슬롯 좌표와 `data` 배정을 함께 담음 (`template@1`) | 템플릿 폴더(`template@2` + `base.pdf` 사본)와 프로젝트(`project@1`)로 분리 |
> | 슬롯 좌표 직접 나열, 카드 85×50·`crop_anchor`·`source_box` 지정 | 시작 위치 + 개수 + 피치 + 셀 크기, 회전만 지정 |
> | `base.safe_area_mm`, `SLOT_OUT_OF_SAFE_AREA` | 허용 영역 검사 없음. 판 바깥만 잘라냄 |
> | `SLOT_OVERLAP` 오류 | `CELL_OVERLAP` 경고 후 진행 |
> | `CARD_TOO_SMALL` 오류 | 경고 없이 진행 |
> | `FILE_NOT_FOUND` 오류 (B 파일 없음) | 빈칸으로 두고 진행, `B_FILE_MISSING` 정보 |
> | `UNKNOWN_SLOT` | `CELL_NOT_IN_TEMPLATE` |
> | `DUPLICATE_SLOT_ASSIGNMENT`, `INVALID_CARD_PDF` | `SCHEMA_INVALID` + 사유 |
> | `DUPLICATE_SLOT_ID`, `BASE_SIZE_MISMATCH` | 해당 없음. 셀은 자동 생성되고 판 크기는 베이스에서 읽는다 |
> | 경로는 저장소 루트 기준 | B는 프로젝트 파일 기준, 베이스는 템플릿 폴더 사본 |
> | 출력 `out/test02/<name>/result.pdf`, `report.json`, `preview.png` | `<이름>.pdf`·`.qiproj.json`·`.png`·`.report.json` |
>
> 2차 실행기는 참고 브랜치 `test/test02-templates`에만 있고 main에는 없다. `samples/templates/t2-*`와 `samples/expected/t2-*`는 이 기록의 픽스처로만 남아 있다.

| 항목 | 내용 |
|---|---|
| 상태 | **대체됨 (2026-11-11)**. 기록용 |
| 문서 버전 | v0.2 (Illustrator 전용 데이터 제거 검증 추가) |
| 작성일 | 2026-11-10 |
| 선행 문서 | `docs/SPEC.md` (v0.5). 이 문서에 없는 규칙은 모두 SPEC을 따른다 |
| 샘플 입력 | `samples/input/` (2차본: B 폰트 윤곽선 처리) |
| 템플릿 | `samples/templates/*.json` |
| 기대값 | `samples/expected/*.expected.json` |

---

## 1. 목적

**JSON 템플릿에 적힌 대로** B 데이터를 베이스 위에 배치하는 기능을 검증한다.

1차 테스트에서는 프리셋 값(열·행, 간격, 정렬)으로 슬롯 좌표를 계산했다. 2차 테스트에서는 템플릿이 **슬롯 좌표와 데이터 배정을 직접 지정**하고, 프로그램은 계산 없이 그대로 따른다.

함께 확인할 것:
- 윤곽선 처리된 B(폰트 없음)를 배치해도 SPEC §4.1의 비변형 원칙이 모두 지켜지는지
- 템플릿 오류(겹침, 영역 밖, 파일 없음 등)를 정확히 잡아내는지

## 2. 1차 테스트와의 차이

| 항목 | 1차 (SPEC) | 2차 (이 문서) |
|---|---|---|
| 배치 입력 | 프리셋(격자 계산식) | 템플릿(슬롯 좌표 직접 지정) |
| 데이터 배정 | 파일 목록 순서대로 슬롯 1번부터 | 템플릿의 `data`에 슬롯 번호별로 명시 |
| 샘플 B | 폰트 포함 | **폰트 윤곽선 처리** (폰트·텍스트 객체 없음) |
| 기대값 | SPEC 표 | 템플릿별 `*.expected.json` 파일 |

프리셋 기능은 유지한다. 구현 시 프리셋은 내부에서 템플릿 형태(슬롯 목록)로 변환해서 같은 배치 엔진을 쓰는 구조를 권장한다.

## 3. 템플릿 형식 (`quick-imposing/template@1`)

### 3.1 최상위 항목

| 키 | 필수 | 형식 | 의미 |
|---|---|---|---|
| `schema` | ✔ | 문자열 | `"quick-imposing/template@1"` 고정. 다른 값이면 오류 |
| `name` | ✔ | 문자열 | 템플릿 이름. 출력 폴더 이름으로도 사용 |
| `description` |  | 문자열 | 설명 |
| `units` | ✔ | 문자열 | `"mm"`만 허용 |
| `origin` | ✔ | 문자열 | `"top-left"`만 허용 (판 좌상단 원점, 아래쪽이 +y) |
| `base` | ✔ | 객체 | 베이스 정보 (3.2) |
| `card` | ✔ | 객체 | 카드 가공 규칙 (3.3) |
| `slots` | ✔ | 배열 | 슬롯 목록 (3.4) |
| `data` | ✔ | 배열 | 슬롯별 B 배정 (3.5) |

### 3.2 `base`

| 키 | 필수 | 의미 |
|---|---|---|
| `file` | ✔ | 베이스 PDF 경로 (저장소 루트 기준 상대 경로) |
| `size_mm` | ✔ | 기대 판 크기 [가로, 세로]. 실제 MediaBox와 ±0.1mm 넘게 다르면 오류 |
| `safe_area_mm` | ✔ | 배치 허용 영역 [x1, y1, x2, y2] |

### 3.3 `card`

| 키 | 필수 | 의미 |
|---|---|---|
| `size_mm` | ✔ | **회전·재단 후** 판 위에 놓이는 크기 [가로, 세로]. 샘플은 [85, 50] |
| `rotation_deg` | ✔ | B 회전 각도. 시계 방향이 음수. 0 / 90 / −90 / 180만 허용 |
| `crop_anchor` | ✔ | `"center"`만 허용 (SPEC §4.2) |
| `source_box` | ✔ | 재단 기준 박스. `"TrimBox"` (없으면 MediaBox로 대체하고 리포트에 경고) |

### 3.4 `slots`

| 키 | 필수 | 의미 |
|---|---|---|
| `id` | ✔ | 슬롯 번호 (정수, 템플릿 안에서 중복 불가) |
| `x`, `y` | ✔ | 회전·재단된 카드의 **좌상단** 위치 (mm) |

- 슬롯 영역은 (x, y) ~ (x + card 가로, y + card 세로)다.
- 슬롯끼리 **변이 맞닿는 것은 허용**한다(간격 0). 면적이 조금이라도 겹치면 오류다.
- 프로그램은 좌표를 다시 계산하거나 보정하지 않는다. 템플릿 값을 그대로 쓴다.

### 3.5 `data`

| 키 | 필수 | 의미 |
|---|---|---|
| `slot` | ✔ | 배치할 슬롯 `id` |
| `file` | ✔ | B PDF 경로 (저장소 루트 기준 상대 경로) |

- `data`의 나열 순서는 의미가 없다. 오직 `slot` 값으로 배치 위치를 정한다.
- 같은 B 파일을 여러 슬롯에 배정해도 된다.
- `data`가 없는 슬롯은 비워 둔다(빈 슬롯은 오류가 아님. 리포트에 기록).

### 3.6 예시 (발췌)

```json
{
  "schema": "quick-imposing/template@1",
  "name": "t2-02-irregular",
  "units": "mm",
  "origin": "top-left",
  "base": { "file": "samples/input/base.pdf", "size_mm": [305, 506], "safe_area_mm": [15, 33, 290, 458] },
  "card": { "size_mm": [85, 50], "rotation_deg": -90, "crop_anchor": "center", "source_box": "TrimBox" },
  "slots": [ { "id": 1, "x": 25, "y": 40 }, { "id": 2, "x": 110, "y": 40 } ],
  "data":  [ { "slot": 2, "file": "samples/input/B-2.pdf" }, { "slot": 1, "file": "samples/input/B-3.pdf" } ]
}
```

## 4. 오류 처리

오류가 하나라도 있으면 결과 PDF를 만들지 않는다. 리포트에는 아래 오류 코드와 원인(해당 슬롯·파일)을 기록한다. 오류가 여러 개면 모두 기록한다.

| 오류 코드 | 조건 |
|---|---|
| `SCHEMA_INVALID` | 필수 항목 누락, 형식 오류, 허용되지 않은 값 (`schema`, `units`, `origin`, `rotation_deg`, `crop_anchor`) |
| `BASE_SIZE_MISMATCH` | 베이스 실제 크기가 `base.size_mm`와 ±0.1mm 넘게 다름 |
| `DUPLICATE_SLOT_ID` | `slots`에 같은 `id`가 2번 이상 |
| `SLOT_OVERLAP` | 슬롯 영역끼리 면적이 겹침 |
| `SLOT_OUT_OF_SAFE_AREA` | 슬롯 영역이 `safe_area_mm`를 벗어남 |
| `UNKNOWN_SLOT` | `data`가 정의되지 않은 슬롯을 가리킴 |
| `DUPLICATE_SLOT_ASSIGNMENT` | 한 슬롯에 `data`가 2개 이상 |
| `FILE_NOT_FOUND` | 베이스나 B 파일이 없음 |
| `INVALID_CARD_PDF` | B가 1페이지가 아니거나 열 수 없음 |
| `CARD_TOO_SMALL` | 회전 전 B가 재단 크기보다 작음 |

## 5. 테스트 케이스

| ID | 템플릿 | 내용 | 기대 결과 |
|---|---|---|---|
| T2-01 | `t2-01-default-3x8` | 기본 사양(3×8, 간격 1mm, 판 중앙). 24슬롯 모두 B-1~B-3 순환 배정 | PASS. SPEC §6.5 표와 동일 좌표 |
| T2-02 | `t2-02-irregular` | 1행 간격 0(맞닿음), 2행 간격 0.5mm, 단독 슬롯 7, 빈 슬롯 8. `data` 순서와 슬롯 번호를 섞음 | PASS. 슬롯 8 비어 있음 |
| T2-03 | `t2-03-err-overlap` | 슬롯 1·2가 겹침 | `SLOT_OVERLAP`, PDF 없음 |
| T2-04 | `t2-04-err-outside` | 슬롯 2의 오른쪽 끝 315mm | `SLOT_OUT_OF_SAFE_AREA`, PDF 없음 |
| T2-05 | `t2-05-err-missing-file` | 없는 파일 `B-9.pdf` 배정 | `FILE_NOT_FOUND`, PDF 없음 |
| T2-06 | `t2-06-err-unknown-slot` | 슬롯 99에 배정 | `UNKNOWN_SLOT`, PDF 없음 |
| T2-07 | `t2-07-err-duplicate-slot` | 슬롯 1에 2개 배정 | `DUPLICATE_SLOT_ASSIGNMENT`, PDF 없음 |

템플릿과 기대값 파일 이름은 1:1로 대응한다(`<name>.json` ↔ `<name>.expected.json`).

## 6. 기대값 파일 형식

**정상 케이스**

| 키 | 의미 |
|---|---|
| `expect` | `"pass"` |
| `placements[]` | 슬롯별 `slot`, `file`, `cm`(변환 행렬 6개 값), `bbox`(Form XObject `/BBox`, B 좌표계 pt), `placed_rect_mm`(판 위 좌상단·우하단, mm) |
| `empty_slots` | 비어 있어야 하는 슬롯 번호 |
| `tolerance_pt` | 허용 오차 (0.01pt) |

**오류 케이스**

| 키 | 의미 |
|---|---|
| `expect` | `"error"` |
| `error_code` | 반드시 포함되어야 하는 오류 코드 |
| `output_pdf` | `"must_not_exist"` (결과 PDF가 생성되면 실패) |

기대값은 실제 샘플 파일의 TrimBox로 계산했다. 프로그램이 같은 값을 독립적으로 계산해서 대조해야 하며, **기대값 파일을 읽어 배치에 쓰면 안 된다**(테스트가 무의미해짐).

## 7. 검증 기준

정상 케이스(T2-01, T2-02)는 아래 항목을 모두 통과해야 한다.

| ID | 검증 | 기준 |
|---|---|---|
| C1 | SPEC §9 전 항목 | V1~V16 통과. 다만 V8의 기대값은 `*.expected.json`의 `cm`을 사용 |
| C2 | 배치 대응 | 각 슬롯에 그려진 XObject가 기대값의 `file`에서 온 것인지 확인 (원본 콘텐츠 스트림 해시로 대조) |
| C3 | 빈 슬롯 | `empty_slots` 영역은 베이스와 픽셀 차이 0 |
| C4 | 폰트 | 결과 PDF의 폰트는 베이스의 2개뿐. B에서 온 폰트가 없음 |
| C5 | 텍스트 연산자 | B에서 가져온 XObject 스트림에 `BT`/`Tj`/`TJ`가 없음 (윤곽선 상태 유지) |
| C6 | 맞닿은 슬롯 | T2-02의 슬롯 1·2·3 경계에서 서로의 내용이 침범하지 않음 (각 슬롯의 `/BBox` 클리핑 확인) |
| C7 | 재현성 | 같은 템플릿을 두 번 실행한 결과 PDF의 페이지 콘텐츠·리소스가 동일 (메타데이터 날짜·ID 제외) |
| C8 | Illustrator 전용 데이터 | SPEC V17 통과. Illustrator에서 열었을 때 카드가 보여야 함(V18, 사람 확인) |

오류 케이스(T2-03~T2-07)는 기대 오류 코드가 리포트에 있고, 결과 PDF가 생성되지 않으면 통과다.

## 8. 실행과 산출물

- 실행 입력: 템플릿 파일 경로 하나. 베이스와 B 경로는 템플릿 안에 있다.
- 출력 위치: `out/test02/<템플릿 name>/`
  - `result.pdf` (정상 케이스만)
  - `report.json` (SPEC §9.3 형식 + 템플릿 이름, 오류 코드 목록, 빈 슬롯 목록)
  - `preview.png` (정상 케이스만)
- 전체 결과 요약: `out/test02/summary.json` — 케이스별 `PASS` / `FAIL`과 실패 사유
- `out/`은 커밋하지 않는다.

## 9. Codex 작업 지시 예시

> `docs/SPEC.md`와 `docs/TEST-02.md`를 읽고, JSON 템플릿 기반 배치 기능을 구현하라. `samples/templates/`의 템플릿 7개를 모두 실행하고, 결과를 `samples/expected/`와 대조해 `out/test02/summary.json`을 만들어라. 입력 파일과 기대값 파일은 수정하지 마라.
