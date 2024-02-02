import traceback
import aiosmtpd
import logging
from typing import AnyStr, Sequence
import shared.constants as constants
import shared.gitlab_helpers as gitlab_helpers
import shared.gitlab_wiki_helpers as wiki

from shared.mail_utils import get_attachments, send_smtp, mime_email_send
from email.utils import getaddresses
import database

from database import TLDatabase
db = TLDatabase()



async def process_email(eventinfo: dict):
    '''
    Receives an email and decide what to do with it.

    - If it's not from a valid sender (Gitlab user), ignore and return
    - If there are no valid group/distro lists (and thus no one to email), send back an error email and return
    - If there are no calendar invites, send immediately and return
    - If there are calendar invites
        - Add to database
        - Email all members of the groups, and note each recipient in the database
    '''
    mail_subject = ''
    try:
        envelope: aiosmtpd.smtp.Envelope     = eventinfo['envelope']
        message: aiosmtpd.smtp.EmailMessage  = eventinfo['message']


        # Reject email not from an approved source (must either be from a gitlab member, or on the explicit allow list)
        mail_from   = envelope.mail_from
        mail_to     = envelope.rcpt_tos
        to_addr = [email for name, email in getaddresses(mail_to)]
        to_addr = list(filter(None, to_addr))   # remove empty/invalid strings


        if len(to_addr) == 0:
            return

        mail_subject = message['Subject']
        if mail_from not in constants.EXPLICIT_ALLOW_EMAILS:
            # only allow authorized users to send to distro lists
            all_users_emails = gitlab_helpers.get_all_user_emails()
            if not (mail_from in all_users_emails):
                logging.error('Unauthorized sender [from=%s] [to=%s] [subject=%s]' % (mail_from, mail_to, mail_subject))
                return
            
        logging.info(f'process_email(subject=[{mail_subject}], mail_from={mail_from}, mail_to={mail_to})')
        
        message_data = gitlab_helpers.clean_email_message(mail_from, to_addr, eventinfo['message'])
        message = message_data['message_content_object']
        groups = message_data['recipients']

        # do not send back to the original sender ()
        # if original_from in groups['send_to']:
        #    groups['send_to'].remove(original_from)

        # build new enevelope
        # new_envelope = {'sender': mail_from, 'send_to': groups['send_to']}

        send_to = groups['send_to']

        sent_success = set()
        # Send the message
        if len(send_to) > 0:
            sent_success=send_smtp(mail_from, send_to, message.as_string())

        if len(groups['invalid_access_groups'])>0:
            errbody = f'''
Unable to send message to the following groups. 
You do not have access to send to these groups:

{groups['invalid_access_groups']}
'''
            if len(sent_success)>0:
                errbody+=f'''
Successfully sent message to these groups:

{sent_success}
'''
            mime_email_send(f"Re: {message['Subject']} - Authorization", to= [mail_from], text=errbody, sender = constants.DEFAULT_FROM)
        attachments = await get_attachments(message, groups['groups'], send_to)

        logging.info('Message processed successfully')
        # if includes a calendar, update the calendar wiki
        if attachments['has_calendar']:
            logging.info('Message has calendar')
            try:
                if attachments['calendar_uid']:
                    await db.meetings_invites_set(attachments['calendar_uid'], sent_success)
                await wiki.update_wiki_calendar_all()
            except Exception as e:
                logging.exception(traceback.format_exc())
                logging.exception(e)

    except Exception as e:
        logging.exception(traceback.format_exc())
        logging.exception(e)
        try:
            errbody = f'''
Original Subject:
{mail_subject}

Unable to process your request. Please check with the system administrator for help. 

The reported error:

{e}

            '''
            mime_email_send(f"Error processing your request", to= [mail_from], text=errbody, sender = constants.DEFAULT_FROM)
        except Exception as e:
            logging.exception(traceback.format_exc())
            logging.exception(e)


async def refresh_wiki(eventinfo: dict):
    logging.info('refresh_wiki')
    gitlab_helpers.flush_caches()
    await wiki.update_wiki_distrolists()
    await wiki.update_wiki_calendar_all()
    logging.info('refresh_wiki done')


async def refresh_invites(eventinfo: dict):
    ''' Sends an email to indicated recipients
    '''
    from refresh_emails import refresh_invite_emails
    logging.info(f'refresh_invites {eventinfo}')
    gitlab_helpers.flush_caches()
    uuid = eventinfo.get('uuid', None)
    group = eventinfo.get('group', None)
    await refresh_invite_emails(uuid, group)
    logging.info('refresh_invites DONE')

async def purge_invite(eventinfo: dict):
    uuid = eventinfo.get('uuid', None)
    if uuid is None:
        logging.error(f'purge_invite: Must provide a uuid to delete invite records')
        return
    logging.info(f'purge_invite: Delete record uuid={uuid}')
    await db.meetings_delete_record(uuid)
    logging.info('purge_invite: Done')


async def force_resend_invite(eventinfo: dict):
    uuid = eventinfo.get('uuid', None)
    if uuid is None:
        logging.error(f'force_resend_invite: Must provide a uuid to delete invite records')
        return
    await db.meetings_invites_delete(uuid)
    await refresh_invites({'uuid': uuid})

async def flush_gitlab_cache(eventinfo: dict):
    gitlab_helpers.flush_caches()


async def refresh_calendars_published(eventinfo: dict):
    '''
    Generates calendar for all invites currently in the database and publishes them to Gitlab
    '''
    gitlab_helpers.flush_caches()
    await wiki.update_wiki_calendar_all()

actions = {}
actions['receive'] = process_email
actions['refresh_wiki'] = refresh_wiki
actions['flush_gitlab_cache'] = flush_gitlab_cache
actions['refresh_invites'] = refresh_invites
actions['refresh_calendars_published'] = refresh_calendars_published
actions['force_resend_invite'] = force_resend_invite
actions['purge_invite'] = purge_invite