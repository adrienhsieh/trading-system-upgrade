"""
Notification Service - 通知服務
支援：
1. LINE Bot 推播通知
2. Email 郵件通知
"""
import logging
import os
import threading
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
except ImportError:
    smtplib = None

_logger = logging.getLogger(__name__)

class NotificationService:
    """多渠道通知服務"""
    
    def __init__(self):
        self.line_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
    
    def send_line_notification(self, username: str, message: str, task_id: str = None) -> bool:
        """發送 LINE 推播通知
        
        Args:
            username: 用戶名
            message: 通知訊息
            task_id: 任務 ID
        
        Returns:
            bool: 是否發送成功
        """
        if not self.line_token:
            _logger.warning("⚠️ LINE_CHANNEL_ACCESS_TOKEN 未設定，跳過 LINE 通知")
            return False
        
        if not requests:
            _logger.warning("⚠️ requests 模組未安裝，無法發送 LINE 通知")
            return False
        
        try:
            # 背景線程發送，不阻擋主線程
            thread = threading.Thread(
                target=self._send_line_async,
                args=(username, message, task_id),
                daemon=True
            )
            thread.start()
            return True
        except Exception as e:
            _logger.error(f"❌ LINE 通知發送失敗: {e}")
            return False
    
    def _send_line_async(self, username: str, message: str, task_id: str):
        """異步發送 LINE 通知"""
        try:
            # 從用戶數據庫或環境變數取得 LINE User ID
            line_user_id = os.getenv(f"LINE_USER_ID_{username}")
            if not line_user_id:
                line_user_id = os.getenv('LINE_USER_ID')
            
            if not line_user_id:
                _logger.warning(f"⚠️ 無法找到用戶 {username} 的 LINE User ID")
                return
            
            url = "https://api.line.me/v2/bot/message/push"
            headers = {
                "Authorization": f"Bearer {self.line_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "to": line_user_id,
                "messages": [
                    {
                        "type": "text",
                        "text": message
                    },
                    {
                        "type": "text",
                        "text": f"任務 ID: {task_id}" if task_id else ""
                    }
                ]
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                _logger.info(f"✓ LINE 通知已發送給 {username}")
            else:
                _logger.error(f"❌ LINE 通知發送失敗: {response.status_code} {response.text}")
        
        except Exception as e:
            _logger.error(f"❌ LINE 非同步發送錯誤: {e}")
    
    def send_email_notification(self, email: str, subject: str, body: str, task_id: str = None) -> bool:
        """發送 Email 通知
        
        Args:
            email: 收件人郵箱
            subject: 郵件主旨
            body: 郵件內容
            task_id: 任務 ID
        
        Returns:
            bool: 是否發送成功
        """
        if not self.smtp_user or not self.smtp_password:
            _logger.warning("⚠️ SMTP 憑證未設定，跳過 Email 通知")
            return False
        
        if not smtplib:
            _logger.warning("⚠️ smtplib 模組不可用，無法發送 Email 通知")
            return False
        
        try:
            # 背景線程發送
            thread = threading.Thread(
                target=self._send_email_async,
                args=(email, subject, body, task_id),
                daemon=True
            )
            thread.start()
            return True
        except Exception as e:
            _logger.error(f"❌ Email 通知發送失敗: {e}")
            return False
    
    def _send_email_async(self, email: str, subject: str, body: str, task_id: str):
        """異步發送 Email 通知"""
        try:
            # 添加任務 ID 到郵件內容
            if task_id:
                body += f"\n\n---\n任務 ID: {task_id}"
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_user
            msg['To'] = email
            
            # HTML 版本
            html = f"""
            <html>
              <body style="font-family: Arial; line-height: 1.6;">
                <div style="color: #333;">
                  {body.replace(chr(10), '<br>')}
                </div>
              </body>
            </html>
            """
            
            part1 = MIMEText(body, 'plain')
            part2 = MIMEText(html, 'html')
            msg.attach(part1)
            msg.attach(part2)
            
            # 發送郵件
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            _logger.info(f"✓ Email 通知已發送至 {email}")
        
        except Exception as e:
            _logger.error(f"❌ Email 非同步發送錯誤: {e}")
