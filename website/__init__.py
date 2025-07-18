from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from os import path, remove
import time, datetime
from website.models_utils.init_models import init_database


DB_NAME = "database.db"
RESET_DB = True
INITA_DB_TABL_VALS = True


db = SQLAlchemy()

def create_app():

    app_flask = Flask(__name__)
    app_flask.config['SECRET_KEY'] = "si0fdmewmfic.k405964305c.fem[serWDO>$K#$%()]"
    app_flask.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'
    db.init_app(app_flask)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app_flask)

    from .views import views
    from .auth import auth
    from .app import app

    # How to access(starting Directory) views & auth files (Web pages)
    app_flask.register_blueprint(views, url_prefix='/')
    app_flask.register_blueprint(auth, url_prefix='/')
    app_flask.register_blueprint(app, url_prefix='/')

    create_database(app_flask)

    from .models import User #, Note
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    return app_flask




# def init_database(db):
#     from website.models_utils.init_models import init_User_table, init_Trainer_table
#     init_User_table(db)
#     init_Trainer_table(db)
#     init_ScheduleTrainning_table(db)

def create_database(app):
    with app.app_context():
        if RESET_DB:
            db.drop_all()
        db.create_all()
        if INITA_DB_TABL_VALS:
            init_database(db)
        





    