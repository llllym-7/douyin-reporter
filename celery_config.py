# celery_config.py

import os

# 明确指定 Broker 和 Backend 为 Redis
broker_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
result_backend = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Celery 会自动发现并导入这个文件里名为 'tasks' 的模块中的任务
imports = ('tasks',)

# 结果设置
task_ignore_result = True

# 【修复】这里原本可能有一个错误的 'execution_count': null
# 我们直接把它删掉，或者如果你需要一个空值，应该用 None。
# 为保持配置文件干净，我们直接删除这行多余的代码。