import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))
from ai_previz_director.director.context import get_previz_state
from ai_previz_director.director.shot import load_shots

state = get_previz_state()
ok = any(a["id"] == "actor_girl_01" for a in state["actors"]) and any(p["id"] == "product_earbud_case" for p in state["products"]) and len(load_shots()) == 2
result = {"name": "TEST 8 restart persistence", "status": "PASS" if ok else "FAIL", "detail": {"actors": state["actors"], "products": state["products"], "shots": load_shots()}}
print("AI_PREVIZ_RELOAD", json.dumps(result, ensure_ascii=False))
if not ok:
    raise SystemExit(1)

