import logging
import json
import os
import threading
from datetime import datetime

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

bp = Blueprint("feedback", __name__)

FEEDBACK_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "next-app", "feedback.json",
)


_feedback_lock = threading.Lock()


@bp.route("/api/feedback", methods=["POST"])
def submit_feedback():
    """接收前端点赞/点踩反馈，追加写入 feedback.json（格式化 JSON 数组）"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求体为空"}), 400

        required = ["userQuestion", "analysisOutput", "type", "feedback"]
        for field in required:
            if field not in data:
                return jsonify({"success": False, "error": f"缺少字段: {field}"}), 400

        entry = {
            "timestamp": datetime.now().isoformat(),
            "userQuestion": data["userQuestion"],
            "analysisOutput": data["analysisOutput"],
            "type": data["type"],
            "feedback": data["feedback"],
        }

        # 读取已有记录，追加新记录，格式化写回
        with _feedback_lock:
            records = []
            if os.path.exists(FEEDBACK_FILE):
                with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                    try:
                        records = json.load(f)
                    except json.JSONDecodeError:
                        records = []

            records.append(entry)

            with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)

        logger.info(f"反馈已记录: type={entry['type']}, feedback={entry['feedback']}")
        return jsonify({"success": True})

    except Exception as e:
        logger.error(f"记录反馈失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
