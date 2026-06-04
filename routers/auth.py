from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from database import get_db
from schemas import LoginRequest, PasswordChange
from auth import hash_password, verify_password, create_token, get_current_user, get_user_roles

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM users WHERE username=? AND is_active=1", (body.username,))
        user = await cur.fetchone()
        if not user or not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_token(user["id"], user["username"])
        roles = await get_user_roles(user["id"])
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "real_name": user["real_name"],
                "department": user["department"],
                "roles": roles,
            },
        }
    finally:
        await db.close()


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {"user": user}


@router.post("/change-password")
async def change_password(body: PasswordChange, user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],))
        row = await cur.fetchone()
        if not verify_password(body.old_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="Old password incorrect")
        await db.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(body.new_password), user["id"]),
        )
        await db.commit()
        return {"message": "Password changed"}
    finally:
        await db.close()


@router.get("/logout")
async def logout():
    return RedirectResponse("/login", status_code=302)
