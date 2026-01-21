import os

from .extensions import db
from .models import Achievement, Category, Post, QuizQuestion, User


def ensure_seed_data() -> None:
    # Categories
    base_categories = [
        ("memes", "Мемы"),
        ("movies", "Кино"),
        ("games", "Игры"),
        ("music", "Музыка"),
        ("humor", "Юмор"),
        ("tech", "Техно‑фан"),
    ]
    for slug, title in base_categories:
        if not Category.query.filter_by(slug=slug).first():
            db.session.add(Category(slug=slug, title=title))
    db.session.commit()

    # Admin by email (optional)
    admin_email = os.getenv("ADMIN_EMAIL")
    if admin_email:
        u = User.query.filter_by(email=admin_email).first()
        if u and not u.is_admin:
            u.is_admin = True
            db.session.commit()

    # Force user with nickname "tw1xty" to be admin, если уже существует
    tw = User.query.filter_by(username="tw1xty").first()
    if tw and not tw.is_admin:
        tw.is_admin = True
        db.session.commit()

    # Starter content (only if no posts exist)
    if Post.query.count() > 0:
        # Still ensure achievements & quiz exist
        _ensure_gamification()
        return

    system_user = User.query.filter_by(email="system@portal.local").first()
    if not system_user:
        system_user = User(username="system", email="system@portal.local", is_admin=True)
        # Not advertised; can be changed or removed later.
        system_user.set_password("change-me")
        db.session.add(system_user)
        db.session.commit()

    cats = {c.slug: c for c in Category.query.all()}

    starter_posts = [
        {
            "title": "Топ‑7 фильмов на вечер, когда хочется просто кайфануть",
            "summary": "Лёгкая подборка без спойлеров — от приключений до комедии.",
            "cover_emoji": "🎬",
            "body": (
                "1) Лёгкая комедия\n"
                "2) Приключение\n"
                "3) Фантастика\n\n"
                "Идея портала: сохраняй подборки, комментируй и добавляй свои посты!"
            ),
            "categories": ["movies", "humor"],
        },
        {
            "title": "Игры, которые запускаются на любом ноуте и затягивают",
            "summary": "Подборка для слабых ПК: быстро стартанул — и уже вечер прошёл.",
            "cover_emoji": "🎮",
            "body": (
                "Здесь могут быть ваши любимые инди‑игры. Добавляйте посты и делитесь находками.\n\n"
                "Совет: делайте короткий анонс и добавляйте категории — так посты проще искать."
            ),
            "categories": ["games"],
        },
        {
            "title": "Мем дня: когда открыл вкладку «поработать»",
            "summary": "…и случайно улетел в рекомендации на 40 минут.",
            "cover_emoji": "🤣",
            "body": "Ситуация знакома каждому. В комментариях — ваши версии мемов и истории!",
            "categories": ["memes", "humor"],
        },
        {
            "title": "Плейлист для фона: учёба, код, уборка — всё подойдёт",
            "summary": "Несколько жанров, чтобы не отвлекаться и держать темп.",
            "cover_emoji": "🎧",
            "body": "Соберите свой плейлист и прикрепите трек‑лист в посте. Мы тут за хороший вайб.",
            "categories": ["music"],
        },
    ]

    for p in starter_posts:
        post = Post(
            title=p["title"],
            summary=p["summary"],
            cover_emoji=p["cover_emoji"],
            body=p["body"],
            author_id=system_user.id,
            is_published=True,
        )
        post.categories = [cats[s] for s in p["categories"] if s in cats]
        db.session.add(post)

    db.session.commit()

    _ensure_gamification()


def _ensure_gamification() -> None:
    achievements = [
        ("first_post", "Первый пост", "Опубликовал свой первый пост", "✍️"),
        ("first_comment", "Первый комментарий", "Оставил первый комментарий", "💬"),
        ("first_like", "Первый лайк", "Поставил первый лайк", "❤️"),
        ("quiz_rookie", "Квиз-новичок", "Прошёл квиз хотя бы раз", "🧠"),
        ("quiz_ace", "Квиз-ас", "Набрал максимум в квизе", "🏅"),
    ]
    for code, title, desc, icon in achievements:
        if not Achievement.query.filter_by(code=code).first():
            db.session.add(Achievement(code=code, title=title, description=desc, icon=icon))
    db.session.commit()

    if QuizQuestion.query.count() > 0:
        return

    questions = [
        {
            "topic": "movies",
            "prompt": "Какой жанр чаще всего ассоциируется с 'роуд-муви'?",
            "a": "Путешествие/приключения",
            "b": "Хоррор",
            "c": "Судебная драма",
            "d": "Документальный спорт",
            "correct": "A",
        },
        {
            "topic": "games",
            "prompt": "Что чаще всего означает 'RNG' в играх?",
            "a": "Сетевая задержка",
            "b": "Случайность/рандом",
            "c": "Новый игровой движок",
            "d": "Уровень графики",
            "correct": "B",
        },
        {
            "topic": "music",
            "prompt": "Что такое BPM в музыке?",
            "a": "Биты в минуту",
            "b": "Бас в миксе",
            "c": "Тип синтезатора",
            "d": "Формат файла",
            "correct": "A",
        },
        {
            "topic": "memes",
            "prompt": "Классический формат мема 'два кадра' обычно строится на…",
            "a": "Сравнении ожидание/реальность",
            "b": "Случайных словах",
            "c": "Сложной формуле",
            "d": "Одной длинной цитате",
            "correct": "A",
        },
        {
            "topic": "tech",
            "prompt": "Что обычно означает 'UI'?",
            "a": "Универсальный интернет",
            "b": "Пользовательский интерфейс",
            "c": "Внутренний апдейт",
            "d": "Уровень интеграции",
            "correct": "B",
        },
        {
            "topic": "humor",
            "prompt": "Панчлайн — это…",
            "a": "Начало истории",
            "b": "Неожиданная концовка шутки",
            "c": "Любой вопрос",
            "d": "Список фактов",
            "correct": "B",
        },
    ]

    for q in questions:
        db.session.add(
            QuizQuestion(
                topic=q["topic"],
                prompt=q["prompt"],
                choice_a=q["a"],
                choice_b=q["b"],
                choice_c=q["c"],
                choice_d=q["d"],
                correct=q["correct"],
            )
        )
    db.session.commit()


