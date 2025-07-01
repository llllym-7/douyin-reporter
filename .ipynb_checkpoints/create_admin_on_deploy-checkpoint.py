# create_admin_on_deploy.py
import os
from app import app, db, User
from werkzeug.security import generate_password_hash

def create_initial_admin():
    """
    在 Flask 应用上下文中，非交互式地创建或更新一个管理员用户。
    这个脚本设计用于在 Render 的预部署命令中运行。
    """
    with app.app_context():
        # --- 【重要】在这里设置你的管理员账户信息 ---
        # 你可以随时修改这里的用户名和密码，然后重新部署来更新账户
        ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
        ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'default_password_123')
        # -----------------------------------------

        # 检查数据库表是否存在，如果不存在则创建
        # 这对于首次部署非常重要
        try:
            # 尝试一个简单的查询来检查连接和表结构
            User.query.first()
        except Exception:
            print("数据库或 User 表不存在，正在创建所有表...")
            db.create_all()
            print("数据库表创建完毕。")

        # 查找管理员用户是否已存在
        admin_user = User.query.filter_by(username=ADMIN_USERNAME).first()

        if not admin_user:
            # 如果不存在，则创建新用户
            print(f"管理员用户 '{ADMIN_USERNAME}' 不存在，正在创建...")
            new_admin = User(
                username=ADMIN_USERNAME,
                password_hash=generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256'),
                role='admin'
            )
            db.session.add(new_admin)
            print(f"管理员 '{ADMIN_USERNAME}' 创建成功。")
        else:
            # 如果已存在，可以选择更新密码或直接跳过
            print(f"管理员用户 '{ADMIN_USERNAME}' 已存在，跳过创建。")
            # 如果你想每次部署都更新密码，可以取消下面这几行的注释
            # print(f"正在为管理员 '{ADMIN_USERNAME}' 更新密码...")
            # admin_user.password_hash = generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256')
            # print("密码更新成功。")
        
        # 提交更改到数据库
        db.session.commit()

if __name__ == '__main__':
    print("开始执行初始管理员创建/检查任务...")
    create_initial_admin()
    print("任务执行完毕。")