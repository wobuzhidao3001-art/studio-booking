from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from database import get_db, get_config, set_config
from auth import get_current_user

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigUpdate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


class ConfigResponse(BaseModel):
    key: str
    value: str
    description: str = ""


@router.get("")
async def list_configs(user=Depends(get_current_user)):
    """List all system configurations (admin/manager only)."""
    roles = set(user.get("roles", []))
    if "admin" not in roles and "studio_manager" not in roles:
        raise HTTPException(status_code=403, detail="Permission denied")

    db = await get_db()
    try:
        cur = await db.execute("SELECT key, value, description FROM system_config ORDER BY key")
        rows = await cur.fetchall()
        return {"configs": [{"key": r["key"], "value": r["value"], "description": r["description"]} for r in rows]}
    finally:
        await db.close()


@router.get("/public")
async def get_public_configs():
    """Get public-facing config values (no auth required)."""
    max_minutes = await get_config("max_booking_minutes", "180")
    unit_name = await get_config("unit_name", "")
    return {
        "max_booking_minutes": int(max_minutes),
        "unit_name": unit_name,
    }


@router.put("")
async def update_config(body: ConfigUpdate, user=Depends(get_current_user)):
    """Update a system configuration (admin only)."""
    roles = set(user.get("roles", []))
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Permission denied")

    if not body.key.strip():
        raise HTTPException(status_code=400, detail="Key is required")
    if not body.value.strip():
        raise HTTPException(status_code=400, detail="Value is required")

    # Validate max_booking_minutes
    if body.key == "max_booking_minutes":
        try:
            val = int(body.value)
            if val < 30 or val > 480:
                raise HTTPException(status_code=400, detail="预约时长必须在30-480分钟之间")
            # Round to nearest 30
            val = round(val / 30) * 30
            body.value = str(val)
        except ValueError:
            raise HTTPException(status_code=400, detail="请输入有效的数字（分钟）")

    desc = body.description or ""
    await set_config(body.key, body.value, desc)

    return {"message": "配置已更新", "key": body.key, "value": body.value}
