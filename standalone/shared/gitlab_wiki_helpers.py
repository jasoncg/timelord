# import shared.constants as constants
import shared.gitlab_helpers as gitlab_helpers
from database import TLDatabase
from icalendar import Calendar
# from dateutil.rrule import *
from email.parser import BytesParser
from email import policy, message
import shared.cal_helpers as cal_helpers
import logging
import traceback
import os
db = TLDatabase()


def get_calendar_project():
    # Get a project by ID
    project_id = gitlab_helpers.gitlab_calendar_wiki_project_id
    project = gitlab_helpers.gl.projects.get(project_id)
    if not project:
        raise f'Unable to find Calendar Project {project_id}'
    return project


def to_html_ul(elements):
    string = "<ul>"
    string += "".join(["<li>" + str(s) + "</li>" for s in elements])
    string += "</ul>"
    return string


def get_email_body(email_obj: message.EmailMessage):
    try:
        if email_obj.is_multipart():
            results = ''
            for part in email_obj.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                # Skip any part that is an attachment or not plain text
                if "attachment" not in content_disposition and content_type == "text/plain":
                    body = part.get_payload(decode=True)
                    results += f"{body.decode('utf-8', errors='replace')}\n"
            return results
        else:
            # If the email is not multipart, simply get the payload
            body = email_obj.get_payload(decode=True)
            return body.decode('utf-8', errors='replace')
    except Exception as e:
        logging.error(e)
        logging.exception(traceback.format_exc())
        return f'Invalid message {e}'


async def update_wiki_distrolists():
    page_slug = 'Distribution Lists'
    logging.info(f'update_wiki_distrolists: Updating {page_slug}')
    try:
        project = get_calendar_project()
        # Get all distro lists
        #groups = gitlab_helpers.get_all_groups(True, True)
        groups = gitlab_helpers.getAllGroupsWithDomainsCache.get_data()

        # logging.info(groups)
        content = "<!-- WARNING: Do not edit this page. Timelord will overwrite changes the next time it runs.-->"
        content += "<table>\n"
        content += "<tr><th>Group</th><th>Email Address</th><th>Members</th></tr>\n"
        for g in groups.keys():
            group_info = groups[g]['info']
            content += f'''
<tr>
<td><a href="{group_info['web_url']}">{group_info['full_name']}</a></td>
<td><a href="mailto:{g}">{g}</a></td>
<td>
'''
            for m in groups[g]['members']:
                content += f'<p>{m}</p>\n'
            content += '''
</td>
</tr>
'''
        content += "</table>"

        try:
            page = project.wikis.get(page_slug)
            if page.content == content:
                # no changes, so skip update
                return
            page.content = content
            # logging.info(f'Updating {page_slug} DONE')
        except Exception as e:
            # Create
            page = project.wikis.create({'title': page_slug,
                                        'content': content})
        page.save()
    finally:
        logging.info(f'Updating {page_slug} DONE')

async def delete_all_calendar_pages(project):
    ''' 
    There seems to be a bug with Gitlab Python API or the Gitlab API where it can't properly update wiki pages in certain cases, so this deletes
    all meeting pages.
    '''
    logging.info('delete_all_calendar_pages: Start')
    try:
        pages = project.wikis.list()
        for p in pages:
            if p.slug[:8]=='meetings':
                p.delete()
    except Exception as e:
            logging.error(e)
            logging.exception(traceback.format_exc())
    finally:
        logging.info('delete_all_calendar_pages: Done')



async def update_wiki_calendar_invite_page(project, meeting, cal, events, 
                                           recurr_details, meeting_invites_sent,
                                           table_row):
    '''
    Lists the details for a particular event
    '''
    page_slug = f"meetings/{meeting['uuid']}"
    try:
        logging.info(f'update_wiki_calendar_invite_page: Updating {page_slug}')

        content = "<table>\n"
        content += "<tr><th>Sender</th><th>Groups</th><th>Date/Time</th><th>Frequency</th></tr>"
        content += table_row
        content += "</table>\n"
        content += "# Details\n"
        email_body = ''

        try:
            # email_content=m['email'].decode('utf-8', errors='replace')
            msg = meeting['email']
            msg = msg[2:-1]  # Removing the leading b' and trailing '
            msg_bytes = msg.encode().decode('unicode_escape').encode()
            parser = BytesParser(policy=policy.default)
            email_message = parser.parsebytes(msg_bytes)

            email_body = get_email_body(email_message)
        except Exception as e:
            logging.error(e)
            logging.exception(traceback.format_exc())
            email_body = e

        content += f"{email_body}"

        content += "# Invites Sent\n"
        for entry in meeting_invites_sent:
            content += f" - {entry}\n"

        try:
            page = project.wikis.get(page_slug)
            if page.content == content:
                # no changes, so skip update
                return
            page.content = content
            page.save()
        except Exception as e:
            # create the page
            page = project.wikis.create({
                                        'title': page_slug,
                                        'content': content})
            page.save()
    except Exception as e:
        logging.exception(e)
        logging.exception(traceback.format_exc())
    finally:
        logging.info(f'update_wiki_calendar_invite_page: Done updating {page_slug}')

async def update_wiki_group_page(group_email, group_info):
    '''
    Lists the details for a particular group, and all the events that group is invited to
    '''
    page_slug = f"groups/{group_email}"
    logging.info(f'update_wiki_group_page: Updating {page_slug}')
    project = get_calendar_project()

    # get group info
    authorized_senders = gitlab_helpers.get_group_and_ancestors_members(group_info['info'])
    group_members = gitlab_helpers.get_group_member_emails(group=group_info['info'], 
                                            recursive=True, 
                                            filter_access_level=None)
    
    content=f'''
# {group_info['info']['name']}
## {group_email}
<table><tr><th>Authorized Senders</th><th>Members</th></tr>
<tr>
<td>{authorized_senders}</td>
<td>{group_members}</td>
</tr>
</table>
'''

    # get all meetings for the group
    meetings = await db.meetings_retrieve_all_records()
    group_meetings = []
    for record in meetings:
        groups = record['groups'].split(',')
        if group_email not in groups:
            continue
        group_meetings.append(record)

    uuids = [record["uuid"] for record in group_meetings]

    try:
        content+='''
# Meetings
<table>
'''
        for m in group_meetings:
            (table_row, cal, events, recurr_details) = build_meeting_info(m, groups)
            if not table_row:
                continue
            content+= table_row
        
        content+='''
</table>
'''

        try:
            page = project.wikis.get(page_slug)
            if page.content == content:
                # no changes, so skip update
                return
            page.content = content
            page.save()
        except Exception as e:
            # create the page
            page = project.wikis.create({
                                        'title': page_slug,
                                        'content': content})
            page.save()
    except Exception as e:
        logging.exception(e)
        logging.exception(traceback.format_exc())
    finally:
        logging.info(f'update_wiki_group_page: Done updating {page_slug}')

def build_meeting_info(m,groups):
    '''
    Extracts details about a particular meeting and returns a table
    '''
    table_row, cal, events, recurr_details =(None,None,None, None)
    try:
        cal = Calendar.from_ical(m['ics_file_data'])
        if cal_helpers.is_event_over(cal):  # skip past events
            return table_row, cal, events, recurr_details
        events = cal_helpers.parse_ics(cal)

        try:
            recurr_details = cal_helpers.getRecurrenceDetails(cal)
        except Exception as e:
            logging.exception(e)
            print(traceback.format_exc())
            recurr_details = []

        if len(recurr_details) >= 1:
            recurr_details = recurr_details[0]
        else:
            recurr_details = ''

        target_groups = []
        for g in m['groups']:
            try:
                group_info = groups[g]['info']
                # target_groups.append(f"<a href=\"{group_info['web_url']}\">{group_info['full_name']}</a>")
                target_groups.append(f"<a href=\"groups/{group_info['id']}\">{group_info['full_name']}</a>")
            except Exception:
                target_groups.append(g)
        target_groups = to_html_ul(target_groups)
        for event in events:
            summary, sender, attendees, dtstart, dtend = event
            if summary is None or len(summary) < 1:
                summary = m['meeting_title']
            if sender is None:
                sender = m['email_from']
            if dtstart:
                dtstart = f'From {dtstart.strftime("%A, %b %d %I:%M%p %Z")}'
            if dtend:
                dtend = f'To {dtend.strftime("%I:%M%p %Z")}'
            # <td><p>{" ".join(attendees)}</p><p>{target_groups}</p></td>
            table_row = f'''
<tr><td colspan="4">[{summary}](./meetings/{m['uuid']})</td></tr>
<tr>
<td>{sender}</td>
<td>{target_groups}</td>
<td>{dtstart} {dtend}</td>
<td>{recurr_details}</td>
</tr>'''
    except Exception as e:
        logging.exception(e)
        logging.error(traceback.format_exc())
        table_row = "<tr><td cols='5'>Invalid Calendar Data</td></tr>"
    return table_row, cal, events, recurr_details

async def update_wiki_calendar_all():
    page_slug = 'home'
    logging.info(f'update_wiki_calendar_all: Updating {page_slug}')
    try:
        # await update_wiki_calendar_distrolists()

        groups = gitlab_helpers.getAllGroupsWithoutDomainsCache.get_data()
        for g in groups:
            await update_wiki_group_page(g, groups[g])
            
        project = get_calendar_project()
        await delete_all_calendar_pages(project)

        # get calendars saved in database
        meetings = await db.meetings_retrieve_all_records()
        uuids = [record["uuid"] for record in meetings]
        all_meeting_invites_sent = await db.meetings_invites_get(uuids)

        system_name = os.environ.get('BRANDING', 'Timelord')
        content = "Program Calendar\n" % system_name

        if len(meetings) == 0:
            content += "No scheduled meetings"
        else:
            content += "<table>"
            content += "<tr><th>Sender</th><th>Groups</th><th>Date/Time</th><th>Frequency</th></tr>"

            for m in meetings:
                (table_row, cal, events, recurr_details) = build_meeting_info(m, groups)
                if not table_row:
                    continue
                content+= table_row
                invites_sent = set(all_meeting_invites_sent.get(m['uuid'], set()))
                await update_wiki_calendar_invite_page(project, m, cal, events, recurr_details, invites_sent, table_row)

            content += "</table>"

        try:
            page = project.wikis.get(page_slug)
            if page.content == content:
                # no changes, so skip update
                return
            page.content = content
        except Exception:
            # create the page
            page = project.wikis.create({'title': page_slug,
                                        'content': content})
        page.save()
    finally:
        logging.info(f'update_wiki_calendar_all: Updating {page_slug} DONE')

