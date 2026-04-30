from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, PasswordField, TextAreaField, FloatField,
                     IntegerField, SelectField, BooleanField, SubmitField)
from wtforms.validators import (DataRequired, Email, EqualTo, Length,
                                 NumberRange, ValidationError, Optional)
from models import User


class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[
        DataRequired(message='Это поле обязательно'),
        Length(min=3, max=80, message='От 3 до 80 символов')
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Это поле обязательно'),
        Email(message='Некорректный email')
    ])
    password = PasswordField('Пароль', validators=[
        DataRequired(message='Это поле обязательно'),
        Length(min=6, message='Минимум 6 символов')
    ])
    password2 = PasswordField('Повторите пароль', validators=[
        DataRequired(message='Это поле обязательно'),
        EqualTo('password', message='Пароли не совпадают')
    ])
    submit = SubmitField('Зарегистрироваться')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Это имя уже занято')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Этот email уже зарегистрирован')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[
        DataRequired(message='Это поле обязательно'),
        Email(message='Некорректный email')
    ])
    password = PasswordField('Пароль', validators=[
        DataRequired(message='Это поле обязательно')
    ])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')


class ProductForm(FlaskForm):
    name = StringField('Название товара', validators=[
        DataRequired(message='Это поле обязательно'),
        Length(max=200)
    ])
    description = TextAreaField('Описание', validators=[Optional()])
    price = FloatField('Цена', validators=[
        DataRequired(message='Это поле обязательно'),
        NumberRange(min=0.01, message='Цена должна быть положительной')
    ])
    old_price = FloatField('Старая цена (для скидки)', validators=[Optional()])
    stock = IntegerField('Количество на складе', validators=[
        DataRequired(message='Это поле обязательно'),
        NumberRange(min=0, message='Не может быть отрицательным')
    ])
    category_id = SelectField('Категория', coerce=int, validators=[Optional()])
    image = FileField('Изображение', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Только изображения!')
    ])
    is_active = BooleanField('Активный товар', default=True)
    submit = SubmitField('Сохранить')


class CategoryForm(FlaskForm):
    name = StringField('Название категории', validators=[
        DataRequired(message='Это поле обязательно'),
        Length(max=100)
    ])
    description = TextAreaField('Описание', validators=[Optional()])
    submit = SubmitField('Сохранить')


class CheckoutForm(FlaskForm):
    address = TextAreaField('Адрес доставки', validators=[
        DataRequired(message='Укажите адрес доставки')
    ])
    phone = StringField('Телефон', validators=[
        DataRequired(message='Укажите номер телефона'),
        Length(max=20)
    ])
    comment = TextAreaField('Комментарий к заказу', validators=[Optional()])
    submit = SubmitField('Оформить заказ')


class OrderStatusForm(FlaskForm):
    status = SelectField('Статус', choices=[
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтверждён'),
        ('shipped', 'Отправлен'),
        ('delivered', 'Доставлен'),
        ('cancelled', 'Отменён')
    ])
    submit = SubmitField('Обновить статус')