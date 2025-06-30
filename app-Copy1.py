# app.py

import os
import json
import base64
import io
import re # 导入正则表达式模块
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from PIL import Image
from openai import OpenAI
from sqlalchemy import UniqueConstraint

# 导入配置
from a_ocr_config import LLM_CONFIG, JSON_PROMPT, IMAGE_1_CONFIG, IMAGE_2_CONFIG, IMAGE_3_CONFIG, IMAGE_4_CONFIG, HISTORICAL_METRICS

# --- 调试开关 ---
DEBUG_MODE_SKIP_OCR = False # 正常使用时请设置为 False

# --- App & DB 初始化 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = '5e67649ca7508d280ac840f20dc2982a2ad0443a64420488'
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['GENERATED_FOLDER'] = 'static/generated_charts/'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///livestream_reporter_final.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
try:
    client = OpenAI(api_key=LLM_CONFIG["API_KEY"], base_url=LLM_CONFIG["BASE_URL"])
except Exception as e:
    print(f"!!! 严重错误：初始化 OpenAI 客户端失败: {e}"); client = None

# --- 数据库模型 ---
class LiveData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    live_date = db.Column(db.Date, nullable=False)
    live_start_time = db.Column(db.String(50), nullable=False)
    gmv = db.Column(db.Float, default=0); gpm = db.Column(db.Float, default=0); order_count = db.Column(db.Integer, default=0); buyer_count = db.Column(db.Integer, default=0); click_to_order_ratio = db.Column(db.Float, default=0); view_to_order_ratio = db.Column(db.Float, default=0); expose_to_view_ratio = db.Column(db.Float, default=0); view_to_interact_ratio = db.Column(db.Float, default=0); avg_watch_time_seconds = db.Column(db.Integer, default=0); new_followers = db.Column(db.Integer, default=0); follower_order_ratio = db.Column(db.Float, default=0); avg_online_users = db.Column(db.Integer, default=0); vv = db.Column(db.Integer, default=0); chart_paths = db.Column(db.Text, default='{}')
    __table_args__ = (UniqueConstraint('live_date', 'live_start_time', name='_live_date_start_time_uc'),)

# --- 辅助函数 ---
def image_to_base64(image: Image.Image, format="PNG") -> str:
    buffered = io.BytesIO();
    if image.mode != 'RGB': image = image.convert('RGB')
    save_format = format.upper()
    if save_format == 'JPEG': image.save(buffered, format="JPEG"); mime_type = "image/jpeg"
    else: image.save(buffered, format="PNG"); mime_type = "image/png"
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:{mime_type};base64,{img_str}"

def ocr_with_llm(image: Image.Image):
    if not client: raise ConnectionError("OpenAI 客户端未初始化")
    base64_image = image_to_base64(image)
    try:
        response = client.chat.completions.create(model=LLM_CONFIG["MODEL_NAME"], messages=[{"role": "user", "content": [{"type": "text", "text": JSON_PROMPT}, {"type": "image_url", "image_url": {"url": base64_image}}]}], max_tokens=2048, temperature=0.0)
        json_string = response.choices[0].message.content
        if json_string.strip().startswith("```json"): json_string = json_string.strip()[7:-3]
        return json.loads(json_string)
    except Exception as e:
        print(f"!!! LLM API 调用或JSON解析失败: {e}"); return None

def process_single_image(image_path, date_str, start_time_str, config):
    if not config: return {}, {}
    ocr_data, cropped_chart_paths = {}, {}
    img = Image.open(image_path)
    if not DEBUG_MODE_SKIP_OCR:
        llm_result_dict = ocr_with_llm(img)
        if llm_result_dict:
            for key, value in llm_result_dict.items():
                if value is not None: ocr_data[key] = value

    if 'chart_crops' in config:
        for key, crop_area in config['chart_crops'].items():
            if crop_area == (0,0,0,0): continue
            chart_img = img.crop(crop_area)
            
            # 【核心修改】对开播时间字符串进行净化，移除所有不适合做文件名的字符
            # 使用正则表达式替换掉所有非字母、非数字、非下划线、非连字符的符号
            safe_start_time = re.sub(r'[^a-zA-Z0-9_-]', '_', str(start_time_str))
            
            chart_filename = f"{date_str}_{safe_start_time}_{key}.png"
            save_path = os.path.join(app.config['GENERATED_FOLDER'], chart_filename)
            chart_img.save(save_path)
            web_path = os.path.join('generated_charts', chart_filename).replace('\\', '/')
            cropped_chart_paths[key] = web_path
    return ocr_data, cropped_chart_paths

# --- 路由 ---
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        live_date_str = request.form.get('live_date')
        if not live_date_str: flash('必须选择一个日期!', 'danger'); return redirect(request.url)
        live_date = datetime.strptime(live_date_str, '%Y-%m-%d').date()
        files = request.files.getlist('images')
        if not files or files[0].filename == '': flash('必须上传至少一张图片!', 'danger'); return redirect(request.url)

        temp_ocr_data = {}
        first_image = files[0]; first_image.seek(0)
        img_for_time_check = Image.open(first_image)
        if not DEBUG_MODE_SKIP_OCR:
            temp_ocr_data = ocr_with_llm(img_for_time_check)
        
        live_start_time = temp_ocr_data.get('live_start_time') if temp_ocr_data else None
        if not live_start_time:
            flash('处理失败：未能从第一张图片中识别到“开播时间”，无法保存数据。', 'danger')
            return redirect(url_for('daily_review'))

        existing_entry = LiveData.query.filter_by(live_date=live_date, live_start_time=live_start_time).first()
        if existing_entry:
            flash(f'日期 {live_date_str} (开播于 {live_start_time}) 的数据已存在，请先清空再上传。', 'warning')
            return redirect(url_for('daily_review', date=live_date_str, start_time=live_start_time))

        configs_to_use = [IMAGE_1_CONFIG, IMAGE_2_CONFIG, IMAGE_3_CONFIG, IMAGE_4_CONFIG]
        final_ocr_data, final_chart_paths = {}, {}
        final_ocr_data.update(temp_ocr_data or {})

        if len(files) < 4: flash(f'提醒：您上传了 {len(files)} 张图片，建议上传全部4张以保证数据完整。', 'warning')
        
        for i, file in enumerate(files[1:4], start=1):
            if i >= len(configs_to_use): break
            file.seek(0)
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"{live_date_str}_{timestamp}_{i+1}_{file.filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            config_for_this_image = configs_to_use[i]
            ocr_data, chart_paths = process_single_image(filepath, live_date_str, live_start_time, config_for_this_image)
            final_ocr_data.update(ocr_data); final_chart_paths.update(chart_paths)
        
        first_image.seek(0)
        timestamp = datetime.now().strftime("%H%M%S")
        filename_1 = f"{live_date_str}_{timestamp}_1_{first_image.filename}"
        filepath_1 = os.path.join(app.config['UPLOAD_FOLDER'], filename_1)
        first_image.save(filepath_1)
        _, chart_paths_1 = process_single_image(filepath_1, live_date_str, live_start_time, configs_to_use[0])
        final_chart_paths.update(chart_paths_1)
        
        entry = LiveData(live_date=live_date, live_start_time=live_start_time)
        if not DEBUG_MODE_SKIP_OCR:
             for key, value in final_ocr_data.items():
                if hasattr(entry, key): setattr(entry, key, value)
        entry.chart_paths = json.dumps(final_chart_paths)
        db.session.add(entry); db.session.commit()
        
        if not DEBUG_MODE_SKIP_OCR: flash(f'日期 {live_date_str} (开播于 {live_start_time}) 的数据已成功处理!', 'success')
        else: flash(f'调试模式：日期 {live_date_str} (开播于 {live_start_time}) 的图表已更新。', 'warning')
        return redirect(url_for('daily_review', date=live_date_str, start_time=live_start_time))
    return render_template('upload.html')

@app.route('/delete_data/<int:entry_id>', methods=['POST'])
def delete_data(entry_id):
    try:
        entry = LiveData.query.get(entry_id)
        if entry:
            date_str = entry.live_date.strftime('%Y-%m-%d')
            db.session.delete(entry); db.session.commit()
            flash(f'日期 {date_str} (开播于 {entry.live_start_time}) 的数据已成功清空。', 'success')
        else: flash(f'未找到要删除的数据记录。', 'warning')
    except Exception as e: flash(f'清空数据时发生错误: {e}', 'danger')
    return redirect(url_for('daily_review'))

@app.route('/')
def index(): return redirect(url_for('daily_review'))

@app.route('/daily_review')
def daily_review():
    date_str = request.args.get('date')
    selected_start_time = request.args.get('start_time')
    if not date_str:
        latest_entry = LiveData.query.order_by(LiveData.live_date.desc(), LiveData.live_start_time.desc()).first()
        if latest_entry: return redirect(url_for('daily_review', date=latest_entry.live_date.strftime('%Y-%m-%d')))
    sessions_this_day, selected_data = [], None
    if date_str:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        sessions_this_day = LiveData.query.filter_by(live_date=selected_date).order_by(LiveData.live_start_time.asc()).all()
        if sessions_this_day:
            if selected_start_time:
                selected_data = next((s for s in sessions_this_day if s.live_start_time == selected_start_time), None)
            if not selected_data:
                selected_data = sessions_this_day[0]
                selected_start_time = selected_data.live_start_time
    if selected_data:
        selected_data.charts = json.loads(selected_data.chart_paths) if selected_data.chart_paths else {}
    all_dates_with_data = [d.live_date.strftime('%Y-%m-%d') for d in db.session.query(LiveData.live_date).distinct().all()]
    return render_template('daily_review.html', data=selected_data, date_str=date_str, all_dates=all_dates_with_data, sessions_this_day=sessions_this_day, selected_start_time=selected_start_time)

@app.route('/historical_trends')
def historical_trends():
    all_data = LiveData.query.order_by(LiveData.live_date.asc(), LiveData.live_start_time.asc()).all()
    
    # 【核心代码】为实现点击跳转，我们额外准备一个包含完整日期和时间信息的列表
    raw_info_list = [{'date': d.live_date.strftime('%Y-%m-%d'), 'time': d.live_start_time} for d in all_data]

    chart_data = {
        'labels': [f'{d.live_date.strftime("%m-%d")} {d.live_start_time}' for d in all_data],
        'raw_info': raw_info_list, # <--- 关键：将这个列表添加到 chart_data 中
    }
    for metric_key in HISTORICAL_METRICS.keys():
        chart_data[metric_key] = [getattr(d, metric_key, 0) for d in all_data]

    # 直接传递完整的Python字典给模板
    return render_template('historical_trends.html', 
                           chart_data=chart_data, 
                           metrics=HISTORICAL_METRICS)

if __name__ == '__main__':
    with app.app_context():
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['GENERATED_FOLDER'], exist_ok=True)
        db.create_all()