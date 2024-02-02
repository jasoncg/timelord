import smtplib
import argparse
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os
import logging
from datetime import datetime, timedelta


class ColoredFormatter(logging.Formatter):
    COLORS = {
        'WARNING':  '\033[93m',
        'INFO':     '\033[94m',
        'DEBUG':    '\033[92m',
        'ERROR':    '\033[91m',
        'CRITICAL': '\033[91m',
        'ENDC':     '\033[0m'
    }

    def format(self, record):
        level_color = self.COLORS.get(record.levelname, '')
        super().format(record)
        return f"{level_color}[{record.levelname}]{self.COLORS['ENDC']} {record.message}"


def send_email(host, port, from_addr, to_addr, cc_addr, subject, body, invite=False, recurrinvite=False, attach=None):
    logging.info(f'send_email({host}:{port}, {from_addr}, {to_addr}, {cc_addr}, {subject})')
    if invite or attach or recurrinvite:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body))
    else:
        msg = EmailMessage()
        msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['CC'] = cc_addr

    # Get the current date and time
    now = datetime.now()

    # Add 7 days
    seven_days_later = now + timedelta(days=7)

    # Format as a string
    timestamp_str = seven_days_later.strftime('%Y%m%dT%H%M%SZ')
    timestamp_str_one_hour_later = (seven_days_later + timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')

    # Attach a calendar invite if requested
    if invite or recurrinvite:
        if not recurrinvite:
            cal = MIMEText(
                "BEGIN:VCALENDAR\n"
                "VERSION:2.0\n"
                "BEGIN:VEVENT\n"
                "UID:123@ical.test\n"
                f"DTSTAMP:{timestamp_str}\n"
                f"DTSTART:{timestamp_str}\n"
                f"DTEND:{timestamp_str_one_hour_later}\n"
                "SUMMARY:Test Calendar Invite\n"
                "END:VEVENT\n"
                "END:VCALENDAR\n", "calendar")
        else:
            cal = MIMEText('''BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//YourCompany//YourProduct//EN
BEGIN:VEVENT
UID:456@ical.test
DTSTART;TZID=America/New_York:20230815T090000
DTEND;TZID=America/New_York:20230815T100000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR
SUMMARY:Recurring Event
DESCRIPTION:This is a recurring event.
LOCATION:Example Location
END:VEVENT
END:VCALENDAR
''', "calendar")
        msg.attach(cal)

    # Attach a file if provided
    if attach:
        with open(attach, "rb") as file:
            part = MIMEApplication(file.read(), Name=os.path.basename(attach))
            part['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(attach)
            msg.attach(part)

    with smtplib.SMTP(host, port) as server:
        server.send_message(msg)
        print(f"Email sent to {host}:{port}")


if __name__ == "__main__":
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(ColoredFormatter('%(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser(description="Send a test email.")
    parser.add_argument('--host', default='localhost',
                        help='SMTP host (default: localhost)')
    parser.add_argument('--port', type=int, default=25,
                        help='SMTP port (default: 25)')
    parser.add_argument('--from', dest='from_addr', default='test@test.test',
                        help='Sender email address (default: test@test.test)')
    parser.add_argument('--to', dest='to_addr', default='recipient@example.com',
                        help='Recipient email address (default: recipient@example.com)')
    parser.add_argument('--cc', dest='cc_addr', default='',
                        help='Recipient email address (default: None)')
    parser.add_argument('--subject', default='Test Subject',
                        help='Email subject (default: Test Subject)')
    parser.add_argument('--body', default='This is a test email.',
                        help='Email body (default: This is a test email.)')
    parser.add_argument('--invite', action='store_true',
                        help='Include a calendar invite (default: False)')
    parser.add_argument('--recurr', action='store_true',
                        help='Include a calendar invite which has a recurrence (default: False)')
    parser.add_argument('--attach', help='Path to a file to attach (default: None)')

    args = parser.parse_args()

    send_email(args.host, args.port, args.from_addr, args.to_addr,
               args.cc_addr, args.subject, args.body, args.invite,
               args.recurr, args.attach)
