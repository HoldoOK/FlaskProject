import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    if os.environ.get('VERCEL'):
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
            'sqlite:////tmp/shop.db'
        UPLOAD_FOLDER = '/tmp/uploads'
    else:
        db_url = os.environ.get('DATABASE_URL') or \
            'sqlite:///' + os.path.join(basedir, 'shop.db')
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        SQLALCHEMY_DATABASE_URI = db_url
        UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 128 * 1024 * 1024
    MAX_SINGLE_FILE_SIZE = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    WTF_CSRF_SSL_STRICT = False
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = 'Lax'