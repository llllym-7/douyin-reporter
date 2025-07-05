# tasks.py

import io
import json
import re
from PIL import Image
import traceback

# 【修改】导入 celery_app 实例
from celery_init import celery_app
# 【修改】只从 app 导入绝对安全、在顶层就需要的东西
from app import db, LiveData, IMAGE_1_CONFIG, IMAGE_2_CONFIG, IMAGE_3_CONFIG, IMAGE_4_CONFIG

@celery_app.task(bind=True)
def process_images_task(self, live_data_id, image_files_as_bytes):
    """
    This is the background task that processes uploaded images.
    """
    # 【修改】在函数内部导入其他需要的模块和函数，避免循环导入
    from app import app, process_single_image, ocr_with_llm, DEBUG_MODE_SKIP_OCR

    live_data_entry = db.session.get(LiveData, live_data_id)
    if not live_data_entry:
        print(f"Task failed: LiveData entry with id {live_data_id} not found.")
        return

    try:
        live_data_entry.status = 'processing'
        db.session.commit()

        # ... (内部逻辑保持不变)
        final_ocr_data = {}
        final_chart_paths = {}
        live_start_time = None
        live_date_str = live_data_entry.live_date.strftime('%Y-%m-%d')
        
        if image_files_as_bytes:
            first_image_stream = io.BytesIO(image_files_as_bytes[0])
            if not DEBUG_MODE_SKIP_OCR:
                temp_ocr_data = ocr_with_llm(Image.open(first_image_stream))
                if temp_ocr_data:
                    final_ocr_data.update(temp_ocr_data)
                    live_start_time = temp_ocr_data.get('live_start_time')
            first_image_stream.seek(0)
        
        if not live_start_time:
            raise ValueError("关键错误: 未能从第一张图片识别出开播时间。")

        existing_entry = LiveData.query.filter_by(
            live_date=live_data_entry.live_date, 
            live_start_time=live_start_time
        ).filter(LiveData.id != live_data_id).first()
        
        if existing_entry:
            db.session.delete(live_data_entry)
            db.session.commit()
            print(f"任务中止：日期 {live_date_str} (开播于 {live_start_time}) 的数据已存在。")
            return

        live_data_entry.live_start_time = live_start_time
        
        configs = [IMAGE_1_CONFIG, IMAGE_2_CONFIG, IMAGE_3_CONFIG, IMAGE_4_CONFIG]
        
        # 处理第一张图的 OCR 和 裁剪
        ocr_data_1, chart_paths_1 = process_single_image(first_image_stream, live_date_str, live_start_time, configs[0])
        final_ocr_data.update(ocr_data_1) # 更新第一张图的 OCR 数据
        final_chart_paths.update(chart_paths_1)
        
        # 处理剩余的图片 (仅裁剪，因为OCR数据都在第一张图)
        for i, img_bytes in enumerate(image_files_as_bytes[1:], start=1):
            if i < len(configs):
                image_stream = io.BytesIO(img_bytes)
                # 注意：我们假设 OCR 数据都在第一张图，这里只处理裁剪
                _, chart_paths = process_single_image(image_stream, live_date_str, live_start_time, configs[i])
                final_chart_paths.update(chart_paths)
        
        for key, value in final_ocr_data.items():
            if hasattr(live_data_entry, key) and value is not None:
                setattr(live_data_entry, key, value)
        
        live_data_entry.chart_paths = json.dumps(final_chart_paths)
        live_data_entry.status = 'completed'
        print(f"任务成功: {live_date_str} (开播于 {live_start_time}) 数据处理完毕。")

    except Exception as e:
        db.session.rollback()
        live_data_entry = db.session.get(LiveData, live_data_id)
        live_data_entry.status = 'failed'
        live_data_entry.error_message = str(e)
        print(f"!!! 任务失败: {e}")
        traceback.print_exc()
    finally:
        db.session.commit()