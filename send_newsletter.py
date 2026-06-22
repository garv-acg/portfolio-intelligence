import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
SENDER_EMAIL = "aidangarv@gmail.com"
APP_PASSWORD = "rmpt jzpi ckwt sear"
RECIPIENT_EMAIL = "aidangarv@gmail.com"

html_path = Path("output/latest_newsletter.html")

if not html_path.exists():
    raise FileNotFoundError("Run python generate_hybrid_newsletter.py first. Newsletter HTML file not found.")

html_content = html_path.read_text(encoding="utf-8")

msg = MIMEMultipart("alternative")
msg["Subject"] = "Daily Market Brief"
msg["From"] = SENDER_EMAIL
msg["To"] = RECIPIENT_EMAIL

msg.attach(MIMEText(html_content, "html"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(SENDER_EMAIL, APP_PASSWORD)
    server.send_message(msg)

print("Newsletter email sent successfully.")
