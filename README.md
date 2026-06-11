# AudViewer

> MariaDB **Hibernate Envers** (`*_AUD`) 변경 이력을 사람이 보기 좋게 보여주는 데스크톱 도구

Envers 감사 테이블은 변경된 컬럼을 `<컬럼>_MOD = 1` 플래그로만 표시하고, 저장하는 값은 *변경 후* 값뿐이라 "무엇이 무엇으로 바뀌었는지" 한눈에 보기 어렵습니다. AudViewer는 리비전을 시간순으로 따라가며 **이전 값 → 이후 값** diff를 깔끔한 타임라인으로 보여줍니다.

## 동작 방식 (3단계)

1. **연결** — MariaDB 접속 정보 입력 후 *연결 테스트* → 성공하면 다음 단계
2. **테이블** — `*_AUD` 테이블 이름 입력 → 컬럼 구성(데이터/`_MOD`/시스템) 미리보기 → 확정
3. **이력** — 식별자(ID) 값 입력 → 해당 레코드의 변경 이력을 타임라인으로 표시
   (생성 / 수정 / 삭제, 컬럼별 `이전 → 이후` diff)

> 처음 둘러볼 때는 1단계의 **“샘플 데이터로 둘러보기”** 로 DB 없이 전체 흐름을 체험할 수 있습니다.

## 실행 (개발)

Windows · Python 3.9+ 필요.

- **원클릭:** `run.vbs` 더블클릭 (첫 실행은 의존성 설치 콘솔이 잠깐 보이고, 이후엔 조용히 실행)
- **콘솔로 보기/디버깅:** `run.bat` 실행 (설치 로그·에러 출력 확인용)
- 둘 다 자동으로 `.venv` 가상환경을 만들고 `requirements.txt` 를 설치한 뒤 앱을 띄웁니다.

개발 편의를 위해 로그인 폼을 자동 채우려면 `config.example.json` 을 `config.local.json` 으로 복사해 값을 채우세요. **`config.local.json` 은 `.gitignore` 에 포함되어 커밋되지 않습니다.**

## .exe 빌드

```bat
build.bat
```
PyInstaller로 `dist\AudViewer.exe` (단일 실행 파일)를 생성합니다.

## 🔒 보안 / 개인정보 정책 (중요)

이 저장소는 **공개(public)** 입니다. 다음을 **절대 커밋하지 마세요**: 실제 DB 자격증명·접속 문자열, 회사/내부 호스트명, 실제 테이블/컬럼명이나 데이터 샘플, 고객·직원 개인정보(PII).

- 모든 예시·스크린샷·테스트는 합성(synthetic) 데이터(`example.com` 등)를 사용합니다.
- **커밋 전 PII 검사**를 실행하세요:
  ```bat
  python scripts\pii_check.py
  ```
  스테이징된 변경분에서 자격증명·이메일·외부 IP·`config.local.json` 등을 검사합니다.

## 기술 스택

- **UI:** PySide6 (Qt) — 단일 라이트 테마, QSS 스타일, 커스텀 타임라인 위젯
- **DB:** PyMySQL (순수 파이썬)
- **패키징:** PyInstaller → 단일 `.exe`

## 프로젝트 구조

```
app.py                 진입점 — QApplication 생성, 테마 적용
audviewer/
  db.py                PyMySQL 연결/쿼리 (자격증명은 메모리에만 존재)
  introspect.py        스키마 분석 + Envers 컬럼 분류, REVINFO 탐지
  history.py           감사 행 → 시간순 변경 타임라인 빌더
  services.py          UI-비의존 서비스 함수 + AppState (DB/데모 분기)
  demo.py              합성 데모 데이터 (DB 없이 둘러보기)
  ui/
    theme.py           색상 팔레트 + 전역 QSS
    widgets.py         재사용 위젯 (스텝퍼, 타임라인 노드, 값 pill, 비동기 워커)
    window.py          메인 윈도우 + 3단계 페이지
scripts/pii_check.py   커밋 전 PII/시크릿 스캐너
scripts/smoke_ui.py    오프스크린 UI 스모크 테스트
run.vbs / run.bat      원클릭 실행
build.bat              .exe 패키징
```

## 라이선스

TBD.
