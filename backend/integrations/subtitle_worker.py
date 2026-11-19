"""Short-lived subtitle worker; model imports never enter the API process."""

import json
import sys
from pathlib import Path

from backend.integrations.subtitles import _align_subtitles


if __name__ == "__main__":
    request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    _align_subtitles(Path(request["audio_path"]), request["text"], request["language"])
