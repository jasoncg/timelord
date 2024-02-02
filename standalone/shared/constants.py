# For testing, security checks can be disable if coming from localhost
ENFORCE_SEC_CHECKS = True

# In test mode, all emails reflect back to the sender.
TEST_MODE = True

# Debug mode won't send any email, and won't delete any email from s3
DEBUG_MODE = True

LOGGING = 'DEBUG'

# @todo - use environment variable or .env file
DOMAIN = ''
DEFAULT_FROM = ''

# REGION = 'us-east-1'
# Normally, only emails registerd in gitlab will be allowed to send to distro lists.
# However, if the sender is in this list, they will be allowed to send to distro lists.
# Seperate with commas
EXPLICIT_ALLOW_EMAILS = ''

CERT_PATH = './certs'
DB_PATH = '/app/database/timelord.db'

GITLAB_CACHE_TIMEOUT_SECONDS = (10*60)


def set_constants():
    import os
    import logging
    global_vars = globals()
    for var_name in [
        'BRANDING', 'GITLAB_CALENDAR_WIKI_PROJECT_URL',
        'ENFORCE_SEC_CHECKS', 'TEST_MODE', 'DEBUG_MODE',
        'DOMAIN', 'DEFAULT_FROM', 'EXPLICIT_ALLOW_EMAILS',
        'DB_PATH', 'CERT_PATH',
        'LOGGING',
        'GITLAB_CACHE_TIMEOUT_SECONDS'
    ]:
        if var_name in os.environ:
            try:
                global_vars[var_name] = os.environ[var_name].strip()
            except Exception:
                logging.exception('')
        try:
            if isinstance(global_vars[var_name], str):
                # Convert boolean strings into Python booleans
                if global_vars[var_name].lower() == 'true':
                    global_vars[var_name] = True
                elif global_vars[var_name].lower() == 'false':
                    global_vars[var_name] = False
        except Exception:
            pass
    try:
        # remove spaces, and split into an array
        global_vars['EXPLICIT_ALLOW_EMAILS'] = global_vars['EXPLICIT_ALLOW_EMAILS'].replace(" ", "").split(',')
    except Exception:
        logging.exception('')


set_constants()
