"""When the catalog was last actually refreshed from ČSFD.

The site wants to tell a visitor how fresh its data is, and none of the timestamps
already lying around answer that:

  - `last_vod_date` is the newest release date in the catalog. It is usually in the
    *future* — the footer showed "Poslední aktualizace: 31. srpna 2026" on 7 August.
  - `generated_at` is when the JSON was written. `csfd streamfinder` can be run on
    its own, with no scraping at all, and it moves — so it can claim freshness the
    data does not have.

What a visitor means by "last updated" is the last time the pipeline successfully
fetched from ČSFD. Only `update` knows that, and only after discover or refresh has
actually run: an `update --skip-discover --skip-refresh` re-exports old data and
must not claim otherwise. So `update` records it here and the exporter copies it
into meta.json, where a standalone export carries the previous value forward
untouched — which is the honest answer, because nothing new was fetched.

State lives with the cache rather than in the repo: it describes this machine's
pipeline, not the checked-out code.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

STATE_FILENAME = "refresh_state.json"


def write_refresh(cache_dir: str | Path, when: Optional[float] = None) -> str:
    """Record that a refresh completed. Returns the timestamp written."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(when if when is not None else time.time()))
    path = Path(cache_dir) / STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_refresh_at": stamp}, indent=2), encoding="utf-8")
    return stamp


def read_refresh(cache_dir: str | Path) -> Optional[str]:
    """The last recorded refresh, or None if the pipeline has never completed one."""
    path = Path(cache_dir) / STATE_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    stamp = data.get("last_refresh_at") if isinstance(data, dict) else None
    return stamp if isinstance(stamp, str) else None
