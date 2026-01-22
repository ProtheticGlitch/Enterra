"""
Модуль для проверки дубликатов постов.
Использует различные алгоритмы для определения схожести контента.
"""
import re
from difflib import SequenceMatcher
from typing import Optional, Tuple

from .models import Post


def normalize_text(text: str) -> str:
    """Нормализует текст для сравнения."""
    if not text:
        return ""
    # Приводим к нижнему регистру
    text = text.lower()
    # Удаляем лишние пробелы
    text = re.sub(r'\s+', ' ', text)
    # Удаляем знаки препинания (опционально)
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()


def calculate_similarity(text1: str, text2: str) -> float:
    """Вычисляет схожесть двух текстов (0.0 - 1.0)."""
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    if not norm1 or not norm2:
        return 0.0
    return SequenceMatcher(None, norm1, norm2).ratio()


def find_similar_posts(post_id: int, title: str, body: str, threshold: float = 0.7) -> list:
    """
    Находит похожие посты.
    
    Args:
        post_id: ID текущего поста (исключается из результатов)
        title: Заголовок поста
        body: Текст поста
        threshold: Порог схожести (0.0 - 1.0)
    
    Returns:
        Список кортежей (post, similarity_score)
    """
    if not title and not body:
        return []
    
    # Получаем все опубликованные посты кроме текущего
    all_posts = Post.query.filter(
        Post.id != post_id,
        Post.is_published.is_(True)
    ).all()
    
    similar = []
    combined_text = f"{title} {body}"
    
    for post in all_posts:
        post_combined = f"{post.title} {post.body}"
        similarity = calculate_similarity(combined_text, post_combined)
        
        if similarity >= threshold:
            similar.append((post, similarity))
    
    # Сортируем по схожести
    similar.sort(key=lambda x: x[1], reverse=True)
    return similar


def check_duplicate(post_id: int, title: str, body: str, threshold: float = 0.85) -> Optional[Tuple[Post, float]]:
    """
    Проверяет, есть ли дубликат поста.
    Использует комбинированный подход: сравнение заголовков и текста.
    
    Args:
        post_id: ID текущего поста
        title: Заголовок поста
        body: Текст поста
        threshold: Порог для дубликата (выше чем для похожих)
    
    Returns:
        Кортеж (post, similarity) если найден дубликат, иначе None
    """
    if not title and not body:
        return None
    
    # Получаем все опубликованные посты кроме текущего
    all_posts = Post.query.filter(
        Post.id != post_id,
        Post.is_published.is_(True)
    ).all()
    
    if not all_posts:
        return None
    
    best_match = None
    best_similarity = 0.0
    
    # Нормализуем текущий текст
    norm_title = normalize_text(title)
    norm_body = normalize_text(body)
    combined_text = f"{norm_title} {norm_body}"
    
    for post in all_posts:
        # Сравниваем заголовки (более важны)
        title_sim = calculate_similarity(title, post.title) if title and post.title else 0.0
        
        # Сравниваем полный текст
        post_combined = f"{normalize_text(post.title)} {normalize_text(post.body)}"
        text_sim = calculate_similarity(combined_text, post_combined)
        
        # Взвешенная схожесть (заголовок важнее)
        similarity = (title_sim * 0.6) + (text_sim * 0.4)
        
        if similarity >= threshold and similarity > best_similarity:
            best_similarity = similarity
            best_match = post
    
    if best_match:
        return (best_match, best_similarity)
    return None

