from fastapi import APIRouter, HTTPException, Depends
from database import get_db
from schemas import MeetingTypeCreate, MeetingTypeUpdate
from auth import get_current_user, require_role

router = APIRouter(tags=["public"])


# ── Meeting Types (admin) ──

@router.get("/api/meeting-types")
async def list_meeting_types():
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM meeting_types WHERE is_active=1 ORDER BY id")
        return {"types": [dict(r) for r in await cur.fetchall()]}
    finally:
        await db.close()


@router.get("/api/meeting-types/all")
async def list_all_meeting_types(user=Depends(require_role("admin", "executor"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM meeting_types ORDER BY id")
        return {"types": [dict(r) for r in await cur.fetchall()]}
    finally:
        await db.close()


@router.post("/api/meeting-types")
async def create_meeting_type(body: MeetingTypeCreate, user=Depends(require_role("admin", "executor"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM meeting_types WHERE name=?", (body.name,))
        if await cur.fetchone():
            raise HTTPException(status_code=400, detail="Meeting type already exists")
        cur = await db.execute("INSERT INTO meeting_types (name) VALUES (?)", (body.name,))
        await db.commit()
        return {"id": cur.lastrowid, "message": "Created"}
    finally:
        await db.close()


@router.put("/api/meeting-types/{type_id}")
async def update_meeting_type(type_id: int, body: MeetingTypeUpdate, user=Depends(require_role("admin", "executor"))):
    db = await get_db()
    try:
        if body.name is not None:
            await db.execute("UPDATE meeting_types SET name=? WHERE id=?", (body.name, type_id))
        if body.is_active is not None:
            await db.execute("UPDATE meeting_types SET is_active=? WHERE id=?", (body.is_active, type_id))
        await db.commit()
        return {"message": "Updated"}
    finally:
        await db.close()


# ── Public Board ──

@router.get("/api/public-board")
async def public_board(user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute("""
            SELECT a.id, a.meeting_topic, a.start_time, a.end_time, a.created_at AS app_created_at,
                   u.real_name AS applicant_name, a.department, a.contact, a.on_site_contact,
                   mt.name AS meeting_type_name,
                   r.items_returned, r.cleanliness, r.damage, r.score, r.id AS report_id
            FROM applications a
            JOIN users u ON a.applicant_id = u.id
            JOIN meeting_types mt ON a.meeting_type_id = mt.id
            JOIN post_event_reports r ON r.application_id = a.id
            WHERE a.status = 'reported' 
            ORDER BY a.created_at DESC
        """)
        items = [dict(r) for r in await cur.fetchall()]
        for item in items:
            cur = await db.execute(
                "SELECT * FROM report_photos WHERE report_id=? ORDER BY category, id",
                (item["report_id"],),
            )
            item["photos"] = [dict(p) for p in await cur.fetchall()]
        return {"board": items}
    finally:
        await db.close()

@router.delete("/api/meeting-types/{type_id}")
async def delete_meeting_type(type_id: int, user=Depends(require_role("admin", "executor"))):
    db = await get_db()
    try:
        await db.execute("DELETE FROM meeting_types WHERE id=?", (type_id,))
        await db.commit()
        return {"message": "Deleted"}
    finally:
        await db.close()


from fastapi.responses import StreamingResponse
from fastapi import UploadFile, File
import io, csv
from datetime import datetime


@router.post("/api/admin/reports/import")
async def import_reports(file: UploadFile = File(...), user=Depends(require_role("admin"))):
    """Import completed applications from CSV"""
    db = await get_db()
    try:
        contents = await file.read()
        # Handle BOM
        if contents[:3] == b'\xef\xbb\xbf':
            contents = contents[3:]
        text = contents.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        
        imported = 0
        errors = []
        for row_num, row in enumerate(reader, start=2):
            try:
                topic = row.get("会议主题", "").strip()
                dept = row.get("学部", "").strip()
                applicant_name = row.get("申请人", "").strip()
                on_site = row.get("现场负责人", "").strip()
                type_name = row.get("会议类型", "").strip()
                start_time = row.get("开始时间", "").strip()
                end_time = row.get("结束时间", "").strip()
                executor_name = row.get("执行人", "").strip()
                score_str = row.get("得分", "").strip()
                items_returned = row.get("物品归位", "").strip()
                cleanliness = row.get("卫生保持", "").strip()
                damage = row.get("公物损坏", "").strip()

                if not topic or not applicant_name:
                    errors.append(f"行{row_num}: 缺少会议主题或申请人")
                    continue

                # Find or create meeting type
                cur = await db.execute("SELECT id FROM meeting_types WHERE name=?", (type_name,))
                mt = await cur.fetchone()
                if not mt:
                    cur = await db.execute("INSERT INTO meeting_types (name) VALUES (?)", (type_name or "其他",))
                    mt_id = cur.lastrowid
                else:
                    mt_id = mt["id"]

                # Find applicant
                cur = await db.execute("SELECT id FROM users WHERE real_name=? AND is_active=1", (applicant_name,))
                app_user = await cur.fetchone()
                if not app_user:
                    errors.append(f"行{row_num}: 未找到用户 '{applicant_name}'")
                    continue
                applicant_id = app_user["id"]

                # Find executor
                executor_id = None
                if executor_name:
                    cur = await db.execute("SELECT id FROM users WHERE real_name=?", (executor_name,))
                    ex = await cur.fetchone()
                    if ex:
                        executor_id = ex["id"]

                # Parse time
                st = start_time.replace(" ", "T") if start_time else datetime.now().strftime("%Y-%m-%dT%H:%M")
                et = end_time.replace(" ", "T") if end_time else datetime.now().strftime("%Y-%m-%dT%H:%M")

                # Create application
                cur = await db.execute(
                    """INSERT INTO applications
                       (applicant_id, department, contact, meeting_topic, meeting_type_id,
                        start_time, end_time, on_site_contact, status, assigned_executor_id)
                       VALUES (?,?,?,?,?,?,?,?,'reported',?)""",
                    (applicant_id, dept, "", topic, mt_id, st, et, on_site, executor_id),
                )
                app_id = cur.lastrowid

                # Create report
                score = float(score_str) if score_str else 0
                cur = await db.execute(
                    """INSERT INTO post_event_reports
                       (application_id, items_returned, cleanliness, damage, score)
                       VALUES (?,?,?,?,?)""",
                    (app_id, items_returned or "", cleanliness or "", damage or "", score),
                )

                imported += 1
            except Exception as e:
                errors.append(f"行{row_num}: {str(e)}")

        await db.commit()
        return {"imported": imported, "errors": errors}
    finally:
        await db.close()


@router.get("/api/admin/reports/export")
async def export_reports(
    start_date: str = "",
    end_date: str = "",
    user=Depends(require_role("admin", "executor")),
):
    db = await get_db()
    try:
        conditions = ["a.status = 'reported'"]
        params = []
        if start_date:
            conditions.append("a.start_time >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("a.start_time <= ?")
            params.append(end_date + " 23:59:59")

        where = " AND ".join(conditions)
        cur = await db.execute(f"""
            SELECT a.id, a.meeting_topic, a.department, a.on_site_contact, a.start_time, a.end_time,
                   u.real_name AS applicant_name, mt.name AS meeting_type,
                   eu.real_name AS executor_name, r.score,
                   r.items_returned, r.cleanliness, r.damage
            FROM applications a
            JOIN users u ON a.applicant_id = u.id
            JOIN meeting_types mt ON a.meeting_type_id = mt.id
            LEFT JOIN users eu ON a.assigned_executor_id = eu.id
            JOIN post_event_reports r ON r.application_id = a.id
            WHERE {where}
            ORDER BY a.start_time DESC
        """, params)

        rows = await cur.fetchall()

        output = io.StringIO()
        output.write('﻿')  # BOM for Excel
        writer = csv.writer(output)
        writer.writerow(["ID", "会议主题", "学部", "申请人", "现场负责人", "会议类型", "开始时间", "结束时间", "执行人", "得分", "物品归位", "卫生保持", "公物损坏"])
        for row in rows:
            writer.writerow([
                row["id"], row["meeting_topic"], row["department"],
                row["applicant_name"], row["on_site_contact"] or "", row["meeting_type"],
                row["start_time"], row["end_time"],
                row["executor_name"] or "", row["score"],
                row["items_returned"], row["cleanliness"], row["damage"] or ""
            ])
        output.seek(0)

        filename = f"reports_{start_date or 'all'}_{end_date or 'all'}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    finally:
        await db.close()
