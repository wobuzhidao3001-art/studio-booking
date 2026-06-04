import bcrypt
import jwt
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_db
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_HOURS

security = HTTPBearer(auto_error=False)



ROLE_NAMES = {
    "admin": "系统管理员",
    "applicant": "申请人",
    "dept_supervisor": "部门主管",
    "studio_manager": "演播厅主管",
    "executor": "执行管理员",
}

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(request: Request):
    token = request.cookies.get("token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM users WHERE id=? AND is_active=1", (int(payload["sub"]),))
        user = await cur.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        cur = await db.execute("SELECT role FROM user_roles WHERE user_id=?", (user["id"],))
        roles = [r["role"] for r in await cur.fetchall()]
        return {**dict(user), "roles": roles}
    finally:
        await db.close()


def require_role(*roles: str):
    async def checker(user=Depends(get_current_user)):
        user_roles = set(user.get("roles", []))
        if not user_roles.intersection(roles):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


async def get_user_roles(user_id: int) -> list:
    db = await get_db()
    try:
        cur = await db.execute("SELECT role FROM user_roles WHERE user_id=?", (user_id,))
        return [r["role"] for r in await cur.fetchall()]
    finally:
        await db.close()
