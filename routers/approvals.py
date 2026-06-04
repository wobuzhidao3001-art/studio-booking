from fastapi import APIRouter, HTTPException, Depends
from database import get_db
from schemas import ApprovalAction, AssignExecutor
from auth import get_current_user, require_role

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.post("/{app_id}/dept")
async def dept_approve(app_id: int, body: ApprovalAction, user=Depends(require_role("dept_supervisor"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM applications WHERE id=?", (app_id,))
        app = await cur.fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        if app["status"] != "pending":
            raise HTTPException(status_code=400, detail="Application is not in pending status")
        if app["department"] != user["department"]:
            raise HTTPException(status_code=403, detail="Can only approve applications from your department")

        new_status = "dept_approved" if body.action == "approve" else "dept_rejected"
        await db.execute(
            "UPDATE applications SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
            (new_status, app_id),
        )
        await db.execute(
            "INSERT INTO approval_records (application_id, approver_id, approver_role, stage, action, comment) VALUES (?,?,?,?,?,?)",
            (app_id, user["id"], "dept_supervisor", "dept", body.action, body.comment),
        )
        await db.commit()
        return {"message": f"Department {'approved' if body.action == 'approve' else 'rejected'}"}
    finally:
        await db.close()


@router.post("/{app_id}/studio")
async def studio_approve(app_id: int, body: ApprovalAction, user=Depends(require_role("studio_manager"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM applications WHERE id=?", (app_id,))
        app = await cur.fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        if app["status"] != "dept_approved":
            raise HTTPException(status_code=400, detail="Application must be dept_approved first")

        new_status = "studio_approved" if body.action == "approve" else "studio_rejected"
        await db.execute(
            "UPDATE applications SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
            (new_status, app_id),
        )
        await db.execute(
            "INSERT INTO approval_records (application_id, approver_id, approver_role, stage, action, comment) VALUES (?,?,?,?,?,?)",
            (app_id, user["id"], "studio_manager", "studio", body.action, body.comment),
        )
        await db.commit()
        return {"message": f"Studio {'approved' if body.action == 'approve' else 'rejected'}"}
    finally:
        await db.close()


@router.post("/{app_id}/assign")
async def assign_executor(app_id: int, body: AssignExecutor, user=Depends(require_role("studio_manager"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM applications WHERE id=?", (app_id,))
        app = await cur.fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        if app["status"] != "studio_approved":
            raise HTTPException(status_code=400, detail="Application must be studio_approved first")

        cur = await db.execute(
            "SELECT 1 FROM user_roles WHERE user_id=? AND role='executor'", (body.executor_id,)
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=400, detail="User is not an executor")

        await db.execute(
            "UPDATE applications SET status='assigned', assigned_executor_id=?, updated_at=datetime('now','localtime') WHERE id=?",
            (body.executor_id, app_id),
        )
        await db.commit()
        return {"message": "Executor assigned"}
    finally:
        await db.close()


@router.post("/{app_id}/complete")
async def complete_usage(app_id: int, user=Depends(require_role("executor"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM applications WHERE id=?", (app_id,))
        app = await cur.fetchone()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        if app["status"] != "assigned":
            raise HTTPException(status_code=400, detail="Application must be assigned first")
        if app["assigned_executor_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="You are not the assigned executor")

        await db.execute(
            "UPDATE applications SET status='completed', updated_at=datetime('now','localtime') WHERE id=?",
            (app_id,),
        )
        await db.commit()
        return {"message": "Usage completed, please submit report"}
    finally:
        await db.close()
