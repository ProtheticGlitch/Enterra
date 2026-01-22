from sqlalchemy import text

from .extensions import db


def run_simple_migrations() -> None:
    """
    Примитивные миграции для SQLite без Alembic.

    Безопасно вызывается на каждом старте приложения.
    """

    def _try(sql: str) -> None:
        try:
            db.session.execute(text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Добавляем колонку reaction в post_like, если её ещё нет
    _try("ALTER TABLE post_like ADD COLUMN reaction VARCHAR(16) NOT NULL DEFAULT 'like';")

    # Добавляем медиа-поля к постам, если их ещё нет
    _try("ALTER TABLE post ADD COLUMN media_path VARCHAR(255);")
    _try("ALTER TABLE post ADD COLUMN media_type VARCHAR(16);")

    # Создаём таблицу track для музыкальных треков
    _try("""
        CREATE TABLE IF NOT EXISTS track (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title VARCHAR(200) NOT NULL,
            artist VARCHAR(200) NOT NULL,
            url VARCHAR(500),
            "order" INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL,
            post_id INTEGER NOT NULL,
            FOREIGN KEY (post_id) REFERENCES post (id) ON DELETE CASCADE
        );
    """)
    _try("CREATE INDEX IF NOT EXISTS ix_track_post_id ON track(post_id);")
    _try("CREATE INDEX IF NOT EXISTS ix_track_created_at ON track(created_at);")

    # Добавляем поля профиля к пользователю
    _try("ALTER TABLE user ADD COLUMN avatar_path VARCHAR(255);")
    _try("ALTER TABLE user ADD COLUMN bio VARCHAR(500);")
    _try("ALTER TABLE user ADD COLUMN is_private BOOLEAN NOT NULL DEFAULT 0;")
    _try("ALTER TABLE user ADD COLUMN theme_preference VARCHAR(16) NOT NULL DEFAULT 'dark';")

    # Добавляем счетчик просмотров к постам
    _try("ALTER TABLE post ADD COLUMN views INTEGER NOT NULL DEFAULT 0;")

    # Создаём таблицу tag для тегов
    _try("""
        CREATE TABLE IF NOT EXISTS tag (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(32) NOT NULL UNIQUE,
            slug VARCHAR(32) NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL
        );
    """)
    _try("CREATE INDEX IF NOT EXISTS ix_tag_name ON tag(name);")
    _try("CREATE INDEX IF NOT EXISTS ix_tag_slug ON tag(slug);")

    # Создаём связующую таблицу post_tags
    _try("""
        CREATE TABLE IF NOT EXISTS post_tags (
            post_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (post_id, tag_id),
            FOREIGN KEY (post_id) REFERENCES post (id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tag (id) ON DELETE CASCADE
        );
    """)

    # Создаём таблицу follow для подписок
    _try("""
        CREATE TABLE IF NOT EXISTS follow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP NOT NULL,
            follower_id INTEGER NOT NULL,
            followed_id INTEGER NOT NULL,
            FOREIGN KEY (follower_id) REFERENCES user (id) ON DELETE CASCADE,
            FOREIGN KEY (followed_id) REFERENCES user (id) ON DELETE CASCADE,
            UNIQUE (follower_id, followed_id)
        );
    """)
    _try("CREATE INDEX IF NOT EXISTS ix_follow_follower_id ON follow(follower_id);")
    _try("CREATE INDEX IF NOT EXISTS ix_follow_followed_id ON follow(followed_id);")
    _try("CREATE INDEX IF NOT EXISTS ix_follow_created_at ON follow(created_at);")

    # Создаём таблицу post_view для отслеживания просмотров
    _try("""
        CREATE TABLE IF NOT EXISTS post_view (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            viewed_at TIMESTAMP NOT NULL,
            progress REAL NOT NULL DEFAULT 0.0,
            is_complete BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES user (id) ON DELETE CASCADE,
            FOREIGN KEY (post_id) REFERENCES post (id) ON DELETE CASCADE,
            UNIQUE (user_id, post_id)
        );
    """)
    _try("CREATE INDEX IF NOT EXISTS ix_post_view_user_id ON post_view(user_id);")
    _try("CREATE INDEX IF NOT EXISTS ix_post_view_post_id ON post_view(post_id);")
    _try("CREATE INDEX IF NOT EXISTS ix_post_view_viewed_at ON post_view(viewed_at);")
    
    # Добавляем колонку view_duration для времени просмотра
    _try("ALTER TABLE post_view ADD COLUMN view_duration REAL NOT NULL DEFAULT 0.0;")

    # Создаём таблицу user_tag_preference для предпочтений по тегам
    _try("""
        CREATE TABLE IF NOT EXISTS user_tag_preference (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            score REAL NOT NULL DEFAULT 1.0,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user (id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tag (id) ON DELETE CASCADE,
            UNIQUE (user_id, tag_id)
        );
    """)
    _try("CREATE INDEX IF NOT EXISTS ix_user_tag_preference_user_id ON user_tag_preference(user_id);")
    _try("CREATE INDEX IF NOT EXISTS ix_user_tag_preference_tag_id ON user_tag_preference(tag_id);")
    _try("CREATE INDEX IF NOT EXISTS ix_user_tag_preference_created_at ON user_tag_preference(created_at);")

    # Создаём таблицу moderated_tag для тегов, требующих модерации
    _try("""
        CREATE TABLE IF NOT EXISTS moderated_tag (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id INTEGER NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (tag_id) REFERENCES tag (id) ON DELETE CASCADE
        );
    """)
    _try("CREATE INDEX IF NOT EXISTS ix_moderated_tag_tag_id ON moderated_tag(tag_id);")


