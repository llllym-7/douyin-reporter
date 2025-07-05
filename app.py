# app.py

import os
import json
import base64
import io
import re
import uuid
from datetime import datetime
from functools import wraps
from openai import OpenAI

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, inspect as sa_inspect
from PIL import Image

from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import generate_password_hash, check_password_hash

import boto3
from botocore.exceptions import NoCredentialsError

# 【修改】导入 celery_app 实例
from celery_init import celery_app
# 【修改】导入 celery_config 模块
import celery_config

from a_ocr_config import LLM_CONFIG, JSON_PROMPT, IMAGE_1_CONFIG, IMAGE_2_CONFIG, IMAGE_3_CONFIG, IMAGE_4_CONFIG, HISTORICAL_METRICS

# --- 调试开关 ---
DEBUG_MODE_SKIP_OCR = False

# --- App 初始化 ---
app = Flask(__name__)

# --- 【修改】Flask App 配置 ---
IS_PRODUCTION = os.environ.get('RENDER', False)
if IS_PRODUCTION:
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-should-be-set-in-env')
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if db_url and '?' not in db_url:
        db_url += '?sslmode=require'
    elif db_url:
        db_url += '&sslmode=require'
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    app.config['SECRET_KEY'] = '5e67649ca7508d280ac840f20dc2982a2ad0443a64420488'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///livestream_reporter_final.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- 【修改】Celery 配置 ---
# 从 celery_config.py 文件加载配置
celery_app.config_from_object(celery_config)

# 定义一个辅助函数，将 Flask 上下文绑定到 Celery 任务
class ContextTask(celery_app.Task):
    def __call__(self, *args, **kwargs):
        with app.app_context():
            return self.run(*args, **kwargs)
celery_app.Task = ContextTask


# --- 数据库和插件初始化 ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
# ... (文件的其余部分代码，从这里开始直到最后，都保持不变)
# ... (class User, class LiveData, load_user, a_ocr_config, routes, etc.)
# ...
# 【请将你原来 app.py 中从这里往下的所有代码都复制过来】
# ...
# --- 数据库模型 ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')

class LiveData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    live_date = db.Column(db.Date, nullable=False)
    live_start_time = db.Column(db.String(50), nullable=True) # 初始可为空
    status = db.Column(db.String(20), nullable=False, default='pending')
    error_message = db.Column(db.Text, nullable=True)
    gmv = db.Column(db.Float, default=0); gpm = db.Column(db.Float, default=0); order_count = db.Column(db.Integer, default=0); buyer_count = db.Column(db.Integer, default=0); click_to_order_ratio = db.Column(db.Float, default=0); view_to_order_ratio = db.Column(db.Float, default=0); expose_to_view_ratio = db.Column(db.Float, default=0); view_to_interact_ratio = db.Column(db.Float, default=0); avg_watch_time_seconds = db.Column(db.Integer, default=0); new_followers = db.Column(db.Integer, default=0); follower_order_ratio = db.Column(db.Float, default=0); avg_online_users = db.Column(db.Integer, default=0); vv = db.Column(db.Integer, default=0); chart_paths = db.Column(db.Text, default='{}')
    __table_args__ = (UniqueConstraint('live_date', 'live_start_time', name='_live_date_start_time_uc'),)

# --- Flask-Login & 表单 ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("此操作需要管理员权限。", "danger")
            return redirect(url_for('daily_review'))
        return f(*args, **kwargs)
    return decorated_function

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    submit = SubmitField('登录')

# --- 辅助函数 ---
try:
    client = OpenAI(api_key=LLM_CONFIG["API_KEY"], base_url=LLM_CONFIG["BASE_URL"])
except Exception as e:
    print(f"!!! 严重错误：初始化 OpenAI 客户端失败: {e}")
    client = None

def image_to_base64(image: Image.Image, format="PNG") -> str:
    buffered = io.BytesIO()
    if image.mode != 'RGB':
        image = image.convert('RGB')
    image.save(buffered, format=format.upper())
    mime_type = f"image/{format.lower()}"
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:{mime_type};base64,{img_str}"

def ocr_with_llm(image: Image.Image):
    if not client:
        raise ConnectionError("OpenAI 客户端未初始化")
    base64_image = image_to_base64(image)
    try:
        response = client.chat.completions.create(
            model=LLM_CONFIG["MODEL_NAME"],
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": JSON_PROMPT},
                    {"type": "image_url", "image_url": {"url": base64_image}}
                ]}
            ],
            max_tokens=2048,
            temperature=0.0
        )
        json_string = response.choices[0].message.content
        if json_string.strip().startswith("```json"):
            json_string = json_string.strip()[7:-3]
        return json.loads(json_string)
    except Exception as e:
        print(f"!!! LLM API 调用或JSON解析失败: {e}")
        return None

def process_single_image(image_stream, date_str, start_time_str, config):
    if not config: 
        return {}, {}
        
    ocr_data, cropped_chart_paths = {}, {}
    img = Image.open(image_stream)

    if 'chart_crops' in config:
        s3_client = None
        if IS_PRODUCTION:
            try:
                s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'), region_name=os.environ.get('AWS_REGION'))
                S3_BUCKET = os.environ.get('S3_BUCKET_NAME')
            except Exception as e: 
                print(f"!!! S3 客户端初始化失败: {e}")

        for key, crop_area in config['chart_crops'].items():
            if crop_area == (0, 0, 0, 0): 
                continue
            chart_img = img.crop(crop_area)
            safe_start_time = re.sub(r'[^a-zA-Z0-9_-]', '_', str(start_time_str))
            unique_id = uuid.uuid4().hex[:8]
            chart_filename = f"{date_str}_{safe_start_time}_{key}_{unique_id}.png"
            
            if IS_PRODUCTION and s3_client and S3_BUCKET:
                try:
                    in_mem_file = io.BytesIO()
                    chart_img.save(in_mem_file, format='PNG')
                    in_mem_file.seek(0)
                    s3_client.upload_fileobj(in_mem_file, S3_BUCKET, chart_filename, ExtraArgs={'ACL': 'public-read', 'ContentType': 'image/png'})
                    web_path = f"https://{S3_BUCKET}.s3.{os.environ.get('AWS_REGION')}.amazonaws.com/{chart_filename}"
                    cropped_chart_paths[key] = web_path
                except Exception as e: 
                    print(f"!!! 上传到 S3 失败: {e}")
            else:
                gen_folder = 'static/generated_charts/'
                os.makedirs(gen_folder, exist_ok=True)
                save_path = os.path.join(gen_folder, chart_filename)
                chart_img.save(save_path)
                web_path = os.path.join('generated_charts', chart_filename).replace('\\', '/')
                cropped_chart_paths[key] = web_path

    if not DEBUG_MODE_SKIP_OCR:
        MAX_WIDTH = 1920
        img_for_ocr = img.copy()
        if img_for_ocr.width > MAX_WIDTH:
            aspect_ratio = img_for_ocr.height / img_for_ocr.width
            new_height = int(MAX_WIDTH * aspect_ratio)
            print(f"Resizing image for OCR from {img_for_ocr.width}x{img_for_ocr.height} to {MAX_WIDTH}x{new_height}")
            img_for_ocr = img_for_ocr.resize((MAX_WIDTH, new_height), Image.LANCZOS)
        
        llm_result_dict = ocr_with_llm(img_for_ocr)
        if llm_result_dict:
            ocr_data.update({k: v for k, v in llm_result_dict.items() if v is not None})
            
    return ocr_data, cropped_chart_paths

# --- 路由 ---
@app.route('/upload', methods=['GET', 'POST'])
@login_required
@admin_required
def upload():
    from tasks import process_images_task

    if request.method == 'POST':
        live_date_str = request.form.get('live_date')
        if not live_date_str:
            flash('必须选择一个日期!', 'danger')
            return redirect(request.url)
        live_date = datetime.strptime(live_date_str, '%Y-%m-%d').date()

        files = request.files.getlist('images')
        if not files or files[0].filename == '':
            flash('必须上传至少一张图片!', 'danger')
            return redirect(request.url)
        
        if len(files) > 4:
            flash(f'提醒：您上传了 {len(files)} 张图片，系统将只处理前4张。', 'warning')
            files = files[:4]

        new_entry = LiveData(live_date=live_date, status='pending')
        db.session.add(new_entry)
        db.session.commit()

        image_files_as_bytes = [file.read() for file in files]
        
        process_images_task.delay(new_entry.id, image_files_as_bytes)
        
        flash(f'日期 {live_date_str} 的图片已上传，正在后台处理中。请稍后刷新“每日数据复盘”页面查看结果。', 'info')
        return redirect(url_for('daily_review'))

    return render_template('upload.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('登录失败，请检查用户名和密码。', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功退出登录。', 'info')
    return redirect(url_for('login'))

@app.route('/delete_data/<int:entry_id>', methods=['POST'])
@login_required
@admin_required
def delete_data(entry_id):
    entry = db.session.get(LiveData, entry_id)
    if not entry:
        flash('未找到要删除的数据条目。', 'danger')
        return redirect(url_for('daily_review'))
    
    date_str = entry.live_date.strftime('%Y-%m-%d')
    db.session.delete(entry)
    db.session.commit()
    flash(f'日期 {date_str} (开播于 {entry.live_start_time or "N/A"}) 的数据已成功清空。', 'success')
    return redirect(url_for('daily_review'))

@app.route('/')
@login_required
def index():
    return redirect(url_for('daily_review'))

# app.py

# ... (其他路由和代码) ...
# app.py

# ... (确保 @app.route('/') 下面就是这个函数) ...

@app.route('/daily_review')
@login_required
def daily_review():
    date_str = request.args.get('date')
    selected_identifier = request.args.get('start_time')

    if not date_str:
        latest_entry = LiveData.query.order_by(LiveData.live_date.desc(), LiveData.id.desc()).first()
        if latest_entry:
            identifier = latest_entry.live_start_time if latest_entry.status == 'completed' else latest_entry.id
            return redirect(url_for('daily_review', date=latest_entry.live_date.strftime('%Y-%m-%d'), start_time=identifier))
        else:
             # 如果数据库为空，显示今天的日期
             return redirect(url_for('daily_review', date=datetime.today().strftime('%Y-%m-%d')))

    sessions_this_day = []
    selected_data = None
    selected_start_time = None

    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            sessions_this_day = LiveData.query.filter_by(live_date=selected_date).order_by(LiveData.id.asc()).all()
            
            if sessions_this_day:
                if selected_identifier:
                    # 尝试按 live_start_time 或 id 查找
                    selected_data = next((s for s in sessions_this_day if str(s.live_start_time) == str(selected_identifier) or str(s.id) == str(selected_identifier)), None)
                
                # 如果没找到或没有标识符，默认选第一个
                if not selected_data:
                    selected_data = sessions_this_day[0]
                
                # 记录用于高亮按钮的 start_time
                if selected_data and selected_data.status == 'completed':
                     selected_start_time = selected_data.live_start_time
        except ValueError:
            flash("日期格式无效。", "danger")
            return redirect(url_for('daily_review'))

    if selected_data and selected_data.status == 'completed':
        charts = json.loads(selected_data.chart_paths) if selected_data.chart_paths else {}
        # 为生产和本地开发适配图表URL
        if IS_PRODUCTION:
             # 在生产环境，路径已经是完整的S3 URL
             selected_data.charts = charts
        else:
             # 在本地开发模式下，为图表路径添加 'static' 前缀
             selected_data.charts = {k: url_for('static', filename=v) for k, v in charts.items()}
    elif selected_data:
        # 对于非 'completed' 状态，确保 charts 字段存在但为空
        selected_data.charts = {}

    all_dates_with_data = [d.live_date.strftime('%Y-%m-%d') for d in db.session.query(LiveData.live_date).distinct().all()]
    
    return render_template(
        'daily_review.html', 
        data=selected_data, 
        date_str=date_str, 
        all_dates=all_dates_with_data, 
        sessions_this_day=sessions_this_day, 
        selected_start_time=selected_start_time
    )

# ... (确保 @app.route('/historical_trends') 在这个函数下面) ...


# ... (其他路由和代码) ...

@app.route('/historical_trends')
@login_required
def historical_trends():
    all_data = LiveData.query.filter_by(status='completed').order_by(LiveData.live_date.asc(), LiveData.live_start_time.asc()).all()
    raw_info_list = [{'date': d.live_date.strftime('%Y-%m-%d'), 'time': d.live_start_time} for d in all_data]
    chart_data = {'labels': [f'{d.live_date.strftime("%m-%d")} {d.live_start_time}' for d in all_data], 'raw_info': raw_info_list}
    for metric_key in HISTORICAL_METRICS.keys():
        chart_data[metric_key] = [getattr(d, metric_key, 0) for d in all_data]
    return render_template('historical_trends.html', chart_data=chart_data, metrics=HISTORICAL_METRICS)

# --- 启动时自动初始化数据库的函数 ---
with app.app_context():
    inspector = sa_inspect(db.engine)
    if not inspector.has_table(User.__tablename__):
        print("数据库或 User 表不存在，正在创建所有表...")
        db.create_all()
        print("数据库表创建完毕。")
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'default_password_123')
        admin_user = User.query.filter_by(username=admin_username).first()
        if not admin_user:
            print(f"创建初始管理员用户: {admin_username}...")
            new_admin = User(
                username=admin_username,
                password_hash=generate_password_hash(admin_password, method='pbkdf2:sha256'),
                role='admin'
            )
            db.session.add(new_admin)
            db.session.commit()
            print(f"管理员 '{admin_username}' 创建成功。")
        else:
             print(f"管理员用户 '{admin_username}' 已存在，跳过创建。")
    else:
        print("数据库表已存在，跳过初始化。")

# --- 应用程序启动入口 (只用于本地开发) ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')