"""
座位偏好配置表
對應 param_schema.py 中的 seatCon:seatRadioGroup enum 值
"""

SEAT_PREFERENCES = {
    "radio17": {
        "value": "radio17",
        "label": "無偏好",
        "description": "不指定座位偏好"
    },
    "radio19": {
        "value": "radio19",
        "label": "靠窗",
        "description": "優先預訂靠窗座位"
    },
    "radio21": {
        "value": "radio21",
        "label": "靠走道",
        "description": "優先預訂靠走道座位"
    }
}

def get_seat_preference_options():
    """返回前端下拉選單用的選項列表"""
    return [
        {"value": "radio17", "label": "無偏好"},
        {"value": "radio19", "label": "靠窗"},
        {"value": "radio21", "label": "靠走道"}
    ]