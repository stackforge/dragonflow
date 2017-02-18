# Copyright (c) 2015 OpenStack Foundation.
# All Rights Reserved.
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

import copy

import mock

from dragonflow.controller.common import constants as const
from dragonflow.tests.unit import test_app_base


class TestL3ProactiveApp(test_app_base.DFAppTestBase):
    apps_list = "l3_proactive_app.L3ProactiveApp"

    def setUp(self):
        super(TestL3ProactiveApp, self).setUp()
        self.app = self.open_flow_app.dispatcher.apps[0]
        self.mock_mod_flow = mock.Mock(name='mod_flow')
        self.app.mod_flow = self.mock_mod_flow
        self.router = copy.deepcopy(test_app_base.fake_logic_router1)

    def test_add_del_route(self):
        _add_subnet_send_to_snat = mock.patch.object(
            self.app,
            '_add_subnet_send_to_snat'
        )
        self.addCleanup(_add_subnet_send_to_snat.stop)
        _add_subnet_send_to_snat.start()
        _del_subnet_send_to_snat = mock.patch.object(
            self.app,
            '_delete_subnet_send_to_snat'
        )
        self.addCleanup(_del_subnet_send_to_snat.stop)
        _del_subnet_send_to_snat.start()

        # delete router
        self.controller.delete_lrouter(self.router.get_id())
        self.assertEqual(4, self.mock_mod_flow.call_count)

        # add router
        self.mock_mod_flow.reset_mock()
        self.controller.update_lrouter(self.router)
        self.assertEqual(3, self.mock_mod_flow.call_count)
        args, kwargs = self.mock_mod_flow.call_args
        self.assertEqual(const.L2_LOOKUP_TABLE, kwargs['table_id'])
        self.app._add_subnet_send_to_snat.assert_called_once_with(
            test_app_base.fake_logic_switch1.get_unique_key(),
            self.router.get_ports()[0].get_mac(),
            self.router.get_ports()[0].get_unique_key()
        )
        self.mock_mod_flow.reset_mock()

        # add route
        route = {"destination": "10.100.0.0/16",
                 "nexthop": "10.0.0.6"}
        router_with_route = copy.deepcopy(self.router)
        router_with_route.inner_obj['routes'] = [route]
        router_with_route.inner_obj['version'] += 1
        self.controller.update_lport(test_app_base.fake_local_port1)
        self.controller.update_lrouter(router_with_route)
        self.assertEqual(2, self.mock_mod_flow.call_count)

        # delete route
        self.mock_mod_flow.reset_mock()
        self.router.inner_obj['routes'] = []
        self.router.inner_obj['version'] += 2
        self.controller.update_lrouter(self.router)
        self.assertEqual(1, self.mock_mod_flow.call_count)
        self.app._delete_subnet_send_to_snat.assert_called_once_with(
            test_app_base.fake_logic_switch1.get_unique_key(),
            self.router.get_ports()[0].get_mac(),
        )

    def test_n_icmp_responder_for_n_router_interface(self):
        router_port1 = {"network": "20.0.0.1/24",
                        "lswitch": "fake_switch2",
                        "topic": "fake_tenant1",
                        "mac": "fa:16:3e:50:96:fe",
                        "unique_key": 15,
                        "lrouter": "fake_router_id",
                        "id": "fake_router_port2"}
        self.router.inner_obj['ports'].append(router_port1)
        dst_router_port = self.router.get_ports()[0]
        with mock.patch("dragonflow.controller.common"
                        ".icmp_responder.ICMPResponder") as icmp:
            self.app._add_new_router_port(self.router, dst_router_port)
            self.assertEqual(1, icmp.call_count)

    def test_add_local_port(self):
        # add local port
        with mock.patch('dragonflow.controller.l3_proactive_app.'
                        'L3ProactiveApp._add_port_process'
                        ) as fake_add_port_process:
            local_port = test_app_base.fake_local_port1
            self.controller.update_lport(local_port)
            fake_add_port_process.assert_called_once_with(
                local_port.get_ip(),
                local_port.get_mac(),
                local_port.get_external_value('local_network_id'),
                local_port.get_unique_key()
            )

    def test_remove_local_port(self):
        local_port = test_app_base.fake_local_port1
        # add local port
        self.controller.update_lport(local_port)
        # remove local port
        with mock.patch('dragonflow.controller.l3_proactive_app.'
                        'L3ProactiveApp._remove_port_process'
                        ) as fake_remove_port_process:
            self.controller.delete_lport(local_port.get_id())
            fake_remove_port_process.assert_called_once_with(
                local_port.get_ip(),
                local_port.get_external_value('local_network_id'),
            )

    def test_add_remote_port(self):
        # add remote port
        with mock.patch('dragonflow.controller.l3_proactive_app.'
                        'L3ProactiveApp._add_port_process'
                        ) as fake_add_port_process:
            remote_port = test_app_base.fake_remote_port1
            self.controller.update_lport(remote_port)
            fake_add_port_process.assert_called_once_with(
                remote_port.get_ip(),
                remote_port.get_mac(),
                remote_port.get_external_value('local_network_id'),
                remote_port.get_unique_key()
            )

    def test_remove_remote_port(self):
        remote_port = test_app_base.fake_remote_port1
        # add remote port
        self.controller.update_lport(remote_port)
        # del remote port
        with mock.patch('dragonflow.controller.l3_proactive_app.'
                        'L3ProactiveApp._remove_port_process'
                        ) as fake_remove_port_process:
            self.controller.delete_lport(remote_port.get_id())
            fake_remove_port_process.assert_called_once_with(
                remote_port.get_ip(),
                remote_port.get_external_value('local_network_id'),
            )
