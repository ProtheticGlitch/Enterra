"""
Скрипт для поиска запрещенных слов в постах и комментариях.
Использование: python -m portal.find_bad_words
"""
import os
import re
from flask import Flask
from dotenv import load_dotenv

from portal import create_app
from portal.extensions import db
from portal.models import Post, Comment, ModerationLog, User
from portal.routes import contains_bad_words, log_moderation, BAD_WORDS

load_dotenv()

app = create_app()


def find_bad_words_in_content():
    """Находит посты и комментарии с запрещенными словами."""
    with app.app_context():
        if not BAD_WORDS:
            print("⚠️ Список запрещенных слов пуст. Добавьте слова в админ-панели.")
            return
        
        print(f"🔍 Поиск запрещенных слов в постах и комментариях...")
        print(f"📋 Список запрещенных слов: {len(BAD_WORDS)} шт.\n")
        
        found_posts = []
        found_comments = []
        
        # Проверяем посты
        posts = Post.query.filter_by(is_published=True).all()
        print(f"📄 Проверяю {len(posts)} опубликованных постов...")
        
        for post in posts:
            text_blob = " ".join([
                post.title or "",
                post.summary or "",
                post.body or "",
            ])
            
            if contains_bad_words(text_blob):
                found_posts.append(post)
                print(f"  ⚠️ Пост #{post.id}: '{post.title[:50]}...' (автор: {post.author.username})")
        
        # Проверяем комментарии
        comments = Comment.query.all()
        print(f"\n💬 Проверяю {len(comments)} комментариев...")
        
        for comment in comments:
            if contains_bad_words(comment.body or ""):
                found_comments.append(comment)
                print(f"  ⚠️ Комментарий #{comment.id} к посту #{comment.post_id} (автор: {comment.author.username})")
        
        # Итоги
        print(f"\n{'='*60}")
        print(f"📊 Результаты поиска:")
        print(f"  Постов с запрещенными словами: {len(found_posts)}")
        print(f"  Комментариев с запрещенными словами: {len(found_comments)}")
        print(f"{'='*60}\n")
        
        if found_posts or found_comments:
            print("💡 Рекомендации:")
            print("  - Посты с запрещенными словами должны быть удалены")
            print("  - Комментарии с запрещенными словами должны быть удалены")
            print("  - Пользователи должны получить предупреждение")
            print("\n  Для автоматического удаления используйте:")
            print("  python -m portal.find_bad_words --delete")
        else:
            print("✅ Запрещенных слов не найдено!")
        
        return found_posts, found_comments


def delete_content_with_bad_words(delete_posts=True, delete_comments=True):
    """Удаляет посты и комментарии с запрещенными словами."""
    with app.app_context():
        if not BAD_WORDS:
            print("⚠️ Список запрещенных слов пуст.")
            return
        
        print(f"🗑️ Удаление контента с запрещенными словами...\n")
        
        deleted_posts = 0
        deleted_comments = 0
        
        # Удаляем посты
        if delete_posts:
            posts = Post.query.filter_by(is_published=True).all()
            for post in posts:
                text_blob = " ".join([
                    post.title or "",
                    post.summary or "",
                    post.body or "",
                ])
                
                if contains_bad_words(text_blob):
                    # Логируем удаление
                    log_moderation(
                        "post_deleted",
                        user_id=post.author_id,
                        post_id=post.id,
                        reason="bad_words_scan",
                        text=text_blob[:200] if text_blob else "",
                    )
                    
                    # Удаляем связанные данные
                    from portal.models import Track, PostLike, PostView
                    Track.query.filter_by(post_id=post.id).delete()
                    Comment.query.filter_by(post_id=post.id).delete()
                    PostLike.query.filter_by(post_id=post.id).delete()
                    PostView.query.filter_by(post_id=post.id).delete()
                    
                    # Удаляем медиафайл если есть
                    if post.media_path:
                        try:
                            media_path = os.path.join(app.root_path, "static", post.media_path)
                            if os.path.exists(media_path):
                                os.remove(media_path)
                        except Exception as e:
                            print(f"  ⚠️ Не удалось удалить медиафайл для поста #{post.id}: {e}")
                    
                    db.session.delete(post)
                    deleted_posts += 1
                    print(f"  🗑️ Удален пост #{post.id}: '{post.title[:50]}...'")
        
        # Удаляем комментарии
        if delete_comments:
            comments = Comment.query.all()
            for comment in comments:
                if contains_bad_words(comment.body or ""):
                    # Логируем удаление
                    log_moderation(
                        "comment_blocked",
                        user_id=comment.author_id,
                        post_id=comment.post_id,
                        comment_id=comment.id,
                        reason="bad_words_scan",
                        text=comment.body[:200] if comment.body else "",
                    )
                    
                    db.session.delete(comment)
                    deleted_comments += 1
                    print(f"  🗑️ Удален комментарий #{comment.id} к посту #{comment.post_id}")
        
        db.session.commit()
        
        print(f"\n{'='*60}")
        print(f"✅ Удалено:")
        print(f"  Постов: {deleted_posts}")
        print(f"  Комментариев: {deleted_comments}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    
    if "--delete" in sys.argv:
        print("⚠️ ВНИМАНИЕ: Будут удалены все посты и комментарии с запрещенными словами!")
        response = input("Продолжить? (yes/no): ")
        if response.lower() == "yes":
            delete_content_with_bad_words()
        else:
            print("Отменено.")
    else:
        find_bad_words_in_content()

