import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from calendar import monthrange
from functools import wraps
from flask import (Flask, render_template, redirect, url_for, flash,
                   request, abort, current_app, jsonify)
from flask_login import (LoginManager, login_user, logout_user,
                          login_required, current_user)
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import func, extract

from config import Config
from models import db, User, Product, ProductImage, Category, CartItem, Order, OrderItem
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

MOSCOW_OFFSET = timezone(timedelta(hours=3))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.template_filter('moscow_time')
def moscow_time_filter(dt, fmt='%d.%m.%Y %H:%M'):
    if dt is None:
        return ''
    return (dt + timedelta(hours=3)).strftime(fmt)



def admin_required(f):
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


def save_multiple_images(files):
    """Сохраняет несколько файлов, возвращает список имён"""
    filenames = []
    for file in files:
        filename = save_image(file)
        if filename:
            filenames.append(filename)
    return filenames


def delete_image_file(filename):
    """Удаляет файл изображения с диска"""
    if filename and filename != 'default.jpg':
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)


def get_revenue_data():
    """Считает прибыль по месяцам за последний год"""
    now = datetime.utcnow()
    months = []
    revenue = []

    for i in range(11, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1

        month_revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
            extract('year', Order.created_at) == year,
            extract('month', Order.created_at) == month,
            Order.status != 'cancelled'
        ).scalar()

        month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                       'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
        months.append(f"{month_names[month - 1]} {year}")
        revenue.append(round(float(month_revenue), 2))

    return months, revenue


def get_daily_revenue_data():
    """Считает прибыль по дням за последний месяц"""
    now = datetime.utcnow()
    days = []
    revenue = []

    for i in range(29, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        day_revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
            Order.created_at >= day_start,
            Order.created_at < day_end,
            Order.status != 'cancelled'
        ).scalar()

        days.append(day.strftime('%d.%m'))
        revenue.append(round(float(day_revenue), 2))

    return days, revenue


def get_orders_count_data():
    """Количество заказов по месяцам"""
    now = datetime.utcnow()
    months = []
    counts = []

    for i in range(11, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1

        count = Order.query.filter(
            extract('year', Order.created_at) == year,
            extract('month', Order.created_at) == month
        ).count()

        month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                       'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
        months.append(f"{month_names[month - 1]} {year}")
        counts.append(count)

    return months, counts



@app.context_processor
def inject_cart_count():
    if current_user.is_authenticated:
        return {'cart_count': current_user.get_cart_count()}
    return {'cart_count': 0}


@app.context_processor
def inject_categories():
    categories = Category.query.all()
    return {'all_categories': categories}



@app.errorhandler(404)
def not_found(error):
    return render_template('base.html', error_code=404, error_message='Страница не найдена'), 404


@app.errorhandler(403)
def forbidden(error):
    return render_template('base.html', error_code=403, error_message='Доступ запрещён'), 403



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

    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort == 'name':
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.paginate(page=page, per_page=12, error_out=False)

    return render_template('index.html', products=products, search=search,
                           current_category=category_id, current_sort=sort)



@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        if User.query.count() == 0:
            user.is_admin = True
        db.session.add(user)
        db.session.commit()
        flash('Регистрация прошла успешно!', 'success')
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



@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_active and (not current_user.is_authenticated or not current_user.is_admin):
        abort(404)
    return render_template('product.html', product=product)



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

    cart_item = CartItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if cart_item:
        cart_item.quantity += quantity
        if cart_item.quantity > product.stock:
            cart_item.quantity = product.stock
            flash(f'В наличии только {product.stock} шт.', 'warning')
    else:
        cart_item = CartItem(user_id=current_user.id, product_id=product_id,
                             quantity=min(quantity, product.stock))
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
        order = Order(user_id=current_user.id, total=total,
                      address=form.address.data, phone=form.phone.data,
                      comment=form.comment.data)
        db.session.add(order)

        for item in items:
            if item.product.stock < item.quantity:
                flash(f'Недостаточно товара "{item.product.name}" на складе', 'danger')
                return redirect(url_for('cart'))

            order_item = OrderItem(order=order, product_id=item.product_id,
                                   product_name=item.product.name,
                                   quantity=item.quantity, price=item.product.price)
            db.session.add(order_item)
            item.product.stock -= item.quantity

        CartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        flash(f'Заказ #{order.id} успешно оформлен!', 'success')
        return redirect(url_for('order_detail', order_id=order.id))

    total = current_user.get_cart_total()
    return render_template('checkout.html', form=form, items=items, total=total)



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



@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    products_count = Product.query.count()
    users_count = User.query.count()
    orders_count = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()

    monthly_labels, monthly_revenue = get_revenue_data()
    daily_labels, daily_revenue = get_daily_revenue_data()
    orders_labels, orders_counts = get_orders_count_data()

    now = datetime.utcnow()

    current_month_revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        extract('year', Order.created_at) == now.year,
        extract('month', Order.created_at) == now.month,
        Order.status != 'cancelled'
    ).scalar()

    prev_month = now.month - 1 if now.month > 1 else 12
    prev_year = now.year if now.month > 1 else now.year - 1
    prev_month_revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        extract('year', Order.created_at) == prev_year,
        extract('month', Order.created_at) == prev_month,
        Order.status != 'cancelled'
    ).scalar()

    year_revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        extract('year', Order.created_at) == now.year,
        Order.status != 'cancelled'
    ).scalar()

    return render_template('admin_panel.html',
                           products_count=products_count,
                           users_count=users_count,
                           orders_count=orders_count,
                           pending_orders=pending_orders,
                           recent_orders=recent_orders,
                           monthly_labels=json.dumps(monthly_labels),
                           monthly_revenue=json.dumps(monthly_revenue),
                           daily_labels=json.dumps(daily_labels),
                           daily_revenue=json.dumps(daily_revenue),
                           orders_labels=json.dumps(orders_labels),
                           orders_counts=json.dumps(orders_counts),
                           current_month_revenue=round(float(current_month_revenue), 2),
                           prev_month_revenue=round(float(prev_month_revenue), 2),
                           year_revenue=round(float(year_revenue), 2))



@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    page = request.args.get('page', 1, type=int)
    products = Product.query.order_by(Product.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
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
        db.session.add(product)
        db.session.flush()

        files = request.files.getlist('images')
        filenames = save_multiple_images(files)

        for idx, filename in enumerate(filenames):
            img = ProductImage(
                product_id=product.id,
                filename=filename,
                is_main=(idx == 0),
                sort_order=idx
            )
            db.session.add(img)

        db.session.commit()
        flash(f'Товар "{product.name}" добавлен! Загружено фото: {len(filenames)}', 'success')
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

        files = request.files.getlist('images')
        filenames = save_multiple_images(files)

        existing_count = product.images.count()
        has_main = product.images.filter_by(is_main=True).first() is not None

        for idx, filename in enumerate(filenames):
            img = ProductImage(
                product_id=product.id,
                filename=filename,
                is_main=(not has_main and idx == 0),
                sort_order=existing_count + idx
            )
            db.session.add(img)

        db.session.commit()
        flash(f'Товар "{product.name}" обновлён!', 'success')
        return redirect(url_for('admin_products'))

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

    for img in product.images.all():
        delete_image_file(img.filename)

    OrderItem.query.filter_by(product_id=product_id).update({'product_id': None})

    db.session.delete(product)
    db.session.commit()
    flash(f'Товар "{product.name}" удалён', 'info')
    return redirect(url_for('admin_products'))



@app.route('/admin/product/image/delete/<int:image_id>', methods=['POST'])
@login_required
@admin_required
def delete_product_image(image_id):
    img = ProductImage.query.get_or_404(image_id)
    product_id = img.product_id
    was_main = img.is_main

    delete_image_file(img.filename)
    db.session.delete(img)

    if was_main:
        next_img = ProductImage.query.filter_by(product_id=product_id).first()
        if next_img:
            next_img.is_main = True

    db.session.commit()
    flash('Изображение удалено', 'info')
    return redirect(url_for('edit_product', product_id=product_id))



@app.route('/admin/product/image/set-main/<int:image_id>', methods=['POST'])
@login_required
@admin_required
def set_main_image(image_id):
    img = ProductImage.query.get_or_404(image_id)

    ProductImage.query.filter_by(product_id=img.product_id).update({'is_main': False})
    img.is_main = True

    db.session.commit()
    flash('Главное изображение обновлено', 'success')
    return redirect(url_for('edit_product', product_id=img.product_id))



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
    Product.query.filter_by(category_id=category_id).update({'category_id': None})
    db.session.delete(category)
    db.session.commit()
    flash(f'Категория "{category.name}" удалена', 'info')
    return redirect(url_for('admin_categories'))



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



def create_tables():
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        print("База данных создана!")


with app.app_context():
    db.create_all()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


if __name__ == '__main__':
    create_tables()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)