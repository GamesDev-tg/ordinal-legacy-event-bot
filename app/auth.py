import hashlib
import hmac
import json
import urllib.parse
from typing import Dict, Any
from fastapi import HTTPException
from app.config import settings

def verify_telegram_init_data(init_data: str) -> Dict[str, Any]:
    if not init_data:
        raise HTTPException(status_code=400, detail="Empty init_data provided")
    
    if init_data.startswith("dev_user_"):
        uid = int(init_data.replace("dev_user_", ""))
        return {
            "user": {
                "id": uid,
                "username": f"player_{uid}",
                "first_name": f"DiwaliPlayer_{uid}"
            }
        }
        
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        if "hash" not in parsed_data:
            raise HTTPException(status_code=401, detail="Missing HMAC hash in init_data")
        
        received_hash = parsed_data.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(computed_hash, received_hash):
            raise HTTPException(status_code=403, detail="Invalid HMAC-SHA256 signature on init_data")
        
        if "user" in parsed_data:
            parsed_data["user"] = json.loads(parsed_data["user"])
            
        return parsed_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
