import logging
import traceback
from shared.actionQueueActions import actions


async def consumer(queue):
    '''
    For the life of the program, waits for events from the queue and processes them
    '''
    while True:
        try:
            # Wait for the next action
            (priority, getevent) = await queue.get()

            logging.info(f'actionQueueConsumer got event priority={priority} {getevent}')

            if getevent['action'] in actions:
                try:
                    await actions[getevent['action']](getevent)
                except Exception as e:
                    logging.exception(traceback.format_exc())
                    logging.error(f'Fatal error processing event {getevent["action"]}', exc_info=e)
            else:
                logging.error(f'Unhandled action event type {getevent["action"]}')
            # notify the queue that we are done
            queue.task_done()
        except Exception as e:
            logging.exception(traceback.format_exc())
            logging.error(f'Fatal error processing event {getevent["action"]}', exc_info=e)
