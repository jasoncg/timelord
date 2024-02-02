import email
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import getaddresses, parseaddr
import os
import traceback
from typing import Sequence, List, Dict, TypedDict
import gitlab
from icalendar import Calendar

import shared.constants as constants
from shared.datacache import DataCache
import logging

gitlab_url = os.environ.get("gitlab_url")
access_token = os.environ.get("gitlab_access_token")

gitlab_calendar_wiki_project_id = os.environ.get("gitlab_calendar_wiki_project_id")

gl = gitlab.Gitlab(gitlab_url, private_token=access_token)


def listAllGitlabGroups():
    return gl.groups.list(all=True)


def listAllGitlabUsers():
    return gl.users.list(all=True)


groupDataCache = DataCache(listAllGitlabGroups, constants.GITLAB_CACHE_TIMEOUT_SECONDS)
userDataCache = DataCache(listAllGitlabUsers, constants.GITLAB_CACHE_TIMEOUT_SECONDS)


def flush_caches():
    groupDataCache.flush()
    userDataCache.flush()
    getAllGroupsWithDomainsCache.flush()
    logging.info('gitlab_helpers.flush_caches')


def get_all_user_emails() -> Dict:
    users = userDataCache.get_data()  # gl.users.list(all=True)
    all_user_emails = {}
    for user in users:
        if user.state != 'active':
            continue
        all_user_emails[user.email] = {'is_admin': user.is_admin}
    # pp.pprint(all_user_emails)
    return all_user_emails


def get_groups_by_email():
    results = {}
    # Get all groups
    # groups = groupDataCache.get_data() #gl.groups.list(all=True)
    groups = gl.groups.list(all=True)
    # Iterate over the groups and print their names
    for group in groups:
        # make an email address from the group name. Extract only letters and numbers and dots from the group name.
        full_path = group.full_path.replace('/', '.').replace(' ', '-')
        group_name = ''.join(e for e in full_path if e.isalnum() or e == '.' or e == '-').lower()
        group_email = group_name + '@' + constants.DOMAIN
        results[group_email] = {'id': group.id, 'name': group_name, 'email': group_email, 'group': group}
    return results


groupEmailCache = DataCache(get_groups_by_email, constants.GITLAB_CACHE_TIMEOUT_SECONDS)


def get_group_by_email(email):
    groups = groupEmailCache.get_data()
    if email in groups:
        return groups[email]
    return None

def get_parent_groups(gl, group):
    parent_groups = []
    while group.parent_id:
        group = gl.groups.get(group.parent_id)
        parent_groups.append(group)
    return parent_groups

def get_group_and_ancestors_members(group, filter_access_level=None):
    results = set()
    members = group.members.list()
    users = userDataCache.get_data()
    for member in members:
        # access level is by group, so users can be in multiple groups at different access levels
        # access_level = member.access_level
        if filter_access_level is not None:
            if member.access_level < filter_access_level:
                continue
        user = None
        for u in users:
            if u.id == member.id:
                user = u
                break
        if not user:
            continue
        if user.state != 'active':
            continue
        # name = member.name
        email = user.email

        results.add(email)

    parent_groups = get_parent_groups(gl, group)

    print("\nParent Groups:")
    for parent in parent_groups:
        results.update(get_group_and_ancestors_members(parent, filter_access_level=filter_access_level))
    return results

def get_group_member_emails(group, recursive=True, filter_access_level=None):
    results = set()
    users = userDataCache.get_data()
    #members = group.members_all.list(get_all=False)
    members = group.members.list(get_all=True)

    for member in members:
        # access level is by group, so users can be in multiple groups at different access levels
        # access_level = member.access_level
        if filter_access_level is not None:
            if member.access_level < filter_access_level:
                continue
        user = None
        for u in users:
            if u.id == member.id:
                user = u
                break
        if not user:
            continue
        if user.state != 'active':
            continue
        # name = member.name
        email = user.email

        results.add(email)

    if recursive:
        descendant_groups = group.descendant_groups.list()
        for g in descendant_groups:
            desc_group = gl.groups.get(g.id)
            results = results.union(get_group_member_emails(group=desc_group, 
                                                            recursive=recursive, 
                                                            filter_access_level=filter_access_level))

    return results


def get_group_members_list(group, recursive=True, filter_access_level=None):
    results = set()
    members = group.members.list(get_all=True)
    for member in members:
        if filter_access_level is not None:
            if member.access_level < filter_access_level:
                continue

        results.add(member)
    if recursive:
        descendant_groups = group.descendant_groups.list()
        for g in descendant_groups:
            desc_group = gl.groups.get(g.id)
            results = results.union(get_group_members_list(desc_group, recursive, filter_access_level))
    return results


# Create a GitLab API client
def get_all_groups(add_domain=False, recursive=True) -> Dict:
    group_members = {}

    # Get all groups
    groups = groupDataCache.get_data()  # gl.groups.list(all=True)
    # need to get list of users to get email addresses
    users = userDataCache.get_data()  # gl.users.list(all=True)

    # Iterate over the groups and print their names
    for group in groups:
        # make an email address from the group name. Extract only letters and numbers and dots from the group name.
        full_path = group.full_path.replace('/', '.').replace(' ', '-')
        group_email = ''.join(e for e in full_path if e.isalnum() or e == '.' or e == '-').lower()
        if add_domain:
            group_email = group_email + '@' + constants.DOMAIN

        # print('Group: %s - %s' % (group.name, group_email))
        members = get_group_members_list(group, recursive)
        # members = group.members.list(all=True)
        # members = group.members_all.list(get_all=True)
        group_members[group_email] = {
            'info': group.attributes,
            'members': {}
        }
        for member in members:
            # user = gl.users.get(member.id)
            user = None
            for u in users:
                if u.id == member.id:
                    user = u
                    break
            if not user:
                continue
            if user.state != 'active':
                continue
            # name = member.name
            email = user.email
            # access level is by group, so users can be in multiple groups at different access levels
            access_level = member.access_level
            # print('  %s - %s' % (name, email))
            group_members[group_email]['members'][email] = {'access_level': access_level}
    return group_members


getAllGroupsWithDomainsCache = DataCache(get_all_groups,
                                         constants.GITLAB_CACHE_TIMEOUT_SECONDS,
                                         add_domain=True,
                                         recursive=True)

getAllGroupsWithoutDomainsCache = DataCache(get_all_groups,
                                         constants.GITLAB_CACHE_TIMEOUT_SECONDS,
                                         add_domain=False,
                                         recursive=True)


def get_group_members_direct(group_name, recursive=True, access_level=None):
    '''
    Returns a list of user email addresses for the specified group.
    recursive: if True, gets subgroups
    access_level: if set to a number, returns users with that access level or greater
    '''
    # Get all groups
    # groups = groupDataCache.get_data()  # gl.groups.list(all=True)
    gl.groups.list(all=True)
    pass


class GroupMembers(TypedDict):
    send_to: List[str]
    email: List[str]
    not_found: List[str]
    group_info: Dict


# Create a GitLab API client
def get_group_members(group_list: List[str]) -> GroupMembers:
    group_members = {}

    # Get all groups
    groups = groupDataCache.get_data()  # gl.groups.list(all=True)
    users = userDataCache.get_data()  # gl.users.list(all=True)
    emails = set()
    group_info = {}
    if '+all' in group_list:
        # send to everyone in Gitlab
        all_users = get_all_user_emails()
        group_email = '+all'
        emails.update(all_users.keys())
        group_info[group_email] = {
            'full_name': '+all',
            'web_url': ''
        }
        group_members[group_email] = list(all_users.keys())
        group_list.remove(group_email)

    if len(group_list) > 0:
        # Iterate over the groups and print their names
        for group in groups:
            # make an email address from the group name. Extract only letters and numbers from the group name.
            full_path = group.full_path.replace('/', '.').replace(' ', '-')
            group_email = ''.join(e for e in full_path if e.isalnum() or e == '.' or e == '-').lower()
            if group_email not in group_list:
                # print('Group [%s] not in group list [%s]' % (group_email, group_list))
                continue
            # group_url = group.web_url
            group_info[group_email] = {
                'full_name': group.full_name,
                'web_url': group.web_url
            }
            group_list.remove(group_email)
            # print('Group: %s - %s' % (group.name, group_email))
            members = group.members.list(all=True)
            group_members[group_email] = []
            for member in members:
                # user = gl.users.get(member.id)
                user = None
                for u in users:
                    if u.id == member.id:
                        user = u
                        break
                if not user:
                    continue
                # name = member.name
                email = user.email
                # print('  %s - %s' % (name, email))
                group_members[group_email].append(email)
                emails.add(email)

    return {'send_to': group_members, 'emails': emails, 'not_found': group_list, 'group_info': group_info}


class Recipients(TypedDict):
    groups: List[str]
    group_emails: List[str]
    send_to: List[str]
    valid: List[str]
    invalid_access_groups: List[str]

def groups_to_recipients(mail_to: Sequence[str], as_groups=False, sender=None) -> Recipients:
    '''
    Parses out a list of email addresses and identifies any Gitlab user email
    addresses that are included in those groups.
    Returns the list of valid groups, and the user email addresses
    '''
    recipients = set()

    groups: list[str] = []
    group_emails: set[str]=set()
    other_domains: list[str] = []
    invalid_groups: list[str] = []
    invalid_access_groups: set[str] = set()
    to_addr = [email for name, email in getaddresses(mail_to)]
    # all_groups =getAllGroupsWithDomainsCache.get_data()# get_all_groups(add_domain=True)
    valid_addresses = set()

    all_users = get_all_user_emails()
    sender_is_admin = False
    if sender is not None:
        sender_name = None
        (sender_name, sender) = parseaddr(sender) 
        # sender must be an admin
        if sender in all_users and all_users[sender]['is_admin']:
            sender_is_admin=True
    for target in to_addr:
        if len(target) == 0:
            continue
        # Determine if the email address is a group, or for another domain

        try:
            if as_groups:
                local_part = target
                target = f"{target}@{constants.DOMAIN}"
            else:
                parts = target.split('@')
                if len(parts) <= 1:  # not a valid email address
                    continue
                local_part = parts[0]
                if parts[1] != constants.DOMAIN:
                    other_domains.append(target)
                    valid_addresses.add(target)
                    continue

            if local_part == '+all':
                # send to everyone in Gitlab
                if sender and not sender_is_admin:
                    invalid_access_groups.add(target)
                    logging.error(f'{sender} is not authorized to send to group {target}')
                    continue
                        
                recipients.update(all_users.keys())
                groups.append('+all')
                group_emails.add(target)
                logging.info('send to all users')
                continue

            group_info = get_group_by_email(target)
            if group_info:
                if sender is not None and not sender_is_admin:
                    # only direct or parent members can send 
                    #group_senders = get_group_member_emails(group=group_info['group'], 
                    #                                    recursive=False, 
                    #                                    inherited=True,
                    #                                    filter_access_level=None)
                    group_senders = get_group_and_ancestors_members(group=group_info['group'])
                    if sender not in group_senders:
                        invalid_access_groups.add(target)
                        logging.error(f'{sender} is not authorized to send to group {target}')
                        logging.info(group_senders)
                        continue

                # recursive members receive
                group_members = get_group_member_emails(group=group_info['group'], 
                                                        recursive=True, 
                                                        filter_access_level=None)
                groups.append(group_info['name'])
                group_emails.add(target)
                recipients.update(group_members)
                logging.debug(group_members)
            else:
                logging.error(f'Group not found {target}')
        except Exception as e:
            # likely an invalid address, ignore it
            if constants.DEBUG_MODE:
                import traceback
                logging.exception('')
                traceback.print_exception(type(e), e, e.__traceback__)
    if len(invalid_groups) > 0:
        logging.error(f'groups_to_recipients(groups={groups}) Invalid => {invalid_groups}')
    logging.debug(f'groups_to_recipients(groups={groups}) => recipients={recipients})')

    # If a recepient was in the original envelope, then don't send
    # from this system because they'll receive multiple copies
    recipients = recipients - valid_addresses

    return {'groups': groups, 'group_emails':group_emails, 'valid': valid_addresses, 'send_to': recipients, 'invalid_access_groups': invalid_access_groups}


class MessageData(TypedDict):
    message_content: str
    message_content_object: email.message.Message
    recipients: Recipients

def clean_email_message(mail_from:str, to_addr:Sequence[str], message_content: str) -> MessageData | None:# -> aiosmtpd.smtp.EmailMessage
    '''
    Modifies the provided email message to a form appropriate for storage and forwarding.

    Returns the updated message, actual To list for the envelope 
    '''
    if isinstance(message_content, email.message.Message):
        message = message_content
    else:
        try:
            message = email.message_from_bytes(message_content, email.policy.default)
        except Exception:
            try:
                message = email.message_from_string(message_content)
            except Exception as e:
                logging.exception(e)
                return None

    # Remove the headers that need to be rebuilt
    strip_headers = [          
        # (without doing this, Google Workspace silently rejects messages, 
        #  probably because later modifications to the message invalidate these signatures)
        "ARC-Authentication-Results",
        "ARC-Message-Signature",
        "ARC-Seal",
        "DKIM-Signature",

        # For AWS SES to not complain about the sender and return path
        "Return-Path",
        "Source",
        "Sender"
    ]
    # Strip out the ARC and DKIM headers
    for header in strip_headers:
        try:
            del message[header]
        except Exception:
            pass

    original_from = message["From"]

    if original_from != constants.DEFAULT_FROM:
        message.replace_header("From", constants.DEFAULT_FROM)
        message.add_header("Reply-To", original_from)
        message.add_header("X-Original-Sender", original_from)
    else:
        if 'Reply-To' in message:
            (sender_name, sender) = parseaddr(message['Reply-To']) 
            original_from = sender
    if mail_from == constants.DEFAULT_FROM:
        if 'Reply-To' in message:
            (sender_name, sender) = parseaddr(message['Reply-To']) 
            mail_from = sender
        elif 'X-Original-Sender' in message:
            (sender_name, sender) = parseaddr(message['X-Original-Sender']) 
            mail_from = sender

    groups: list[str] = []

    if mail_from not in constants.EXPLICIT_ALLOW_EMAILS:
        groups = groups_to_recipients(mail_to=to_addr, sender=mail_from)
    else:
        # allow certain senders to send to any group
        groups = groups_to_recipients(mail_to=to_addr)

    # Replace the message body To: with only the groups we are sending to
    try:
        message.replace_header("To", ', '.join(groups['group_emails']))
    except Exception as e:
        logging.exception(traceback.format_exc())
        logging.exception(e)

    try:
        # Remove CC entirely
        del message["Cc"]
    except Exception:
        pass
    try:
        # Remove BCC entirely (shouldn't actually exist, but just in case)
        del message["Bcc"]
    except Exception:
        pass

    # Update any embedded iCalendar file with the actual attendee list
    # Step 1: Extract iCalendar data
    if message.is_multipart():
        ical_content = None
        content_type = None
        original_part = None
        original_encoding = None
        cal_method = None
        if hasattr(message, 'iter_parts'):  # For aiosmtpd.smtp.EmailMessage
            parts_iterator = message.iter_parts()
        else:  # For email.message.Message
            parts_iterator = message.walk()
        for part in parts_iterator:
            content_type = part.get_content_type()
            if content_type == 'text/calendar':
                logging.info(f'Found calendar attachment')
                original_part = part
                try:
                    cal_method          = part.get_param('method', None)
                    original_encoding   = part.get_content_charset()
                    ical_content        = part.get_payload(decode=True) #.decode('utf-8')
                    break
                except Exception as e:
                    logging.error(f'Problem extracting embedded iCalendar data')
                    logging.exception(e)
                    logging.exception(traceback.format_exc())
        if ical_content:
            try:
                # Parse the iCalendar content
                cal = Calendar.from_ical(ical_content)

                for component in cal.walk():
                    if component.name == "VEVENT":
                        if 'ATTENDEE' in component:
                            logging.warn(f"Old Attendee List: [{component['ATTENDEE']}]")
                            # Remove all existing 'ATTENDEE' properties
                            del component['ATTENDEE']

                        # Add each attendee individually, prefixed with 'mailto:'
                        for attendee in groups['send_to']:
                            formatted_attendee = f"mailto:{attendee}"
                            component.add('ATTENDEE', formatted_attendee)
                        if 'ATTENDEE' in component:
                            logging.warn(f"NEW Attendee List: [{component['ATTENDEE']}]")

                # Serialize the modified iCalendar content
                new_ical_content = cal.to_ical().decode(original_encoding)
                if hasattr(message, 'iter_parts'):  # For aiosmtpd.smtp.EmailMessage
                    parts_iterator = message.iter_parts()
                else:  # For email.message.Message
                    parts_iterator = message.walk()

                if original_part is not None:
                    # Clone original MIME headers, then update the payload
                    new_part = MIMEText(new_ical_content, 'calendar', original_encoding)
                    if cal_method:
                        new_part.set_param('method', cal_method)
                    #new_part = MIMEBase('text', 'calendar')
                    #part.set_payload(new_ical_content)
                    for key, value in original_part.items():
                        new_part[key] = value

                    #email.encoders.encode_base64(new_part)
                    #original_part.set_payload(new_ical_content, original_encoding)

                    # Remove the original calendar part from the payload
                    message.get_payload().remove(original_part)

                    # Attach the new part with updated payload but original MIME headers
                    message.attach(new_part)

            except Exception as e:
                logging.error(f'Problem updating embedded iCalendar data')
                logging.exception(e)
                logging.exception(traceback.format_exc())
                
    return {
        'message': message.as_string(),
        'message_content_object': message,
        'recipients': groups
    }

