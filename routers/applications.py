from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional
from database import get_db, get_config
from schemas import ApplicationCreate, ApplicationUpdate
from auth import get_current_user, require_role
from datetime import datetime

router = APIRouter(prefix="/api/applications", tags=["applications"])


async def check_conflict(db, start_time: str, end_time: str, exclude_id: int = None):
    sql = """
        SELECT id, meeting_topic, start_time, end_time FROM applications
        WHERE status NOT IN ('rejected','dept_rejected','studio_rejected')
        AND start_time < ? AND end_time > ?
    """
    params = [end_time, start_time]
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    cur = await db.execute(sql, params)
    return [dict(r) for r in await cur.fetchall()]


@router.get("")
async def list_applications(
    status: str = Query(None),
    user=Depends(get_current_user),
):
    db = await get_db()
    try:
        roles = set(user.get("roles", []))
        params = []
        conditions = []

        if "admin" in roles or "studio_manager" in roles:
            pass
        elif "applicant" in roles and len(roles) == 1:
            conditions.append("a.applicant_id = ?")
            params.append(user["id"])
        elif "dept_supervisor" in roles:
            conditions.append("a.department = ?")
            params.append(user["department"])
        elif "executor" in roles:
            pass

        if status:
            conditions.append("a.status = ?")
            params.append(status)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT a.*, u.real_name AS applicant_name, mt.name AS meeting_type_name,
                   eu.real_name AS executor_name, r.score
            FROM applications a
            JOIN users u ON a.applicant_id = u.id
            JOIN meeting_types mt ON a.meeting_type_id = mt.id
            LEFT JOIN users eu ON a.assigned_executor_id = eu.id
            LEFT JOIN post_event_reports r ON r.application_id = a.id
            {where}
            ORDER BY a.created_at DESC
        """
        cur = await db.execute(sql, params)
        return {"applications": [dict(r) for r in await cur.fetchall()]}
    finally:
        await db.close()


@router.get("/calendar")
async def calendar_view(days: int = 7, user=Depends(get_current_user)):
    """Return applications grouped by day with time-slot mapping for calendar view"""
    db = await get_db()
    try:
        from datetime import date, timedelta
        today = date.today().strftime("%Y-%m-%d")
        end = (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")

        cur = await db.execute(
            """SELECT a.id, a.meeting_topic, a.start_time, a.end_time, a.status, a.department,
                      a.on_site_contact, a.applicant_id,
                      u.real_name AS applicant_name, mt.name AS meeting_type_name
               FROM applications a
               JOIN users u ON a.applicant_id = u.id
               JOIN meeting_types mt ON a.meeting_type_id = mt.id
               WHERE a.status NOT IN ('dept_rejected','studio_rejected')
               AND a.start_time >= ? AND a.start_time < ?
               ORDER BY a.start_time ASC""",
            (today, end),
        )
        apps = [dict(r) for r in await cur.fetchall()]

        # Stats
        cur = await db.execute(
            "SELECT COUNT(*) FROM applications WHERE start_time >= ? AND start_time < ? AND status NOT IN ('dept_rejected','studio_rejected')",
            (today, end),
        )
        week_total = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM applications WHERE status NOT IN ('dept_rejected','studio_rejected') AND date(start_time) = ?",
            (today,),
        )
        today_total = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM applications WHERE status = 'reported'"
        )
        completed_total = (await cur.fetchone())[0]

        # Group by day and compute slots
        days_map = {}
        SLOT_START = 7.5  # 7:30
        SLOT_END = 21.0

        for app in apps:
            day = app["start_time"][:10]
            if day not in days_map:
                days_map[day] = {"date": day, "apps": []}

            # Compute start/end slot indices
            try:
                st = app["start_time"]
                et = app["end_time"]
                st_h = int(st[11:13]) + int(st[14:16]) / 60.0
                et_h = int(et[11:13]) + int(et[14:16]) / 60.0
                start_slot = max(0, int((st_h - SLOT_START) / 0.5))
                end_slot = min(53, int((et_h - SLOT_START) / 0.5))
            except:
                start_slot = 0
                end_slot = 0

            # Determine status color class
            if app["status"] == "reported":
                status_class = "completed"
            elif app["status"] in ("dept_rejected", "studio_rejected"):
                status_class = "overdue"
            else:
                status_class = "booked"

            days_map[day]["apps"].append({
                "id": app["id"],
                "topic": app["meeting_topic"],
                "applicant": app["applicant_name"],
                "department": app["department"],
                "on_site_contact": app["on_site_contact"] or "",
                "type": app["meeting_type_name"],
                "start": app["start_time"],
                "end": app["end_time"],
                "start_slot": start_slot,
                "end_slot": end_slot,
                "status": app["status"],
                "status_class": status_class,
            })

        return {
            "today": today,
            "stats": {
                "today_total": today_total,
                "week_total": week_total,
                "completed_total": completed_total,
            },
            "days": [days_map[d] for d in sorted(days_map.keys())],
        }
    finally:
        await db.close()


@router.get("/{app_id}")
async def get_application(app_id: int, user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT a.*, u.real_name AS applicant_name, mt.name AS meeting_type_name,
                      eu.real_name AS executor_name, r.score
               FROM applications a
               JOIN users u ON a.applicant_id = u.id
               JOIN meeting_types mt ON a.meeting_type_id = mt.id
               LEFT JOIN users eu ON a.assigned_executor_id = eu.id
               LEFT JOIN post_event_reports r ON r.application_id = a.id
               WHERE a.id = ?""",
            (app_id,),
        )
        app = await cur.fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        cur = await db.execute(
            """SELECT ar.*, u.real_name AS approver_name, u.department AS approver_dept, u.phone AS approver_phone
               FROM approval_records ar
               LEFT JOIN users u ON ar.approver_id = u.id
               WHERE ar.application_id=? ORDER BY ar.created_at ASC""",
            (app_id,),
        )
        approvals = [dict(r) for r in await cur.fetchall()]

        cur = await db.execute(
            "SELECT * FROM reminders WHERE application_id=? ORDER BY created_at ASC",
            (app_id,),
        )
        reminders = [dict(r) for r in await cur.fetchall()]

        report = None
        cur = await db.execute(
            "SELECT * FROM post_event_reports WHERE application_id=?", (app_id,)
        )
        r = await cur.fetchone()
        if r:
            report = dict(r)
            cur = await db.execute(
                "SELECT * FROM report_photos WHERE report_id=? ORDER BY category, id",
                (r["id"],),
            )
            report["photos"] = [dict(p) for p in await cur.fetchall()]

        # Query pending approvers based on current status
        pending_approvers = []
        app_dict = dict(app)
        if app_dict["status"] == "pending":
            cur = await db.execute(
                """SELECT u.id, u.real_name, u.department, u.phone FROM users u
                   JOIN user_roles ur ON u.id=ur.user_id
                   WHERE ur.role='dept_supervisor' AND u.department=? AND u.is_active=1""",
                (app_dict["department"],),
            )
            pending_approvers = [dict(r) for r in await cur.fetchall()]
        elif app_dict["status"] == "dept_approved":
            cur = await db.execute(
                """SELECT u.id, u.real_name, u.department, u.phone FROM users u
                   JOIN user_roles ur ON u.id=ur.user_id
                   WHERE ur.role='studio_manager' AND u.is_active=1""",
            )
            pending_approvers = [dict(r) for r in await cur.fetchall()]
        elif app_dict["status"] == "studio_approved":
            cur = await db.execute(
                """SELECT u.id, u.real_name, u.department, u.phone FROM users u
                   JOIN user_roles ur ON u.id=ur.user_id
                   WHERE ur.role='executor' AND u.is_active=1""",
            )
            pending_approvers = [dict(r) for r in await cur.fetchall()]

        return {
            "application": app_dict,
            "approvals": approvals,
            "reminders": reminders,
            "report": report,
            "pending_approvers": pending_approvers,
        }
    finally:
        await db.close()


@router.post("")
async def create_application(body: ApplicationCreate, user=Depends(get_current_user)):
    db = await get_db()
    try:
        # Validate meeting type
        cur = await db.execute("SELECT id FROM meeting_types WHERE id=? AND is_active=1", (body.meeting_type_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=400, detail="Invalid meeting type")

        # Validate time
        try:
            st = datetime.fromisoformat(body.start_time)
            et = datetime.fromisoformat(body.end_time)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datetime format, use ISO 8601")
        if st >= et:
            raise HTTPException(status_code=400, detail="Start time must be before end time")

        # Dynamic max duration check
        max_minutes = int(await get_config("max_booking_minutes", "180"))
        if (et - st).total_seconds() > max_minutes * 60:
            hours = max_minutes // 60
            mins = max_minutes % 60
            detail = f"超过{hours}小时了" if mins == 0 else f"超过{hours}小时{mins}分钟了"
            raise HTTPException(status_code=400, detail=f"预约时长超过限制（最长{hours}小时{mins}分钟），分两次或多次进行申请")

        # Conflict check
        conflicts = await check_conflict(db, body.start_time, body.end_time)
        if conflicts:
            c = conflicts[0]
            raise HTTPException(
                status_code=409,
                detail="存在时间重叠或交叉，请修改时间",
            )

        cur = await db.execute(
            """INSERT INTO applications
               (applicant_id, department, contact, meeting_topic, meeting_type_id, start_time, end_time, remarks, on_site_contact)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (user["id"], body.department, body.contact, body.meeting_topic,
             body.meeting_type_id, body.start_time, body.end_time, body.remarks, body.on_site_contact),
        )
        await db.commit()
        return {"id": cur.lastrowid, "message": "Application submitted"}
    finally:
        await db.close()


@router.put("/{app_id}")
async def update_application(app_id: int, body: ApplicationUpdate, user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM applications WHERE id=?", (app_id,))
        app = await cur.fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Not found")
        if app["applicant_id"] != user["id"] and "admin" not in user.get("roles", []):
            raise HTTPException(status_code=403, detail="Permission denied")

        allowed_statuses = ("dept_rejected", "studio_rejected")
        if app["status"] not in allowed_statuses:
            raise HTTPException(status_code=400, detail=f"Can only edit applications with status: {', '.join(allowed_statuses)}")

        fields = {}
        for f in ("department","contact","meeting_topic","meeting_type_id","start_time","end_time","remarks","on_site_contact"):
            v = getattr(body, f, None)
            if v is not None:
                fields[f] = v

        if "meeting_type_id" in fields:
            cur = await db.execute("SELECT id FROM meeting_types WHERE id=? AND is_active=1", (fields["meeting_type_id"],))
            if not await cur.fetchone():
                raise HTTPException(status_code=400, detail="Invalid meeting type")

        if "start_time" in fields or "end_time" in fields:
            st = fields.get("start_time", app["start_time"])
            et = fields.get("end_time", app["end_time"])
            try:
                dt_st = datetime.fromisoformat(st)
                dt_et = datetime.fromisoformat(et)
                if dt_st >= dt_et:
                    raise HTTPException(status_code=400, detail="Start time must be before end time")
                max_minutes = int(await get_config("max_booking_minutes", "180"))
                if (dt_et - dt_st).total_seconds() > max_minutes * 60:
                    hours = max_minutes // 60
                    mins = max_minutes % 60
                    detail = f"超过{hours}小时了" if mins == 0 else f"超过{hours}小时{mins}分钟了"
                    raise HTTPException(status_code=400, detail=f"预约时长超过限制（最长{hours}小时{mins}分钟），分两次或多次进行申请")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid datetime format")

            conflicts = await check_conflict(db, st, et, exclude_id=app_id)
            if conflicts:
                c = conflicts[0]
                raise HTTPException(status_code=409, detail="存在时间重叠或交叉，请修改时间")

        set_clause = ", ".join(f"{k}=?" for k in fields)
        if set_clause:
            fields["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            set_clause += ", updated_at=?"
            await db.execute(
                f"UPDATE applications SET {set_clause}, status=pending WHERE id=?",
                list(fields.values()) + [app_id],
            )
            await db.commit()

        return {"message": "Application updated and resubmitted"}
    finally:
        await db.close()


@router.delete("/{app_id}")
async def delete_application(app_id: int, user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM applications WHERE id=?", (app_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Application not found")

        cur = await db.execute("SELECT id FROM post_event_reports WHERE application_id=?", (app_id,))
        report = await cur.fetchone()
        if report:
            await db.execute("DELETE FROM report_photos WHERE report_id=?", (report["id"],))
            await db.execute("DELETE FROM post_event_reports WHERE application_id=?", (app_id,))

        await db.execute("DELETE FROM approval_records WHERE application_id=?", (app_id,))
        await db.execute("DELETE FROM reminders WHERE application_id=?", (app_id,))
        await db.execute("DELETE FROM applications WHERE id=?", (app_id,))
        await db.commit()
        return {"message": "Application deleted"}
    finally:
        await db.close()


class TransferRequest(BaseModel):
    applicant_id: Optional[int] = None
    department: Optional[str] = None
    status: Optional[str] = None
    executor_id: Optional[int] = None


@router.put("/{app_id}/admin-transfer")
async def admin_transfer(app_id: int, body: TransferRequest, user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM applications WHERE id=?", (app_id,))
        app = await cur.fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        if body.applicant_id is not None:
            cur2 = await db.execute("SELECT id FROM users WHERE id=? AND is_active=1", (body.applicant_id,))
            if not await cur2.fetchone():
                raise HTTPException(status_code=400, detail="Target user not found")
            await db.execute("UPDATE applications SET applicant_id=? WHERE id=?", (body.applicant_id, app_id))

        if body.department is not None:
            await db.execute("UPDATE applications SET department=? WHERE id=?", (body.department, app_id))

        if body.status is not None:
            valid_statuses = ["pending", "dept_approved", "dept_rejected", "studio_approved", "studio_rejected", "assigned", "completed", "reported"]
            if body.status not in valid_statuses:
                raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
            await db.execute("UPDATE applications SET status=? WHERE id=?", (body.status, app_id))
            # If setting to assigned and executor_id provided
            if body.status == "assigned" and body.executor_id is not None:
                cur2 = await db.execute("SELECT id FROM users u JOIN user_roles ur ON u.id=ur.user_id WHERE u.id=? AND ur.role='executor' AND u.is_active=1", (body.executor_id,))
                if not await cur2.fetchone():
                    raise HTTPException(status_code=400, detail="Target executor not found")
                await db.execute("UPDATE applications SET assigned_executor_id=? WHERE id=?", (body.executor_id, app_id))

        if body.executor_id is not None and body.status is None:
            cur2 = await db.execute("SELECT id FROM users u JOIN user_roles ur ON u.id=ur.user_id WHERE u.id=? AND ur.role='executor' AND u.is_active=1", (body.executor_id,))
            if not await cur2.fetchone():
                raise HTTPException(status_code=400, detail="Target executor not found")
            await db.execute("UPDATE applications SET assigned_executor_id=?, status=assigned WHERE id=?", (body.executor_id, app_id))

        await db.commit()
        return {"message": "Transfer successful"}
    finally:
        await db.close()


@router.get("/stats/dashboard")
async def dashboard_stats(user=Depends(get_current_user)):
    db = await get_db()
    try:
        roles = set(user.get("roles", []))
        stats = {}

        if "applicant" in roles:
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE applicant_id=?", (user["id"],))
            stats["total"] = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE applicant_id=? AND status=pending", (user["id"],))
            stats["pending"] = (await cur.fetchone())[0]
            cur = await db.execute(
                "SELECT COUNT(*) FROM applications WHERE applicant_id=? AND status IN ('dept_approved','studio_approved','assigned','completed')",
                (user["id"],))
            stats["in_progress"] = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE applicant_id=? AND status=reported", (user["id"],))
            stats["completed"] = (await cur.fetchone())[0]

        if "dept_supervisor" in roles:
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE department=? AND status=pending", (user["department"],))
            stats["pending_approval"] = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE department=?", (user["department"],))
            stats["dept_total"] = (await cur.fetchone())[0]

        if "studio_manager" in roles:
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE status=dept_approved")
            stats["pending_final"] = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE status=studio_approved")
            stats["pending_assign"] = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM applications")
            stats["total_all"] = (await cur.fetchone())[0]

        if "executor" in roles:
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE assigned_executor_id=? AND status=assigned", (user["id"],))
            stats["pending_handle"] = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE assigned_executor_id=? AND status=completed", (user["id"],))
            stats["pending_report"] = (await cur.fetchone())[0]

        if "admin" in roles:
            cur = await db.execute("SELECT COUNT(*) FROM users WHERE is_active=1")
            stats["total_users"] = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM applications")
            stats["total_apps"] = (await cur.fetchone())[0]

        return {"stats": stats}
    finally:
        await db.close()
