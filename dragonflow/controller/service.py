#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import functools

from dragonflow.common import report_status
from dragonflow import conf as cfg
from dragonflow.db import api_nb
from dragonflow.db.models import service


class Service(object):
    def __init__(self,):
        binary = self.service_name
        self.nb_api = api_nb.NbApi.get_instance(False)
        chassis_id = cfg.CONF.host
        self.nb_api.create(service.Service(chassis=chassis_id, binary=binary),
                           skip_send_event=True)
        callback = functools.partial(service.Service.update_last_seen,
                                     self.nb_api, chassis_id, binary)
        report_status.run_status_reporter(callback)
