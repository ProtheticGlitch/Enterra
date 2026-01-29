from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, FieldList, FormField, PasswordField, SelectMultipleField, StringField, TextAreaField
from wtforms.validators import Email, Length, DataRequired, EqualTo, Optional, URL


class RegisterForm(FlaskForm):
    username = StringField("Никнейм", validators=[DataRequired(), Length(min=3, max=32)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(min=6, max=128)])
    password2 = PasswordField("Повтор пароля", validators=[DataRequired(), EqualTo("password")])


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Пароль", validators=[DataRequired()])


class TrackForm(FlaskForm):
    title = StringField("Название трека", validators=[DataRequired(), Length(max=200)])
    artist = StringField("Артист", validators=[DataRequired(), Length(max=200)])
    url = StringField("Ссылка (Spotify, YouTube и т.д.)", validators=[Optional(), URL(), Length(max=500)])


class PostForm(FlaskForm):
    title = StringField("Заголовок", validators=[DataRequired(), Length(min=3, max=140)])
    summary = StringField("Коротко (анонс)", validators=[Length(max=240)])
    cover_emoji = StringField("Обложка (эмодзи)", validators=[Length(max=8)])
    tags = StringField("Теги (через запятую)", validators=[Optional(), Length(max=200)])
    body = TextAreaField("Текст", validators=[DataRequired(), Length(min=20)])
    is_published = BooleanField("Опубликовать", default=True)
    media = FileField(
        "Медиа (фото/видео)",
        validators=[
            FileAllowed(
                ["jpg", "jpeg", "png", "gif", "webp", "mp4", "webm", "mov"],
                "Только изображения (jpg, png, webp, gif) или видео (mp4, webm, mov).",
            )
        ],
    )


class CommentForm(FlaskForm):
    body = TextAreaField("Комментарий", validators=[DataRequired(), Length(min=1, max=1000)])


class SearchForm(FlaskForm):
    q = StringField("Поиск", validators=[DataRequired(), Length(min=1, max=80)])


class CategoryForm(FlaskForm):
    title = StringField("Название", validators=[DataRequired(), Length(min=2, max=64)])
    slug = StringField("Slug", validators=[DataRequired(), Length(min=2, max=64)])


class ProfileEditForm(FlaskForm):
    bio = TextAreaField("О себе", validators=[Optional(), Length(max=500)])
    is_private = BooleanField("Приватный профиль", default=False)
    theme_preference = StringField("Тема", validators=[Optional(), Length(max=16)])
    avatar = FileField(
        "Аватар",
        validators=[
            FileAllowed(
                ["jpg", "jpeg", "png", "gif", "webp"],
                "Только изображения (jpg, png, webp, gif).",
            )
        ],
    )

