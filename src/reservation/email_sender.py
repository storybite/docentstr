import smtplib
from email.mime.text import MIMEText
import os

email_fail_template = """
문화해설사 예약이 실패했습니다. 담당자가 확인 후 메일 드리겠습니다.
불편을 끼친 점 양해 부탁드립니다.

감사합니다.
""".strip()

email_success_template = """
안녕하세요? 문화해설사 예약이 완료되었습니다.

1. 신청 내용: 
{application_form}

2. 문화해설사 정보:
👤 이름: {docent_name}
📧 연락처: {docent_email}
🔴 부득이한 사정으로 예약 취소 시 방문일 전일까지 문화해설사님 이메일로 통지 부탁드립니다.

3. 만날 장소: 
🏛 국립중앙박물관 1층 기획전시실 앞

✨ 유익하고 즐거운 시간되시길 바랍니다. 감사합니다!
""".strip()


def send_mail(sender: str, receiver: str, cc: str, subject: str, body: str):
    recipients = [receiver, cc]
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = os.getenv("sender_email")
    msg["To"] = receiver
    msg["Cc"] = cc

    # # Gmail SMTP: smtp.gmail.com, 포트 587(STARTTLS) 사용
    smtp_server = smtplib.SMTP("smtp.gmail.com", 587)
    smtp_server.ehlo()  # 서버 연결 식별
    smtp_server.starttls()  # TLS(보안) 연결 시작
    smtp_server.login(sender, os.getenv("smtp_key"))

    smtp_server.sendmail(sender, recipients, msg.as_string())
    smtp_server.quit()
    print("메일 전송 완료")


def send_success_mail(application_form: str, receiver: str, bot_response: dict):
    body = email_success_template.format(
        application_form=application_form,
        docent_name=bot_response["docent_name"],
        docent_email=bot_response["docent_email"],
    )
    sender = os.getenv("sender_email")
    subject = "문화해설사 예약이 완료되었습니다."
    cc = bot_response["docent_email"]
    send_mail(sender, receiver, cc, subject, body)


def send_fail_mail(receiver: str):
    body = email_fail_template
    sender = os.getenv("sender_email")
    subject = "문화해설사 예약이 실패했습니다."
    cc = os.getenv("manager_email")
    send_mail(sender, receiver, cc, subject, body)
