import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Default to console logging if no SMTP host is set
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

def send_email(to_email: str, subject: str, body: str, from_email: str = "ar-learn@example.com") -> bool:
    """
    Send an email. If SMTP_HOST is not configured, logs the email to the console.
    Returns True if successful (or logged), False otherwise.
    """
    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if not SMTP_HOST:
        # Development mode – just print the email
        print(f"=== EMAIL (not sent) ===")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body}")
        print("========================")
        return True

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False