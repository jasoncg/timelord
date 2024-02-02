import logging
from icalendar import Calendar
import traceback
import shared.mail_utils as mail_utils
import shared.gitlab_helpers as gitlab_helpers
import shared.cal_helpers as cal_helpers
from database import TLDatabase
db = TLDatabase()


async def refresh_invite_emails(email_uuid=None, group_name=None):
    '''
    Send out calendar invites to everyone who hasn't received it yet.
    1. Get list of calendar invites from the database
    2. Refresh group membership against each calendar invite
    3. For all who do not have an invite
    3.1 Add to send send_to envelope
    4. If send_to envelope has at least 1 entry, send the email
    '''
    try:
        logging.info('refresh_invite_emails...')
        # flush caches
        gitlab_helpers.flush_caches()

        # Get all events/emails
        if email_uuid is not None:
            meetings = await db.meetings_retrieve_record(email_uuid)
        else:
            meetings = await db.meetings_retrieve_all_records()
            
        uuids = [record["uuid"] for record in meetings]

        meeting_invites_sent = await db.meetings_invites_get(uuids)

        for m in meetings:
            try:
                # convert groups to group email addresses
                groups=gitlab_helpers.groups_to_recipients(m['groups'], as_groups=True)
                if len(groups['group_emails'])==0:
                    logging.error(f'No valid group email addresses found for {m["meeting_title"]}')
                    continue
                message_data = gitlab_helpers.clean_email_message(m['email_from'], groups['group_emails'], m['email'])
                m['email'] = message_data['message']
                groups = message_data['recipients']

                logging.info(f"Meeting: {m['meeting_title']}")
                cal = Calendar.from_ical(m['ics_file_data'])
                if cal_helpers.is_event_over(cal):
                    logging.warn(f'This meeting has past, it should be deleted')
                    logging.info(cal)
                    continue
                # groups = m['groups']

                invites_sent = set(meeting_invites_sent.get(m['uuid'], set()))
                # get the members of the group
                #group_members = gitlab_helpers.get_group_members(groups)
                # invites_emails = set(group_members['emails'])
                # groups = gitlab_helpers.groups_to_recipients(groups, True)
                invites_emails = set(groups['send_to'])

                # remove from send_to people that have already received it (in meetings_invites_sent)
                # also, don't send to the originator
                invites_emails = invites_emails-invites_sent - set([m['email_from']])
                # add all to the table
                # logging.info(f'{m} {invites_emails}')
                if len(invites_emails) > 0:
                    logging.info(f'Send email {invites_emails}')
                    mail_utils.send_smtp(m['email_from'], invites_emails, m['email'])
                    # update database to indicate that the invites were sent
                    await db.meetings_invites_set(m['uuid'], invites_emails)
            except Exception as e:
                logging.error(e)
                logging.exception(traceback.format_exc())
            finally:
                logging.info(f"Meeting {m['meeting_title']}: Done")
    finally:
        logging.info('refresh_invite_emails Done')
