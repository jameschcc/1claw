#!/usr/bin/env python3
"""Send 4 软著 PDFs to ics2@qq.com with correct application/pdf Content-Type."""
import smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

SMTP_HOST = "mail.maxqs.com"
SMTP_PORT = 587
FROM = "paper.ai@maxqs.com"
PASS = "Hermes123"
TO = "ics2@qq.com"

files = [
    ("01-用户操作手册.pdf", "01-用户操作手册.pdf"),
    ("02-软件设计说明书.pdf", "02-软件设计说明书.pdf"),
    ("03-源代码节选.pdf", "03-源代码节选.pdf"),
    ("04-软件著作权登记申请表.pdf", "04-软件著作权登记申请表.pdf"),
]
DIR = "/home/j/Codes/1claw/soft-copyright-docs"

msg = MIMEMultipart()
msg["From"] = FROM
msg["To"] = TO
msg["Subject"] = "1Claw 软著申请材料（PDF附件）"

body = MIMEText("""Hi，

附件为 1Claw 计算机软件著作权登记申请材料，共 4 个 PDF：

1. 01-用户操作手册.pdf — 用户安装部署与使用指南
2. 02-软件设计说明书.pdf — 系统架构与模块设计
3. 03-源代码节选.pdf — 前30页 + 后30页源代码
4. 04-软件著作权登记申请表.pdf — 填写好的申请表

全部以 application/pdf 格式发送，请确认能否正常打开。

Best
""", "plain", "utf-8")
msg.attach(body)

for local_name, disp_name in files:
    path = f"{DIR}/{local_name}"
    with open(path, "rb") as f:
        pdf_data = f.read()
    part = MIMEApplication(pdf_data, _subtype='pdf')
    part.add_header("Content-Disposition", "attachment", filename=disp_name)
    msg.attach(part)
    print(f"  Attached: {disp_name} ({len(pdf_data)} bytes)")

print("Connecting...")
ctx = ssl._create_unverified_context()
with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
    s.starttls(context=ctx)
    s.login(FROM, PASS)
    s.send_message(msg)

print("DONE — 4 PDFs sent to ics2@qq.com")
