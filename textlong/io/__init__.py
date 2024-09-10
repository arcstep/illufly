from .base import BaseLog, TextBlock, create_chk_block
from .queue import QueueLog
from .zero_mq import ZeroMQLog
from .redis import RedisLog
from .log import StreamLog, stream_log
from .utils import merge_blocks_by_index