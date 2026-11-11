# quick-imposing

템플릿의 셀 배열에 PDF 카드를 배치하고, 작업별 텍스트를 K100으로 추가합니다. 기존 PDF의 콘텐츠·이미지·폰트 스트림을 재해석하거나 래스터화하지 않습니다. 3-1차 기준은 [TASK-03-1](docs/TASK-03-1.md)입니다. 자동 배열과 GUI는 포함하지 않습니다.

## 설치

Python 3.12 이상과 **qpdf**, **Poppler**(`pdftoppm`, `pdffonts`, `pdfimages`, `pdftotext`)를 설치하고 실행 파일을 PATH에 추가합니다.

```sh
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell에서는 .venv\Scripts\Activate.ps1
python -m pip install -e '.[test]'
```

한글 픽스처는 시스템에 설치된 **Noto Sans CJK KR Regular**를 사용합니다. 운영체제 글꼴 폴더에서 이름으로 찾으며, `--font-dir <폴더>`를 반복 지정해 추가 폴더를 검색할 수 있습니다. 다른 글꼴로 조용히 대체하지 않습니다. TrueType와 CID-keyed CFF를 서브셋 임베드하며 ToUnicode를 포함합니다. 글꼴 임베드 권한이나 글리프가 없으면 오류를 보고합니다.

## 템플릿 만들기

```sh
quick-imposing create-template samples/test03-1/template-defs/T31-front-3x8.json \
  --base samples/input/base-front-blank.pdf \
  --templates-root out/my-templates
```

`out/my-templates/T31-front-3x8/`에 `template.json`과 원본과 바이트가 같은 `base.pdf`를 만듭니다. 기존 템플릿 폴더를 덮어쓰지 않습니다. 일반 입력은 `template@2` JSON입니다. 테스트용 정의 파일은 `template`과 원본 위치 `source_base`를 가진 외부 래퍼이며, 템플릿 폴더에 저장하는 JSON에는 이 래퍼가 들어가지 않습니다.

## 프로젝트로 PDF 생성

```sh
quick-imposing build samples/test03-1/projects/T31-01.qiproj.json \
  --templates-root out/my-templates \
  --output out/example/result.pdf
```

`python -m imposing`도 같은 명령을 제공합니다. 출력 PDF 옆에 `result.qiproj.json`, `result.png`, `report.json`을 저장합니다. 프로젝트의 B 경로는 입력 프로젝트 위치에서 해석하고, 저장할 때 새 프로젝트 위치 기준으로 다시 계산합니다. 저장한 프로젝트도 같은 명령으로 다시 열 수 있습니다. 수정된 현재 템플릿을 읽으며, 사라진 셀은 오류로 처리합니다.

- 셀 번호는 행 우선으로 고정합니다. `fill_direction`은 형식만 검사합니다.
- 그리는 순서는 베이스 → `order` 오름차순의 B → 텍스트입니다.
- 겹침은 경고 후 진행합니다. 판 경계는 B 좌표계의 Form BBox로 잘라냅니다.
- B 크기 차이는 경고하지 않습니다. 없는 B와 알 수 없는 텍스트 id는 리포트 정보에만 기록합니다.
- 빈 텍스트는 그리지 않습니다. 좌표는 첫 글자의 왼쪽 기준선입니다.
- 기존 PDF·프로젝트·리포트·미리보기가 있으면 덮어쓰지 않습니다. 새 출력 폴더를 선택하세요.

## 테스트

```sh
python -m pytest -q
python test03_runner.py
# 기본 출력 폴더가 이미 있다면 새 폴더 사용
python test03_runner.py --out out/test03-1-rerun
```

실행기는 `out/test03-1/templates/`에 베이스 사본을 포함한 템플릿을 생성하고, T31-01~09(03a/03b 별도, 총 10개)를 실행합니다. §4.3의 숫자는 기대값 JSON에 그대로 적었으며 배치 엔진은 이 파일을 읽지 않습니다. 독립 행렬 계산과 원본 페이지로 만든 참조 PDF의 렌더링을 실제 결과와 비교합니다. 다른 B를 넣었을 때 이미지 차이가 나는지도 검사합니다.

결과는 `out/test03-1/summary.json` 및 각 케이스 `report.json`에 기록됩니다. `out/`은 커밋하지 않습니다. 생성 명령의 PASS는 PDF 구문·입력 보존 검사를 뜻하며, C1~C10의 전체 비교 결과는 테스트 실행기에서 확인합니다. Illustrator 직접 표시와 사람 방향 확인은 별도 항목으로 남깁니다.

## Illustrator 처리

결과 저장 전 카탈로그와 페이지의 `/PieceInfo/Illustrator`만 제거하고, 다른 앱의 PieceInfo는 유지합니다. 베이스에 남은 배치 전 Illustrator 편집 데이터를 다시 여는 문제를 막기 위한 SPEC R11 처리입니다. 원본 입력은 변경하지 않으며 처리 위치를 리포트에 기록합니다. 결과를 일반 PDF로 열게 되므로 Illustrator 고유 편집 구조의 왕복 보존은 지원하지 않습니다.

상세 결과와 질문은 [TEST-03-1-RESULTS](docs/TEST-03-1-RESULTS.md)를 참조하세요.
