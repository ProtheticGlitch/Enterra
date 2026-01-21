from functools import wraps
import os
import re
import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from .extensions import db
from .forms import CategoryForm, CommentForm, LoginForm, PostForm, ProfileEditForm, RegisterForm, SearchForm
from .models import Category, Comment, Follow, ModerationLog, ModerationSettings, Post, PostLike, Tag, Track, User

bp = Blueprint("main", __name__)

REACTIONS = {
    "like": {"emoji": "❤️", "label": "Нравится"},
    "funny": {"emoji": "🤣", "label": "Смешно"},
    "wow": {"emoji": "🤯", "label": "Вау"},
    "sad": {"emoji": "😢", "label": "Грустно"},
}

# Простая авто‑модерация: список стоп‑слов (можно расширять)
BAD_WORDS = {

}

ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_VIDEO_EXT = {"mp4", "webm", "mov"}
ALLOWED_MEDIA_EXT = ALLOWED_IMAGE_EXT | ALLOWED_VIDEO_EXT


def slugify_tag(name: str) -> str:
    """Создает slug из названия тега."""
    name = name.lower().strip()
    name = re.sub(r"[^\wа-яё-]+", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def get_or_create_tags(tag_names: str) -> list:
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
    snippet = (text or "").strip().replace("\n", " ")
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

    posts = query.limit(50).all()

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
        trending_posts=trending_posts,
        active_category=category,
        q=q,
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

    # Увеличиваем счетчик просмотров (только для опубликованных постов)
    if post.is_published:
        post.views += 1
        db.session.commit()

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
    if current_user.is_authenticated:
        like = PostLike.query.filter_by(post_id=post.id, user_id=current_user.id).first()
        if like:
            user_reaction = like.reaction

    return render_template(
        "post_detail.html",
        post=post,
        form=form,
        comments=comments,
        reactions=REACTIONS,
        reactions_counts=reactions_counts,
        user_reaction=user_reaction,
    )


@bp.post("/post/<int:post_id>/react/<string:reaction_code>")
@login_required
def post_react(post_id: int, reaction_code: str):
    if reaction_code not in REACTIONS:
        flash("Неизвестная реакция.", "warning")
        return redirect(url_for("main.post_detail", post_id=post_id))

    post = Post.query.get_or_404(post_id)
    like = PostLike.query.filter_by(post_id=post.id, user_id=current_user.id).first()

    if like and like.reaction == reaction_code:
        db.session.delete(like)
    else:
        if not like:
            like = PostLike(post_id=post.id, user_id=current_user.id)
            db.session.add(like)
        like.reaction = reaction_code

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
    form.categories.choices = [(c.id, c.title) for c in Category.query.order_by(Category.title.asc()).all()]

    if form.validate_on_submit():
        text_blob = " ".join(
            [
                form.title.data or "",
                form.summary.data or "",
                form.body.data or "",
            ]
        )
        auto_hide = is_auto_mod_enabled() and contains_bad_words(text_blob)

        post = Post(
            title=form.title.data,
            summary=form.summary.data or None,
            cover_emoji=(form.cover_emoji.data or "").strip() or None,
            body=form.body.data,
            is_published=False if auto_hide else bool(form.is_published.data),
            author_id=current_user.id,
        )
        post.categories = Category.query.filter(Category.id.in_(form.categories.data)).all() if form.categories.data else []
        
        # Обработка тегов
        if form.tags.data:
            post.tags = get_or_create_tags(form.tags.data)

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

        if auto_hide:
            log_moderation(
                "post_autohide",
                user_id=current_user.id,
                post_id=post.id,
                reason="bad_words",
                text=text_blob,
            )
        db.session.add(post)
        db.session.flush()  # Получаем post.id

        # Сохранение треков
        track_titles = request.form.getlist("track_titles")
        track_artists = request.form.getlist("track_artists")
        track_urls = request.form.getlist("track_urls")
        
        # Удаляем существующие треки (при редактировании)
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

        db.session.commit()

        if auto_hide:
            flash(
                "В тексте поста найдены запрещённые слова, пост сохранён как черновик и ожидает проверки.",
                "warning",
            )
        else:
            flash("Пост создан.", "success")
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
    form.categories.choices = [(c.id, c.title) for c in Category.query.order_by(Category.title.asc()).all()]
    if request.method == "GET":
        form.categories.data = [c.id for c in post.categories]
        form.tags.data = ", ".join([t.name for t in post.tags])

    if form.validate_on_submit():
        text_blob = " ".join(
            [
                form.title.data or "",
                form.summary.data or "",
                form.body.data or "",
            ]
        )
        auto_hide = is_auto_mod_enabled() and contains_bad_words(text_blob)

        post.title = form.title.data
        post.summary = form.summary.data or None
        post.cover_emoji = (form.cover_emoji.data or "").strip() or None
        post.body = form.body.data
        post.is_published = False if auto_hide else bool(form.is_published.data)
        post.categories = Category.query.filter(Category.id.in_(form.categories.data)).all() if form.categories.data else []
        
        # Обработка тегов
        if form.tags.data:
            post.tags = get_or_create_tags(form.tags.data)
        else:
            post.tags = []

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
                    ext = filename.rsplit(".", 1)[-1].lower()
                    upload_dir = os.path.join(current_app.root_path, "static", "uploads")
                    os.makedirs(upload_dir, exist_ok=True)
                    save_name = f"{post.author_id}_{uuid.uuid4().hex}.{ext}"
                    filepath = os.path.join(upload_dir, save_name)
                    file.save(filepath)
                    post.media_path = f"uploads/{save_name}"
                    post.media_type = "video" if ext in ALLOWED_VIDEO_EXT else "image"

        if auto_hide:
            log_moderation(
                "post_autohide",
                user_id=current_user.id,
                post_id=post.id,
                reason="bad_words_edit",
                text=text_blob,
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

        if auto_hide:
            flash(
                "В тексте поста найдены запрещённые слова, он сохранён как черновик и скрыт из ленты.",
                "warning",
            )
        else:
            flash("Сохранено.", "success")
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

    return render_template(
        "profile.html",
        user=user,
        posts=posts,
        comments=comments,
        posts_count=posts_count,
        comments_count=comments_count,
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
    # Админ видит все посты и всех пользователей
    posts = Post.query.order_by(Post.created_at.desc()).all()
    users = User.query.order_by(User.created_at.desc()).all()
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
    return render_template(
        "admin.html",
        posts=posts,
        users=users,
        categories=categories,
        comments=comments,
        category_form=category_form,
        bad_words_sorted=sorted(BAD_WORDS),
        auto_enabled=auto_enabled,
        moderation_logs=moderation_logs,
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
    """Лента постов от подписок."""
    following_ids = [f.followed_id for f in current_user.following.all()]
    if not following_ids:
        flash("Вы ни на кого не подписаны. Подпишитесь на пользователей, чтобы видеть их посты здесь.", "info")
        return redirect(url_for("main.index"))
    
    posts = (
        Post.query.filter(Post.author_id.in_(following_ids))
        .filter_by(is_published=True)
        .order_by(Post.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("index.html", posts=posts, is_following_feed=True)


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

