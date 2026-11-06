import sys
from pathlib import Path

# Import the HA-independent core as a top-level package so tests don't need Home Assistant.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "eink_calendar"))
