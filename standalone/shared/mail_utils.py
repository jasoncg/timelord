from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.parser import BytesParser
from email.message import Message
import base64
import pytz
import re
from typing import Sequence, TypedDict
from icalendar import Calendar
from email import policy, message_from_string
import logging
from datetime import datetime, timedelta, timezone
import dateutil.rrule
import os
import traceback
import smtplib
from database import TLDatabase
import shared.constants as constants

CHUNK_SIZE = 45

db = TLDatabase()


def append_footer(email_content, footer):
    try:
        # Check if the email is multipart (i.e., HTML + plain text)
        if email_content.is_multipart():
            for part in email_content.walk():
                content_type = part.get_content_type()
                content_disposition = part.get("Content-Disposition")
                content_transfer_encoding = part.get("Content-Transfer-Encoding")

                # Skip any part that has a content disposition of 'attachment'
                if content_disposition and "attachment" in content_disposition:
                    continue
                
                original_encoding = part.get_content_charset()
                payload = part.get_payload(decode=True)
                if payload is not None:
                    data    = payload.decode(original_encoding)

                    #decoded = payload.decode('utf-8')
                    if decoded is not None:
                        payload = decoded
                else:
                    payload = part.get_payload()

                if content_type == "text/plain":
                    new_payload = payload + "\n\n" + footer
                    part.set_payload(new_payload)
                elif content_type == "text/html":
                    footer_html = footer.replace('\n', '<br/>\n')
                    new_payload = payload.replace("</body>", f"<p>{footer_html}</p></body>")
                    part.set_payload(new_payload)
                else:
                    continue

                # Re-encode if the original was base64
                if content_transfer_encoding == 'base64':
                    new_payload = base64.b64encode(new_payload.encode(original_encoding)).decode(original_encoding)
                part.set_payload(new_payload)
        else:
            payload = email_content.get_payload(decode=True)
            if payload is not None:
                original_encoding = email_content.get_content_charset()
                decoded = payload.decode(original_encoding)
                if decoded is not None:
                    payload = decoded
            else:
                payload = email_content.get_payload()

            # If the email is only plain text
            if email_content.get_content_type() == "text/plain":
                new_payload = payload + "\n" + footer

            # If the email is only HTML
            elif email_content.get_content_type() == "text/html":
                footer_html = footer.replace('\n', '<br/>\n')
                new_payload = payload.replace("</body>", f"<p>{footer_html}</p></body>")
            else:
                logging.error(f'append_footer: Unknown content type {content_type}')
                return email_content

            email_content.set_payload(new_payload)
    except Exception as e:
        logging.exception(e)
        logging.exception(traceback.format_exc())

    return email_content


def send_smtp(sender: str, receiver: str | Sequence[str], msg: str, additionalDetails:str='') -> Sequence[str]:
    try:
        logging.warn(f'send_smtp(sender={sender}, to={receiver})')

        sent_success = set()

        # Connect to the server and send the email.
        host = os.environ.get("smtp_address")
        port = os.environ.get("smtp_port")
        smtp_username = os.environ.get("smtp_user_name")
        smtp_password = os.environ.get("smtp_password")

        # make receiver into a list if it isn't one already
        if isinstance(receiver, str):
            receiver = [receiver]
        else:
            receiver = list(receiver)

        # Ensure receive doesn't have any address destined for self server
        removed =  [email for email in receiver if constants.DOMAIN in email]
        receiver = [email for email in receiver if constants.DOMAIN not in email]
        if len(removed)>0:
            logging.error(f'The following destination emails were removed: {removed}')
        if len(receiver) == 0 :
            logging.error(f'There are no destination emails provdied, cancel send_smtp')

        try:
            system_name = os.environ.get('BRANDING', 'Timelord')
            gitlab_url = os.environ.get('gitlab_url', '')
            gitlab_calendar_wiki_project_url = os.environ.get('GITLAB_CALENDAR_WIKI_PROJECT_URL', '%s/calendar/'%gitlab_url)
                                                              
            email_msg = message_from_string(msg)
            email_msg = append_footer(email_msg, f'''
    **** {system_name} ****
    {additionalDetails}
    You received this message because you are a member of a {system_name} Gitlab group / Distribution List.

    To stop receiving messages, remove yourself from the group on Gitlab.

    Distribution Lists:
    {gitlab_calendar_wiki_project_url}-/wikis/Distribution-Lists

    Calendars:
    {gitlab_calendar_wiki_project_url}-/wikis/home

    *******************
    ''')

            msg = email_msg.as_string()
        except Exception as e:
            logging.exception(e)
            logging.exception(traceback.format_exc())

        if constants.DEBUG_MODE:
            logging.warn(f'DEBUG MODE (Not sending email) - send_smtp[host={host}:{port} sender={sender}]])')
            try:
                email_msg = message_from_string(msg)
                email_msg = append_footer(email_msg, f'''
        **** TEST MODE ****
        Envelope - Send to:

        {receiver}

        *******************
        ''')
                msg = email_msg.as_string()
            except Exception as e:
                logging.exception(e)
                logging.exception(traceback.format_exc())

            logging.warn(msg)

            if len(receiver) > CHUNK_SIZE:
                logging.warn('Chunking email sending...')
                # Iterate through the list in chunks of 45
                for i in range(0, len(receiver), CHUNK_SIZE):
                    s = receiver[i:i+CHUNK_SIZE]
                    logging.warn(f'Send Chunk: {s}')
            else:
                logging.warn(f'Send: {receiver}')
            return True

        try:
            server = smtplib.SMTP_SSL(host, port)
            server.ehlo()
            server.login(smtp_username, smtp_password)
            if constants.TEST_MODE:
                logging.warn(f'TEST MODE (Reflect to sender) - send_smtp[host={host}:{port} sender={sender}]])')
                try:
                    email_msg = message_from_string(msg)
                    append_footer(email_msg, f'''
            **** TEST MODE ****
            Envelope - Send to:

            {receiver}

            *******************
            ''')
                    msg = email_msg.as_string()
                except Exception as e:
                    logging.exception(e)
                    logging.exception(traceback.format_exc())
                server.sendmail(constants.DEFAULT_FROM, sender, msg)
                sent_success.update(sender)
            else:
                if len(receiver) > CHUNK_SIZE:
                    logging.warn(f'Chunking email sending {len(receiver)} > {CHUNK_SIZE}...')
                    # Iterate through the list in chunks of 45
                    for i in range(0, len(receiver), CHUNK_SIZE):
                        s = receiver[i:i+CHUNK_SIZE]
                        logging.warn(f'Chunk {i} {len(s)}: {s}')
                        server.sendmail(constants.DEFAULT_FROM, s, msg)
                        sent_success.update(s)
                else:
                    logging.warn('Sending to all...')
                    server.sendmail(constants.DEFAULT_FROM, receiver, msg)
                    sent_success.update(receiver)
                logging.warn(f'Email sent over SMTP - send_smtp[host={host}:{port} sender={sender}]]({receiver})')
        except Exception as e:
            logging.exception(e)
            logging.exception(traceback.format_exc())
            logging.error(email_msg)
        finally:
            server.quit()
    finally:
        return sent_success

def remove_emails(email_list, domain):
    '''
    Returns a copy of email_list with all email addresses that do not match domain (including subdomains)
    '''
    domain_pattern = re.compile(r'@(?:[^@]*\.)?' + re.escape(domain) + r'\b', re.IGNORECASE)
    return [email for email in email_list if not domain_pattern.search(email)]


def get_calendar_file(raw_email):
    msg = BytesParser(policy=policy.default).parsebytes(raw_email)

    if msg.is_multipart():
        for part in msg.iter_parts():
            content_type = part.get_content_type()
            # filename = part.get_filename()
            if content_type == 'text/calendar':
                return part.get_content()
    else:
        return None


WIN_TZ_MAPPINGS = {
    'AUS Central Standard Time': 'Australia/Darwin',
    'AUS Eastern Standard Time': 'Australia/Sydney',
    'Afghanistan Standard Time': 'Asia/Kabul',
    'Alaskan Standard Time': 'America/Anchorage',
    'Arab Standard Time': 'Asia/Riyadh',
    'Arabian Standard Time': 'Asia/Dubai',
    'Arabic Standard Time': 'Asia/Baghdad',
    'Argentina Standard Time': 'America/Buenos_Aires',
    'Atlantic Standard Time': 'America/Halifax',
    'Azerbaijan Standard Time': 'Asia/Baku',
    'Azores Standard Time': 'Atlantic/Azores',
    'Bahia Standard Time': 'America/Bahia',
    'Bangladesh Standard Time': 'Asia/Dhaka',
    'Canada Central Standard Time': 'America/Regina',
    'Cape Verde Standard Time': 'Atlantic/Cape_Verde',
    'Caucasus Standard Time': 'Asia/Yerevan',
    'Cen. Australia Standard Time': 'Australia/Adelaide',
    'Central America Standard Time': 'America/Guatemala',
    'Central Asia Standard Time': 'Asia/Almaty',
    'Central Brazilian Standard Time': 'America/Cuiaba',
    'Central Europe Standard Time': 'Europe/Budapest',
    'Central European Standard Time': 'Europe/Warsaw',
    'Central Pacific Standard Time': 'Pacific/Guadalcanal',
    'Central Standard Time': 'America/Chicago',
    'Central Standard Time (Mexico)': 'America/Mexico_City',
    'China Standard Time': 'Asia/Shanghai',
    'Dateline Standard Time': 'Etc/GMT+12',
    'E. Africa Standard Time': 'Africa/Nairobi',
    'E. Australia Standard Time': 'Australia/Brisbane',
    'E. Europe Standard Time': 'Asia/Nicosia',
    'E. South America Standard Time': 'America/Sao_Paulo',
    'Eastern Standard Time': 'America/New_York',
    'Egypt Standard Time': 'Africa/Cairo',
    'Ekaterinburg Standard Time': 'Asia/Yekaterinburg',
    'FLE Standard Time': 'Europe/Kiev',
    'Fiji Standard Time': 'Pacific/Fiji',
    'GMT Standard Time': 'Europe/London',
    'GTB Standard Time': 'Europe/Bucharest',
    'Georgian Standard Time': 'Asia/Tbilisi',
    'Greenland Standard Time': 'America/Godthab',
    'Greenwich Standard Time': 'Atlantic/Reykjavik',
    'Hawaiian Standard Time': 'Pacific/Honolulu',
    'India Standard Time': 'Asia/Calcutta',
    'Iran Standard Time': 'Asia/Tehran',
    'Israel Standard Time': 'Asia/Jerusalem',
    'Jordan Standard Time': 'Asia/Amman',
    'Kaliningrad Standard Time': 'Europe/Kaliningrad',
    'Korea Standard Time': 'Asia/Seoul',
    'Magadan Standard Time': 'Asia/Magadan',
    'Mauritius Standard Time': 'Indian/Mauritius',
    'Middle East Standard Time': 'Asia/Beirut',
    'Montevideo Standard Time': 'America/Montevideo',
    'Morocco Standard Time': 'Africa/Casablanca',
    'Mountain Standard Time': 'America/Denver',
    'Mountain Standard Time (Mexico)': 'America/Chihuahua',
    'Myanmar Standard Time': 'Asia/Rangoon',
    'N. Central Asia Standard Time': 'Asia/Novosibirsk',
    'Namibia Standard Time': 'Africa/Windhoek',
    'Nepal Standard Time': 'Asia/Katmandu',
    'New Zealand Standard Time': 'Pacific/Auckland',
    'Newfoundland Standard Time': 'America/St_Johns',
    'North Asia East Standard Time': 'Asia/Irkutsk',
    'North Asia Standard Time': 'Asia/Krasnoyarsk',
    'Pacific SA Standard Time': 'America/Santiago',
    'Pacific Standard Time': 'America/Los_Angeles',
    'Pacific Standard Time (Mexico)': 'America/Santa_Isabel',
    'Pakistan Standard Time': 'Asia/Karachi',
    'Paraguay Standard Time': 'America/Asuncion',
    'Romance Standard Time': 'Europe/Paris',
    'Russian Standard Time': 'Europe/Moscow',
    'SA Eastern Standard Time': 'America/Cayenne',
    'SA Pacific Standard Time': 'America/Bogota',
    'SA Western Standard Time': 'America/La_Paz',
    'SE Asia Standard Time': 'Asia/Bangkok',
    'Samoa Standard Time': 'Pacific/Apia',
    'Singapore Standard Time': 'Asia/Singapore',
    'South Africa Standard Time': 'Africa/Johannesburg',
    'Sri Lanka Standard Time': 'Asia/Colombo',
    'Syria Standard Time': 'Asia/Damascus',
    'Taipei Standard Time': 'Asia/Taipei',
    'Tasmania Standard Time': 'Australia/Hobart',
    'Tokyo Standard Time': 'Asia/Tokyo',
    'Tonga Standard Time': 'Pacific/Tongatapu',
    'Turkey Standard Time': 'Europe/Istanbul',
    'US Eastern Standard Time': 'America/Indianapolis',
    'US Mountain Standard Time': 'America/Phoenix',
    'UTC': 'Etc/GMT',
    'UTC+12': 'Etc/GMT-12',
    'UTC-02': 'Etc/GMT+2',
    'UTC-11': 'Etc/GMT+11',
    'Ulaanbaatar Standard Time': 'Asia/Ulaanbaatar',
    'Venezuela Standard Time': 'America/Caracas',
    'Vladivostok Standard Time': 'Asia/Vladivostok',
    'W. Australia Standard Time': 'Australia/Perth',
    'W. Central Africa Standard Time': 'Africa/Lagos',
    'W. Europe Standard Time': 'Europe/Berlin',
    'West Asia Standard Time': 'Asia/Tashkent',
    'West Pacific Standard Time': 'Pacific/Port_Moresby',
    'Yakutsk Standard Time': 'Asia/Yakutsk'
 }


def get_end_date(component):
    # Assuming you already have 'component' as the VEVENT component
    crr = component.get('rrule')
    if crr is None:
        return
    rrule_data = crr.to_ical().decode("utf-8")
    start_date = component.get('dtstart').dt
    dtend = component.get('dtend')
    duration = dtend.dt - start_date
    start_tz = component.get('dtstart').params.get('tzid')  # Get the timezone
    # Get the last occurrence
    # If the timezone is available, use it. Otherwise, default to UTC.
    if start_tz:
        if start_tz in WIN_TZ_MAPPINGS:
            start_tz = WIN_TZ_MAPPINGS[start_tz]
        now = datetime.now(pytz.timezone(start_tz))
    else:
        now = datetime.now(timezone.utc)
    # Create a recurrence rule
    rrule = dateutil.rrule.rrulestr(rrule_data, dtstart=start_date)

    # Define a maximum date far into the future. Adjust this to your needs.
    max_date = now + timedelta(days=5*365)  # 5 years into the future

    # Get all occurrences up to the maximum date
    occurrences = rrule.between(now, max_date, inc=True)

    # Pick the last occurrence
    last_occurrence_start = occurrences[-1] if occurrences else None

    # Calculate the end time of the last occurrence
    if last_occurrence_start is not None:
        last_occurrence_end = last_occurrence_start + duration

    return last_occurrence_end


async def receive_calendar(raw_email: str, msg: Message, target_groups: Sequence[str],
                           send_to: Sequence[str], ics_file: str, method: str) -> str | None:
    # Parse the ics file data to extract the UID and other details
    cal = Calendar.from_ical(ics_file)

    email_from = msg['From']

    for component in cal.walk():
        if component.name == "VEVENT":
            uid = str(component.get('uid'))
            meeting_title = str(component.get('summary'))
            rrule = component.get('rrule')
            dtend = component.get('dtend')
            if dtend:
                # end_datetime = str(dtend.dt)
                end_date = str(get_end_date(component))
            else:
                # end_datetime = None
                end_date = None
            break

    if not uid:
        # there was an error, uid not found
        logging.error(f"Received calendar without a uid '{meeting_title}'")
        return

    '''
    # Send the email
    if len(send_to) > 0:
        try:
            send_smtp(email_from, send_to, msg.as_string())
            await db.meetings_invites_set(uid, send_to)
        except Exception as e:
            traceback.print_exc(e)
            logging.exception()'''

    recurrence_id = component.get('recurrence-id')
    if recurrence_id:
        # this is an update for a specific instance, so don't update the database
        logging.info("Event for a specific instance, " +
                     f"don't update database uid={uid} rid={recurrence_id} '{meeting_title}'")
        pass
    else:
        if method == 'CANCEL':
            logging.info(f'Cancel entire event series {uid}')
            # Delete the entire series from the DB
            await db.meetings_delete_record(uid)
            # Cancelled, so don't set in sent receipts in the database
            return None
        else:
            # If the event is not cancelled, put (create or update) the item in database
            record = {
                    'uuid': uid,                        # string
                    'meeting_title': meeting_title,     # string
                    'email_from': email_from,           # string
                    'email': raw_email,                 # string
                    'recurr': (rrule is not None),      # bool
                    'end_date': end_date,               # string
                    'groups': target_groups,            # list of strings
                    'ics_file_data': ics_file           # string
            }

            await db.meetings_insert_record(record)

            logging.debug(f'Add Invite {record}')
            # Send the calendar/update to everyone
            # Clear the table of people that received the invite
            await db.meetings_invites_delete(uid)
    return uid


async def get_attachments(raw_email, received_groups: Sequence[str] = [],
                          send_to: Sequence[str] = []) -> TypedDict:
    msg = raw_email  # BytesParser(policy=policy.default).parsebytes(raw_email)
    uid = None
    results = []
    has_calendar = False
    if msg.is_multipart():
        for part in msg.iter_parts():
            try:
                content_type = part.get_content_type()
                if content_type == 'text/calendar':
                    method      = part.get_param('method')
                    filename    = part.get_filename()
                    try:
                        data    = part.get_content()
                    except Exception:
                        try:
                            original_encoding = part.get_content_charset()
                            data    = part.get_payload(decode=True)
                            data    = data.decode(original_encoding)
                        except Exception as e:
                            logging.exception(e)
                            logging.exception(traceback.format_exc())
                            data    = ''
                    # logging.info('GOT METHOD[filename=%s %s]: %s'%(filename, content_type, method))
                    results.append({
                        'filename': filename,
                        'content_type': content_type,
                        'method': method,
                        'data': data
                    })

                    uid = await receive_calendar(msg.as_string(), msg, received_groups, send_to, data, method)
                    has_calendar = True
            except Exception as e:
                logging.error(f'Attachment File Process exception: {str(e)}')
                logging.exception(e)
                logging.exception(traceback.format_exc())
                # Ignore if it's not a file
                pass
    return {'attachments': results, 'has_calendar': has_calendar, 'calendar_uid': uid}


def mime_email_send(subject: str, to: Sequence[str], cc: Sequence[str] = [], bcc: Sequence[str] = [],
                    text: str = None, html: str = None,
                    attachments: Sequence = [],
                    sender: str = None, send_from: str = None):
    '''
    Attachments is a list, with each entry a dictionary in the format of
    {filename, content_type, data}
    '''
    multipart_content_subtype = 'alternative' if text and html else 'mixed'
    msg = MIMEMultipart(multipart_content_subtype)
    msg['Subject'] = subject
    msg['From'] = send_from or constants.DEFAULT_FROM
    msg['To'] = ', '.join(to)
    msg['CC'] = ', '.join(cc)
    msg['BCC'] = ', '.join(bcc)
    if sender:
        msg.add_header('reply-to', sender)
    if text:
        part = MIMEText(text, 'plain')
        msg.attach(part)
        # print('Text:\n%s' %text)
    if html:
        part = MIMEText(html, 'html')
        msg.attach(part)
        # print('html:\n%s' %html)

    for attachment in attachments or []:
        maintype, subtype = attachment['content_type'].split('/', 1)
        if constants.DEBUG_MODE:
            print('Attach Mime: %s;method=%s %s' %
                  (attachment['content_type'], attachment['method'], attachment['filename']))
        if subtype == 'calendar':
            if attachment['method']:
                subtype += ';method=%s' % attachment['method']
            part = MIMEText(attachment['data'], subtype)
        elif maintype == 'text':
            part = MIMEText(attachment['data'], _subtype=subtype)
        elif maintype == 'image':
            part = MIMEImage(attachment['data'], _subtype=subtype)
        elif maintype == 'audio':
            part = MIMEAudio(attachment['data'], _subtype=subtype)
        else:
            part = MIMEBase(maintype, subtype)
            part.set_payload(attachment['data'])

        # part = MIMEApplication(attachment['data'], attachment['content_type'])
        if attachment['filename'] is not None:
            part.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
        msg.attach(part)
        print('Part: filename=%s content_type=%s' % (attachment['filename'], attachment['content_type']))

    destinations = list(set().union(to).union(cc).union(bcc))

    send_smtp(sender, destinations, msg.as_string())
    return msg


def generate_footer(sender, groups=[], users=[], html=True, group_info=None):
    # convert groups and users to HTML lists
    group_list = ''
    user_list = ''
    for group in groups:
        if group_info and group in group_info:
            info = group_info[group]
            if html:
                group_list += '<li>%s %s</li>' % (group, info['web_url'])
            else:
                group_list += '%s %s\n' % (group, info['web_url'])
        else:
            if html:
                group_list += '<li>%s</li>' % group
            else:
                group_list += '%s\n' % group
    for user in users:
        if html:
            user_list += '<li>%s</li>' % user
        else:
            user_list += '%s\n' % user
    gitlab_url = os.environ.get('gitlab_url', '')
    system_name = os.environ.get('BRANDING', 'Timelord')
    if html:
        return '''
        <br/>
        <hr/>
        <strong>Sender</strong>: {sender}
        <br/>
        <p>This message was generated by the {system_name} email system.</p>
        <p>You received this message because you are a member of a group in {gitlab_url}.
        If you believe you received this message in error, please contact the sender.</p>
        <br/>
        <strong>Groups</strong>
        <ul>
        {group_list}
        </ul>
        <strong>Members</strong>
        <ul>
        {user_list}
        </ul>
        '''
    else:
        return '''
----
Sender: {sender}

This message was generated by the {system_name} email system.
You received this message because you are a member of a group in {gitlab_url}.
If you believe you received this message in error, please contact the sender.

Groups:
{group_list}

Members:
{user_list}
'''
