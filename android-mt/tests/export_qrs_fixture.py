"""Write SYNTHETIC, non-secret QRS frames for the independent decoder test."""
import json
import random
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'app/src/main/python'))
import qrs_profile
rng = random.Random(7821)
config = json.dumps({'unicode':'中文 🇯🇵', 'payload': ''.join(rng.choices('abcdef0123456789', k=40000))},ensure_ascii=False)
out = root/'test-output'
out.mkdir(exist_ok=True)
(out/'qrs-fixture.json').write_text(json.dumps({'name':'跨设备测试 🇯🇵', 'config':config,
    'frames':qrs_profile.frames(config,'跨设备测试 🇯🇵')},ensure_ascii=False),encoding='utf-8')
print('Synthetic QRS fixture generated.')
