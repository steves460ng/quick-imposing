# quick-imposing

템플릿의 셀 배열에 PDF 카드를 배치하고, 작업별 텍스트를 K100으로 추가합니다. 기존 PDF의 콘텐츠·이미지·폰트 스트림을 재해석하거나 래스터화하지 않습니다. PDF 생성 기준은 [TASK-03-1](docs/TASK-03-1.md), 자동 배열 기준은 [TASK-03-2](docs/TASK-03-2.md)입니다. GUI는 포함하지 않습니다.

## 설치

Python 3.12 이상과 **qpdf**, **Poppler**(`pdftoppm`, `pdffonts`, `pdfimages`, `pdftotext`)를 설치하고 실행 파일을 PATH에 추가합니다.

```sh
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell에서는 .venv\Scripts\Activate.ps1
python -m pip install -e '.[test]'
```

한글 픽스처는 시스템에 설치된 **Noto Sans CJK KR Regular**를 사용합니다. 운영체제 글꼴 폴더에서 이름으로 찾으며, `--font-dir <폴더>`를 반복 지정해 추가 폴더를 검색할 수 있습니다. 이름이 nameID 1·4·6에 정확히 일치하는 글꼴을 nameID 16 별칭보다 우선하며, 같은 우선순위에서는 nameID 17(없으면 2)의 Regular 스타일을 선택합니다. 다른 글꼴로 조용히 대체하지 않습니다. TrueType와 CID-keyed CFF를 서브셋 임베드하며 ToUnicode를 포함합니다. 글꼴 임베드 권한이나 글리프가 없으면 오류를 보고합니다.

## 템플릿 만들기

```sh
quick-imposing create-template template.json \
  --base samples/input/base-front-blank.pdf \
  --templates-root out/my-templates
```

먼저 TASK-03-1 §2.1 형식으로 `template.json`을 준비합니다(`name`이 `T31-front-3x8`인 예). 명령은 `out/my-templates/T31-front-3x8/`에 `template.json`과 원본과 바이트가 같은 `base.pdf`를 만듭니다. 기존 템플릿 폴더를 덮어쓰지 않습니다.

`samples/test03-1/template-defs/`의 `{source_base, template}` 래퍼는 **테스트 실행기 전용**입니다. `template@2`의 일부가 아니며 일반 생성 CLI의 입력도 아닙니다. 실행기는 내부 `template`만 생성 함수에 전달하므로 저장된 `template.json`에 `source_base`나 원본 베이스 경로가 남지 않습니다. 샘플로 CLI를 실행하려면 실행기가 만든 `out/test03-1/templates/T31-front-3x8/template.json`을 입력으로 사용할 수 있습니다.

## 프로젝트로 PDF 생성

```sh
quick-imposing build samples/test03-1/projects/T31-01.qiproj.json \
  --templates-root out/my-templates \
  --output out/example/result.pdf
```

`python -m imposing`도 같은 명령을 제공합니다. 출력 PDF 옆에 `result.qiproj.json`, `result.png`, `report.json`을 저장합니다. 프로젝트의 B 경로는 입력 프로젝트 위치에서 해석하고, 저장할 때 새 프로젝트 위치 기준으로 다시 계산합니다. 저장한 프로젝트도 같은 명령으로 다시 열 수 있습니다. 수정된 현재 템플릿을 읽으며, 사라진 셀은 오류로 처리합니다.

- 셀 번호는 행 우선으로 고정합니다. `fill_direction`은 자동 배열의 채움 순서에 사용하며 PDF 생성에서는 배정된 셀과 `order`를 따릅니다.
- 그리는 순서는 베이스 → `order` 오름차순의 B → 텍스트입니다.
- 피치는 0 이상이어야 합니다. 음수는 `SCHEMA_INVALID`이고 0으로 셀이 겹치면 `CELL_OVERLAP` 경고 후 진행합니다.
- 겹침은 경고 후 진행합니다. 판 경계는 B 좌표계의 Form BBox로 잘라냅니다.
- 완전히 판 밖인 셀은 `drawn=false`, `bbox=null`로 기록하고 경고 없이 그리기를 생략합니다. 프로젝트에는 셀·파일·order를 유지하며 템플릿 수정 후 다시 열면 그립니다.
- B 크기 차이는 경고하지 않습니다. 없는 B와 알 수 없는 텍스트 id는 리포트 정보에만 기록합니다.
- 빈 텍스트는 그리지 않습니다. 좌표는 첫 글자의 왼쪽 기준선입니다.
- 기존 PDF·프로젝트·리포트·미리보기가 있으면 덮어쓰지 않습니다. 새 출력 폴더를 선택하세요.

## 자동 배열로 프로젝트 편집

먼저 아래 테스트 실행기로 예제 템플릿을 준비할 수 있습니다.

```sh
python test32_runner.py
quick-imposing autofill --template T32-fwd-3x3 \
  --templates-root out/test03-2/templates --start-cell 1 \
  --files samples/test03-2/data/c-10.pdf samples/test03-2/data/c-2.pdf \
  --output out/autofill/first.qiproj.json
quick-imposing autofill --project out/autofill/first.qiproj.json \
  --templates-root out/test03-2/templates --start-cell 3 \
  --files samples/test03-2/data/c-3.pdf \
  --output out/autofill/second.qiproj.json \
  --report out/autofill/second-report.json
quick-imposing build out/autofill/second.qiproj.json \
  --templates-root out/test03-2/templates --output out/autofill/pdf/result.pdf
```

`--template`은 빈 프로젝트를 만들고, `--project`는 기존 프로젝트를 읽습니다. 둘 중 하나만 지정합니다. `--files`의 상대경로는 명령을 실행한 폴더 기준입니다. 기존 B는 입력 프로젝트 위치에서 찾고, 모든 B 경로를 출력 프로젝트 위치 기준으로 다시 계산합니다. 기존 셀·파일 대상·order와 텍스트는 유지합니다.

파일 이름(확장자 포함)을 숫자 값과 대소문자 무시 문자열로 비교하고, 동률이면 전체 절대경로 문자열로 순서를 고정합니다. 새 order는 기존 최댓값 다음부터 증가합니다. 현재 템플릿의 `fill_direction`에 따라 시작 셀부터 채우며, 방향을 바꾸는 CLI 옵션은 없습니다.

이미 배정된 셀이나 마지막 셀에서 막히면 그 앞까지 저장하고 `AUTOFILL_BLOCKED`를 기록합니다. 리포트에는 `reason`, `blocked_cell`(끝에 도달하면 null), 정렬된 미배정 파일 목록이 포함됩니다. 없는 기존 B도 배정된 셀로 취급합니다. 새 파일 목록 전체를 먼저 검사하므로 뒤쪽에 없는 파일이 있어도 프로젝트를 저장하지 않습니다.

`--report`를 생략하면 출력 프로젝트의 마지막 확장자를 `.autofill.json`으로 바꾼 경로에 리포트를 씁니다. `sorted_files`와 `unplaced_files`는 절대경로, `added[].file`은 출력 프로젝트 기준 상대경로입니다. 막힘 경고는 종료 코드 0, 입력 오류는 1입니다. 기존 프로젝트와 리포트는 덮어쓰지 않습니다. 기존 리포트와 충돌하면 CLI 오류로 종료하므로 새 출력 경로를 지정하세요.

자동 배열은 PDF를 만들지 않습니다. 저장된 프로젝트를 기존 `build` 명령에 전달합니다. `samples/test03-2/template-defs/`의 `{source_base, template}`도 테스트 실행기 전용 래퍼입니다.

## 테스트

```sh
python -m pytest -q
python test03_runner.py
python test32_runner.py
# 기본 출력 폴더가 이미 있다면 새 폴더 사용
python test03_runner.py --out out/test03-1-rerun
python test32_runner.py --out out/test03-2-rerun
```

실행기는 `out/test03-1/templates/`에 베이스 사본을 포함한 템플릿을 생성하고, T31-01~09(03a/03b 별도, 총 10개)를 실행합니다. §4.3의 숫자는 기대값 JSON에 그대로 적었으며 배치 엔진은 이 파일을 읽지 않습니다. 독립 행렬 계산과 원본 페이지로 만든 참조 PDF의 렌더링을 실제 결과와 비교합니다. 다른 B를 넣었을 때 이미지 차이가 나는지도 검사합니다.

결과는 `out/test03-1/summary.json` 및 각 케이스 `report.json`에 기록됩니다. `out/`은 커밋하지 않습니다. 생성 명령의 PASS는 PDF 구문·입력 보존 검사를 뜻하며, C1~C10의 전체 비교 결과는 테스트 실행기에서 확인합니다. Illustrator 직접 표시와 사람 방향 확인은 별도 항목으로 남깁니다.

## Illustrator 처리

결과 저장 전 카탈로그와 페이지의 `/PieceInfo/Illustrator`만 제거하고, 다른 앱의 PieceInfo는 유지합니다. 베이스에 남은 배치 전 Illustrator 편집 데이터를 다시 여는 문제를 막기 위한 SPEC R11 처리입니다. 원본 입력은 변경하지 않으며 처리 위치를 리포트에 기록합니다. 결과를 일반 PDF로 열게 되므로 Illustrator 고유 편집 구조의 왕복 보존은 지원하지 않습니다.

상세 결과와 질문은 [TEST-03-1-RESULTS](docs/TEST-03-1-RESULTS.md)를 참조하세요.

3-2차 실행기는 T32-01~11의 배정·경고·오류와 PDF 행렬·BBox·그리기 순서·셀별 렌더링을 검사하고, 3-1차 실행기 10개도 함께 실행합니다. 결과는 `out/test03-2/summary.json`에 저장합니다. pytest는 별도 명령으로 실행합니다. 자세한 결과는 [TEST-03-2-RESULTS](docs/TEST-03-2-RESULTS.md)를 참조하세요.
