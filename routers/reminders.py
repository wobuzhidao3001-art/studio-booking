from fastapi import APIRouter, HTTPException, Depends
from database import get_db
from schemas import ReminderCreate
from auth import get_current_user

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.post("/{app_id}")
async def create_reminder(app_id: int, body: ReminderCreate, user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM applications WHERE id=?", (app_id,))
        app = await cur.fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        if app["applicant_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Only the applicant can send reminders")

        # Check already reminded for this stage
        cur = await db.execute(
            "SELECT id FROM reminders WHERE application_id=? AND target_stage=?",
            (app_id, body.target_stage),
        )
        if await cur.fetchone():
            raise HTTPException(status_code=400, detail="Already reminded for this stage")

        cur = await db.execute(
            "INSERT INTO reminders (application_id, from_user_id, target_stage, message) VALUES (?,?,?,?)",
            (app_id, user["id"], body.target_stage, body.message),
        )
        await db.commit()
        return {"id": cur.lastrowid, "message": "Reminder sent"}
    finally:
        await db.close()


@router.get("/pending")
async def pending_reminders(user=Depends(get_current_user)):
    db = await get_db()
    try:
        roles = set(user.get("roles", []))
        stage_map = {}
        if "dept_supervisor" in roles:
            stage_map["dept"] = True
        if "studio_manager" in roles:
            stage_map["studio"] = True
        if "executor" in roles:
            stage_map["assign"] = True

        if not stage_map:
            return {"reminders": []}

        conditions = []
        params = []
        for stage in stage_map:
            conditions.append("r.target_stage = ?")
            params.append(stage)

        sql = f"""
            SELECT r.*, a.meeting_topic, u.real_name AS applicant_name
            FROM reminders r
            JOIN applications a ON r.application_id = a.id
            JOIN users u ON r.from_user_id = u.id
            WHERE ({' OR '.join(conditions)})
            ORDER BY r.created_at DESC
            LIMIT 20
        """
        cur = await db.execute(sql, params)
        return {"reminders": [dict(r) for r in await cur.fetchall()]}
    finally:
        await db.close()
