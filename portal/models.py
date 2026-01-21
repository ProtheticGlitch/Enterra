from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


post_categories = db.Table(
    "post_categories",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("category.id"), primary_key=True),
)

post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    # Профиль
    avatar_path = db.Column(db.String(255), nullable=True)
    bio = db.Column(db.String(500), nullable=True)
    is_private = db.Column(db.Boolean, default=False, nullable=False)
    theme_preference = db.Column(db.String(16), default="dark", nullable=False)  # dark, light, auto

    posts = db.relationship("Post", backref="author", lazy=True, cascade="all, delete-orphan")
    comments = db.relationship("Comment", backref="author", lazy=True, cascade="all, delete-orphan")
    likes = db.relationship("PostLike", backref="user", lazy=True, cascade="all, delete-orphan")
    achievements = db.relationship("UserAchievement", backref="user", lazy=True, cascade="all, delete-orphan")
    quiz_results = db.relationship("QuizResult", backref="user", lazy=True, cascade="all, delete-orphan")
    # Подписки
    following = db.relationship(
        "Follow",
        foreign_keys="Follow.follower_id",
        backref="follower",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    followers = db.relationship(
        "Follow",
        foreign_keys="Follow.followed_id",
        backref="followed",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(64), unique=True, nullable=False)


class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False, index=True)
    slug = db.Column(db.String(32), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    summary = db.Column(db.String(240), nullable=True)
    body = db.Column(db.Text, nullable=False)
    cover_emoji = db.Column(db.String(8), nullable=True)
    media_path = db.Column(db.String(255), nullable=True)
    media_type = db.Column(db.String(16), nullable=True)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    views = db.Column(db.Integer, default=0, nullable=False)  # Счетчик просмотров
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    categories = db.relationship("Category", secondary=post_categories, lazy="subquery")
    tags = db.relationship("Tag", secondary=post_tags, lazy="subquery")
    comments = db.relationship("Comment", backref="post", lazy=True, cascade="all, delete-orphan")
    likes = db.relationship("PostLike", backref="post", lazy=True, cascade="all, delete-orphan")
    tracks = db.relationship("Track", backref="post", lazy=True, cascade="all, delete-orphan", order_by="Track.order")

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


class Track(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=True)  # Ссылка на Spotify, YouTube и т.д.
    order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False, index=True)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False, index=True)


class PostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False, index=True)
    reaction = db.Column(db.String(16), nullable=False, default="like")
    __table_args__ = (db.UniqueConstraint("user_id", "post_id", name="uq_like_user_post"),)


class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    icon = db.Column(db.String(8), nullable=False, default="🏆")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    achievement_id = db.Column(db.Integer, db.ForeignKey("achievement.id"), nullable=False, index=True)
    achievement = db.relationship("Achievement")
    __table_args__ = (db.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),)


class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.String(240), nullable=False)
    choice_a = db.Column(db.String(120), nullable=False)
    choice_b = db.Column(db.String(120), nullable=False)
    choice_c = db.Column(db.String(120), nullable=False)
    choice_d = db.Column(db.String(120), nullable=False)
    correct = db.Column(db.String(1), nullable=False)  # A/B/C/D
    topic = db.Column(db.String(64), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class QuizResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)


class ModerationSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    auto_enabled = db.Column(db.Boolean, default=True, nullable=False)


class ModerationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False)  # post_autohide, comment_blocked, file_blocked
    reason = db.Column(db.String(120), nullable=True)
    snippet = db.Column(db.String(200), nullable=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=True, index=True)
    comment_id = db.Column(db.Integer, nullable=True, index=True)


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    followed_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint("follower_id", "followed_id", name="uq_follow"),)

