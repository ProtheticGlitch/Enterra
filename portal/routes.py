from functools import wraps
from datetime import datetime, timezone
import os
import re
import uuid

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from .duplicate_checker import check_duplicate, find_similar_posts
from .extensions import db
from .forms import CategoryForm, CommentForm, LoginForm, PostForm, ProfileEditForm, RegisterForm, SearchForm
from .models import (
    Category, Comment, Follow, ModerationLog, ModerationSettings, ModeratedTag, 
    Post, PostLike, PostView, Tag, Track, User, UserTagPreference
)

bp = Blueprint("main", __name__)

REACTIONS = {
    "like": {"emoji": "❤️", "label": "Нравится"},
    "dislike": {"emoji": "👎", "label": "Не нравится"},
}

# Простая авто‑модерация: список стоп‑слов (можно расширять)
BAD_WORDS = {

}

# Функция для получения списка тегов, требующих модерации
def get_moderated_tags() -> set:
    """Получает список slug тегов, требующих модерации."""
    moderated = ModeratedTag.query.join(Tag).all()
    return {mt.tag.slug for mt in moderated}

ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_VIDEO_EXT = {"mp4", "webm", "mov"}
ALLOWED_MEDIA_EXT = ALLOWED_IMAGE_EXT | ALLOWED_VIDEO_EXT


def slugify_tag(name: str) -> str:
    """Создает slug из названия тега."""
    name = name.lower().strip()
    name = re.sub(r"[^\wа-яё-]+", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def get_or_create_tags(tag_names: str) -> tuple:
    """Получает или создает теги из строки с запятыми. Возвращает (tags, requires_moderation)."""
    if not tag_names:
        return [], False
    tags = []
    requires_moderation = False
    for name in tag_names.split(","):
        name = name.strip()
        if not name:
            continue
        slug = slugify_tag(name)
        if not slug:
            continue
        # Проверка на модерацию по тегам
        moderated_tags = get_moderated_tags()
        if slug in moderated_tags or name.lower() in moderated_tags:
            requires_moderation = True
        tag = Tag.query.filter_by(slug=slug).first()
        if not tag:
            tag = Tag(name=name, slug=slug)
            db.session.add(tag)
        tags.append(tag)
    return tags, requires_moderation


def create_categories_from_tags(tags: list) -> list:
    """Автоматически создает категории на основе тегов поста."""
    if not tags:
        return []
    
    categories = []
    # Маппинг тегов к категориям (можно расширить)
    tag_to_category = {
        # Мемы и юмор
        "мемы": ("memes", "Мемы"),
        "мем": ("memes", "Мемы"),
        "юмор": ("humor", "Юмор"),
        "шутка": ("humor", "Юмор"),
        "вирусное": ("memes", "Мемы"),
        "тренд": ("memes", "Мемы"),
        
        # Кино
        "кино": ("movies", "Кино"),
        "фильм": ("movies", "Кино"),
        "сериал": ("movies", "Кино"),
        "сериалы": ("movies", "Кино"),
        "тв": ("movies", "Кино"),
        "трейлер": ("movies", "Кино"),
        "рецензия": ("movies", "Кино"),
        "комедия": ("movies", "Кино"),
        "драма": ("movies", "Кино"),
        "фантастика": ("movies", "Кино"),
        "хоррор": ("movies", "Кино"),
        "приключения": ("movies", "Кино"),
        "аниме": ("movies", "Кино"),
        "стриминг": ("movies", "Кино"),
        
        # Игры
        "игры": ("games", "Игры"),
        "игра": ("games", "Игры"),
        "cs2": ("games", "Игры"),
        "dota": ("games", "Игры"),
        "valorant": ("games", "Игры"),
        "fps": ("games", "Игры"),
        "rpg": ("games", "Игры"),
        "mmo": ("games", "Игры"),
        "инди": ("games", "Игры"),
        "pc": ("games", "Игры"),
        "консоль": ("games", "Игры"),
        "мобильные": ("games", "Игры"),
        
        # Музыка
        "музыка": ("music", "Музыка"),
        "рок": ("music", "Музыка"),
        "поп": ("music", "Музыка"),
        "электроника": ("music", "Музыка"),
        "хип-хоп": ("music", "Музыка"),
        "джаз": ("music", "Музыка"),
        "альбом": ("music", "Музыка"),
        "сингл": ("music", "Музыка"),
        "концерт": ("music", "Музыка"),
        "фестиваль": ("music", "Музыка"),
        
        # Технологии
        "технологии": ("tech", "Техно‑фан"),
        "техно": ("tech", "Техно‑фан"),
        "программирование": ("tech", "Техно‑фан"),
        "разработка": ("tech", "Техно‑фан"),
        "дизайн": ("tech", "Техно‑фан"),
        "веб": ("tech", "Техно‑фан"),
    }
    
    # Собираем уникальные категории из тегов
    category_slugs = set()
    for tag in tags:
        tag_name_lower = tag.name.lower()
        if tag_name_lower in tag_to_category:
            slug, title = tag_to_category[tag_name_lower]
            category_slugs.add((slug, title))
    
    # Создаем или получаем категории
    for slug, title in category_slugs:
        category = Category.query.filter_by(slug=slug).first()
        if not category:
            category = Category(slug=slug, title=title)
            db.session.add(category)
        categories.append(category)
    
    return categories


def contains_bad_words(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    # Убираем знаки препинания
    cleaned = re.sub(r"[^\wа-яё]+", " ", lowered, flags=re.IGNORECASE)
    words = set(cleaned.split())
    return any(bad in words for bad in BAD_WORDS)


def is_allowed_media(filename: str) -> bool:
    if not filename:
        return False
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext in ALLOWED_MEDIA_EXT


def is_auto_mod_enabled() -> bool:
    settings = ModerationSettings.query.first()
    # По умолчанию считаем, что включена
    return not settings or bool(settings.auto_enabled)


def log_moderation(kind: str, *, user_id=None, post_id=None, comment_id=None, reason: str = "", text: str = "") -> None:
    # Очищаем текст от HTML-тегов для snippet
    import re
    clean_text = re.sub(r'<[^>]+>', '', text or "")  # Удаляем HTML-теги
    clean_text = clean_text.strip().replace("\n", " ").replace("\r", "")
    # Удаляем множественные пробелы
    clean_text = re.sub(r'\s+', ' ', clean_text)
    snippet = clean_text
    if len(snippet) > 180:
        snippet = snippet[:177] + "..."
    log = ModerationLog(
        kind=kind,
        reason=reason or None,
        snippet=snippet or None,
        user_id=user_id,
        post_id=post_id,
        comment_id=comment_id,
    )
    db.session.add(log)


@bp.app_errorhandler(413)
def handle_large_request(_error):
    flash("Файл слишком большой. Попробуйте загрузить медиа меньшего размера.", "warning")
    # Возвращаем на предыдущую страницу или на создание поста
    return redirect(request.referrer or url_for("main.post_new"))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Нужны права администратора.", "warning")
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)

    return wrapped


@bp.context_processor
def inject_globals():
    # Популярные теги для облака
    popular_tags = (
        db.session.query(Tag, func.count(Post.id).label("count"))
        .join(Post.tags)
        .filter(Post.is_published.is_(True))
        .group_by(Tag.id)
        .order_by(func.count(Post.id).desc())
        .limit(20)
        .all()
    )
    return {
        "all_categories": Category.query.order_by(Category.title.asc()).all(),
        "popular_tags": [t[0] for t in popular_tags],
        "search_form": SearchForm(),
    }


def calculate_recommendations(user_id: int, limit: int = 20) -> list:
    """
    Рассчитывает рекомендации постов на основе взаимодействия пользователя:
    - Время просмотра поста
    - Комментарии пользователя
    - Реакции (лайки/дизлайки)
    """
    # Получаем все посты, с которыми пользователь взаимодействовал
    user_views = PostView.query.filter_by(user_id=user_id).all()
    user_comments = Comment.query.filter_by(author_id=user_id).all()
    user_likes = PostLike.query.filter_by(user_id=user_id).all()
    
    # Собираем данные о взаимодействии по постам
    post_scores = {}  # {post_id: score}
    
    # 1. Время просмотра (чем дольше смотрел, тем выше интерес)
    for view in user_views:
        post_id = view.post_id
        if post_id not in post_scores:
            post_scores[post_id] = 0.0
        
        # Нормализуем время просмотра (максимум 5 минут = 300 секунд = 1.0 балл)
        time_score = min(1.0, view.view_duration / 300.0) if view.view_duration else 0.0
        # Учитываем прогресс просмотра
        progress_score = view.progress or 0.0
        # Если просмотрен полностью - бонус
        complete_bonus = 0.5 if view.is_complete else 0.0
        
        post_scores[post_id] += (time_score * 2.0) + (progress_score * 1.0) + complete_bonus
    
    # 2. Комментарии (если писал комментарии - высокий интерес)
    for comment in user_comments:
        post_id = comment.post_id
        if post_id not in post_scores:
            post_scores[post_id] = 0.0
        # Каждый комментарий добавляет 3.0 балла
        post_scores[post_id] += 3.0
    
    # 3. Реакции
    for like in user_likes:
        post_id = like.post_id
        if post_id not in post_scores:
            post_scores[post_id] = 0.0
        
        if like.reaction == "like":
            # Лайк добавляет 5.0 балла
            post_scores[post_id] += 5.0
        elif like.reaction == "dislike":
            # Дизлайк уменьшает интерес, но не убирает полностью
            post_scores[post_id] -= 2.0
    
    # Получаем ID всех постов, с которыми пользователь взаимодействовал
    viewed_post_ids = {view.post_id for view in user_views}
    liked_post_ids = {like.post_id for like in user_likes if like.reaction == "like"}
    commented_post_ids = {comment.post_id for comment in user_comments}
    all_interacted_ids = viewed_post_ids | liked_post_ids | commented_post_ids
    
    # Если есть хоть какое-то взаимодействие, используем его для рекомендаций
    if post_scores:
        # Берем посты с любым положительным рейтингом (не только > 2.0)
        # Сортируем по рейтингу и берем топ-10
        sorted_posts = sorted(post_scores.items(), key=lambda x: x[1], reverse=True)
        top_posts = [pid for pid, score in sorted_posts[:10] if score > 0]
        
        if top_posts:
            # Получаем теги из этих постов
            preferred_tags = (
                db.session.query(Tag.id, Tag.name)
                .join(Post.tags)
                .filter(Post.id.in_(top_posts))
                .group_by(Tag.id, Tag.name)
                .all()
            )
            
            if preferred_tags:
                preferred_tag_ids = [tag_id for tag_id, _ in preferred_tags]
                
                # Находим посты с похожими тегами, которые пользователь еще не видел
                recommended_query = (
                    Post.query.join(Post.tags)
                    .filter(Post.is_published.is_(True))
                    .filter(Tag.id.in_(preferred_tag_ids))
                    .filter(~Post.id.in_(all_interacted_ids) if all_interacted_ids else True)
                    .order_by(Post.created_at.desc())
                    .limit(limit * 2)
                    .all()
                )
                
                if recommended_query:
                    # Сортируем по релевантности (количество совпадающих тегов)
                    post_relevance = {}
                    for post in recommended_query:
                        post_tags = {tag.id for tag in post.tags}
                        matching_tags = len(post_tags.intersection(set(preferred_tag_ids)))
                        post_relevance[post.id] = matching_tags
                    
                    # Сортируем по релевантности и свежести
                    recommended_posts = sorted(
                        recommended_query,
                        key=lambda p: (post_relevance.get(p.id, 0), p.created_at),
                        reverse=True
                    )[:limit]
                    
                    if recommended_posts:
                        return recommended_posts
    
    # Fallback: если нет данных о взаимодействии, показываем популярные посты с лайками
    # или просто свежие посты, которые пользователь еще не видел
    if not all_interacted_ids:
        # Для новых пользователей показываем популярные посты
        popular_posts = (
            Post.query.join(PostLike)
            .filter(Post.is_published.is_(True))
            .filter(PostLike.reaction == "like")
            .group_by(Post.id)
            .order_by(func.count(PostLike.id).desc(), Post.created_at.desc())
            .limit(limit)
            .all()
        )
        if popular_posts:
            return popular_posts
    
    # Если все еще нет рекомендаций, показываем свежие посты, которые пользователь не видел
    fresh_posts = (
        Post.query.filter_by(is_published=True)
        .filter(~Post.id.in_(all_interacted_ids) if all_interacted_ids else True)
        .order_by(Post.created_at.desc())
        .limit(limit)
        .all()
    )
    
    return fresh_posts


@bp.get("/")
def index():
    category = request.args.get("category")
    tag_slug = request.args.get("tag")
    q = request.args.get("q")

    query = Post.query.filter_by(is_published=True).order_by(Post.created_at.desc())

    if category:
        query = query.join(Post.categories).filter(Category.slug == category)
    if tag_slug:
        query = query.join(Post.tags).filter(Tag.slug == tag_slug)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((Post.title.ilike(like)) | (Post.body.ilike(like)))

    # Если пользователь авторизован, показываем рекомендации на основе взаимодействия
    recommended_posts = []
    if current_user.is_authenticated and not category and not tag_slug and not q:
        recommended_posts = calculate_recommendations(current_user.id, limit=10)

    posts = query.limit(50).all()
    
    # Если есть рекомендации, добавляем их в начало
    if recommended_posts:
        # Исключаем дубликаты
        existing_ids = {p.id for p in posts}
        new_recommended = [p for p in recommended_posts if p.id not in existing_ids]
        posts = new_recommended[:10] + posts

    trending_rows = (
        db.session.query(Post, func.count(Comment.id).label("comments_count"))
        .outerjoin(Comment, Comment.post_id == Post.id)
        .filter(Post.is_published.is_(True))
        .group_by(Post.id)
        .order_by(func.count(Comment.id).desc(), Post.created_at.desc())
        .limit(5)
        .all()
    )
    trending_posts = [row[0] for row in trending_rows]

    return render_template(
        "index.html",
        posts=posts,
        recommended_posts=recommended_posts,
        trending_posts=trending_posts,
        active_category=category,
        q=q,
        has_recommendations=bool(recommended_posts),
    )


@bp.route("/search", methods=["GET", "POST"])
def search():
    form = SearchForm()
    if form.validate_on_submit():
        return redirect(url_for("main.index", q=form.q.data))
    return redirect(url_for("main.index"))


@bp.get("/random")
def random_post():
    post = (
        Post.query.filter_by(is_published=True)
        .order_by(func.random())
        .first()
    )
    if not post:
        flash("Пока нет опубликованных постов.", "info")
        return redirect(url_for("main.index"))
    return redirect(url_for("main.post_detail", post_id=post.id))


@bp.get("/post/<int:post_id>")
def post_detail(post_id: int):
    post = Post.query.get_or_404(post_id)
    if not post.is_published and (not current_user.is_authenticated or (current_user.id != post.author_id and not current_user.is_admin)):
        flash("Пост скрыт.", "warning")
        return redirect(url_for("main.index"))

    # Просмотры отслеживаются через PostView, не накручиваем счетчик

    form = CommentForm()
    comments = Comment.query.filter_by(post_id=post.id).order_by(Comment.created_at.asc()).all()

    # Reactions summary
    reactions_counts = {code: 0 for code in REACTIONS.keys()}
    rows = (
        db.session.query(PostLike.reaction, func.count(PostLike.id))
        .filter_by(post_id=post.id)
        .group_by(PostLike.reaction)
        .all()
    )
    for reaction, count in rows:
        if reaction in reactions_counts:
            reactions_counts[reaction] = count

    user_reaction = None
    user_view = None
    similar_tags = []
    
    if current_user.is_authenticated:
        like = PostLike.query.filter_by(post_id=post.id, user_id=current_user.id).first()
        if like:
            user_reaction = like.reaction
            # Если понравилось, показываем похожие теги
            if user_reaction == "like":
                # Получаем теги из понравившихся постов пользователя
                liked_posts = (
                    Post.query.join(PostLike)
                    .filter(PostLike.user_id == current_user.id, PostLike.reaction == "like")
                    .filter(Post.id != post.id)
                    .all()
                )
                tag_counts = {}
                for liked_post in liked_posts:
                    for tag in liked_post.tags:
                        if tag.id not in tag_counts:
                            tag_counts[tag.id] = {"tag": tag, "count": 0}
                        tag_counts[tag.id]["count"] += 1
                # Сортируем по популярности и берем топ-5
                similar_tags = sorted(tag_counts.values(), key=lambda x: x["count"], reverse=True)[:5]
                similar_tags = [item["tag"] for item in similar_tags]
        
        # Получаем информацию о просмотре
        user_view = PostView.query.filter_by(post_id=post.id, user_id=current_user.id).first()

    return render_template(
        "post_detail.html",
        post=post,
        form=form,
        comments=comments,
        reactions=REACTIONS,
        reactions_counts=reactions_counts,
        user_reaction=user_reaction,
        user_view=user_view,
        similar_tags=similar_tags,
    )


@bp.post("/post/<int:post_id>/react/<string:reaction_code>")
@login_required
def post_react(post_id: int, reaction_code: str):
    if reaction_code not in REACTIONS:
        flash("Неизвестная реакция.", "warning")
        return redirect(url_for("main.post_detail", post_id=post_id))

    post = Post.query.get_or_404(post_id)
    like = PostLike.query.filter_by(post_id=post.id, user_id=current_user.id).first()

    # Если пользователь уже поставил эту реакцию - убираем её
    if like and like.reaction == reaction_code:
        db.session.delete(like)
        # Удаляем предпочтения по тегам при отмене лайка
        if reaction_code == "like":
            for tag in post.tags:
                pref = UserTagPreference.query.filter_by(user_id=current_user.id, tag_id=tag.id).first()
                if pref:
                    pref.score = max(0.1, pref.score - 0.2)  # Уменьшаем вес
                    if pref.score < 0.2:
                        db.session.delete(pref)
    else:
        # Если пользователь меняет реакцию или ставит новую
        old_reaction = like.reaction if like else None
        
        if not like:
            like = PostLike(post_id=post.id, user_id=current_user.id)
            db.session.add(like)
        
        # Удаляем старые предпочтения при смене с лайка на дизлайк
        if old_reaction == "like" and reaction_code == "dislike":
            for tag in post.tags:
                pref = UserTagPreference.query.filter_by(user_id=current_user.id, tag_id=tag.id).first()
                if pref:
                    pref.score = max(0.1, pref.score - 0.3)
                    if pref.score < 0.2:
                        db.session.delete(pref)
        
        like.reaction = reaction_code
        
        # Обновляем предпочтения по тегам при лайке
        if reaction_code == "like":
            for tag in post.tags:
                pref = UserTagPreference.query.filter_by(user_id=current_user.id, tag_id=tag.id).first()
                if pref:
                    pref.score = min(10.0, pref.score + 0.5)  # Увеличиваем вес
                    pref.updated_at = datetime.now(timezone.utc)
                else:
                    pref = UserTagPreference(user_id=current_user.id, tag_id=tag.id, score=1.0)
                    db.session.add(pref)

    db.session.commit()
    return redirect(url_for("main.post_detail", post_id=post.id))


@bp.post("/post/<int:post_id>/comment")
@login_required
def add_comment(post_id: int):
    post = Post.query.get_or_404(post_id)
    if not post.is_published and not current_user.is_admin and post.author_id != current_user.id:
        flash("Нельзя комментировать скрытый пост.", "warning")
        return redirect(url_for("main.post_detail", post_id=post.id))

    form = CommentForm()
    if form.validate_on_submit():
        text = form.body.data or ""
        if is_auto_mod_enabled() and contains_bad_words(text):
            log_moderation(
                "comment_blocked",
                user_id=current_user.id,
                post_id=post.id,
                reason="bad_words",
                text=text,
            )
            db.session.commit()
            flash("В комментарии обнаружены запрещённые слова. Исправьте текст и попробуйте снова.", "warning")
        else:
            c = Comment(body=text, author_id=current_user.id, post_id=post.id)
            db.session.add(c)
            db.session.commit()
            flash("Комментарий добавлен.", "success")
    else:
        flash("Комментарий слишком короткий/длинный.", "danger")
    return redirect(url_for("main.post_detail", post_id=post.id))


@bp.route("/new", methods=["GET", "POST"])
@login_required
def post_new():
    form = PostForm()

    if form.validate_on_submit():
        text_blob = " ".join(
            [
                form.title.data or "",
                form.summary.data or "",
                form.body.data or "",
            ]
        )
        
        # Проверяем на запрещенные слова (удаление поста)
        has_bad_words = is_auto_mod_enabled() and contains_bad_words(text_blob)
        
        # Проверка на дубликаты с улучшенным сообщением
        duplicate = check_duplicate(0, form.title.data, form.body.data, threshold=0.75)
        if duplicate:
            duplicate_post, similarity = duplicate
            if similarity >= 0.85:
                flash(
                    f"⚠️ Обнаружен очень похожий пост: '{duplicate_post.title}' (схожесть {similarity:.0%}). "
                    f"<a href='{url_for('main.post_detail', post_id=duplicate_post.id)}' class='alert-link'>Посмотреть</a>",
                    "danger"
                )
            else:
                flash(
                    f"💡 Похожий пост: '{duplicate_post.title}' (схожесть {similarity:.0%}). "
                    f"<a href='{url_for('main.post_detail', post_id=duplicate_post.id)}' class='alert-link'>Посмотреть</a>",
                    "warning"
                )

        # Если есть запрещенные слова - удаляем пост и показываем предупреждение
        if has_bad_words:
            # Логируем удаление
            log_moderation(
                "post_deleted",
                user_id=current_user.id,
                post_id=None,
                reason="bad_words",
                text=text_blob[:200] if text_blob else "",
            )
            db.session.commit()
            flash(
                "🚫 Пост удалён. В тексте обнаружены запрещённые слова. "
                "Пожалуйста, соблюдайте правила сообщества и не используйте нецензурную лексику.",
                "danger",
            )
            return redirect(url_for("main.post_new"))

        post = Post(
            title=form.title.data,
            summary=form.summary.data or None,
            cover_emoji=(form.cover_emoji.data or "").strip() or None,
            body=form.body.data,
            author_id=current_user.id,
        )
        
        # Обработка тегов
        requires_tag_moderation = False
        if form.tags.data:
            tags_result, requires_tag_moderation = get_or_create_tags(form.tags.data)
            post.tags = tags_result
            # Автоматически создаем категории на основе тегов
            post.categories = create_categories_from_tags(tags_result)
        else:
            post.tags = []
            post.categories = []

        # Если есть модерируемые теги - скрываем пост
        if requires_tag_moderation:
            post.is_published = False
        else:
            post.is_published = bool(form.is_published.data)

        file = form.media.data
        if file:
            filename = secure_filename(file.filename or "")
            if filename:
                if is_auto_mod_enabled() and (not is_allowed_media(filename) or contains_bad_words(filename)):
                    log_moderation(
                        "file_blocked",
                        user_id=current_user.id,
                        post_id=None,
                        reason="bad_extension_or_name",
                        text=filename,
                    )
                    flash("Файл отклонён: недопустимое расширение или запрещённые слова в названии.", "warning")
                else:
                    ext = filename.rsplit(".", 1)[-1].lower()
                    upload_dir = os.path.join(current_app.root_path, "static", "uploads")
                    os.makedirs(upload_dir, exist_ok=True)
                    save_name = f"{post.author_id}_{uuid.uuid4().hex}.{ext}"
                    filepath = os.path.join(upload_dir, save_name)
                    file.save(filepath)
                    post.media_path = f"uploads/{save_name}"
                    post.media_type = "video" if ext in ALLOWED_VIDEO_EXT else "image"

        db.session.add(post)
        db.session.flush()  # Получаем post.id для логирования
        
        if requires_tag_moderation:
            # Логируем модерацию тегов
            log_moderation(
                "post_autohide",
                user_id=current_user.id,
                post_id=post.id,
                reason="moderated_tags",
                text=text_blob[:200] if text_blob else "",
            )

        # Сохранение треков
        track_titles = request.form.getlist("track_titles")
        track_artists = request.form.getlist("track_artists")
        track_urls = request.form.getlist("track_urls")
        
        # Добавляем новые треки
        for idx, (title, artist) in enumerate(zip(track_titles, track_artists)):
            title = title.strip()
            artist = artist.strip()
            if title and artist:
                url = track_urls[idx].strip() if idx < len(track_urls) else ""
                track = Track(
                    title=title,
                    artist=artist,
                    url=url if url else None,
                    post_id=post.id,
                    order=idx,
                )
                db.session.add(track)

        db.session.commit()

        if requires_tag_moderation:
            flash(
                "⚠️ Пост отправлен на модерацию и скрыт из публичной ленты. "
                "Используются модерируемые теги. Пост сохранён и ожидает проверки администратором. "
                "Вы можете редактировать его в любое время.",
                "warning",
            )
        else:
            flash("Пост создан и опубликован.", "success")
        return redirect(url_for("main.post_detail", post_id=post.id))

    return render_template("post_edit.html", form=form, mode="new")


@bp.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def post_edit(post_id: int):
    post = Post.query.get_or_404(post_id)
    if not current_user.is_admin and post.author_id != current_user.id:
        flash("Нельзя редактировать чужой пост.", "warning")
        return redirect(url_for("main.post_detail", post_id=post.id))

    form = PostForm(obj=post)
    if request.method == "GET":
        form.tags.data = ", ".join([t.name for t in post.tags])

    if form.validate_on_submit():
        text_blob = " ".join(
            [
                form.title.data or "",
                form.summary.data or "",
                form.body.data or "",
            ]
        )
        
        # Проверяем на запрещенные слова (удаление поста)
        has_bad_words = is_auto_mod_enabled() and contains_bad_words(text_blob)
        
        # Проверка на дубликаты при редактировании
        duplicate = check_duplicate(post.id, form.title.data, form.body.data, threshold=0.75)
        if duplicate:
            duplicate_post, similarity = duplicate
            if similarity >= 0.85:
                flash(
                    f"⚠️ Обнаружен очень похожий пост: '{duplicate_post.title}' (схожесть {similarity:.0%}). "
                    f"<a href='{url_for('main.post_detail', post_id=duplicate_post.id)}' class='alert-link'>Посмотреть</a>",
                    "danger"
                )
            elif similarity >= 0.75:
                flash(
                    f"💡 Похожий пост: '{duplicate_post.title}' (схожесть {similarity:.0%}). "
                    f"<a href='{url_for('main.post_detail', post_id=duplicate_post.id)}' class='alert-link'>Посмотреть</a>",
                    "warning"
                )

        # Если есть запрещенные слова - удаляем пост и показываем предупреждение
        if has_bad_words:
            post_id = post.id
            # Удаляем связанные данные
            Track.query.filter_by(post_id=post_id).delete()
            Comment.query.filter_by(post_id=post_id).delete()
            PostLike.query.filter_by(post_id=post_id).delete()
            PostView.query.filter_by(post_id=post_id).delete()
            # Удаляем медиафайл если есть
            if post.media_path:
                try:
                    media_path = os.path.join(current_app.root_path, "static", post.media_path)
                    if os.path.exists(media_path):
                        os.remove(media_path)
                except Exception:
                    pass
            # Логируем удаление
            log_moderation(
                "post_deleted",
                user_id=current_user.id,
                post_id=post_id,
                reason="bad_words_edit",
                text=text_blob[:200] if text_blob else "",
            )
            db.session.delete(post)
            db.session.commit()
            flash(
                "🚫 Пост удалён. В тексте обнаружены запрещённые слова. "
                "Пожалуйста, соблюдайте правила сообщества и не используйте нецензурную лексику.",
                "danger",
            )
            return redirect(url_for("main.index"))

        post.title = form.title.data
        post.summary = form.summary.data or None
        post.cover_emoji = (form.cover_emoji.data or "").strip() or None
        post.body = form.body.data
        
        # Обработка тегов
        requires_tag_moderation = False
        if form.tags.data:
            tags_result, requires_tag_moderation = get_or_create_tags(form.tags.data)
            post.tags = tags_result
            # Автоматически создаем категории на основе тегов
            post.categories = create_categories_from_tags(tags_result)
        else:
            post.tags = []
            post.categories = []

        # Если есть модерируемые теги - скрываем пост
        if requires_tag_moderation:
            post.is_published = False
        else:
            post.is_published = bool(form.is_published.data)

        file = form.media.data
        if file:
            filename = secure_filename(file.filename or "")
            if filename:
                if is_auto_mod_enabled() and (not is_allowed_media(filename) or contains_bad_words(filename)):
                    log_moderation(
                        "file_blocked",
                        user_id=current_user.id,
                        post_id=post.id,
                        reason="bad_extension_or_name",
                        text=filename,
                    )
                    flash("Файл отклонён: недопустимое расширение или запрещённые слова в названии.", "warning")
                else:
                    # Удаляем старый файл если есть
                    if post.media_path:
                        try:
                            old_media_path = os.path.join(current_app.root_path, "static", post.media_path)
                            if os.path.exists(old_media_path):
                                os.remove(old_media_path)
                        except Exception:
                            pass
                    ext = filename.rsplit(".", 1)[-1].lower()
                    upload_dir = os.path.join(current_app.root_path, "static", "uploads")
                    os.makedirs(upload_dir, exist_ok=True)
                    save_name = f"{post.author_id}_{uuid.uuid4().hex}.{ext}"
                    filepath = os.path.join(upload_dir, save_name)
                    file.save(filepath)
                    post.media_path = f"uploads/{save_name}"
                    post.media_type = "video" if ext in ALLOWED_VIDEO_EXT else "image"

        post.touch()
        db.session.flush()  # Получаем актуальный post.id
        
        if requires_tag_moderation:
            log_moderation(
                "post_autohide",
                user_id=current_user.id,
                post_id=post.id,
                reason="moderated_tags_edit",
                text=text_blob[:200] if text_blob else "",
            )

        # Сохранение треков
        track_titles = request.form.getlist("track_titles")
        track_artists = request.form.getlist("track_artists")
        track_urls = request.form.getlist("track_urls")
        
        # Удаляем существующие треки
        Track.query.filter_by(post_id=post.id).delete()
        
        # Добавляем новые треки
        for idx, (title, artist) in enumerate(zip(track_titles, track_artists)):
            title = title.strip()
            artist = artist.strip()
            if title and artist:
                url = track_urls[idx].strip() if idx < len(track_urls) else ""
                track = Track(
                    title=title,
                    artist=artist,
                    url=url if url else None,
                    post_id=post.id,
                    order=idx,
                )
                db.session.add(track)

        post.touch()
        db.session.commit()

        if requires_tag_moderation:
            flash(
                "⚠️ Пост отправлен на модерацию и скрыт из публичной ленты. "
                "Используются модерируемые теги. Пост сохранён и ожидает проверки администратором.",
                "warning",
            )
        else:
            flash("Пост сохранён и опубликован.", "success")
        return redirect(url_for("main.post_detail", post_id=post.id))

    return render_template("post_edit.html", form=form, mode="edit", post=post)


@bp.post("/post/<int:post_id>/delete")
@login_required
def post_delete(post_id: int):
    post = Post.query.get_or_404(post_id)
    if not current_user.is_admin and post.author_id != current_user.id:
        flash("Нельзя удалять чужой пост.", "warning")
        return redirect(url_for("main.post_detail", post_id=post.id))
    db.session.delete(post)
    db.session.commit()
    flash("Пост удалён.", "success")
    return redirect(url_for("main.index"))


@bp.get("/u/<string:username>")
def profile(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    posts_query = Post.query.filter_by(author_id=user.id).order_by(Post.created_at.desc())
    if not (current_user.is_authenticated and (current_user.is_admin or current_user.id == user.id)):
        posts_query = posts_query.filter_by(is_published=True)
    posts = posts_query.limit(50).all()

    comments = (
        Comment.query.filter_by(author_id=user.id)
        .order_by(Comment.created_at.desc())
        .limit(30)
        .all()
    )
    posts_count = Post.query.filter_by(author_id=user.id).count()
    comments_count = Comment.query.filter_by(author_id=user.id).count()
    followers_count = Follow.query.filter_by(followed_id=user.id).count()
    following_count = Follow.query.filter_by(follower_id=user.id).count()

    is_following = False
    if current_user.is_authenticated and current_user.id != user.id:
        is_following = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first() is not None

    return render_template(
        "profile.html",
        user=user,
        posts=posts,
        comments=comments,
        posts_count=posts_count,
        comments_count=comments_count,
        followers_count=followers_count,
        following_count=following_count,
        is_following=is_following,
    )


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Никнейм уже занят.", "danger")
            return render_template("auth_register.html", form=form)
        if User.query.filter_by(email=form.email.data).first():
            flash("Email уже зарегистрирован.", "danger")
            return render_template("auth_register.html", form=form)

        username = form.username.data.strip()
        u = User(username=username, email=form.email.data)
        u.password_hash = generate_password_hash(form.password.data)
        if username.lower() == "tw1xty":
            u.is_admin = True
        db.session.add(u)
        db.session.commit()
        login_user(u)
        flash("Добро пожаловать!", "success")
        return redirect(url_for("main.index"))

    return render_template("auth_register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        u = User.query.filter_by(email=form.email.data).first()
        if not u or not u.check_password(form.password.data):
            flash("Неверный email или пароль.", "danger")
            return render_template("auth_login.html", form=form)
        login_user(u)
        flash("Вы вошли.", "success")
        return redirect(url_for("main.index"))

    return render_template("auth_login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли.", "info")
    return redirect(url_for("main.index"))


@bp.get("/admin")
@login_required
@admin_required
def admin():
    # Поиск по постам
    post_search = request.args.get("post_search", "").strip()
    
    # Админ видит все посты и всех пользователей
    posts_query = Post.query
    if post_search:
        search_like = f"%{post_search}%"
        posts_query = posts_query.filter(
            (Post.title.ilike(search_like)) | 
            (Post.body.ilike(search_like)) |
            (Post.summary.ilike(search_like))
        )
    posts = posts_query.order_by(Post.created_at.desc()).limit(100).all()
    
    users = User.query.order_by(User.created_at.desc()).all()
    # Создаем словарь пользователей для быстрого доступа в шаблоне
    users_dict = {u.id: u for u in users}
    categories = Category.query.order_by(Category.title.asc()).all()
    comments = Comment.query.order_by(Comment.created_at.desc()).limit(50).all()
    category_form = CategoryForm()
    auto_settings = ModerationSettings.query.first()
    auto_enabled = not auto_settings or bool(auto_settings.auto_enabled)
    moderation_logs = (
        ModerationLog.query.order_by(ModerationLog.created_at.desc())
        .limit(50)
        .all()
    )
    # Получаем все теги и теги, требующие модерации
    all_tags = Tag.query.order_by(Tag.name.asc()).all()
    moderated_tag_ids = {mt.tag_id for mt in ModeratedTag.query.all()}
    return render_template(
        "admin.html",
        posts=posts,
        users=users,
        users_dict=users_dict,
        categories=categories,
        comments=comments,
        category_form=category_form,
        bad_words_sorted=sorted(BAD_WORDS),
        auto_enabled=auto_enabled,
        moderation_logs=moderation_logs,
        all_tags=all_tags,
        moderated_tag_ids=moderated_tag_ids,
        post_search=post_search,
    )


@bp.post("/admin/post/<int:post_id>/toggle")
@login_required
@admin_required
def admin_toggle_post(post_id: int):
    post = Post.query.get_or_404(post_id)
    post.is_published = not post.is_published
    post.touch()
    db.session.commit()
    flash("Статус поста обновлён.", "success")
    return redirect(url_for("main.admin"))


@bp.post("/admin/post/<int:post_id>/delete")
@login_required
@admin_required
def admin_delete_post(post_id: int):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash("Пост удалён.", "success")
    return redirect(url_for("main.admin"))


@bp.post("/admin/user/<int:user_id>/toggle-admin")
@login_required
@admin_required
def admin_toggle_user(user_id: int):
    u = User.query.get_or_404(user_id)
    if current_user.id == u.id:
        flash("Нельзя снять админа с самого себя.", "warning")
        return redirect(url_for("main.admin"))
    u.is_admin = not u.is_admin
    db.session.commit()
    flash("Роль пользователя обновлена.", "success")
    return redirect(url_for("main.admin"))


@bp.post("/admin/user/<int:user_id>/delete")
@login_required
@admin_required
def admin_delete_user(user_id: int):
    u = User.query.get_or_404(user_id)
    if current_user.id == u.id:
        flash("Нельзя удалить самого себя.", "warning")
        return redirect(url_for("main.admin"))
    db.session.delete(u)
    db.session.commit()
    flash("Пользователь и его контент удалены.", "success")
    return redirect(url_for("main.admin"))

@bp.post("/admin/comment/<int:comment_id>/delete")
@login_required
@admin_required
def admin_delete_comment(comment_id: int):
    c = Comment.query.get_or_404(comment_id)
    db.session.delete(c)
    db.session.commit()
    flash("Комментарий удалён.", "success")
    return redirect(url_for("main.admin"))


@bp.post("/admin/category/create")
@login_required
@admin_required
def admin_create_category():
    form = CategoryForm()
    if not form.validate_on_submit():
        flash("Проверьте поля категории.", "danger")
        return redirect(url_for("main.admin"))

    slug = (form.slug.data or "").strip().lower()
    title = (form.title.data or "").strip()
    if Category.query.filter_by(slug=slug).first():
        flash("Такой slug уже существует.", "danger")
        return redirect(url_for("main.admin"))
    if Category.query.filter_by(title=title).first():
        flash("Такая категория уже существует.", "danger")
        return redirect(url_for("main.admin"))

    db.session.add(Category(slug=slug, title=title))
    db.session.commit()
    flash("Категория создана.", "success")
    return redirect(url_for("main.admin"))


@bp.post("/admin/category/<int:category_id>/delete")
@login_required
@admin_required
def admin_delete_category(category_id: int):
    c = Category.query.get_or_404(category_id)
    # Remove links from posts before deleting category (safe for SQLite)
    for p in Post.query.join(Post.categories).filter(Category.id == c.id).all():
        p.categories = [cat for cat in p.categories if cat.id != c.id]
        p.touch()
    db.session.delete(c)
    db.session.commit()
    flash("Категория удалена.", "success")
    return redirect(url_for("main.admin"))


@bp.post("/admin/bad-words")
@login_required
@admin_required
def admin_update_bad_words():
    raw = request.form.get("bad_words", "")
    new_set = set()
    for line in raw.splitlines():
        word = line.strip().lower()
        if word:
            new_set.add(word)

    if not new_set:
        flash("Список не может быть полностью пустым.", "warning")
        return redirect(url_for("main.admin"))

    global BAD_WORDS
    BAD_WORDS = new_set
    flash("Список запрещённых слов обновлён (до перезапуска приложения).", "success")
    return redirect(url_for("main.admin"))


@bp.post("/admin/moderation-toggle")
@login_required
@admin_required
def admin_toggle_moderation():
    enabled = request.form.get("auto_enabled") == "on"
    settings = ModerationSettings.query.first()
    if not settings:
        settings = ModerationSettings(auto_enabled=enabled)
        db.session.add(settings)
    else:
        settings.auto_enabled = enabled
    db.session.commit()
    flash(
        "Автомодерация включена." if enabled else "Автомодерация отключена. Помните о рисках.",
        "success",
    )
    return redirect(url_for("main.admin"))


@bp.post("/admin/tag/<int:tag_id>/toggle-moderation")
@login_required
@admin_required
def admin_toggle_tag_moderation(tag_id: int):
    tag = Tag.query.get_or_404(tag_id)
    moderated = ModeratedTag.query.filter_by(tag_id=tag_id).first()
    
    if moderated:
        db.session.delete(moderated)
        flash(f"Тег #{tag.name} больше не требует модерации. Посты с этим тегом теперь публикуются автоматически.", "success")
    else:
        moderated = ModeratedTag(tag_id=tag_id)
        db.session.add(moderated)
        # Скрываем все существующие посты с этим тегом
        posts_with_tag = Post.query.join(Post.tags).filter(Tag.id == tag_id).all()
        hidden_count = 0
        for post in posts_with_tag:
            if post.is_published:
                post.is_published = False
                hidden_count += 1
        if hidden_count > 0:
            flash(f"Тег #{tag.name} теперь требует модерации. {hidden_count} существующих постов скрыто и требует проверки.", "warning")
        else:
            flash(f"Тег #{tag.name} теперь требует модерации. Новые посты с этим тегом будут автоматически скрыты.", "success")
    
    db.session.commit()
    return redirect(url_for("main.admin"))


# Подписки
@bp.post("/user/<int:user_id>/follow")
@login_required
def follow_user(user_id: int):
    user_to_follow = User.query.get_or_404(user_id)
    if user_to_follow.id == current_user.id:
        flash("Нельзя подписаться на самого себя.", "warning")
        return redirect(url_for("main.profile", username=user_to_follow.username))
    
    existing = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
    if existing:
        flash("Вы уже подписаны на этого пользователя.", "info")
    else:
        follow = Follow(follower_id=current_user.id, followed_id=user_id)
        db.session.add(follow)
        db.session.commit()
        flash(f"Вы подписались на {user_to_follow.username}.", "success")
    return redirect(url_for("main.profile", username=user_to_follow.username))


@bp.post("/user/<int:user_id>/unfollow")
@login_required
def unfollow_user(user_id: int):
    user_to_unfollow = User.query.get_or_404(user_id)
    follow = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
    if follow:
        db.session.delete(follow)
        db.session.commit()
        flash(f"Вы отписались от {user_to_unfollow.username}.", "info")
    return redirect(url_for("main.profile", username=user_to_unfollow.username))


@bp.get("/following")
@login_required
def following_feed():
    """Лента постов от подписок и список подписок."""
    following_list = current_user.following.all()
    following_ids = [f.followed_id for f in following_list]
    
    # Получаем пользователей, на которых подписан
    following_users = User.query.filter(User.id.in_(following_ids)).all() if following_ids else []
    
    # Получаем посты от подписок
    posts = []
    if following_ids:
        posts = (
            Post.query.filter(Post.author_id.in_(following_ids))
            .filter_by(is_published=True)
            .order_by(Post.created_at.desc())
            .limit(50)
            .all()
        )
    
    return render_template("following.html", posts=posts, following_users=following_users, is_following_feed=True)


# Редактирование профиля
@bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def profile_edit():
    form = ProfileEditForm(obj=current_user)
    if request.method == "GET":
        form.theme_preference.data = current_user.theme_preference or "dark"
    
    if form.validate_on_submit():
        current_user.bio = form.bio.data or None
        current_user.is_private = bool(form.is_private.data)
        current_user.theme_preference = form.theme_preference.data or "dark"
        
        # Обработка аватара
        file = form.avatar.data
        if file:
            filename = secure_filename(file.filename or "")
            if filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_IMAGE_EXT:
                ext = filename.rsplit(".", 1)[-1].lower()
                upload_dir = os.path.join(current_app.root_path, "static", "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                save_name = f"avatar_{current_user.id}_{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(upload_dir, save_name)
                file.save(filepath)
                current_user.avatar_path = f"uploads/{save_name}"
        
        db.session.commit()
        flash("Профиль обновлён.", "success")
        return redirect(url_for("main.profile", username=current_user.username))
    
    return render_template("profile_edit.html", form=form)


# Переключение темы
@bp.post("/theme/toggle")
@login_required
def toggle_theme():
    theme = request.form.get("theme", "dark")
    if theme not in ["dark", "light", "auto"]:
        theme = "dark"
    current_user.theme_preference = theme
    db.session.commit()
    return redirect(request.referrer or url_for("main.index"))


# Облако тегов
@bp.get("/tags")
def tags_cloud():
    """Страница со всеми тегами."""
    tags_with_counts = (
        db.session.query(Tag, func.count(Post.id).label("count"))
        .join(Post.tags)
        .filter(Post.is_published.is_(True))
        .group_by(Tag.id)
        .order_by(func.count(Post.id).desc())
        .all()
    )
    return render_template("tags_cloud.html", tags_with_counts=tags_with_counts)


@bp.get("/api/tags/check")
def check_tag():
    """Проверка существования тега."""
    tag_name = request.args.get("name", "").strip()
    if not tag_name:
        return jsonify({"exists": False})
    slug = slugify_tag(tag_name)
    if not slug:
        return jsonify({"exists": False})
    tag = Tag.query.filter_by(slug=slug).first()
    return jsonify({"exists": tag is not None, "tag": {"name": tag.name, "slug": tag.slug} if tag else None})


@bp.get("/api/tags/suggestions")
def tag_suggestions():
    """Получить предложения тегов на основе ввода."""
    query = request.args.get("q", "").strip().lower()
    if not query or len(query) < 2:
        return jsonify({"suggestions": []})
    
    tags = Tag.query.filter(Tag.name.ilike(f"%{query}%")).limit(10).all()
    return jsonify({"suggestions": [{"name": t.name, "slug": t.slug} for t in tags]})

@bp.get("/api/tags/recommendations")
@login_required
def tag_recommendations():
    """Получить рекомендации тегов на основе предпочтений пользователя."""
    # Получаем топ-10 предпочитаемых тегов пользователя
    preferences = (
        UserTagPreference.query
        .filter_by(user_id=current_user.id)
        .order_by(UserTagPreference.score.desc())
        .limit(10)
        .all()
    )
    
    recommendations = []
    for pref in preferences:
        tag = Tag.query.get(pref.tag_id)
        if tag:
            recommendations.append({"name": tag.name, "slug": tag.slug, "score": pref.score})
    
    # Если мало предпочтений, добавляем популярные теги
    if len(recommendations) < 5:
        popular_tags = (
            db.session.query(Tag, func.count(Post.id).label('post_count'))
            .join(Post.tags)
            .filter(Post.is_published.is_(True))
            .group_by(Tag.id)
            .order_by(func.count(Post.id).desc())
            .limit(5)
            .all()
        )
        existing_slugs = {r["slug"] for r in recommendations}
        for tag, count in popular_tags:
            if tag.slug not in existing_slugs:
                recommendations.append({"name": tag.name, "slug": tag.slug, "score": 0.5})
    
    return jsonify({"recommendations": recommendations[:10]})


@bp.post("/api/post/<int:post_id>/view")
@login_required
def track_post_view(post_id: int):
    """Отслеживание прогресса просмотра поста."""
    post = Post.query.get_or_404(post_id)
    
    # Обрабатываем как JSON, так и sendBeacon (Blob)
    if request.is_json:
        data = request.json
    else:
        try:
            data = request.get_json(force=True)
        except:
            data = {}
    
    progress = float(data.get("progress", 0.0))
    is_complete = bool(data.get("is_complete", False))
    view_duration = float(data.get("view_duration", 0.0))  # Время просмотра в секундах
    
    view = PostView.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    
    if not view:
        view = PostView(
            post_id=post_id, 
            user_id=current_user.id, 
            progress=progress, 
            is_complete=is_complete,
            view_duration=view_duration
        )
        db.session.add(view)
    else:
        view.progress = max(view.progress, progress)  # Сохраняем максимальный прогресс
        view.is_complete = is_complete or view.is_complete
        view.view_duration = max(view.view_duration, view_duration)  # Сохраняем максимальное время
        view.viewed_at = datetime.now(timezone.utc)
    
    db.session.commit()
    return jsonify({"success": True, "progress": view.progress, "is_complete": view.is_complete})
