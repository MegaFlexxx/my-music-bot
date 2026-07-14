import yandex_music
from yandex_music import Client as OriginalClient
from yandex_music.utils.difference import Difference
from yandex_music.exceptions import YandexMusicError

# Исправление бага с common_period_duration
original_product_init = yandex_music.Product.__init__
def patched_product_init(self, *args, **kwargs):
    kwargs.setdefault('common_period_duration', None)
    original_product_init(self, *args, **kwargs)
yandex_music.Product.__init__ = patched_product_init

class Client(OriginalClient):
    def __init__(self, token=None, base_url=None, request_timeout=None, *args, **kwargs):
        super().__init__(token, base_url, request_timeout, *args, **kwargs)
