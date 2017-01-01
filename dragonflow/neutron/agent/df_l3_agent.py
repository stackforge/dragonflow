# Copyright (c) 2015 OpenStack Foundation.
#
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
#

from neutron.agent import l3_agent

from dragonflow import conf as cfg
from dragonflow.controller import service
from dragonflow.db import api_nb


def main(manager='dragonflow.neutron.agent.l3.df_router.'
                 'DfL3NATAgentWithStateReport'):
    cfg.CONF.set_override('enable_df_pub_sub', False, group='df')
    nb_api = api_nb.NbApi.get_instance(False)
    service.register_service('df-l3-agent', nb_api)
    l3_agent.main(manager)
