# SPDX-License-Identifier: Apache-2.0
"""attu_logging | workspace logging bootstrap and webhook reporter."""

from attu_logging import webhook
from attu_logging.config import configure, set_webhook_url


__all__ = ['configure', 'set_webhook_url', 'webhook']
