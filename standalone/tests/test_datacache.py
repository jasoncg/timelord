from datetime import datetime, timedelta
# import pytest
from shared.datacache import DataCache


def fetch_function_example(*args, **kwargs):
    return 'data'


def test_data_cache():
    cache = DataCache(fetch_function_example, 60)

    # Test initialization
    assert cache.last_updated == datetime.min
    assert cache.cached_data is None

    # Test get_data with empty cache
    assert cache.get_data() == 'data'
    assert cache.cached_data == 'data'

    # Test flush
    cache.flush()
    assert cache.last_updated == datetime.min

    # Test timeout by altering last_updated
    cache.last_updated = datetime.now() - timedelta(seconds=61)
    assert cache.get_data() == 'data'  # fetch_function should be called again
