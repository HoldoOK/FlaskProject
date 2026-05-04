from functools import wraps
from flask import request, Blueprint
from flask_restful import Api, Resource
from models import db, Order, OrderItem, User, Product, ProductImage, Category

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')
api = Api(api_bp)

API_TOKENS = {}


def generate_token(user):
    import uuid
    token = uuid.uuid4().hex
    API_TOKENS[token] = user.id
    return token


def get_current_api_user():
    token = request.headers.get('Auth', '').strip()

    if not token:
        return None

    user_id = API_TOKENS.get(token)
    if user_id:
        return User.query.get(user_id)
    return None


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_api_user()
        if not user:
            return {
                'error': 'Требуется аутентификация',
                'message': 'Передайте токен в заголовке Auth: <token>'
            }, 401
        return f(*args, **kwargs)

    return decorated


def api_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_api_user()
        if not user:
            return {'error': 'Требуется аутентификация'}, 401
        if not user.is_admin:
            return {'error': 'Доступ запрещён', 'message': 'Требуются права администратора'}, 403
        return f(*args, **kwargs)

    return decorated


def serialize_image(image, base_url=''):
    return {
        'id': image.id,
        'filename': image.filename,
        'url': f'/static/uploads/{image.filename}',
        'is_main': image.is_main,
        'sort_order': image.sort_order
    }


def serialize_product(product, detailed=False):
    data = {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'old_price': product.old_price,
        'discount_percent': product.discount_percent,
        'stock': product.stock,
        'in_stock': product.is_in_stock,
        'is_active': product.is_active,
        'main_image': f'/static/uploads/{product.main_image}',
        'category': {
            'id': product.category.id,
            'name': product.category.name
        } if product.category else None,
        'created_at': product.created_at.isoformat() if product.created_at else None
    }

    if detailed:
        data['description'] = product.description
        data['images'] = [serialize_image(img) for img in product.all_images]
        data['images_count'] = len(data['images'])
        data['updated_at'] = product.updated_at.isoformat() if product.updated_at else None

    return data


def serialize_order_item(item):
    return {
        'id': item.id,
        'product_id': item.product_id,
        'product_name': item.display_name,
        'quantity': item.quantity,
        'price': item.price,
        'subtotal': item.subtotal
    }


def serialize_order(order, detailed=False):
    data = {
        'id': order.id,
        'user_id': order.user_id,
        'customer': order.customer.username,
        'status': order.status,
        'status_label': order.status_label,
        'total': order.total,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'updated_at': order.updated_at.isoformat() if order.updated_at else None
    }

    if detailed:
        data['address'] = order.address
        data['phone'] = order.phone
        data['comment'] = order.comment
        data['items'] = [serialize_order_item(item) for item in order.items]
        data['items_count'] = len(data['items'])

    return data


# ============ AUTH ============

class AuthTokenResource(Resource):

    def post(self):
        data = request.get_json()

        if not data:
            return {'error': 'Тело запроса должно быть JSON'}, 400

        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return {'error': 'Поля email и password обязательны'}, 400

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            return {'error': 'Неверный email или пароль'}, 401

        token = generate_token(user)

        return {
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_admin': user.is_admin
            }
        }, 200


# ============ PRODUCTS ============

class ProductListResource(Resource):

    def get(self):
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)
        category_id = request.args.get('category', type=int)
        search = request.args.get('search', '', type=str)
        sort = request.args.get('sort', 'new', type=str)
        in_stock = request.args.get('in_stock', type=str)

        query = Product.query.filter_by(is_active=True)

        if category_id:
            category = Category.query.get(category_id)
            if not category:
                return {'error': f'Категория #{category_id} не найдена'}, 404
            query = query.filter_by(category_id=category_id)

        if search:
            query = query.filter(
                Product.name.ilike(f'%{search}%') |
                Product.description.ilike(f'%{search}%')
            )

        if in_stock == 'true':
            query = query.filter(Product.stock > 0)
        elif in_stock == 'false':
            query = query.filter(Product.stock == 0)

        valid_sorts = ['new', 'old', 'price_asc', 'price_desc', 'name', 'name_desc']
        if sort not in valid_sorts:
            return {'error': f'Недопустимая сортировка. Допустимые: {", ".join(valid_sorts)}'}, 400

        if sort == 'price_asc':
            query = query.order_by(Product.price.asc())
        elif sort == 'price_desc':
            query = query.order_by(Product.price.desc())
        elif sort == 'name':
            query = query.order_by(Product.name.asc())
        elif sort == 'name_desc':
            query = query.order_by(Product.name.desc())
        elif sort == 'old':
            query = query.order_by(Product.created_at.asc())
        else:  # new
            query = query.order_by(Product.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return {
            'products': [serialize_product(p) for p in pagination.items],
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev,
                'next_page': pagination.next_num if pagination.has_next else None,
                'prev_page': pagination.prev_num if pagination.has_prev else None
            }
        }, 200


class ProductDetailResource(Resource):

    def get(self, product_id):
        product = Product.query.get(product_id)

        if not product:
            return {'error': f'Товар #{product_id} не найден'}, 404

        if not product.is_active:
            # Проверяем — может быть это админ
            user = get_current_api_user()
            if not user or not user.is_admin:
                return {'error': f'Товар #{product_id} не найден'}, 404

        return {'product': serialize_product(product, detailed=True)}, 200


class CategoryListResource(Resource):

    def get(self):
        categories = Category.query.order_by(Category.name).all()

        return {
            'categories': [
                {
                    'id': c.id,
                    'name': c.name,
                    'description': c.description,
                    'products_count': c.products.filter_by(is_active=True).count()
                }
                for c in categories
            ]
        }, 200


# ============ ORDERS ============

class OrderListResource(Resource):

    @api_login_required
    def get(self):
        user = get_current_api_user()

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)
        status = request.args.get('status', type=str)
        sort = request.args.get('sort', 'desc', type=str)

        if user.is_admin:
            query = Order.query
        else:
            query = Order.query.filter_by(user_id=user.id)

        if status:
            valid_statuses = ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled']
            if status not in valid_statuses:
                return {'error': f'Недопустимый статус. Допустимые: {", ".join(valid_statuses)}'}, 400
            query = query.filter_by(status=status)

        if sort == 'asc':
            query = query.order_by(Order.created_at.asc())
        else:
            query = query.order_by(Order.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return {
            'orders': [serialize_order(order) for order in pagination.items],
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev,
                'next_page': pagination.next_num if pagination.has_next else None,
                'prev_page': pagination.prev_num if pagination.has_prev else None
            }
        }, 200


class OrderDetailResource(Resource):

    @api_login_required
    def get(self, order_id):
        user = get_current_api_user()
        order = Order.query.get(order_id)

        if not order:
            return {'error': f'Заказ #{order_id} не найден'}, 404

        if not user.is_admin and order.user_id != user.id:
            return {'error': 'Доступ запрещён'}, 403

        return {'order': serialize_order(order, detailed=True)}, 200

    @api_admin_required
    def patch(self, order_id):
        order = Order.query.get(order_id)

        if not order:
            return {'error': f'Заказ #{order_id} не найден'}, 404

        data = request.get_json()
        if not data:
            return {'error': 'Тело запроса должно быть JSON'}, 400

        new_status = data.get('status')
        valid_statuses = ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled']

        if not new_status:
            return {'error': 'Поле status обязательно'}, 400

        if new_status not in valid_statuses:
            return {'error': f'Недопустимый статус. Допустимые: {", ".join(valid_statuses)}'}, 400

        old_status = order.status
        order.status = new_status
        db.session.commit()

        return {
            'message': f'Статус заказа #{order.id} изменён: {old_status} → {new_status}',
            'order': serialize_order(order, detailed=True)
        }, 200


class OrderStatsResource(Resource):

    @api_admin_required
    def get(self):
        from sqlalchemy import func

        total_orders = Order.query.count()
        total_revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
            Order.status != 'cancelled'
        ).scalar() or 0

        status_counts = {}
        for status, label in Order.STATUS_LABELS.items():
            count = Order.query.filter_by(status=status).count()
            status_counts[status] = {'label': label, 'count': count}

        return {
            'stats': {
                'total_orders': total_orders,
                'total_revenue': round(total_revenue, 2),
                'by_status': status_counts
            }
        }, 200


api.add_resource(AuthTokenResource, '/auth/token')

api.add_resource(ProductListResource, '/products')
api.add_resource(ProductDetailResource, '/products/<int:product_id>')
api.add_resource(CategoryListResource, '/categories')

api.add_resource(OrderListResource, '/orders')
api.add_resource(OrderDetailResource, '/orders/<int:order_id>')
api.add_resource(OrderStatsResource, '/orders/stats')
