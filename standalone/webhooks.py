from aiohttp import web
import logging
import asyncio
import json
import shared.gitlab_helpers as gitlab_helpers
import shared.mail_utils as mail_utils

async def handle_gitlab_test(request: web.Request):
    logging.info(request)
    # await request.app['actionQueue'].put((10, {'action':'test'}))
    request.app['mainEventLoop'].call_soon_threadsafe(request.app['actionQueue'].put_nowait,
                                                      (10, {'action': 'test'}))
    return web.Response(text='Request received')


async def handle_refresh_wiki(request: web.Request):
    '''
    Refreshes calendars and meeting info on the Gitlab Wiki
    '''
    logging.info(request)
    # await request.app['actionQueue'].put((10, {'action':'test'}))
    request.app['mainEventLoop'].call_soon_threadsafe(request.app['actionQueue'].put_nowait,
                                                      (10, {'action': 'refresh_wiki'}))
    return web.Response(text='Request received')


async def handle_gitlab_flush(request: web.Request):
    '''
    Forces flush of Python caches
    '''
    # flush gitlab caches, high-priority
    # await request.app['actionQueue'].put((0, {'action':'flush_gitlab_cache'}))
    request.app['mainEventLoop'].call_soon_threadsafe(request.app['actionQueue'].put_nowait,
                                                      (0, {'action': 'flush_gitlab_cache'}))
    return web.Response(text='Request received')

'''
            uuid TEXT PRIMARY KEY,
            meeting_title TEXT,
            email_from TEXT,
            email TEXT,
            recurr BOOLEAN,
            end_date TEXT,
            groups TEXT,
            ics_file_data TEXT'''

async def handle_force_resend_email(request: web.Request):
    try:
        # Extract JSON payload from the request
        payload = await request.json()
        logging.info(payload)

        uuid=None
        meeting_title = None
        if 'uuid' in payload:
            uuid = payload['uuid']
        elif 'meeting_title' in payload:
            bmeeting_title = payload['meeting_title']
        
        if uuid is None and meeting_title is None:
            logging.error(f'Need either a uuid or meeting_title to force resend')
        else:
            request.app['mainEventLoop'].call_soon_threadsafe(request.app['actionQueue'].put_nowait,
                                                            (0, {'action': 'force_resend_invite', 
                                                                 'uuid':uuid, 
                                                                 'meeting_title':meeting_title}))
    except Exception:
        pass


    return web.Response(text='Request received')

async def handle_purge_email(request: web.Request):
    try:
        # Extract JSON payload from the request
        payload = await request.json()
        logging.info(payload)

        uuid=None
        if 'uuid' in payload:
            uuid = payload['uuid']
        
        if uuid is None:
            logging.error(f'Need a uuid to delete')
        else:
            request.app['mainEventLoop'].call_soon_threadsafe(request.app['actionQueue'].put_nowait,
                                                            (0, {'action': 'purge_invite', 
                                                                 'uuid':uuid
                                                                 }))
    except Exception:
        pass
    return web.Response(text='Request received')

async def handle_refresh_email(request: web.Request):
    # flush gitlab caches, high-priority
    # await request.app['actionQueue'].put((0, {'action':'flush_gitlab_cache'}))
    try:
        # Extract JSON payload from the request
        payload = await request.json()
        logging.info(payload)
    except Exception:
        pass

    request.app['mainEventLoop'].call_soon_threadsafe(request.app['actionQueue'].put_nowait,
                                                      (0, {'action': 'refresh_invites'}))

    return web.Response(text='Request received')
async def handle_get_admins(request: web.Request):
    '''
curl --header "Content-Type: application/json" \
--request POST \
--data '{"from":"sender@example.com","to":["group1@example.com", "group2@example.com"]}' \
http://localhost:8080/get-admins
    '''
    try:
        # Extract JSON payload from the request
        payload = await request.json()
        logging.info(payload)
        from_addr = payload['from']
        to_addr=payload['to']
        print(f'from_addr={from_addr}\nto_addr={to_addr}')
        groups = gitlab_helpers.groups_to_recipients(mail_to=to_addr, sender=from_addr)
        #return web.json_response(groups, default=list)
        json_str =json.dumps(groups, default=list)
        return web.Response(text=json_str, content_type='application/json')
    except Exception:
        logging.error('no payload')
        return web.json_response({'text':'no payload', 'type':'error'})

async def handle_send_message(request: web.Request):
    '''
    Sends an email from the specified email address, to the specified groups

    payload json:
    {
        'from': 'user@example.com',             # Must be a registerd / active user address
        'to': ['email1@example.com', '...'],    # May be groups or any valid email address
        'subject': '...',
        'body': '...'
    }
curl --header "Content-Type: application/json" \
--request POST \
--data '{"from":"sender@example.com","to":["group1@example.com", "group2@example.com"], "subject":"Test email", "text":"body of message"}' \
http://localhost:8080/send_message

    mime_email_send(subject: str, to: Sequence[str], cc: Sequence[str] = [], bcc: Sequence[str] = [],
                    text: str = None, html: str = None,
                    attachments: Sequence = [],
                    sender: str = None, send_from: str = None):
    '''
    try:
        # Extract JSON payload from the request
        payload = await request.json()
        logging.info(payload)

        from_addr = payload['sender']
        subject = payload['subject']

        groups_to = gitlab_helpers.groups_to_recipients(mail_to=payload['to'], sender=from_addr) if 'to' in payload else None
        groups_cc = gitlab_helpers.groups_to_recipients(mail_to=payload['cc'], sender=from_addr) if 'cc' in payload else None
        groups_bcc = gitlab_helpers.groups_to_recipients(mail_to=payload['bcc'], sender=from_addr) if 'bcc' in payload else None

        payload['to'] = set()
        payload['cc'] = set()
        payload['bcc'] = set()
        if groups_to:
            payload['to'] = groups_to['send_to']
            # payload['to'].update(groups_to['valid'])
        if groups_cc:
            payload['cc'] = groups_cc['send_to']
            # payload['cc'].update(groups_cc['valid'])
        if groups_bcc:
            payload['bcc'] = groups_bcc['send_to']
            # payload['bcc'].update(groups_bcc['valid'])

        logging.info(payload)
        all_receive = set()
        all_receive.update(payload['to'])
        all_receive.update(payload['cc'])
        all_receive.update(payload['bcc'])
        if len(all_receive) == 0:
            logging.warn('No one to send to')
        print(f'{subject} :: from_addr={from_addr}\nto_addr={all_receive}')
        mail_utils.mime_email_send(**payload)
        json_str =json.dumps(all_receive, default=list)
        return web.Response(text=json_str, content_type='application/json')
    except Exception as e:
        logging.error(e)
        return web.json_response({'text':e, 'type':'error'})
async def handle_gitlab_member_hook(request: web.Request):
    '''
    Send out calendar invites to everyone who hasn't received it yet.
    1. Get list of calendar invites from the database
    2. Refresh group membership against each calendar invite
    3. For all who do not have an invite
    3.1 Add to send send_to envelope
    4. If send_to envelope has at least 1 entry, send the email
    '''

    # Extract JSON payload from the request
    payload = await request.json()

    # flush gitlab caches, high-priority
    # await request.app['actionQueue'].put((0, {'action':'flush_gitlab_cache'}))
    request.app['mainEventLoop'].call_soon_threadsafe(request.app['actionQueue'].put_nowait,
                                                      (0, {'action': 'flush_gitlab_cache'}))

    event_name = payload['event_name']
    if event_name == 'user_update_for_group':
        # user was added to a group. Refresh all group invites.
        # refresh_emails.refresh_invite_emails()
        request.app['mainEventLoop'].call_soon_threadsafe(request.app['actionQueue'].put_nowait,
                                                          (0, {'action': 'refresh_invites'}))

    elif event_name == 'user_remove_from_group':
        # user was removed from a group. Remove from tables
        pass
    else:
        logging.error(f'Unhandled gitlab-member-hook: {event_name}')
        # raise web.HTTPClientError()

    return web.Response()

'''
async def handle_gitlab_webhook(request: web.Request):
    # Extract JSON payload from the request
    payload = await request.json()

    # TODO: Process the payload as needed for your application
    # ...

    return web.Response(text='Webhook received')
'''


def run(actionQueue: asyncio.PriorityQueue, mainEventLoop, interface='0.0.0.0', port=8080):
    '''
    An extremely basic web server
    '''
    async def start():
        app = web.Application()

        # aiohttp supports variables added to the app, making them accessible to handlers
        app['actionQueue'] = actionQueue
        app['mainEventLoop'] = mainEventLoop

        app.router.add_post('/gitlab-member-hook', handle_gitlab_member_hook)
        # app.router.add_post('/gitlab-webhook', handle_gitlab_webhook)

        app.router.add_post('/purge-email', handle_purge_email)

        app.router.add_post('/refresh-email', handle_refresh_email)
        app.router.add_get('/refresh-email', handle_refresh_email)
        
        app.router.add_post('/force-resend-email', handle_force_resend_email)

        app.router.add_get('/refresh-wiki', handle_refresh_wiki)
        app.router.add_post('/refresh-wiki', handle_refresh_wiki)

        app.router.add_get('/test', handle_gitlab_test)
        app.router.add_get('/flush', handle_gitlab_flush)

        app.router.add_post('/get-admins', handle_get_admins)
        app.router.add_post('/send-message', handle_send_message)
        # Create and start web server
        runner = web.AppRunner(app)

        await runner.setup()

        site = web.TCPSite(runner, interface, port)  # Choose an appropriate port

        await site.start()

        return runner
    loop = asyncio.new_event_loop()
    runner = loop.run_until_complete(start())
    loop.run_forever()
    return runner
