# app.py
from datetime import datetime, timedelta, timezone
import os
import uuid
from functools import wraps
from flask import (Flask, render_template, redirect, url_for, flash,
                   request, abort, current_app)
from flask_login import (LoginManager, login_user, logout_user,
                          login_required, current_user)
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from models import db, User, Product, Category, CartItem, Order, OrderItem
from forms import (RegistrationForm, LoginForm, ProductForm, CategoryForm,
                   CheckoutForm, OrderStatusForm)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config.from_object(Config)

db.init_app(app)
migrate = Migrate(app, db)
from api_routes import api_bp
app.register_blueprint(api_bp)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в аккаунт'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


MOSCOW_OFFSET = timezone(timedelta(hours=3))


@app.template_filter('moscow_time')
def moscow_time_filter(dt, fmt='%d.%m.%Y %H:%M'):
    """Конвертирует UTC время в московское (GMT+3)"""
    if dt is None:
        return ''
    return (dt + timedelta(hours=3)).strftime(fmt)

# ============ УТИЛИТЫ ============

def admin_required(f):
    """Декоратор для проверки прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def save_image(file):
    """Сохраняет загруженное изображение и возвращает имя файла"""
    # Проверяем, что file является объектом файла, а не строкой
    if not isinstance(file, FileStorage):
        return None

    if file and file.filename and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
        file.save(filepath)
        return filename
    return None


# ============ КОНТЕКСТ ============

@app.context_processor
def inject_cart_count():
    """Добавляет количество товаров в корзине во все шаблоны"""
    if current_user.is_authenticated:
        return {'cart_count': current_user.get_cart_count()}
    return {'cart_count': 0}


@app.context_processor
def inject_categories():
    """Добавляет категории во все шаблоны"""
    categories = Category.query.all()
    return {'all_categories': categories}


# ============ ОБРАБОТЧИКИ ОШИБОК ============

@app.errorhandler(404)
def not_found(error):
    return render_template('base.html', error_code=404, error_message='Страница не найдена'), 404


@app.errorhandler(403)
def forbidden(error):
    return render_template('base.html', error_code=403, error_message='Доступ запрещён'), 403


# ============ ГЛАВНАЯ СТРАНИЦА ============

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category', type=int)
    search = request.args.get('search', '', type=str)
    sort = request.args.get('sort', 'new', type=str)

    query = Product.query.filter_by(is_active=True)

    if category_id:
        query = query.filter_by(category_id=category_id)

    if search:
        query = query.filter(
            Product.name.ilike(f'%{search}%') |
            Product.description.ilike(f'%{search}%')
        )

    # Сортировка
    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort == 'name':
        query = query.order_by(Product.name.asc())
    else:  # new
        query = query.order_by(Product.created_at.desc())

    products = query.paginate(page=page, per_page=12, error_out=False)

    return render_template('index.html',
                           products=products,
                           search=search,
                           current_category=category_id,
                           current_sort=sort)


# ============ АУТЕНТИФИКАЦИЯ ============

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)

        # Первый пользователь становится администратором
        if User.query.count() == 0:
            user.is_admin = True

        db.session.add(user)
        db.session.commit()
        flash('Регистрация прошла успешно! Теперь войдите в аккаунт.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            flash(f'Добро пожаловать, {user.username}!', 'success')
            return redirect(next_page or url_for('index'))
        flash('Неверный email или пароль', 'danger')

    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из аккаунта', 'info')
    return redirect(url_for('index'))


# ============ ТОВАРЫ ============

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_active and (not current_user.is_authenticated or not current_user.is_admin):
        abort(404)
    return render_template('product.html', product=product)


# ============ КОРЗИНА ============

@app.route('/cart')
@login_required
def cart():
    items = current_user.cart.all()
    total = current_user.get_cart_total()
    return render_template('cart.html', items=items, total=total)


@app.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)

    if not product.is_in_stock:
        flash('Товар отсутствует на складе', 'warning')
        return redirect(url_for('product_detail', product_id=product_id))

    quantity = request.form.get('quantity', 1, type=int)
    if quantity < 1:
        quantity = 1

    cart_item = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product_id
    ).first()

    if cart_item:
        cart_item.quantity += quantity
        if cart_item.quantity > product.stock:
            cart_item.quantity = product.stock
            flash(f'В наличии только {product.stock} шт.', 'warning')
    else:
        cart_item = CartItem(
            user_id=current_user.id,
            product_id=product_id,
            quantity=min(quantity, product.stock)
        )
        db.session.add(cart_item)

    db.session.commit()
    flash(f'"{product.name}" добавлен в корзину', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    cart_item = CartItem.query.get_or_404(item_id)
    if cart_item.user_id != current_user.id:
        abort(403)

    quantity = request.form.get('quantity', 1, type=int)
    if quantity <= 0:
        db.session.delete(cart_item)
    else:
        cart_item.quantity = min(quantity, cart_item.product.stock)

    db.session.commit()
    return redirect(url_for('cart'))


@app.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    cart_item = CartItem.query.get_or_404(item_id)
    if cart_item.user_id != current_user.id:
        abort(403)

    db.session.delete(cart_item)
    db.session.commit()
    flash('Товар удалён из корзины', 'info')
    return redirect(url_for('cart'))


# ============ ОФОРМЛЕНИЕ ЗАКАЗА ============

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    items = current_user.cart.all()
    if not items:
        flash('Ваша корзина пуста', 'warning')
        return redirect(url_for('cart'))

    form = CheckoutForm()
    if form.validate_on_submit():
        total = current_user.get_cart_total()

        order = Order(
            user_id=current_user.id,
            total=total,
            address=form.address.data,
            phone=form.phone.data,
            comment=form.comment.data
        )
        db.session.add(order)

        for item in items:
            if item.product.stock < item.quantity:
                flash(f'Недостаточно товара "{item.product.name}" на складе', 'danger')
                return redirect(url_for('cart'))

            order_item = OrderItem(
                order=order,
                product_id=item.product_id,
                product_name=item.product.name,  # <-- сохраняем название
                quantity=item.quantity,
                price=item.product.price
            )
            db.session.add(order_item)
            item.product.stock -= item.quantity

        CartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()

        flash(f'Заказ #{order.id} успешно оформлен!', 'success')
        return redirect(url_for('order_detail', order_id=order.id))

    total = current_user.get_cart_total()
    return render_template('checkout.html', form=form, items=items, total=total)


# ============ ЗАКАЗЫ ПОЛЬЗОВАТЕЛЯ ============

@app.route('/orders')
@login_required
def my_orders():
    orders = current_user.orders.order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=orders)


@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    return render_template('order_detail.html', order=order)


# ============ АДМИН-ПАНЕЛЬ ============

@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    products_count = Product.query.count()
    users_count = User.query.count()
    orders_count = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()

    return render_template('admin_panel.html',
                           products_count=products_count,
                           users_count=users_count,
                           orders_count=orders_count,
                           pending_orders=pending_orders,
                           recent_orders=recent_orders)


# --- Управление товарами ---

@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    page = request.args.get('page', 1, type=int)
    products = Product.query.order_by(Product.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('admin_products.html', products=products)


@app.route('/admin/product/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    form = ProductForm()
    form.category_id.choices = [(0, '-- Без категории --')] + \
        [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]

    if form.validate_on_submit():
        product = Product(
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            old_price=form.old_price.data,
            stock=form.stock.data,
            category_id=form.category_id.data if form.category_id.data != 0 else None,
            is_active=form.is_active.data
        )

        if form.image.data:
            filename = save_image(form.image.data)
            if filename:
                product.image = filename

        db.session.add(product)
        db.session.commit()
        flash(f'Товар "{product.name}" успешно добавлен!', 'success')
        return redirect(url_for('admin_products'))

    return render_template('add_product.html', form=form, title='Добавить товар')


@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    form = ProductForm(obj=product)
    form.category_id.choices = [(0, '-- Без категории --')] + \
        [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]

    if form.validate_on_submit():
        product.name = form.name.data
        product.description = form.description.data
        product.price = form.price.data
        product.old_price = form.old_price.data
        product.stock = form.stock.data
        product.category_id = form.category_id.data if form.category_id.data != 0 else None
        product.is_active = form.is_active.data

        # Сохраняем новое изображение только если оно было загружено
        new_image = save_image(form.image.data)
        if new_image:  # None если файл не выбран — оставляем старое
            # Удаляем старое изображение
            if product.image and product.image != 'default.jpg':
                old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], product.image)
                if os.path.exists(old_path):
                    os.remove(old_path)
            product.image = new_image

        db.session.commit()
        flash(f'Товар "{product.name}" обновлён!', 'success')
        return redirect(url_for('admin_products'))

    # При GET-запросе устанавливаем текущую категорию
    if product.category_id:
        form.category_id.data = product.category_id
    else:
        form.category_id.data = 0

    return render_template('add_product.html', form=form,
                           title='Редактировать товар', product=product)

@app.route('/admin/product/delete/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)

    # Удаляем изображение
    if product.image and product.image != 'default.jpg':
        old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], product.image)
        if os.path.exists(old_path):
            os.remove(old_path)

    # Обнуляем product_id в существующих заказах (товар удалён, но история остаётся)
    OrderItem.query.filter_by(product_id=product_id).update({'product_id': None})

    db.session.delete(product)
    db.session.commit()
    flash(f'Товар "{product.name}" удалён', 'info')
    return redirect(url_for('admin_products'))


# --- Управление категориями ---

@app.route('/admin/categories')
@login_required
@admin_required
def admin_categories():
    categories = Category.query.order_by(Category.name).all()
    return render_template('admin_categories.html', categories=categories)


@app.route('/admin/category/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_category():
    form = CategoryForm()
    if form.validate_on_submit():
        category = Category(name=form.name.data, description=form.description.data)
        db.session.add(category)
        db.session.commit()
        flash(f'Категория "{category.name}" создана!', 'success')
        return redirect(url_for('admin_categories'))
    return render_template('add_category.html', form=form, title='Добавить категорию')


@app.route('/admin/category/delete/<int:category_id>', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    # Убираем категорию у товаров
    Product.query.filter_by(category_id=category_id).update({'category_id': None})
    db.session.delete(category)
    db.session.commit()
    flash(f'Категория "{category.name}" удалена', 'info')
    return redirect(url_for('admin_categories'))


# --- Управление заказами ---

@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')

    query = Order.query.order_by(Order.created_at.desc())
    if status:
        query = query.filter_by(status=status)

    orders = query.paginate(page=page, per_page=20, error_out=False)
    return render_template('admin_orders.html', orders=orders, current_status=status)


@app.route('/admin/order/<int:order_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    form = OrderStatusForm(obj=order)

    if form.validate_on_submit():
        order.status = form.status.data
        db.session.commit()
        flash(f'Статус заказа #{order.id} обновлён', 'success')
        return redirect(url_for('admin_orders'))

    return render_template('admin_order_detail.html', order=order, form=form)


# --- Управление пользователями ---

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)


@app.route('/admin/user/toggle-admin/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Нельзя снять права администратора с себя', 'danger')
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        action = 'назначен администратором' if user.is_admin else 'лишён прав администратора'
        flash(f'Пользователь {user.username} {action}', 'success')
    return redirect(url_for('admin_users'))


# ============ СОЗДАНИЕ БД И ЗАПУСК ============

def create_tables():
    """Создание таблиц и данных по умолчанию"""
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        print("База данных создана!")


if __name__ == '__main__':
    create_tables()
    app.run(
        host='0.0.0.0',  # важно — слушаем все интерфейсы
        port=8080,
        debug=False       # debug=False для публичного доступа
    )