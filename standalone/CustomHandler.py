from email.parser import BytesParser
from email import policy
from dkim import DKIM
import spf
import dmarc
import logging
from concurrent.futures import ThreadPoolExecutor
import aiosmtpd 

import shared.specialHandlers as specialHandlers
# from shared.mail_utils import *
from database import TLDatabase

db = TLDatabase()
'''
Special Handlers intercept inbound messages and can perform special actions,
such as generating an response
'''
special = {
    '+admin': specialHandlers.specialHandlerAdmin,
    '+getgroups': specialHandlers.specialHandlerGetGroups,
    '+all': specialHandlers.specialHandlerAll,
    '+ooo': specialHandlers.specialHandlerOutOfOffice
}


class CustomHandler:
    def __init__(self, actionQueue, eventLoop, enforce_security=True):
        self.executor = ThreadPoolExecutor()
        self.actionQueue = actionQueue
        self.eventLoop = eventLoop
        self.enforce_security = enforce_security

    async def handle_RCPT(self, server, session, envelope, address,
                          rcpt_options):
        # if not address.endswith('@%s' % constants.DOMAIN):
        #    return '550 not relaying to that domain'
        if not self.enforce_security and session.peer[0] == '127.0.0.1':
            logging.error('Security Enforcement Disabled')
            envelope.rcpt_tos.append(address)
            return '250 OK'

        # Validate SPF
        result = spf.check2(
            i=session.peer[0],
            s=envelope.mail_from,
            h=session.peer[1]
        )
        if result[0] != 'pass':
            logging.error(f'550 SPF check failed i={session.peer[0]} ' +
                          f's={ envelope.mail_from } h={session.peer[1]} result={result}')
            return '550 SPF check failed'

        envelope.rcpt_tos.append(address)
        return '250 OK'

    async def handle_DATA(self, server:aiosmtpd.smtp.SMTP, session:aiosmtpd.smtp.Session, envelope:aiosmtpd.smtp.Envelope) -> str:
        # See https://aiosmtpd-pepoluan.readthedocs.io/en/latest/concepts.html#Envelope
        try:
            # Validate DKIM
            parser = BytesParser(policy=policy.default)
            message = parser.parsebytes(envelope.content)
            if not self.enforce_security and session.peer[0] != '127.0.0.1':
                try:
                    result = DKIM.verify(message)
                    if not result:
                        logging.error('550 DKIM validation failed')
                        return '550 DKIM validation failed'
                except DKIM.DKIMException as e:
                    logging.error(f'550 DKIM exception: {str(e)}')
                    return f'550 DKIM exception: {str(e)}'

                # Validate DMARC
                from_addr = envelope.mail_from
                dmarc_result = dmarc.dmarc_validate(from_addr, message)
                if dmarc_result != 'pass':
                    return '550 DMARC validation failed'

            logging.info(f'Message from: {envelope.mail_from}')
            logging.info(f'Message for: {envelope.rcpt_tos}')

            # At this point the message has passed SPF, DKIM, and DMARC, but that's no guarantee that we will actually
            # do something with this message.

            # Push the message to the action queue in the main event loop
            self.eventLoop.call_soon_threadsafe(self.actionQueue.put_nowait,
                                                (1, {'action': 'receive', 'envelope': envelope, 'message': message}))

            return '250 Message accepted for delivery'
        except Exception as e:
            import traceback
            logging.error(f'Failed to process email: {str(e)}')
            logging.exception('')
            if not self.eventLoop:
                logging.error('The event loop is not running')
            traceback.print_exception(type(e), e, e.__traceback__)
            return '451 Temporary failure, please try again later'
