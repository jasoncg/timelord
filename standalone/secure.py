import asyncio
from aiosmtpd.controller import Controller
from dkim import DKIM
import spf
import dmarc
import ssl

# For testing, security checks can be disable if coming from localhost
ENFORCE_SEC_CHECKS = True


class CustomHandler:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        # if not ENFORCE_SEC_CHECKS:
        #    return '250 OK'
        if not ENFORCE_SEC_CHECKS and session.peer[0] == '127.0.0.1':
            envelope.rcpt_tos.append(address)
            return '250 OK'

        # Validate SPF
        result = spf.check(
            i=session.peer[0],
            s=envelope.mail_from,
            h=session.peer[1]
        )
        if result != 'pass':
            return '550 SPF check failed'

        return '250 OK'

    async def handle_DATA(self, server, session, envelope):
        # Validate DKIM
        message = bytes(envelope.original_content)
        if not ENFORCE_SEC_CHECKS and session.peer[0] != '127.0.0.1':
            try:
                result = DKIM.verify(message)
                if not result:
                    return '550 DKIM validation failed'
            except DKIM.DKIMException as e:
                return f'550 DKIM exception: {str(e)}'

            # Validate DMARC
            from_addr = envelope.mail_from
            dmarc_result = dmarc.dmarc_validate(from_addr, message)
            if dmarc_result != 'pass':
                return '550 DMARC validation failed'

        print("Email received:", envelope.content.decode('utf-8', errors='replace'))
        return '250 Message accepted for delivery'


# Create an SSL context
ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ssl_context.load_cert_chain(certfile='standalone/certs/cert.pem', keyfile='standalone/certs/key.pem')

controller = Controller(handler=CustomHandler(), hostname='0.0.0.0', port=25, tls_context=ssl_context)
controller.start()
try:
    asyncio.get_event_loop().run_forever()
except KeyboardInterrupt:
    pass
finally:
    controller.stop()
