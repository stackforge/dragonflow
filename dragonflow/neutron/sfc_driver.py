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

from networking_sfc.services.flowclassifier.drivers import base as fc_driver
from networking_sfc.services.sfc.drivers import base as sfc_driver
from oslo_log import helpers as log_helpers
from oslo_log import log

from dragonflow.db import api_nb

LOG = log.getLogger(__name__)


class _DfSfcDriverHiddenBase(sfc_driver.SfcDriverBase):
    def create_port_chain(self, context):
        pass

    def update_port_chain(self, context):
        pass

    def create_port_pair_group(self, context):
        pass

    def update_port_pair_group(self, context):
        pass

    def create_port_pair(self, context):
        pass

    def update_port_pair(self, context):
        pass


class DfSfcDriver(_DfSfcDriverHiddenBase):
    def initialize(self):
        self.api_nb = api_nb.NbApi.get_instance(True)

    @log_helpers.log_method_call
    def create_port_chain_postcommit(self, context):
        pc = context.current
        pc_params = pc.get('chain_parameters')

        self.api_nb.portchain.create(
            id=pc['id'],
            topic=pc['tenant_id'],
            name=pc.get('name'),
            port_pair_ids=pc.get('port_pair_groups', ()),
            flow_classifier_ids=pc.get('flow_classifiers', ()),
            proto=pc_params.get('correlation'),
            service_path_id=pc.get('chain_id'),
        )

    @log_helpers.log_method_call
    def update_port_chain_postcommit(self, context):
        pc = context.current

        self.api_nb.portchain.update(
            id=pc['id'],
            topic=pc['tenant_id'],
            name=pc.get('name'),
            port_pair_ids=pc.get('port_pair_groups', ()),
            flow_classifier_ids=pc.get('flow_classifiers', ()),
        )

    @log_helpers.log_method_call
    def delete_port_chain(self, context):
        pc = context.current

        self.api_nb.portchain.delete(
            id=pc['id'],
            topic=pc['tenant_id'],
        )

    @log_helpers.log_method_call
    def create_port_pair_group_postcommit(self, context):
        ppg = context.current
        self.api_nb.portpairgroup.create(
            id=ppg['id'],
            topic=ppg['tenant_id'],
            name=ppg.get('name'),
            port_pair_ids=ppg.get('port_pairs', ()),
            # FIXME lb_fields, service_type
        )

    @log_helpers.log_method_call
    def update_port_pair_group_postcommit(self, context):
        ppg = context.current
        self.api_nb.portpairgroup.update(
            id=ppg['id'],
            topic=ppg['tenant_id'],
            name=ppg.get('name'),
            port_pair_ids=ppg.get('port_pairs', ()),
        )

    @log_helpers.log_method_call
    def delete_port_pair_group(self, context):
        ppg = context.current
        self.api_nb.portpairgroup.delete(
            id=ppg['id'],
            topic=ppg['tenant_id'],
        )

    @log_helpers.log_method_call
    def create_port_pair_postcommit(self, context):
        pp = context.current
        pp_params = pp.get('port_pair_parameters', {})
        self.api_nb.portpair.create(
            id=pp['id'],
            topic=pp['tenant_id'],
            name=pp.get('name'),
            ingress_port=pp['ingress'],
            egress_port=pp['egress'],
            correlation_mechanism=pp_params.get('correlation'),
            weight=pp_params.get('weight')
        )

    @log_helpers.log_method_call
    def update_port_pair_postcommit(self, context):
        pp = context.current
        self.api_nb.portpair.update(
            id=pp['id'],
            topic=pp['tenant_id'],
            name=pp.get('name'),
        )

    @log_helpers.log_method_call
    def delete_port_pair(self, context):
        pp = context.current
        self.api_nb.portpair.delete(
            id=pp['id'],
            topic=pp['tenant_id'],
        )


class _DfFlowClassifierDriverHiddenBase(fc_driver.FlowClassifierDriverBase):
    def create_flow_classifier(self, context):
        pass

    def update_flow_classifier(self, context):
        pass


class DfFlowClassifierDriver(_DfFlowClassifierDriverHiddenBase):
    def initialize(self):
        self.api_nb = api_nb.NbApi.get_instance(True)

    @log_helpers.log_method_call
    def create_flow_classifier_precommit(self, context):
        pass

    @log_helpers.log_method_call
    def create_flow_classifier_postcommit(self, context):
        fc = context.current

        self.api_nb.flowclassifier.create(
            id=fc['id'],
            topic=fc['tenant_id'],
            name=fc.get('name'),
            ether_type=fc.get('ethertype'),
            protocol=fc.get('protocol'),
            source_transport_ports=(
                fc.get('source_port_range_min'),
                fc.get('source_port_range_max'),
            ),
            dest_transport_ports=(
                fc.get('destination_port_range_min'),
                fc.get('destination_port_range_max'),
            ),
            source_cidr=fc.get('source_ip_prefix'),
            destination_cidr=fc.get('destination_ip_prefix'),
            source_port_id=fc.get('logical_source_port'),
            dest_port_id=fc.get('logical_destination_port'),
            l7_parameters=fc.get('l7_parameters'),
        )

    @log_helpers.log_method_call
    def update_flow_classifier_postcommit(self, context):
        fc = context.current

        # Only name can be updated (and description which we ignore)
        self.api_nb.flowclassifier.update(
            id=fc['id'],
            topic=fc['tenant_id'],
            name=fc.get('name'),
        )

    @log_helpers.log_method_call
    def delete_flow_classifier(self, context):
        self.api_nb.flowclassifier.delete(
            id=context.current['id'],
            topic=context.current['tenant_id'],
        )
