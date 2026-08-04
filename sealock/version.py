"""App version — the single source of truth.

The value committed here is a placeholder. Release builds get it rewritten by
GitHub Actions from the pushed git tag (`vX.Y.Z`) — see the "Inject version
from tag" step in `.github/workflows/release.yml`.

A ``+dev`` suffix therefore means "not a release build", and the updater
refuses to replace anything in that state (see updater.can_self_update).
To exercise the update flow from a local build, write a plain version that is
*older* than the published release here (e.g. "0.0.2") and run ./build.sh.
"""

__version__ = "0.0.3+dev"
