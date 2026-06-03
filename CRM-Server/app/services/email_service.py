from abc import ABC, abstractmethod
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.core.config import get_settings

settings = get_settings()


class EmailProvider(ABC):
    """邮件发送提供商基类"""

    @abstractmethod
    async def send_email(self, to: str, subject: str, body: str) -> bool:
        """发送邮件"""
        pass


class ConsoleEmailProvider(EmailProvider):
    """开发环境：打印日志，不发送真实邮件"""

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        print(f"\n{'='*60}")
        print(f"[EMAIL] 发送邮件")
        print(f"  收件人: {to}")
        print(f"  主题: {subject}")
        print(f"  内容: {body}")
        print(f"{'='*60}\n")
        return True


class SMTPEmailProvider(EmailProvider):
    """通用 SMTP（腾讯企业邮箱、自建邮件服务器）"""

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        try:
            msg = MIMEMultipart()
            msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg['To'] = to
            msg['Subject'] = subject

            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            if settings.SMTP_USE_SSL:
                smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
            else:
                smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
                smtp.starttls()

            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.sendmail(settings.SMTP_FROM_EMAIL, to, msg.as_string())
            smtp.quit()

            return True
        except Exception as e:
            print(f"[EMAIL] SMTP 发送失败: {e}")
            return False


class AliyunEmailProvider(EmailProvider):
    """阿里云邮件推送 API"""

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        import hashlib
        import base64
        import hmac
        import time
        import httpx

        try:
            region = settings.ALIYUN_MAIL_REGION
            access_key = settings.ALIYUN_MAIL_ACCESS_KEY
            secret_key = settings.ALIYUN_MAIL_SECRET_KEY

            params = {
                "Action": "SingleSendMail",
                "AccountName": settings.SMTP_FROM_EMAIL,
                "ReplyToAddress": "true",
                "AddressType": 1,
                "ToAddress": to,
                "FromAlias": settings.SMTP_FROM_NAME,
                "Subject": subject,
                "TextBody": body,
                "Format": "JSON",
                "Version": "2015-11-23",
                "SignatureMethod": "HMAC-SHA1",
                "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "SignatureVersion": "1.0",
                "SignatureNonce": str(time.time()),
                "AccessKeyId": access_key,
            }

            # 构造签名
            sorted_params = sorted(params.items())
            query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
            string_to_sign = "GET&%2F&" + self._quote(query_string)
            signature = base64.b64encode(
                hmac.new((secret_key + "&").encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha1).digest()
            ).decode('utf-8')

            params["Signature"] = signature

            # 发送请求
            url = f"https://dm.{region}.aliyuncs.com/"
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                result = response.json()

            if result.get("Code") == "OK" or "EnvId" in result:
                print(f"[EMAIL] 阿里云邮件发送成功: {to}")
                return True
            else:
                print(f"[EMAIL] 阿里云邮件发送失败: {result}")
                return False
        except Exception as e:
            print(f"[EMAIL] 阿里云邮件推送失败: {e}")
            return False

    def _quote(self, s: str) -> str:
        """URL 编码（阿里云签名要求）"""
        import urllib.parse
        return urllib.parse.quote(s, safe='').replace('+', '%20').replace('*', '%2A').replace('%7E', '~')


class EmailService:
    """邮件服务"""

    def __init__(self):
        provider = settings.SMTP_PROVIDER
        if provider == "console":
            self._provider = ConsoleEmailProvider()
        elif provider == "aliyun":
            self._provider = AliyunEmailProvider()
        else:
            self._provider = SMTPEmailProvider()

    async def send_verification_code(self, email: str, code: str, purpose: str) -> bool:
        """发送验证码邮件"""
        purpose_display = {
            "register": "注册",
            "login": "登录",
            "reset_password": "重置密码"
        }
        purpose_text = purpose_display.get(purpose, purpose)

        subject = f"CRMWolf {purpose_text}验证码"
        body = f"""
您好！

您正在进行{purpose_text}操作，验证码为：{code}

验证码将在10分钟内有效，请尽快完成操作。

如果这不是您本人的操作，请忽略此邮件。

CRMWolf 智能客户关系管理系统
"""
        return await self._provider.send_email(email, subject, body)

    async def send_team_invite(self, email: str, team_name: str, invite_code: str, inviter_name: str) -> bool:
        """发送团队邀请邮件"""
        subject = f"邀请您加入团队 {team_name}"
        body = f"""
您好！

{inviter_name} 邀请您加入团队 {team_name}。

加入团队后，您可以：
- 与团队成员共享客户数据
- 协作跟进商机和合同
- 使用团队公海池功能

请使用以下邀请码加入团队：{invite_code}

您可以在注册或登录后，通过"加入团队"功能输入邀请码完成加入。

CRMWolf 智能客户关系管理系统
"""
        return await self._provider.send_email(email, subject, body)


email_service = EmailService()