from functools import wraps
from flask import request, jsonify, Blueprint
from flask_restful import Api, Resource
from models import db, Order, OrderItem, User
from datetime import timedelta


def to_moscow(dt):
    if dt is None:
        return None
    return (dt + timedelta(hours=3)).isoformat()


api_bp = Blueprint('api', __name__, url_prefix='/api/v1')
api = Api(api_bp)

API_TOKENS = {}


def generate_token(user):
    import uuid
    token = uuid.uuid4().hex
    API_TOKENS[token] = user.id
    return token


def get_current_api_user():
    auth_header = request.headers.get('Authorization', '')

    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    elif auth_header.startswith('Token '):
        token = auth_header[6:]
    else:
        token = auth_header

    user_id = API_TOKENS.get(token)
    if user_id:
        return User.query.get(user_id)
    return None


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_api_user()
        if not user:
            return {'error': 'Требуется аутентификация',
                    'message': 'Передайте токен в заголовке Authorization: Bearer <token>'}, 401
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


def serialize_order_item(item):
    return {
        'id': item.id,
        'product_id': item.product_id,
        'product_name': item.product.name if item.product else None,
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
        'created_at': to_moscow(order.created_at),
        'updated_at': to_moscow(order.updated_at),
    }

    if detailed:
        data['address'] = order.address
        data['phone'] = order.phone
        data['comment'] = order.comment
        data['items'] = [serialize_order_item(item) for item in order.items]
        data['items_count'] = len(data['items'])

    return data



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
                return {
                    'error': f'Недопустимый статус. Допустимые: {", ".join(valid_statuses)}'
                }, 400
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
            return {
                'error': f'Недопустимый статус. Допустимые: {", ".join(valid_statuses)}'
            }, 400

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
        total_revenue = db.session.query(func.sum(Order.total)).filter(
            Order.status != 'cancelled'
        ).scalar() or 0

        status_counts = {}
        for status, label in Order.STATUS_LABELS.items():
            count = Order.query.filter_by(status=status).count()
            status_counts[status] = {
                'label': label,
                'count': count
            }

        return {
            'stats': {
                'total_orders': total_orders,
                'total_revenue': round(total_revenue, 2),
                'by_status': status_counts
            }
        }, 200


api.add_resource(AuthTokenResource, '/auth/token')
api.add_resource(OrderListResource, '/orders')
api.add_resource(OrderDetailResource, '/orders/<int:order_id>')
api.add_resource(OrderStatsResource, '/orders/stats')
