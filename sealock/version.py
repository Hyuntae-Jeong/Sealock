"""App version — the single source of truth.

The value committed here is a placeholder. Release builds get it rewritten by
GitHub Actions from the pushed git tag (`vX.Y.Z`) — see the "Inject version
from tag" step in `.github/workflows/release.yml`.

A ``+dev`` suffix therefore means "not a release build", and the updater
refuses to replace anything in that state (see updater.can_self_update).

업데이트 흐름을 시험할 때는 아래 줄을 고치지 말고, 한 번의 실행 동안만 낮은
버전을 뒤집어쓴다. 파일을 고치는 방식은 되돌리기를 잊기 쉬웠고 — 시험용 값이
작업 트리에 남아 커밋에 딸려 들어가기를 기다렸다 — 값을 바꿀 때마다 ./build.sh
를 다시 돌려야 했다:

    export SEALOCK_VERSION=0.0.2
    dist/Sealock.app/Contents/MacOS/Sealock     # → "새 버전이 있습니다"
    unset SEALOCK_VERSION                       # (창을 닫아도 사라진다)

``export`` 로 깔아두어야 한다: ``SEALOCK_VERSION=0.0.2 sealock`` 처럼 앞에 붙이면
그 별칭이 ``cd ... && python ...`` 이라 값이 ``cd`` 에만 붙는다. ``open`` 으로 여는
.app 에도 넘어가지 않으므로, 시험할 때는 실행 파일 경로로 띄운다.

CI 가 이 파일을 통째로 새로 쓰므로 릴리즈 빌드에는 이 우회로가 아예 없다 —
개발용으로 열어둔 문이지 사용자가 건드릴 수 있는 스위치가 아니다.
"""
import os

__version__ = os.environ.get("SEALOCK_VERSION", "").strip() or "1.0.2+dev"
