# manage_users.py
import getpass
import sys
from app import app, db, User
from werkzeug.security import generate_password_hash

def main():
    with app.app_context():
        print("--- 用户管理工具 ---")
        print("1. 创建新用户")
        print("2. 列出所有用户")
        choice = input("请选择一个操作 (1/2): ")

        if choice == '1':
            create_user()
        elif choice == '2':
            list_users()
        else:
            print("无效的选择。")

def create_user():
    username = input("输入新用户名: ")
    if User.query.filter_by(username=username).first():
        print(f"错误: 用户 '{username}' 已存在。")
        return

    password = getpass.getpass("输入密码: ")
    password2 = getpass.getpass("再次确认密码: ")
    if password != password2:
        print("错误: 两次输入的密码不一致。")
        return

    role = input("输入角色 ('admin' 或 'user'): ").lower()
    if role not in ['admin', 'user']:
        print("错误: 角色必须是 'admin' 或 'user'。")
        return

    new_user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role
    )
    db.session.add(new_user)
    db.session.commit()
    print(f"用户 '{username}' (角色: {role}) 创建成功！")

def list_users():
    users = User.query.all()
    if not users:
        print("数据库中没有用户。")
        return
    print("\n--- 用户列表 ---")
    for user in users:
        print(f"ID: {user.id}, 用户名: {user.username}, 角色: {user.role}")
    print("----------------")

if __name__ == '__main__':
    main()