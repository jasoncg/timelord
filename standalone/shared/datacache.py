from datetime import datetime, timedelta


class DataCache:
    def __init__(self, fetch_function, timeout_seconds=60, *fetch_function_args, **fetch_function_kwags):
        self.fetch_function = fetch_function
        self.fetch_function_args = fetch_function_args
        self.fetch_function_kwags = fetch_function_kwags

        self.timeout_seconds = timeout_seconds
        self.last_updated = datetime.min
        self.cached_data = None

    def flush(self):
        self.last_updated = datetime.min

    def get_data(self):
        # Check if it's been more than the timeout_minutes since the last update
        if datetime.now() - self.last_updated > timedelta(seconds=self.timeout_seconds):
            # If it has, get fresh data using the provided fetch_function
            self.cached_data = self.fetch_function(*self.fetch_function_args, **self.fetch_function_kwags)
            self.last_updated = datetime.now()

        return self.cached_data
