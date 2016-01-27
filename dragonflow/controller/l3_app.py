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

import netaddr

from ryu.lib.packet import arp
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import ipv6
from ryu.lib.packet import packet
from ryu.ofproto import ether

from dragonflow.controller.common import constants as const
from dragonflow.controller.df_base_app import DFlowApp

from oslo_config import cfg
from oslo_log import log

from neutron.i18n import _LE

DF_L3_APP_OPTS = [
    cfg.BoolOpt('df_arp_responder',
        default=True,
        help=_('Install OVS flows to respond to ARP requests.'))
]

LOG = log.getLogger(__name__)


class L3App(DFlowApp):
    def __init__(self, *args, **kwargs):
        super(L3App, self).__init__(*args, **kwargs)
        self.idle_timeout = 30
        self.hard_timeout = 0
        self.api.register_table_handler(const.L3_LOOKUP_TABLE,
                self.packet_in_handler)
        cfg.CONF.register_opts(DF_L3_APP_OPTS)
        self.is_arp_responder = cfg.CONF.df_arp_responder

    def switch_features_handler(self, ev):
        self.add_flow_go_to_table(self.get_datapath(),
                                  const.L3_LOOKUP_TABLE,
                                  const.PRIORITY_DEFAULT,
                                  const.EGRESS_TABLE)
        self._install_flows_on_switch_up()

    def _get_match_arp_responder(self, datapath, network_id, interface_ip):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        match.set_dl_type(ether.ETH_TYPE_ARP)
        match.set_arp_tpa(self.ipv4_text_to_int(str(interface_ip)))
        match.set_arp_opcode(arp.ARP_REQUEST)
        match.set_metadata(network_id)
        return match

    def _get_inst_arp_responder(self,
            datapath,
            mac_address,
            interface_ip,
            is_unicast=False):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        actions = [parser.OFPActionSetField(arp_op=arp.ARP_REPLY),
                   parser.NXActionRegMove(src_field='arp_sha',
                                          dst_field='arp_tha',
                                          n_bits=48),
                   parser.NXActionRegMove(src_field='arp_spa',
                                          dst_field='arp_tpa',
                                          n_bits=32)]
        if is_unicast:
            actions.append(parser.NXActionRegMove(src_field='eth_src',
                    dst_field='eth_dst',
                    n_bits=48))
        actions.extend([
                parser.OFPActionSetField(eth_src=mac_address),
                parser.OFPActionSetField(arp_sha=mac_address),
                parser.OFPActionSetField(arp_spa=interface_ip),
                parser.OFPActionOutput(ofproto.OFPP_IN_PORT, 0)])
        instructions = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions)]
        return instructions

    def _add_arp_responder(self,
            network_id,
            mac_address,
            interface_ip,
            is_unicast=False):
            match = self._get_match_arp_responder(
                self.get_datapath(), network_id, interface_ip)
            instructions = self._get_inst_arp_responder(
                self.get_datapath(), mac_address, interface_ip, is_unicast)
            ofproto = self.get_datapath().ofproto
            parser = self.get_datapath().ofproto_parser
            msg = parser.OFPFlowMod(datapath=self.get_datapath(),
                                    table_id=const.ARP_TABLE,
                                    command=ofproto.OFPFC_ADD,
                                    priority=const.PRIORITY_MEDIUM,
                                    match=match, instructions=instructions,
                                    flags=ofproto.OFPFF_SEND_FLOW_REM)
            self.get_datapath().send_msg(msg)

    def _remove_arp_responder(self,
            network_id,
            interface_ip):
        ofproto = self.get_datapath().ofproto
        parser = self.get_datapath().ofproto_parser
        match = self._get_match_arp_responder(
            self.get_datapath(), network_id, interface_ip)
        msg = parser.OFPFlowMod(datapath=self.get_datapath(),
                                cookie=0,
                                cookie_mask=0,
                                table_id=const.ARP_TABLE,
                                command=ofproto.OFPFC_DELETE,
                                priority=const.PRIORITY_MEDIUM,
                                out_port=ofproto.OFPP_ANY,
                                out_group=ofproto.OFPG_ANY,
                                match=match)
        self.get_datapath().send_msg(msg)

    def send_port_desc_stats_request(self, datapath):
        ofp_parser = datapath.ofproto_parser
        req = ofp_parser.OFPPortDescStatsRequest(datapath, 0)
        datapath.send_msg(req)

    def packet_in_handler(self, event):
        msg = event.msg

        pkt = packet.Packet(msg.data)
        is_pkt_ipv4 = pkt.get_protocol(ipv4.ipv4) is not None

        if is_pkt_ipv4:
            pkt_ip = pkt.get_protocol(ipv4.ipv4)
        else:
            pkt_ip = pkt.get_protocol(ipv6.ipv6)

        if pkt_ip is None:
            LOG.error(_LE("Received None IP Packet"))
            return

        network_id = msg.match.get('metadata')
        pkt_ethernet = pkt.get_protocol(ethernet.ethernet)
        try:
            self.get_route(pkt_ip, pkt_ethernet, network_id, msg)
        except Exception as e:
            LOG.error(_LE("L3 App PacketIn exception raised"))
            LOG.error(e)

    def get_route(self, pkt_ip, pkt_ethernet, network_id, msg):
        ip_addr = netaddr.IPAddress(pkt_ip.dst)
        router = self.db_store.get_router_by_router_interface_mac(
            pkt_ethernet.dst)
        for router_port in router.get_ports():
            if ip_addr in netaddr.IPNetwork(router_port.get_network()):
                if str(ip_addr) == router_port.get_ip():
                    self._install_flow_send_to_output_table(
                        network_id,
                        router_port.get_ip())
                    return
                dst_ports = self.db_store.get_ports_by_network_id(
                    router_port.get_lswitch_id())
                for out_port in dst_ports:
                    if out_port.get_ip() == pkt_ip.dst:
                        self._install_l3_flow(router_port,
                                              out_port, msg,
                                              network_id)
                        return

    def _install_l3_flow(self, dst_router_port, dst_port, msg,
                         src_network_id):
        reg7 = dst_port.get_tunnel_key()
        dst_ip = dst_port.get_ip()
        src_mac = dst_router_port.get_mac()
        dst_mac = dst_port.get_mac()

        parser = self.get_datapath().ofproto_parser
        ofproto = self.get_datapath().ofproto

        if netaddr.IPAddress(dst_ip).version == 4:
            match = parser.OFPMatch(eth_type=ether.ETH_TYPE_IP,
                                    metadata=src_network_id,
                                    ipv4_dst=dst_ip)
        else:
            match = parser.OFPMatch(eth_type=ether.ETH_TYPE_IPV6,
                                    metadata=src_network_id,
                                    ipv6_dst=dst_ip)

        actions = []
        actions.append(parser.OFPActionDecNwTtl())
        actions.append(parser.OFPActionSetField(eth_src=src_mac))
        actions.append(parser.OFPActionSetField(eth_dst=dst_mac))
        actions.append(parser.OFPActionSetField(reg7=reg7))
        action_inst = self.get_datapath().ofproto_parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS, actions)

        goto_inst = parser.OFPInstructionGotoTable(const.EGRESS_TABLE)
        inst = [action_inst, goto_inst]

        self.mod_flow(
            self.get_datapath(),
            cookie=dst_router_port.get_tunnel_key(),
            inst=inst,
            table_id=const.L3_LOOKUP_TABLE,
            priority=const.PRIORITY_VERY_HIGH,
            match=match,
            idle_timeout=self.idle_timeout,
            hard_timeout=self.hard_timeout)

        in_port = msg.match.get('in_port')
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=self.get_datapath(),
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=data)
        self.get_datapath().send_msg(out)

    def add_router_port(self, router, router_port, local_network_id):

        if self.get_datapath() is None:
            return

        parser = self.get_datapath().ofproto_parser

        mac = router_port.get_mac()
        tunnel_key = router_port.get_tunnel_key()

        # Add router ARP responder for IPv4 Addresses
        if netaddr.IPAddress(router_port.get_ip()).version == 4:
            self._add_arp_responder(local_network_id, mac,
                    router_port.get_ip())

        # If router interface IP, send to output table
        dst_ip = router_port.get_ip()
        if netaddr.IPAddress(dst_ip).version == 4:
            match = parser.OFPMatch(eth_type=ether.ETH_TYPE_IP,
                                    metadata=local_network_id,
                                    ipv4_dst=dst_ip)
        else:
            match = parser.OFPMatch(eth_type=ether.ETH_TYPE_IPV6,
                                    metadata=local_network_id,
                                    ipv6_dst=dst_ip)

        goto_inst = parser.OFPInstructionGotoTable(const.EGRESS_TABLE)
        inst = [goto_inst]
        self.mod_flow(
            self.get_datapath(),
            inst=inst,
            table_id=const.L3_LOOKUP_TABLE,
            priority=const.PRIORITY_HIGH,
            match=match)

        # Match all possible routeable traffic and send to controller
        for port in router.get_ports():
            if port.get_name() != router_port.get_name():
                # From this router interface to all other interfaces
                self._add_subnet_send_to_controller(local_network_id,
                                                    port.get_cidr_network(),
                                                    port.get_cidr_netmask(),
                                                    port.get_tunnel_key())

                # From all the other interfaces to this new interface
                router_port_net_id = self.db_store.get_network_id(
                    port.get_lswitch_id())
                self._add_subnet_send_to_controller(
                    router_port_net_id,
                    router_port.get_cidr_network(),
                    router_port.get_cidr_netmask(),
                    tunnel_key)

    def _install_flow_send_to_output_table(self, network_id, dst_ip):

        parser = self.get_datapath().ofproto_parser
        if netaddr.IPAddress(dst_ip).version == 4:
            match = parser.OFPMatch(eth_type=ether.ETH_TYPE_IP,
                                    metadata=network_id,
                                    ipv4_dst=dst_ip)
        else:
            match = parser.OFPMatch(eth_type=ether.ETH_TYPE_IPV6,
                                    metadata=network_id,
                                    ipv6_dst=dst_ip)

        goto_inst = parser.OFPInstructionGotoTable(const.EGRESS_TABLE)
        inst = [goto_inst]
        self.mod_flow(
            self.get_datapath(),
            inst=inst,
            table_id=const.L3_LOOKUP_TABLE,
            priority=const.PRIORITY_HIGH,
            match=match,
            idle_timeout=self.idle_timeout,
            hard_timeout=self.hard_timeout)

    def _add_subnet_send_to_controller(self, network_id, dst_network,
                                       dst_netmask, dst_router_tunnel_key):
        parser = self.get_datapath().ofproto_parser
        ofproto = self.get_datapath().ofproto

        if netaddr.IPAddress(dst_network).version == 4:
            match = parser.OFPMatch(eth_type=ether.ETH_TYPE_IP,
                                    metadata=network_id,
                                    ipv4_dst=(dst_network, dst_netmask))
        else:
            match = parser.OFPMatch(eth_type=ether.ETH_TYPE_IPV6,
                                    metadata=network_id,
                                    ipv6_dst=(dst_network, dst_netmask))

        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        inst = [self.get_datapath().ofproto_parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions)]

        self.mod_flow(
            self.get_datapath(),
            cookie=dst_router_tunnel_key,
            inst=inst,
            table_id=const.L3_LOOKUP_TABLE,
            priority=const.PRIORITY_MEDIUM,
            match=match)

    def remove_router_port(self, router_port, local_network_id):

        parser = self.get_datapath().ofproto_parser
        ofproto = self.get_datapath().ofproto
        tunnel_key = router_port.get_tunnel_key()

        if netaddr.IPAddress(router_port.get_ip()).version == 4:
            self._remove_arp_responder(local_network_id,
                    router_port.get_ip())

        match = parser.OFPMatch()
        match.set_metadata(local_network_id)
        message = parser.OFPFlowMod(
            datapath=self.get_datapath(),
            cookie=0,
            cookie_mask=0,
            table_id=const.L3_LOOKUP_TABLE,
            command=ofproto.OFPFC_DELETE,
            priority=const.PRIORITY_MEDIUM,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=match)

        self.get_datapath().send_msg(message)

        match = parser.OFPMatch()
        cookie = tunnel_key
        message = parser.OFPFlowMod(
            datapath=self.get_datapath(),
            cookie=cookie,
            cookie_mask=cookie,
            table_id=const.L3_LOOKUP_TABLE,
            command=ofproto.OFPFC_DELETE,
            priority=const.PRIORITY_MEDIUM,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=match)

        self.get_datapath().send_msg(message)

    def _install_flows_on_switch_up(self):
        for lrouter in self.db_store.get_routers():
            for router_port in lrouter.get_ports():
                local_network_id = self.db_store.get_network_id(
                    router_port.get_lswitch_id())
                self.add_router_port(lrouter, router_port,
                        local_network_id)

    def add_port(self, lport):
        if not self.is_arp_responder:
            return
        ip = lport.get_ip()
        if netaddr.IPAddress(ip).version != 4:
            return
        network_id = lport.get_external_value('local_network_id')
        mac = lport.get_mac()
        self._add_arp_responder(network_id, mac, ip, True)

    def remove_port(self, lport):
        if not self.is_arp_responder:
            return
        ip = lport.get_ip()
        if netaddr.IPAddress(ip).version != 4:
            return
        network_id = lport.get_external_value('local_network_id')
        mac = lport.get_mac()
        self._remove_arp_responder(network_id, mac, ip)

    def add_local_port(self, lport):
        self.add_port(lport)

    def add_remote_port(self, lport):
        self.add_port(lport)

    def remove_local_port(self, lport):
        self.remove_port(lport)

    def remove_remote_port(self, lport):
        self.remove_port(lport)
