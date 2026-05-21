<p align="center">
  <img src="https://github.com/user-attachments/assets/d4f48f71-d76e-4ffe-9fb1-0b075d79bf05" alt="forza-painter FH6 logo" width="720">
</p>

<h1 align="center">forza-painter FH6</h1>

<p align="center">
  <strong>이미지를 Forza Horizon 6 비닐 그룹 레이어로 변환하고 가져오는 도구입니다.</strong>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">中文</a> ·
  <a href="README.ko-KR.md">한국어</a>
</p>

<p align="center">
  <code>v1.4.0</code> · <code>Windows</code> · <code>Forza Horizon 6</code> · <code>GPU/OpenCL</code>
</p>

PNG/JPG/BMP 이미지를 Forza Horizon 6 비닐 그룹 레이어용 geometry JSON으로 변환합니다. 데스크톱 앱에서 JSON 생성, 미리보기, FH6 가져오기를 한 번에 처리할 수 있으며 일반 사용자는 메모리 주소를 직접 입력하지 않아도 됩니다.

> **결과가 흐릿해 보이면:** 먼저 `Random samples` 값을 높이세요. **200000** 이상부터 품질 차이가 크게 보이는 경우가 많습니다. 값이 높을수록 선명해지지만 생성 시간도 길어집니다.

> **가져오기가 너무 느리면:** v1.4.0 이후 버전은 읽기 알고리즘과 타임아웃 제한이 개선되었습니다. 그래도 완료 전에 타임아웃이 발생하면 로그 파일을 첨부해 이슈를 등록해 주세요.

## 빠른 시작

1. 이 저장소를 ZIP으로 내려받아 압축을 풉니다.
2. 64비트 Python을 설치합니다. Python 3.12를 권장합니다.
3. `install_dependencies.bat`을 더블클릭합니다.
4. `start_app.bat`을 더블클릭합니다.
5. FH6에서 Vinyl Group Editor를 열고 sphere 템플릿을 불러온 뒤 Ungroup합니다.
6. 앱에서 JSON을 생성하고, Import 페이지에서 템플릿 레이어 수를 입력한 뒤 가져오기를 실행합니다.

## 설정

대부분의 사용자는 아래 두 파일만 실행하면 됩니다.

```text
install_dependencies.bat
start_app.bat
```

앱이 시작되지 않으면 아래 파일을 실행해 환경을 확인하세요.

```text
check_environment.bat
```

핵심 Python 앱은 `psutil`과 `pywin32`만 필요합니다. 이미지/JSON 미리보기는 선택 의존성인 NumPy/OpenCV를 사용하며, Python 버전에 따라 설치 프로그램이 미리보기 패키지를 건너뛸 수 있습니다.

## JSON 생성

1. `JSON 생성` 페이지를 엽니다.
2. `이미지 추가`를 클릭하고 PNG/JPG/BMP 이미지를 선택합니다.
3. 품질 프리셋을 선택합니다.
4. 필요하면 `사용자 설정 사용`을 켜고 출력 레이어, 해상도, 무작위 샘플, 변형 샘플을 조정합니다.
5. 하단의 `현재 설정으로 생성` 버튼을 클릭합니다.
6. 미리보기와 로그가 업데이트될 때까지 기다립니다.

생성된 파일은 원본 이미지 옆에 저장됩니다.

```text
image.500.json
image.1000.json
image.3000.json
```

템플릿 레이어 수와 맞는 가장 높은 레이어 JSON을 사용하는 것이 좋습니다. 예를 들어 3000 레이어 템플릿에는 `image.3000.json` 또는 최종 `image.json`을 사용하세요.

## FH6 준비

1. Forza Horizon 6를 실행합니다.
2. `Create Vinyl Group` / `Vinyl Group Editor`를 엽니다.
3. 많은 단순 sphere 레이어로 만든 템플릿을 불러옵니다.
4. 템플릿을 `Ungroup`합니다.
5. 게임에 표시된 정확한 레이어 수를 기억합니다.
6. 가져오기 중에는 이 편집기 화면을 유지합니다.

권장 템플릿 크기는 500~3000 레이어입니다.

## JSON 가져오기

1. `가져오기` 페이지를 엽니다.
2. `새로고침`을 클릭하고 실행 중인 `forzahorizon6.exe`를 선택합니다.
3. 현재 게임 안 템플릿 레이어 수를 입력합니다.
4. 생성된 `.json`을 추가하거나 `생성된 JSON 사용`을 클릭합니다.
5. 고급 주소 입력칸은 비워둡니다.
6. `JSON 가져오기`를 클릭합니다.

앱은 현재 FH6 레이어 테이블을 찾아 검증한 뒤 쓰기를 진행합니다. 안전하게 검증할 수 없으면 쓰기 전에 중지합니다.

> FH는 커버 저장과 적용 범위를 올바르게 처리하려면 경계 레이어 4개가 더 필요합니다.  
> 예: 1000 레이어 JSON은 최소 1004 레이어 템플릿을 사용해야 하며, 3000 레이어 템플릿은 약 2996개의 그릴 수 있는 shape를 가져올 수 있습니다.

## 규칙

- 템플릿은 반드시 ungroup 상태여야 합니다.
- 앱에 입력한 레이어 수는 게임의 레이어 수와 정확히 같아야 합니다.
- 가져오는 동안 게임 메뉴를 전환하지 마세요.
- 게임을 재시작하거나 템플릿을 다시 불러오거나 레이어 수가 바뀌면 새 값으로 다시 가져오세요.
- JSON 레이어가 템플릿보다 적으면 남는 템플릿 레이어는 숨겨집니다.
- JSON 레이어가 템플릿보다 많으면 초과 shape는 잘립니다.
- 가져온 이미지가 흐릿하면 낮은 레이어 체크포인트를 가져왔거나 출력 레이어를 너무 적게 생성했을 가능성이 큽니다.
- 투명 PNG 배경은 보이는 배경으로 가져오지 않습니다.
