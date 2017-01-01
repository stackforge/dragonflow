# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from oslo_config import cfg
from oslo_service import loopingcall


from dragonflow._i18n import _LE


LOG = logging.getLogger(__name__)


def report_status(callback, host, binary):
    try:
        callback(host, binary)
    except Exception:
        LOG.exception(_LE("Failed to report status of %(host)s on %(binary)s"),
                      {'host': host, 'binary': binary})

    return True


def run_status_reporter(status_update_callback, host, binary):
    loopingcall.FixedIntervalLoopingCall(
        report_status,
        initial_delay=cfg.CONF.df.report_interval)
