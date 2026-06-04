import os
import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from database import get_db
from auth import get_current_user, require_role
from config import UPLOAD_DIR, BASE_DIR

router = APIRouter(prefix="/api/reports", tags=["reports"])


def get_upload_path(category: str) -> str:
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    p = os.path.join(BASE_DIR, UPLOAD_DIR, month, category)
    os.makedirs(p, exist_ok=True)
    return p


@router.post("/{app_id}/submit")
async def submit_report(
    app_id: int,
    items_returned: str = Form(...),
    cleanliness: str = Form(...),
    damage: str = Form(""),
    score: float = Form(...),
    photos_returned: list[UploadFile] = File(default=[]),
    photos_cleanliness: list[UploadFile] = File(default=[]),
    photos_damage: list[UploadFile] = File(default=[]),
    user=Depends(require_role("executor")),
):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM applications WHERE id=?", (app_id,))
        app = await cur.fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        if app["status"] != "completed":
            raise HTTPException(status_code=400, detail="Application must be completed first")
        if app["assigned_executor_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="You are not the assigned executor")

        if score < 0 or score > 10.0:
            raise HTTPException(status_code=400, detail="Score must be 0-10")

        cur = await db.execute(
            "SELECT id FROM post_event_reports WHERE application_id=?", (app_id,)
        )
        if await cur.fetchone():
            raise HTTPException(status_code=400, detail="Report already exists")

        cur = await db.execute(
            "INSERT INTO post_event_reports (application_id, items_returned, cleanliness, damage, score) VALUES (?,?,?,?,?)",
            (app_id, items_returned, cleanliness, damage, score),
        )
        report_id = cur.lastrowid

        photo_groups = [
            ("returned", photos_returned),
            ("cleanliness", photos_cleanliness),
            ("damage", photos_damage),
        ]
        for category, files in photo_groups:
            for f in files:
                if f.filename:
                    ext = os.path.splitext(f.filename)[1] or ".jpg"
                    filename = f"{uuid.uuid4().hex}{ext}"
                    up = get_upload_path(category)
                    filepath = os.path.join(up, filename)
                    content = await f.read()
                    with open(filepath, "wb") as wf:
                        wf.write(content)
                    rel_path = os.path.relpath(filepath, BASE_DIR)
                    await db.execute(
                        "INSERT INTO report_photos (report_id, category, file_path) VALUES (?,?,?)",
                        (report_id, category, rel_path),
                    )

        await db.execute(
            "UPDATE applications SET status='reported', updated_at=datetime('now','localtime') WHERE id=?",
            (app_id,),
        )
        await db.commit()
        return {"message": "Report submitted", "report_id": report_id}
    finally:
        await db.close()
