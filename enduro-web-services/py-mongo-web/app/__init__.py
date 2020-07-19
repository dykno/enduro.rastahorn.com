from celery import Celery
from flask import Flask
import os
import logging
from os import environ as env
import sys

#REFERENCE: https://github.com/nickjj/build-a-saas-app-with-flask/blob/master/snakeeyes/app.py
CELERY_TASK_LIST = ['app.web.tasks']

def create_celery_app(app=None):
    app = flask_app

    celery = Celery(app.import_name, broker=app.config['CELERY_BROKER_URL'], include=CELERY_TASK_LIST)
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    return celery

with open(env['APP_SECRET'], 'r') as secret:
    app_secret = secret.read().strip()

flask_app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'web', 'templates'), static_folder=os.path.join(os.path.dirname(__file__), 'web', 'static'))
flask_app.config['CELERY_BROKER_URL'] = 'redis://celery-redis:6379/0'
#app.config['CELERY_RESULT_BACKEND'] = 'redis://celery-redis:6379/0'

flask_app.secret_key = app_secret

from .web import routes