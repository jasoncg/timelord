import asyncio
from aiosmtpd.controller import Controller
import logging
import ssl
import pprint
import threading
import datetime
import pytz
import atexit
import signal

import shared.constants as constants
from CustomHandler import CustomHandler
from database import TLDatabase
import webhooks
from shared.actionQueueConsumer import consumer as actionQueueConsumer

if not constants.ENFORCE_SEC_CHECKS:
    constants.EXPLICIT_ALLOW_EMAILS.append('test@test.test')

pp = pprint.PrettyPrinter(indent=4)


def format_time_with_timezone(record, datefmt=None):
    dt = datetime.datetime.fromtimestamp(record.created, pytz.utc)
    local_dt = dt.astimezone(pytz.timezone('US/Eastern'))  # Replace with your desired time zone
    tz_name = local_dt.tzname()

    if datefmt:
        time_str = local_dt.strftime(datefmt)
    else:
        time_str = local_dt.strftime('%Y-%m-%d %H:%M:%S')
    return f"{time_str} {tz_name}"


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

        record.asctime = format_time_with_timezone(record, self.datefmt)
        return (
            f"{level_color}[{record.levelname}] " +
            f"({record.filename}:{record.lineno} {record.funcName})" +
            f"{self.COLORS['ENDC']} {record.message}"
        )


logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s %(levelname)s: %(module)s:%(lineno)s %(funcName)s %(message)s'))
logger.addHandler(handler)
logger.setLevel(constants.LOGGING)

if not constants.ENFORCE_SEC_CHECKS:
    logging.error('Email Security Disabled')


def smtpd_start(actionQueue, loop):
    # note that the aiosmtpd controller runs in a seperate thread,
    # and a seperate event loop, so pass the main event loop so that it
    # can properly publish events to it
    smtp_handler = CustomHandler(actionQueue, loop, constants.ENFORCE_SEC_CHECKS)
    # Create an SSL context
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=f'{constants.CERT_PATH}/cert.pem', keyfile=f'{constants.CERT_PATH}/key.pem')

    controller = Controller(smtp_handler, hostname='0.0.0.0', port=25, tls_context=ssl_context)

    controller.start()


async def main():
    loop = asyncio.get_running_loop()
    actionQueue = asyncio.PriorityQueue()
    db = TLDatabase()
    await db.initialize()

    if constants.DEBUG_MODE:
        logging.info('DEBUG_MODE ENABLED - No email will be sent')
    if constants.TEST_MODE:
        logging.info('TEST_MODE ENABLED - Emails will reflect back to the originator')

    # webhook_runner = await webhooks.run(actionQueue, loop)
    webhook_thread = threading.Thread(target=webhooks.run, args=(actionQueue, loop))
    webhook_thread.start()

    shutdown_event = asyncio.Event()

    async def shutdown_coro():
        logging.warning('Shutting down...')
        await db.close()
        logging.info('Database closed')
        # await webhook_runner.cleanup()
        logging.info('Webhook runner cleaned up')

        shutdown_event.set()

    def shutdown():
        # avoid double-shutdown, which can happen in certain circumstances
        if shutdown_event.is_set():
            return
        # loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(asyncio.create_task, shutdown_coro())

    def signal_handler(signum, frame):
        logging.warning(f'signal handler {signum} {frame}')
        shutdown()

    atexit.register(shutdown)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    loop.create_task(actionQueueConsumer(actionQueue))

    smtpd_start(actionQueue, loop)

    logging.info('Server started')
    # await actionQueue.join()
    # await consumer_task
    # logging.info('done await consumer_task')

    await shutdown_event.wait()
    logging.info('Process any remaining action queue items...')
    await actionQueue.join()

if __name__ == "__main__":
    asyncio.run(main())
