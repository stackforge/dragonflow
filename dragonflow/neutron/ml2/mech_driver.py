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

from dragonflow._i18n import _LI
from dragonflow.common import common_params
from dragonflow.common import constants as df_common_const
from dragonflow.common import exceptions as df_exceptions
from dragonflow.db import api_nb
from dragonflow.db.neutron import lockedobjects_db as lock_db
from dragonflow.db.neutron import versionobjects_db as version_db
from dragonflow.neutron.common import constants as df_const

from neutron.api.v2 import attributes as attr
from neutron.callbacks import events
from neutron.callbacks import registry
from neutron.callbacks import resources
from neutron.common import constants as n_const
from neutron.db import db_base_plugin_v2
from neutron.db import extradhcpopt_db
from neutron.db import portbindings_db
from neutron.db import securitygroups_db
from neutron.extensions import extra_dhcp_opt as edo_ext
from neutron.extensions import portbindings
from neutron.plugins.common import constants
from neutron.plugins.ml2 import driver_api
from neutron.plugins.ml2 import models

from oslo_config import cfg
from oslo_log import log
from oslo_utils import importutils

LOG = log.getLogger(__name__)
cfg.CONF.register_opts(common_params.df_opts, 'df')


class DFMechDriver(driver_api.MechanismDriver,
                   db_base_plugin_v2.NeutronDbPluginV2,
                   securitygroups_db.SecurityGroupDbMixin,
                   portbindings_db.PortBindingMixin,
                   extradhcpopt_db.ExtraDhcpOptMixin):

    """Dragonflow ML2 MechanismDriver for Neutron.

    """
    def initialize(self):
        LOG.info(_LI("Starting DFMechDriver"))

        # When set to True, Nova plugs the VIF directly into the ovs bridge
        # instead of using the hybrid mode.
        self.vif_details = {portbindings.CAP_PORT_FILTER: True}
        self.vif_type = portbindings.VIF_TYPE_OVS
        self._set_base_port_binding()

        nb_driver_class = importutils.import_class(cfg.CONF.df.nb_db_class)
        self.nb_api = api_nb.NbApi(
                nb_driver_class(),
                use_pubsub=cfg.CONF.df.enable_df_pub_sub,
                is_neutron_server=True)
        self.nb_api.initialize(db_ip=cfg.CONF.df.remote_db_ip,
                               db_port=cfg.CONF.df.remote_db_port)

        registry.subscribe(self.create_security_group,
                           resources.SECURITY_GROUP,
                           events.AFTER_CREATE)
        registry.subscribe(self.delete_security_group,
                           resources.SECURITY_GROUP,
                           events.BEFORE_DELETE)
        registry.subscribe(self.create_security_group_rule,
                           resources.SECURITY_GROUP_RULE,
                           events.AFTER_CREATE)
        registry.subscribe(self.delete_security_group_rule,
                           resources.SECURITY_GROUP_RULE,
                           events.BEFORE_DELETE)

    def _set_base_port_binding(self):
        self.base_binding_dict = {
            portbindings.VIF_TYPE: portbindings.VIF_TYPE_OVS,
            portbindings.VIF_DETAILS: {
                portbindings.CAP_PORT_FILTER:
                'security-group' in self.supported_extension_aliases}}

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_SECURITY_GROUP)
    def create_security_group(self, resource, event, trigger, **kwargs):
        sg = kwargs['security_group']
        sg_name = sg['id']
        tenant_id = sg['tenant_id']
        rules = sg.get('security_group_rules')
        context = kwargs['context']

        with context.session.begin(subtransactions=True):
            sg_version = version_db._create_db_version_row(context.session,
                                                           sg['id'])

        self.nb_api.create_security_group(name=sg_name, topic=tenant_id,
                                          rules=rules, version=sg_version)

        LOG.info(_LI("DFMechDriver: create security group %s") % sg_name)
        return sg

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_SECURITY_GROUP)
    def delete_security_group(self, resource, event, trigger, **kwargs):
        sg = kwargs['security_group']
        sg_id = kwargs['security_group_id']
        tenant_id = sg['tenant_id']
        context = kwargs['context']

        with context.session.begin(subtransactions=True):
            version_db._delete_db_version_row(context.session, sg_id)

        self.nb_api.delete_security_group(sg_id, topic=tenant_id)
        LOG.info(_LI("DFMechDriver: delete security group %s") % sg_id)

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_SECURITY_GROUP_RULE_CREATE)
    def create_security_group_rule(self, resource, event, trigger, **kwargs):
        sg_rule = kwargs['security_group_rule']
        sg_id = sg_rule['security_group_id']
        context = kwargs['context']

        with context.session.begin(subtransactions=True):
            sg_version_id = version_db._update_db_version_row(context.session,
                                                              sg_id)

        self.nb_api.add_security_group_rules(sg_id, sg_rule['tenant_id'],
                                             sg_rules=[sg_rule],
                                             sg_version=sg_version_id)
        LOG.info(_LI("DFMechDriver: create security group rule in group %s"),
                 sg_id)
        return sg_rule

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_SECURITY_GROUP_RULE_DELETE)
    def delete_security_group_rule(self, resource, event, trigger, **kwargs):
        context = kwargs['context']
        tenant_id = context.tenant_id
        sgr_id = kwargs['security_group_rule_id']
        sgr = self.get_security_group_rule(context, sgr_id)
        sg_id = sgr['security_group_id']

        with context.session.begin(subtransactions=True):
            sg_version_id = version_db._update_db_version_row(context.session,
                                                              sg_id)

        self.nb_api.delete_security_group_rule(sg_id, sgr_id, tenant_id,
                                               sg_version=sg_version_id)
        LOG.info(_LI("DFMechDriver: delete security group rule %s"), sgr_id)

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_CORE)
    def create_network_postcommit(self, context):
        network = context.current
        external_ids = {df_const.DF_NETWORK_NAME_EXT_ID_KEY: network['name']}
        plugin_context = context._plugin_context

        with plugin_context.session.begin(subtransactions=True):
            nw_version = version_db._create_db_version_row(
                plugin_context.session, network['id'])

        self.nb_api.create_lswitch(
            name=network['id'],
            topic=network['tenant_id'],
            network_type=network['provider:network_type'],
            segmentation_id=network['provider:segmentation_id'],
            external_ids=external_ids,
            version=nw_version,
            subnets=[])

        LOG.info(_LI("DFMechDriver: create network %s"), network['id'])
        return network

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_CORE)
    def delete_network_postcommit(self, context):
        network = context.current
        network_id = network['id']
        tenant_id = network['tenant_id']
        plugin_context = context._plugin_context

        with plugin_context.session.begin(subtransactions=True):
            version_db._delete_db_version_row(plugin_context.session,
                                              network_id)

        for port in self.nb_api.get_all_logical_ports(topic=tenant_id):
            if port.get_lswitch_id() == network_id:
                try:
                    self.nb_api.delete_lport(name=port.get_id(),
                                             topic=tenant_id)
                    LOG.info(_LI("DFMechDriver: delete port %(port)s when "
                                 "delete network %(network)s"),
                             {'port': port.get_id(), 'network': network_id})
                except df_exceptions.DBKeyNotFound:
                    LOG.debug("port %s is not found in DB, might have "
                              "been deleted concurrently" % port.get_id())

        try:
            self.nb_api.delete_lswitch(name=network_id,
                                       topic=tenant_id)
        except df_exceptions.DBKeyNotFound:
            LOG.debug("lswitch %s is not found in DF DB, might have "
                      "been deleted concurrently" % network_id)

        LOG.info(_LI("DFMechDriver: delete network %s"), network_id)

    def _get_dhcp_port_for_subnet(self, context, subnet_id):
        filters = {'fixed_ips': {'subnet_id': [subnet_id]},
                   'device_owner': [n_const.DEVICE_OWNER_DHCP]}

        ports = self.get_ports(context, filters=filters)
        if 0 != len(ports):
            return ports[0]
        else:
            return None

    def _process_portbindings_create_and_update(self, context, port_data,
                                                port):
        binding_profile = port.get(portbindings.PROFILE)
        binding_profile_set = attr.is_attr_set(binding_profile)
        if not binding_profile_set and binding_profile is not None:
            del port[portbindings.PROFILE]

        binding_vnic = port.get(portbindings.VNIC_TYPE)
        binding_vnic_set = attr.is_attr_set(binding_vnic)
        if not binding_vnic_set and binding_vnic is not None:
            del port[portbindings.VNIC_TYPE]

        host = port_data.get(portbindings.HOST_ID)
        host_set = attr.is_attr_set(host)
        with context.session.begin(subtransactions=True):
            bind_port = context.session.query(
                models.PortBinding).filter_by(port_id=port['id']).first()
            if host_set:
                if not bind_port:
                    context.session.add(models.PortBinding(
                        port_id=port['id'],
                        host=host,
                        vif_type=self.vif_type))
                else:
                    bind_port.host = host
            else:
                host = bind_port.host if bind_port else None
        self._extend_port_dict_binding_host(port, host)

    def _create_dhcp_port(self, context, port):
        with context.session.begin(subtransactions=True):
            db_port = self.create_port(context, port)

            dhcp_opts = port['port'].get(edo_ext.EXTRADHCPOPTS, [])
            sgids = self._get_security_groups_on_port(context, port)
            self._process_port_create_security_group(context, db_port, sgids)
            self._process_portbindings_create_and_update(context,
                                                         port['port'],
                                                         db_port)

            db_port[portbindings.VIF_TYPE] = portbindings.VNIC_NORMAL
            if (df_const.DF_PORT_BINDING_PROFILE in port['port'] and
                    attr.is_attr_set(
                        port['port'][df_const.DF_PORT_BINDING_PROFILE])):
                db_port[df_const.DF_PORT_BINDING_PROFILE] = (
                    port['port'][df_const.DF_PORT_BINDING_PROFILE])

            self._process_port_create_extra_dhcp_opts(context, db_port,
                                                      dhcp_opts)

            port_version = version_db._create_db_version_row(
                context.session, db_port['id'])

        port_model = self._get_port(context, db_port['id'])
        self._apply_dict_extend_functions('ports', db_port, port_model)

        return self._create_port_in_nb_api(db_port, sgids, port_version)

    def _create_dhcp_server_port(self, context, subnet):
        """Create and return dhcp port information.

        If an expected failure occurs, a None port is returned.
        """
        port = {'port': {'tenant_id': context.tenant_id,
                         'network_id': subnet['network_id'], 'name': '',
                         'binding:host_id': (
                             df_common_const.DRAGONFLOW_VIRTUAL_PORT),
                         'admin_state_up': True, 'device_id': '',
                         'device_owner': n_const.DEVICE_OWNER_DHCP,
                         'mac_address': attr.ATTR_NOT_SPECIFIED,
                         'fixed_ips': [{'subnet_id': subnet['id']}]}}
        port = self._create_dhcp_port(context, port)
        return port

    def _handle_create_subnet_dhcp(self, context, subnet):
        """Create the dhcp configration for the subnet

        Returns the dhcp server port if configured
        """
        if subnet['enable_dhcp']:
            if cfg.CONF.df.use_centralized_ipv6_DHCP:
                return subnet['allocation_pools'][0]['start']
            else:
                dhcp_port = self._create_dhcp_server_port(context, subnet)
                return dhcp_port
        return None

    def _get_ip_from_port(self, port):
        """Get The first Ip address from the port.

        Returns the first fixed_ip address for a port
        """
        if not port:
            return None

        for fixed_ip in port['fixed_ips']:
            ip = fixed_ip.get('ip_address', None)
            if ip:
                return ip

    def _get_subnet_dhcp_port_address(self, context, subnet):
        """Create the dhcp configration for the subnet
        Returns the dhcp server ip address if configured
        """
        try:
            dhcp_port = self._get_dhcp_port_for_subnet(context, subnet['id'])
            dhcp_address = self._get_ip_from_port(dhcp_port)
            return dhcp_address
        except Exception as e:
            LOG.exception(e)
            return None

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_CORE)
    def create_subnet_postcommit(self, context):
        subnet = context.current
        net_id = subnet['network_id']
        plugin_context = context._plugin_context

        with plugin_context.session.begin(subtransactions=True):
            network_version = version_db._update_db_version_row(
                plugin_context.session, net_id)

        try:
            dhcp_port = self._handle_create_subnet_dhcp(plugin_context,
                                                        subnet)
        except Exception as e:
            LOG.exception(e)
            return None

        dhcp_address = self._get_ip_from_port(dhcp_port)
        self.nb_api.add_subnet(
            subnet['id'],
            net_id,
            subnet['tenant_id'],
            nw_version=network_version,
            enable_dhcp=subnet['enable_dhcp'],
            cidr=subnet['cidr'],
            dhcp_ip=dhcp_address,
            gateway_ip=subnet['gateway_ip'],
            dns_nameservers=subnet.get('dns_nameservers', []))

        LOG.info(_LI("DFMechDriver: create subnet %s"), subnet['id'])
        return subnet

    def _update_subnet_dhcp_centralized(self, context, subnet):
        """Update the dhcp configration for the subnet.

        Returns the dhcp server ip address if configured
        """
        if subnet['enable_dhcp']:
            port = self._get_dhcp_port_for_subnet(
                    context,
                    subnet['id'])
            return self._get_ip_from_port(port)
        else:
            return subnet['allocation_pools'][0]['start']

    def _delete_subnet_dhcp_port(self, context, port):
        port_id = port['id']
        topic = port['tenant_id']
        self.nb_api.delete_lport(name=port_id, topic=topic)
        self.delete_port(context, port_id)

    def _handle_update_subnet_dhcp(self, context, old_subnet, new_subnet):
        """Update the dhcp configration for the subnet.

        Returns the dhcp server port if configured
        """
        if cfg.CONF.df.use_centralized_ipv6_DHCP:
            return self._update_subnet_dhcp_centralized(context, new_subnet)

        if old_subnet['enable_dhcp']:
            port = self._get_dhcp_port_for_subnet(context, old_subnet['id'])

        if not new_subnet['enable_dhcp'] and old_subnet['enable_dhcp']:
            if port:
                self._delete_subnet_dhcp_port(context, port)
            return None

        if new_subnet['enable_dhcp'] and not old_subnet['enable_dhcp']:
            port = self._create_dhcp_server_port(context, new_subnet)

        return port

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_CORE)
    def update_subnet_postcommit(self, context):
        new_subnet = context.current
        old_subnet = context.original
        plugin_context = context._plugin_context

        with plugin_context.session.begin(subtransactions=True):
            network_version = version_db._update_db_version_row(
                plugin_context.session, new_subnet['network_id'])

        try:
            dhcp_port = self._handle_update_subnet_dhcp(plugin_context,
                                                        old_subnet,
                                                        new_subnet)
        except Exception as e:
            LOG.exception(e)
            return None

        dhcp_address = self._get_ip_from_port(dhcp_port)
        self.nb_api.update_subnet(
            new_subnet['id'],
            new_subnet['network_id'],
            new_subnet['tenant_id'],
            nw_version=network_version,
            enable_dhcp=new_subnet['enable_dhcp'],
            cidr=new_subnet['cidr'],
            dhcp_ip=dhcp_address,
            gateway_ip=new_subnet['gateway_ip'],
            dns_nameservers=new_subnet.get('dns_nameservers', []))

        LOG.info(_LI("DFMechDriver: update subnet %s"), new_subnet['id'])
        return new_subnet

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_CORE)
    def delete_subnet_postcommit(self, context):
        """If the subnet enabled dhcp, the dhcp server port should be deleted.
        But the operation of delete dhcp port can't do here, because in this
        case, we can't get dhcp port by subnet id. The dhcp port will be
        deleted in update_port_postcommit.
        """
        subnet = context.current
        net_id = subnet['network_id']
        subnet_id = subnet['id']
        plugin_context = context._plugin_context

        with plugin_context.session.begin(subtransactions=True):
            network_version = version_db._update_db_version_row(
                plugin_context.session, net_id)

        # update df controller with subnet delete
        try:
            self.nb_api.delete_subnet(subnet_id, net_id, subnet['tenant_id'],
                                      nw_version=network_version)
        except df_exceptions.DBKeyNotFound:
            LOG.debug("network %s is not found in DB, might have "
                      "been deleted concurrently" % net_id)

        LOG.info(_LI("DFMechDriver: delete subnet %s"), subnet_id)

    def _get_allowed_mac_addresses_from_port(self, port):
        allowed_macs = set()
        allowed_macs.add(port['mac_address'])
        allowed_address_pairs = port.get('allowed_address_pairs', [])
        for allowed_address in allowed_address_pairs:
            allowed_macs.add(allowed_address['mac_address'])
        return list(allowed_macs)

    def _create_port_in_nb_api(self, port, sgids, port_version):
        # The port name *must* be port['id'].  It must match the iface-id set
        # in the Interfaces table of the Open_vSwitch database, which nova sets
        # to be the port ID.
        external_ids = {df_const.DF_PORT_NAME_EXT_ID_KEY: port['name']}
        allowed_macs = self._get_allowed_mac_addresses_from_port(port)
        ips = [ip['ip_address'] for ip in port.get('fixed_ips', [])]
        tunnel_key = self.nb_api.allocate_tunnel_key()

        # Router GW ports are not needed by dragonflow controller and
        # they currently cause error as they couldnt be mapped to
        # a valid ofport (or location)
        if port.get('device_owner') == n_const.DEVICE_OWNER_ROUTER_GW:
            chassis = None
        else:
            chassis = port.get('binding:host_id', None)

        self.nb_api.create_lport(
            name=port['id'],
            lswitch_name=port['network_id'],
            topic=port['tenant_id'],
            macs=[port['mac_address']], ips=ips,
            external_ids=external_ids,
            enabled=port.get('admin_state_up', None),
            chassis=chassis, tunnel_key=tunnel_key,
            version=port_version,
            port_security=allowed_macs,
            device_owner=port.get('device_owner', None),
            security_groups=port.get('security_groups', None))

        return port

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_CORE)
    def create_port_postcommit(self, context):
        port = context.current
        sgids = port.get('security_groups', None)
        plugin_context = context._plugin_context

        with plugin_context.session.begin(subtransactions=True):
            port_version = version_db._create_db_version_row(
                plugin_context.session, port['id'])

        self._create_port_in_nb_api(port, sgids, port_version)
        LOG.info(_LI("DFMechDriver: create port %s"), port['id'])
        return port

    def _is_dhcp_port_after_subnet_delete(self, port):
        # If a subnet enabled dhcp, the DFMechDriver will create a dhcp server
        # port. When delete this subnet, the port should be deleted.
        # In ml2\plugin.py, when delete subnet, it will call
        # update_port_postcommit, DFMechDriver should judge the port is dhcp
        # port or not, if it is, then delete it.
        host_id = port.get('binding:host_id', None)
        subnet_id = None

        for fixed_ip in port['fixed_ips']:
            subnet_id = fixed_ip.get('subnet_id', None)
            if subnet_id:
                break

        if host_id == df_common_const.DRAGONFLOW_VIRTUAL_PORT \
                and subnet_id is None:
            return True
        else:
            return False

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_CORE)
    def update_port_postcommit(self, context):
        updated_port = context.current
        plugin_context = context._plugin_context

        with plugin_context.session.begin(subtransactions=True):
            port_version = version_db._update_db_version_row(
                plugin_context.session, updated_port['id'])

        # If a subnet enabled dhcp, the DFMechDriver will create a dhcp server
        # port. When delete this subnet, the port should be deleted.
        # In ml2\plugin.py, when delete subnet, it will call
        # update_port_postcommit, DFMechDriver should judge the port is dhcp
        # port or not, if it is, then delete it.
        if self._is_dhcp_port_after_subnet_delete(updated_port):
            self._delete_subnet_dhcp_port(context._plugin_context,
                                          updated_port)
            return None

        # Router GW ports are not needed by dragonflow controller and
        # they currently cause error as they couldnt be mapped to
        # a valid ofport (or location)
        if updated_port.get('device_owner') == n_const.DEVICE_OWNER_ROUTER_GW:
            chassis = None
        else:
            chassis = updated_port.get('binding:host_id', None)

        updated_security_groups = updated_port.get('security_groups')
        if updated_security_groups:
            security_groups = updated_security_groups
        else:
            security_groups = None

        external_ids = {
            df_const.DF_PORT_NAME_EXT_ID_KEY: updated_port['name']}
        allowed_macs = self._get_allowed_mac_addresses_from_port(updated_port)
        ips = [ip['ip_address'] for ip in updated_port.get('fixed_ips', [])]

        self.nb_api.update_lport(
            name=updated_port['id'],
            topic=updated_port['tenant_id'],
            macs=[updated_port['mac_address']], ips=ips,
            external_ids=external_ids,
            enabled=updated_port['admin_state_up'],
            port_security=allowed_macs,
            chassis=chassis,
            device_owner=updated_port.get('device_owner', None),
            security_groups=security_groups,
            version=port_version)

        LOG.info(_LI("DFMechDriver: update port %s"), updated_port['id'])
        return updated_port

    @lock_db.wrap_db_lock(lock_db.RESOURCE_ML2_CORE)
    def delete_port_postcommit(self, context):
        port = context.current
        port_id = port['id']
        plugin_context = context._plugin_context

        with plugin_context.session.begin(subtransactions=True):
            version_db._delete_db_version_row(plugin_context.session, port_id)

        try:
            topic = port['tenant_id']
            self.nb_api.delete_lport(name=port_id, topic=topic)
        except df_exceptions.DBKeyNotFound:
            LOG.debug("port %s is not found in DF DB, might have "
                      "been deleted concurrently" % port_id)

        LOG.info(_LI("DFMechDriver: delete port %s"), port_id)

    def bind_port(self, context):
        """Set porting binding data for use with nova."""
        LOG.debug("Attempting to bind port %(port)s on "
                  "network %(network)s",
                  {'port': context.current['id'],
                   'network': context.network.current['id']})

        # Prepared porting binding data
        for segment in context.segments_to_bind:
            if self._check_segment(segment):
                context.set_binding(segment[driver_api.ID],
                                    self.vif_type,
                                    self.vif_details,
                                    status=n_const.PORT_STATUS_ACTIVE)
                LOG.debug("Bound using segment: %s", segment)
                return
            else:
                LOG.debug("Refusing to bind port for segment ID %(id)s, "
                          "segment %(seg)s, phys net %(physnet)s, and "
                          "network type %(nettype)s",
                          {'id': segment[driver_api.ID],
                           'seg': segment[driver_api.SEGMENTATION_ID],
                           'physnet': segment[driver_api.PHYSICAL_NETWORK],
                           'nettype': segment[driver_api.NETWORK_TYPE]})

    def _check_segment(self, segment):
        """Verify a segment is valid for the dragonflow MechanismDriver."""
        return segment[driver_api.NETWORK_TYPE] in [constants.TYPE_VLAN,
                                                    constants.TYPE_VXLAN,
                                                    constants.TYPE_FLAT,
                                                    constants.TYPE_GRE,
                                                    constants.TYPE_LOCAL]
