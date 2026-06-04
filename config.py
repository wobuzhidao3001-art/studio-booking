import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/app.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
