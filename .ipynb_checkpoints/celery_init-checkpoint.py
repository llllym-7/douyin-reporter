# celery_init.py

from celery import Celery

# 创建一个 Celery 实例。
# 我们不再在这里进行复杂的配置，而是让它从一个专门的配置文件中读取。
celery_app = Celery()