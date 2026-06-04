from fastapi import APIRouter, HTTPException, Depends, Form
from database import get_db
from schemas import UserCreate, UserUpdate
from auth import hash_password, require_role

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
async def list_users(user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id, username, real_name, department, phone, is_active, created_at FROM users ORDER BY id")
        users = [dict(r) for r in await cur.fetchall()]
        for u in users:
            cur2 = await db.execute("SELECT role FROM user_roles WHERE user_id=?", (u["id"],))
            u["roles"] = [r["role"] for r in await cur2.fetchall()]
        return {"users": users}
    finally:
        await db.close()


@router.post("")
async def create_user(body: UserCreate, user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM users WHERE username=?", (body.username,))
        if await cur.fetchone():
            raise HTTPException(status_code=400, detail="Username exists")
        cur = await db.execute(
            "INSERT INTO users (username, password_hash, real_name, department, phone) VALUES (?,?,?,?,?)",
            (body.username, hash_password(body.password), body.real_name, body.department, body.phone),
        )
        uid = cur.lastrowid
        for role in body.roles:
            await db.execute("INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?,?)", (uid, role))
        await db.commit()
        return {"id": uid, "message": "User created"}
    finally:
        await db.close()


@router.put("/{user_id}")
async def update_user(user_id: int, body: UserUpdate, user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM users WHERE id=?", (user_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="User not found")
        if body.real_name is not None:
            await db.execute("UPDATE users SET real_name=? WHERE id=?", (body.real_name, user_id))
        if body.department is not None:
            await db.execute("UPDATE users SET department=? WHERE id=?", (body.department, user_id))
        if body.phone is not None:
            await db.execute("UPDATE users SET phone=? WHERE id=?", (body.phone, user_id))
        if body.password is not None:
            await db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.password), user_id))
        if body.is_active is not None:
            await db.execute("UPDATE users SET is_active=? WHERE id=?", (body.is_active, user_id))
        if body.roles is not None:
            await db.execute("DELETE FROM user_roles WHERE user_id=?", (user_id,))
            for role in body.roles:
                await db.execute("INSERT INTO user_roles (user_id, role) VALUES (?,?)", (user_id, role))
        await db.commit()
        return {"message": "User updated"}
    finally:
        await db.close()


@router.delete("/{user_id}")
async def delete_user(user_id: int, user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM users WHERE id=?", (user_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="User not found")
        await db.execute("DELETE FROM user_roles WHERE user_id=?", (user_id,))
        await db.execute("DELETE FROM users WHERE id=?", (user_id,))
        await db.commit()
        return {"message": "User deleted"}
    finally:
        await db.close()


@router.get("/executors")
async def list_executors(user=Depends(require_role("admin", "studio_manager"))):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT u.id, u.real_name, u.department FROM users u "
            "JOIN user_roles ur ON u.id=ur.user_id WHERE ur.role='executor' AND u.is_active=1 ORDER BY u.id"
        )
        return {"executors": [dict(r) for r in await cur.fetchall()]}
    finally:
        await db.close()


@router.get("/dept_supervisors")
async def list_dept_supervisors(user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT u.id, u.real_name, u.department FROM users u "
            "JOIN user_roles ur ON u.id=ur.user_id WHERE ur.role='dept_supervisor' AND u.is_active=1 ORDER BY u.id"
        )
        return {"supervisors": [dict(r) for r in await cur.fetchall()]}
    finally:
        await db.close()


# -- department management --

@router.get("/departments", response_model=None)
async def list_departments():
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM departments WHERE is_active=1 ORDER BY id")
        return {"departments": [dict(r) for r in await cur.fetchall()]}
    finally:
        await db.close()


@router.get("/departments/all", response_model=None)
async def list_all_departments_api(user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM departments ORDER BY id")
        return {"departments": [dict(r) for r in await cur.fetchall()]}
    finally:
        await db.close()


@router.post("/departments", response_model=None)
async def create_department(name: str = Form(...), user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        cur = await db.execute("INSERT INTO departments (name) VALUES (?)", (name,))
        await db.commit()
        return {"id": cur.lastrowid, "message": "Created"}
    finally:
        await db.close()


@router.put("/departments/{dept_id}", response_model=None)
async def update_department(dept_id: int, name: str = Form(None), is_active: int = Form(None), user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        if name is not None:
            await db.execute("UPDATE departments SET name=? WHERE id=?", (name, dept_id))
        if is_active is not None:
            await db.execute("UPDATE departments SET is_active=? WHERE id=?", (is_active, dept_id))
        await db.commit()
        return {"message": "Updated"}
    finally:
        await db.close()


@router.delete("/departments/{dept_id}", response_model=None)
async def delete_department(dept_id: int, user=Depends(require_role("admin"))):
    db = await get_db()
    try:
        await db.execute("DELETE FROM departments WHERE id=?", (dept_id,))
        await db.commit()
        return {"message": "Deleted"}
    finally:
        await db.close()
