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

from oslo_serialization import jsonutils

from dragonflow.db import migration
from dragonflow.db.models import l2


@migration.define_migration(
    id='dragonflow.core.queens.dhcp_port_per_network',
    description='DHCP port per network.',
    release=migration.QUEENS,
    proposed_at='2017-11-17 00:00:00',
    affected_models=[l2.LogicalSwitch]
)
def migration(nb_api):
    """
    dhcp_ip and enable_dhcp is removed from subnet.
    The DHCP-owned lport already exists
    """
    db_driver = nb_api.db_driver
    keys = db_driver.get_all_keys(l2.LogicalSwitch.table_name)
    for key in keys:
        network_json = db_driver.get_key(l2.LogicalSwitch.table_name, key)
        network = jsonutils.loads(network_json)
        for subnet in network['subnets']:
            subnet.pop('dhcp_ip', None)
            subnet.pop('enable_dhcp', None)
        network_json = jsonutils.dumps(network)
        db_driver.set_key(l2.LogicalSwitch.table_name, key, network_json,
                          topic=network['topic'])