import sys
import os

# Ensure the repository root directory is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.main import app

try:
    from app.database import init_db
    init_db()
except Exception as e:
    print(f"[COLD_START_INIT_DB_ERROR]: {e}")
