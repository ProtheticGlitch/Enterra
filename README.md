Я создам полноценный проект развлекательного портала для студентов HYPELAND на Python. Это будет масштабное веб-приложение с использованием современных технологий.

📁 Структура проекта

```
hypeland/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── core/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── utils/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
├── docker-compose.yml
├── nginx/
└── README.md
```

🚀 1. Backend на FastAPI

backend/requirements.txt

```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
alembic==1.12.1
psycopg2-binary==2.9.9
redis==5.0.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6
aioredis==2.0.1
boto3==1.34.0
pillow==10.1.0
pydantic==2.5.0
pydantic-settings==2.1.0
celery==5.3.4
celery[redis]
pytest==7.4.3
httpx==0.25.1
aiosmtplib==3.0.0
openai==1.3.0
```

backend/app/core/config.py

```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Настройки приложения
    APP_NAME: str = "HYPELAND"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Настройки базы данных
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "hypeland_user"
    POSTGRES_PASSWORD: str = "hypeland_pass"
    POSTGRES_DB: str = "hypeland_db"
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    # JWT
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 дней
    
    # S3/MinIO
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "hypeland-media"
    
    # AI
    OPENAI_API_KEY: Optional[str] = None
    
    # CORS
    CORS_ORIGINS: list = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    class Config:
        env_file = ".env"

settings = Settings()
```

backend/app/core/database.py

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

SQLALCHEMY_DATABASE_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis подключение
import redis
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

backend/app/models/

user.py

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

user_badges = Table(
    'user_badges',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('badge_id', Integer, ForeignKey('badges.id'))
)

followers = Table(
    'followers',
    Base.metadata,
    Column('follower_id', Integer, ForeignKey('users.id')),
    Column('followed_id', Integer, ForeignKey('users.id'))
)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(100))
    hashed_password = Column(String(255), nullable=True)
    avatar_url = Column(String(500))
    bio = Column(Text)
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    coins = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    age_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))
    
    # Связи
    posts = relationship("Post", back_populates="author")
    memes = relationship("Meme", back_populates="author")
    videos = relationship("Video", back_populates="author")
    comments = relationship("Comment", back_populates="author")
    likes = relationship("Like", back_populates="user")
    challenges_participated = relationship("ChallengeParticipation", back_populates="user")
    badges = relationship("Badge", secondary=user_badges, back_populates="users")
    following = relationship(
        "User",
        secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref="followers"
    )
    
    # OAuth
    oauth_provider = Column(String(20))  # google, vk, telegram
    oauth_id = Column(String(255))
```

content.py

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

class Post(Base):
    __tablename__ = "posts"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    content = Column(Text)
    image_url = Column(String(500))
    post_type = Column(String(20))  # meme, video, text, poll
    tags = Column(JSON, default=list)
    views = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    shares_count = Column(Integer, default=0)
    is_trending = Column(Boolean, default=False)
    is_featured = Column(Boolean, default=False)
    is_nsfw = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    author_id = Column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post")
    likes = relationship("Like", back_populates="post")

class Meme(Base):
    __tablename__ = "memes"
    
    id = Column(Integer, primary_key=True, index=True)
    image_url = Column(String(500), nullable=False)
    caption = Column(String(300))
    template_name = Column(String(100))
    tags = Column(JSON, default=list)
    votes_count = Column(Integer, default=0)
    battle_wins = Column(Integer, default=0)
    battle_losses = Column(Integer, default=0)
    is_nsfw = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    author_id = Column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="memes")
    battle_participations = relationship("MemeBattleParticipation", back_populates="meme")

class Video(Base):
    __tablename__ = "videos"
    
    id = Column(Integer, primary_key=True, index=True)
    video_url = Column(String(500), nullable=False)
    thumbnail_url = Column(String(500))
    title = Column(String(200))
    description = Column(Text)
    duration = Column(Integer)  # в секундах
    is_short = Column(Boolean, default=True)
    views = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    category = Column(String(50))  # humor, challenge, no_context и т.д.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    author_id = Column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="videos")
```

interactive.py

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

class Challenge(Base):
    __tablename__ = "challenges"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    challenge_type = Column(String(50))  # weekly, user_created, brand
    rules = Column(Text)
    prize = Column(String(200))
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    participant_count = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    participations = relationship("ChallengeParticipation", back_populates="challenge")

class ChallengeParticipation(Base):
    __tablename__ = "challenge_participations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    challenge_id = Column(Integer, ForeignKey("challenges.id"))
    submission_url = Column(String(500))
    description = Column(Text)
    votes_count = Column(Integer, default=0)
    position = Column(Integer)
    is_winner = Column(Boolean, default=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="challenges_participated")
    challenge = relationship("Challenge", back_populates="participations")

class MemeBattle(Base):
    __tablename__ = "meme_battles"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    theme = Column(String(100))
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    total_votes = Column(Integer, default=0)
    
    participations = relationship("MemeBattleParticipation", back_populates="battle")

class MemeBattleParticipation(Base):
    __tablename__ = "meme_battle_participations"
    
    id = Column(Integer, primary_key=True, index=True)
    battle_id = Column(Integer, ForeignKey("meme_battles.id"))
    meme_id = Column(Integer, ForeignKey("memes.id"))
    votes_count = Column(Integer, default=0)
    
    battle = relationship("MemeBattle", back_populates="participations")
    meme = relationship("Meme", back_populates="battle_participations")
```

gamification.py

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

class Badge(Base):
    __tablename__ = "badges"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    icon_url = Column(String(500))
    badge_type = Column(String(50))  # achievement, special, premium
    requirement = Column(Text)
    rarity = Column(String(20))  # common, rare, epic, legendary
    
    users = relationship("User", secondary="user_badges", back_populates="badges")

class Achievement(Base):
    __tablename__ = "achievements"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action_type = Column(String(50))  # post_created, meme_uploaded, challenge_won
    points_earned = Column(Integer)
    description = Column(Text)
    achieved_at = Column(DateTime(timezone=True), server_default=func.now())

class Leaderboard(Base):
    __tablename__ = "leaderboards"
    
    id = Column(Integer, primary_key=True, index=True)
    leaderboard_type = Column(String(50))  # weekly, monthly, all_time
    game_type = Column(String(50))  # meme_quiz, guess_meme
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class LeaderboardEntry(Base):
    __tablename__ = "leaderboard_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    leaderboard_id = Column(Integer, ForeignKey("leaderboards.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    score = Column(Integer, default=0)
    position = Column(Integer)
    games_played = Column(Integer, default=0)
    
    leaderboard = relationship("Leaderboard")
    user = relationship("User")
```

backend/app/schemas/

user.py

```python
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None

class UserCreate(UserBase):
    password: Optional[str] = None
    oauth_provider: Optional[str] = None
    oauth_id: Optional[str] = None
    age_verified: bool = False

class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

class UserInDB(UserBase):
    id: int
    level: int
    experience: int
    coins: int
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserProfile(UserInDB):
    followers_count: int
    following_count: int
    posts_count: int
    badges: List[dict] = []
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserInDB

class OAuthRequest(BaseModel):
    provider: str
    token: str
```

backend/app/api/

api_v1.py

```python
from fastapi import APIRouter
from .endpoints import auth, users, posts, memes, videos, challenges, games, ai

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(posts.router, prefix="/posts", tags=["posts"])
api_router.include_router(memes.router, prefix="/memes", tags=["memes"])
api_router.include_router(videos.router, prefix="/videos", tags=["videos"])
api_router.include_router(challenges.router, prefix="/challenges", tags=["challenges"])
api_router.include_router(games.router, prefix="/games", tags=["games"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
```

endpoints/auth.py

```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Any

from ...core.config import settings
from ...core.database import get_db
from ...models.user import User
from ...schemas.user import UserCreate, UserInDB, Token, OAuthRequest
from ...services.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_password_hash,
    verify_oauth_token
)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

@router.post("/register", response_model=UserInDB)
async def register(
    user_in: UserCreate,
    db: Session = Depends(get_db)
):
    # Проверка возраста
    if not user_in.age_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Age verification required (18+)"
        )
    
    # Проверка существующего пользователя
    if db.query(User).filter(User.username == user_in.username).first():
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    
    if user_in.email and db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    # Создание пользователя
    user = create_user(db, user_in)
    return user

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.post("/oauth")
async def oauth_login(
    oauth_data: OAuthRequest,
    db: Session = Depends(get_db)
):
    # Верификация OAuth токена
    user_info = verify_oauth_token(oauth_data.provider, oauth_data.token)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OAuth token"
        )
    
    # Поиск или создание пользователя
    user = db.query(User).filter(
        User.oauth_provider == oauth_data.provider,
        User.oauth_id == user_info["id"]
    ).first()
    
    if not user:
        user = User(
            username=user_info.get("username"),
            email=user_info.get("email"),
            display_name=user_info.get("name"),
            avatar_url=user_info.get("avatar"),
            oauth_provider=oauth_data.provider,
            oauth_id=user_info["id"],
            age_verified=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }
```

endpoints/memes.py

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import shutil
import uuid
from pathlib import Path

from ...core.database import get_db
from ...models.user import User
from ...models.content import Meme, MemeBattle, MemeBattleParticipation
from ...schemas.meme import MemeCreate, MemeResponse, MemeBattleCreate, VoteRequest
from ...services.auth import get_current_user
from ...services.meme_generator import generate_meme
from ...utils.storage import upload_to_s3

router = APIRouter()

@router.post("/upload", response_model=MemeResponse)
async def upload_meme(
    image: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    tags: Optional[str] = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Сохранение изображения
    file_extension = Path(image.filename).suffix
    filename = f"memes/{uuid.uuid4()}{file_extension}"
    
    # Загрузка в S3
    image_url = await upload_to_s3(
        image.file,
        filename,
        content_type=image.content_type
    )
    
    # Создание записи в БД
    meme = Meme(
        image_url=image_url,
        caption=caption,
        tags=tags.split(",") if tags else [],
        author_id=current_user.id
    )
    
    db.add(meme)
    db.commit()
    db.refresh(meme)
    
    # Начисление опыта
    current_user.experience += 10
    db.commit()
    
    return meme

@router.post("/generate")
async def generate_meme_from_template(
    template: str = Form(...),
    top_text: str = Form(""),
    bottom_text: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Генерация мема
    meme_image = generate_meme(template, top_text, bottom_text)
    
    # Сохранение
    filename = f"generated/{uuid.uuid4()}.png"
    image_url = await upload_to_s3(
        meme_image,
        filename,
        content_type="image/png"
    )
    
    meme = Meme(
        image_url=image_url,
        capt
