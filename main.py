import os
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from database import init_db, seed_db
from auth import get_current_user
from config import UPLOAD_DIR, BASE_DIR

app = FastAPI(title="演播厅预约管理系统")

# Static files
os.makedirs(os.path.join(BASE_DIR, UPLOAD_DIR), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=os.path.join(BASE_DIR, UPLOAD_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Routers
from routers import auth as auth_router
from routers import users
from routers import applications
from routers import approvals
from routers import reports
from routers import reminders
from routers import public as public_router
from routers import config as config_router

app.include_router(auth_router.router)
app.include_router(users.router)
app.include_router(applications.router)
app.include_router(approvals.router)
app.include_router(reports.router)
app.include_router(reminders.router)
app.include_router(public_router.router)
app.include_router(config_router.router)


@app.on_event("startup")
async def startup():
    await init_db()
    await seed_db()


# ── Page routes ──

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse("/dashboard")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    try:
        user = await get_current_user(request)
        return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")


@app.get("/apply", response_class=HTMLResponse)
async def apply_page(request: Request):
    try:
        user = await get_current_user(request)
        return templates.TemplateResponse("apply.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")


@app.get("/my-applications", response_class=HTMLResponse)
async def my_applications_page(request: Request):
    try:
        user = await get_current_user(request)
        return templates.TemplateResponse("my_applications.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")


@app.get("/my-todos", response_class=HTMLResponse)
async def my_todos_page(request: Request):
    try:
        user = await get_current_user(request)
        return templates.TemplateResponse("my_todos.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")


@app.get("/public-board", response_class=HTMLResponse)
async def public_board_page(request: Request):
    try:
        user = await get_current_user(request)
        return templates.TemplateResponse("public_board.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    try:
        user = await get_current_user(request)
        if "admin" not in user.get("roles") and "executor" not in user.get("roles", []):
            return RedirectResponse("/dashboard")
        return templates.TemplateResponse("admin_users.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")


@app.get("/admin/meeting-types", response_class=HTMLResponse)
async def admin_types_page(request: Request):
    try:
        user = await get_current_user(request)
        if "admin" not in user.get("roles") and "executor" not in user.get("roles", []):
            return RedirectResponse("/dashboard")
        return templates.TemplateResponse("admin_meeting_types.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request):
    try:
        user = await get_current_user(request)
        if "admin" not in user.get("roles"):
            return RedirectResponse("/dashboard")
        return templates.TemplateResponse("admin_settings.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")


@app.get("/applications/{app_id}", response_class=HTMLResponse)
async def application_detail_page(app_id: int, request: Request):
    try:
        user = await get_current_user(request)
        return templates.TemplateResponse("application_detail.html", {"request": request, "user": user, "app_id": app_id})
    except:
        return RedirectResponse("/login")



@app.get("/admin/departments", response_class=HTMLResponse)
async def admin_departments_page(request: Request):
    try:
        user = await get_current_user(request)
        if "admin" not in user.get("roles") and "executor" not in user.get("roles", []):
            return RedirectResponse("/dashboard")
        return templates.TemplateResponse("admin_departments.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")


@app.get("/admin/reports", response_class=HTMLResponse)
async def admin_reports_page(request: Request):
    try:
        user = await get_current_user(request)
        if "admin" not in user.get("roles") and "executor" not in user.get("roles", []):
            return RedirectResponse("/dashboard")
        return templates.TemplateResponse("admin_reports.html", {"request": request, "user": user})
    except:
        return RedirectResponse("/login")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
