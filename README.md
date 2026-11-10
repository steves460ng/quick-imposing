# quick-imposing

원본 PDF 콘텐츠와 이미지·폰트 스트림을 보존하면서 카드를 회전·클리핑하여 배치합니다. Python 3.12 이상, qpdf, Poppler(`pdftoppm`, `pdffonts`, `pdfimages`)가 필요합니다.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## JSON 템플릿 실행

```sh
python quick_imposing.py samples/templates/t2-01-default-3x8.json
python quick_imposing.py samples/templates/t2-02-irregular.json
```

경로는 저장소 루트 기준입니다. 템플릿의 슬롯 좌표와 배정을 그대로 사용하며 빈 슬롯도 기록합니다. 결과는 `out/test02/<name>/result.pdf`, `report.json`, `preview.png`에 생성됩니다. 잘못된 템플릿은 가능한 오류를 모두 리포트에 기록하고 PDF를 생성하지 않습니다. 기존 출력이 있으면 덮어쓰지 않습니다. 재실행에는 `--out <새 폴더>`를 지정하세요.

## 프리셋 실행

```sh
python quick_imposing.py --base samples/input/base.pdf \
  --files samples/input/B-1.pdf samples/input/B-2.pdf samples/input/B-3.pdf \
  --out out/preset-example
```

기본 프리셋은 `presets/default-3x8.json`(3×8, 간격 1mm, 판 중앙)입니다. `--preset <파일 또는 이름>`으로 변경할 수 있습니다. 카드 크기, 0/90/−90/180도 회전, `sheet-center`/`safe-area-center`/`margin` 정렬과 직접 지정 `slots_mm`를 지원합니다. `slots_mm`가 있으면 격자 대신 사용하고 명시한 격자의 슬롯 수와 다를 경우 경고를 기록합니다. 기존 `--layout layout.json --cards samples/input` 인터페이스도 유지합니다.

## 검증

```sh
python -m pytest -q
python test02_runner.py
# 결과 폴더가 이미 있으면:
python test02_runner.py --out out/test02-rerun
```

TEST-02 실행기는 기대값을 읽어 생성된 PDF의 실제 연산자와 리소스를 대조합니다. 배치 엔진은 기대값을 읽지 않습니다. 요약은 `out/test02/summary.json`입니다. 자동 검사의 PASS와 V15 사람 방향 확인은 구분하며 Illustrator에서 직접 열기 검증도 별도입니다. 생성 후 검증 실패 시 FAIL 리포트와 진단용 PDF가 남을 수 있습니다.

현재 클라우드에서는 `/workspace/.venvs/quick-imposing/bin/python`을 사용할 수 있습니다. qpdf가 PATH에 없으면 이 환경에 준비된 `/workspace/.setup/qpdf/usr/bin/qpdf`를 사용합니다.

## Illustrator 호환 처리

베이스의 `/PieceInfo/Illustrator`에는 배치 전의 전용 편집 데이터가 남을 수 있습니다. 결과 저장 전에 이 항목만 문서·페이지에서 제거하여 Illustrator가 이전 artwork를 여는 것을 방지합니다. 다른 프로그램의 PieceInfo와 PDF 콘텐츠·리소스, 입력 파일은 보존합니다. 처리 위치는 리포트의 `illustrator_private_data_removed`에 기록합니다. Illustrator 고유 편집 데이터의 왕복 보존은 지원하지 않습니다. 실제 Illustrator에서 카드가 표시되는지는 별도 확인이 필요합니다.

요구사항: [SPEC](docs/SPEC.md), [TEST-02](docs/TEST-02.md). 실행 결과: [2차 테스트 보고](docs/TEST-02-RESULTS.md).
