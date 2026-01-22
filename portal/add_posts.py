"""
Скрипт для добавления постов из интернета
Использует публичные API и создает реалистичные посты
"""
import os
import sys
import random
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    requests = None
    print("Предупреждение: библиотека requests не установлена. Изображения не будут загружаться.")

# Добавляем путь к приложению
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal import create_app
from portal.extensions import db
from portal.models import Post, User, Category, Tag
import re


def download_image(url, save_path):
    """Скачивает изображение по URL"""
    if not requests:
        return False
    try:
        response = requests.get(url, timeout=10, stream=True)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception as e:
        print(f"Ошибка загрузки изображения {url}: {e}")
    return False


def get_random_images():
    """Получает случайные изображения из публичных источников"""
    # Используем Unsplash Source API (публичный, не требует ключа)
    image_urls = [
        "https://source.unsplash.com/400x300/?gaming",
        "https://source.unsplash.com/400x300/?movie",
        "https://source.unsplash.com/400x300/?music",
        "https://source.unsplash.com/400x300/?technology",
        "https://source.unsplash.com/400x300/?anime",
        "https://source.unsplash.com/400x300/?comedy",
        "https://source.unsplash.com/400x300/?art",
        "https://source.unsplash.com/400x300/?nature",
        "https://source.unsplash.com/400x300/?city",
        "https://source.unsplash.com/400x300/?space",
    ]
    return image_urls


def slugify_tag(name: str) -> str:
    """Создает slug из названия тега."""
    name = name.lower().strip()
    name = re.sub(r"[^\wа-яё-]+", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def get_or_create_tags(tag_names: str):
    """Получает или создает теги из строки с запятыми."""
    if not tag_names:
        return []
    tags = []
    for name in tag_names.split(","):
        name = name.strip()
        if not name:
            continue
        slug = slugify_tag(name)
        if not slug:
            continue
        tag = Tag.query.filter_by(slug=slug).first()
        if not tag:
            tag = Tag(name=name, slug=slug)
            db.session.add(tag)
        tags.append(tag)
    return tags


def create_posts_from_data():
    """Создает посты из реалистичных данных"""
    
    app = create_app()
    with app.app_context():
        # Получаем или создаем пользователя для постов
        user = User.query.filter_by(username="system").first()
        if not user:
            user = User.query.first()
        if not user:
            print("Ошибка: нет пользователей в системе. Создайте пользователя сначала.")
            return
        
        # Получаем категории
        categories_map = {c.slug: c for c in Category.query.all()}
        
        # Создаем посты
        created_count = 0
        image_urls = get_random_images()
        
        for i, post_data in enumerate(posts_data):
            # Создаем пост
            post = Post(
                title=post_data["title"],
                summary=post_data["summary"],
                body=post_data["body"],
                cover_emoji=post_data["cover_emoji"],
                author_id=user.id,
                is_published=True,
            )
            
            # Устанавливаем случайную дату в последние 30 дней
            days_ago = random.randint(0, 30)
            post.created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
            post.updated_at = post.created_at
            
            # Добавляем категории
            post.categories = [categories_map[cat] for cat in post_data["categories"] if cat in categories_map]
            
            # Добавляем теги
            if post_data.get("tags"):
                tags = get_or_create_tags(post_data["tags"])
                post.tags = tags
            
            db.session.add(post)
            db.session.flush()
            
            # Пытаемся скачать изображение (опционально)
            # Можно раскомментировать, если нужны реальные изображения
            # try:
            #     img_url = random.choice(image_urls)
            #     upload_dir = os.path.join(app.root_path, "static", "uploads")
            #     os.makedirs(upload_dir, exist_ok=True)
            #     ext = "jpg"
            #     save_name = f"{user.id}_{post.id}_{random.randint(1000, 9999)}.{ext}"
            #     filepath = os.path.join(upload_dir, save_name)
            #     if download_image(img_url, filepath):
            #         post.media_path = f"uploads/{save_name}"
            #         post.media_type = "image"
            # except Exception as e:
            #     print(f"Не удалось загрузить изображение для поста {post.id}: {e}")
            
            created_count += 1
            if created_count % 5 == 0:
                print(f"Создано постов: {created_count}")
                db.session.commit()
        
        db.session.commit()
        print(f"Успешно создано {created_count} постов!")


if __name__ == "__main__":
    print("Начинаю создание постов...")
    create_posts_from_data()
    print("Готово!")

