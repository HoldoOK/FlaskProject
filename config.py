import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'my-super-secret-key-change-it'

    if os.environ.get('REPL_ID'):
        SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/shop.db'
        UPLOAD_FOLDER = '/tmp/uploads'
    else:
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                                  'sqlite:///' + os.path.join(basedir, 'shop.db')
        UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAX_CONTENT_LENGTH = 128 * 1024 * 1024
    MAX_SINGLE_FILE_SIZE = 10 * 1024 * 1024

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
