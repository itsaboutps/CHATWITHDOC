from collections import deque
from typing import Deque, Dict, Any, List
import time

_BUFFER: Deque[Dict[str, Any]] = deque(maxlen=50)

def record(entry: Dict[str, Any]):
    entry['ts'] = time.time()
    _BUFFER.append(entry)

def last(limit: int = 5) -> List[Dict[str, Any]]:
    out = list(_BUFFER)[-limit:]
    return out[::-1]
