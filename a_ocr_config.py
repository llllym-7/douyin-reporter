# a_ocr_config.py

# ... (LLM_CONFIG 和 JSON_PROMPT 保持不变) ...
LLM_CONFIG = {
    "API_KEY": "sk-udzsogssqinpcokdsgxehmopfobqycpwflgtzarmdhqtcuio",
    "BASE_URL": "https://api.siliconflow.cn/v1",
    "MODEL_NAME": "Qwen/Qwen2.5-VL-72B-Instruct"
}

JSON_PROMPT = """
你是一个顶级的抖音直播数据分析专家，拥有精确的视觉识别能力（OCR）。
你的任务是严格按照用户提供的图片，提取所有关键数据指标，并以一个纯净的、不含任何额外解释的JSON格式返回。
请根据图片内容，填充以下JSON结构。
- 对于图片中存在的指标，请精确提取其数值。
- 对于数值，只返回数字（整数或浮点数），不要包含任何单位如 "¥"、"%" 或 "分秒"。对于百分比，请直接返回数字，例如 "12.5%" 应返回 12.5。对于时间 "1分"，请计算总秒数后返回 60。
- 对于图片中不存在或无法识别的指标，请使用 `null` 作为其值。
- 最终的输出必须是一个能被直接解析的JSON对象，不要在JSON代码块前后添加任何文字、注释或markdown标记(如```json ```)。
这是你必须严格遵守的JSON结构，请根据图片中的中文标签进行精确匹配和提取：
{
  "live_start_time": "字符串 (对应 '开播时间')",
  "gmv": "浮点数 (对应 '直播间成交金额' 或 '直播间用户支付金额')",
  "gpm": "浮点数 (对应 '千次观看成交金额')",
  "order_count": "整数 (对应 '成交件数')",
  "buyer_count": "整数 (对应 '成交人数')",
  "vv": "整数 (对应 '累计观看人数')",
  "avg_online_users": "整数 (对应 '平均在线人数')",
  "avg_watch_time_seconds": "整数 (对应 '人均观看时长', 结果转为总秒数)",
  "new_followers": "整数 (对应 '新增粉丝数')",
  "click_to_order_ratio": "浮点数 (对应 '商品点击-成交率(人数)')",
  "view_to_order_ratio": "浮点数 (对应 '观看-成交率(人数)')",
  "expose_to_view_ratio": "浮点数 (对应 '曝光-观看率(次数)')",
  "view_to_interact_ratio": "浮点数 (对应 '观看-互动率(人数)')",
  "follower_order_ratio": "浮点数 (对应 '成交粉丝占比' 或 '粉丝成交占比')"
}
"""

# ==============================================================================
#  !! 关键步骤: 根据新的图片定义和布局，重新组织配置 !!
# ==============================================================================

# 图片1: 综合趋势图
IMAGE_1_CONFIG = {
    'chart_crops': {
        'overall_trend_chart': (140, 450, 1753, 1120),
    }
}

# 图片2: 分钟级流量结构图
IMAGE_2_CONFIG = {
    'chart_crops': {
        'minute_traffic_flow_chart':  (135, 450, 1753, 850),
    }
}

# 图片3: 罗盘页面图
IMAGE_3_CONFIG = {
    'chart_crops': {
        'traffic_source_chart': (47, 100, 531, 320),
        #'user_profile_chart': (38, 678, 290, 830),
        'live_users_trend_chart': (1730, 100, 2195, 430),
    }
}

# 【新增】图片4: 人群画像图 (4.png)
# !! 请务必用截图工具，测量您实际的“人群画像”图的坐标 !!
IMAGE_4_CONFIG = {
    'chart_crops': {
        'user_profile_chart': (113, 100, 2175, 1160), # <--- 请在这里填入您测量的精确坐标
    }
}


# “历史数据趋势”页面下拉框的可选指标 (保持不变)
HISTORICAL_METRICS = {
    'gmv': '成交金额 (GMV)',
    'order_count': '成交件数',
    'gpm': '千次观看成交金额 (GPM)',
    'buyer_count': '成交人数',
    'click_to_order_ratio': '点击-成交转化率 (%)',
    'avg_watch_time_seconds': '人均观看时长 (秒)',
    'vv': '累计观看人数',
    'new_followers': '新增粉丝数',
    'avg_online_users': '平均在线人数',
        # --- 【新增】的三个指标 ---
    'view_to_order_ratio': '观看-成交率 (%)',
    'expose_to_view_ratio': '曝光-观看率 (%)',
    'follower_order_ratio': '成交粉丝占比 (%)',
}