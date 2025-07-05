# run_worker.py
from app import app  # 导入 Flask app 以确保所有配置已加载
from celery_init import celery_app
# 这行代码是关键，它确保了在启动 worker 之前，
# Flask app 和 Celery 的绑定关系已经建立。
# 我们导入 app 变量但并不直接使用它，只是为了触发 app.py 中的配置代码。
# flake8: noqa (这行注释是告诉代码检查工具忽略“未使用的导入”警告)
if __name__ == '__main__':
    # 使用 solo 池以兼容 Windows
    # 使用 '-l info' 设置日志级别为 info
    # 我们在这里以编程方式构建命令行参数
    worker_argv = [
        'worker',
        '--loglevel=info',
        '--pool=solo',
    ]
    celery_app.worker_main(argv=worker_argv)