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

from networking_sfc.services.sfc.drivers import base

from dragonflow.db.models import sfc
from dragonflow.neutron.services import mixins


def _get_optional_params(obj, *params):
    '''This function returns a dictionary with all the parameters from `params`
    that were present in `obj`, for example:


    >>> _get_optional_params({'a': 1, 'b': 2}, 'a', 'c')
    {'a': 1}
    '''

    res = {}
    for param in params:
        if param in obj:
            res[param] = obj.get(param)
    return res


class DfSfcDriver(base.SfcDriverBase, mixins.LazyNbApiMixin):
    def initialize(self):
        pass

    # The new SFC driver API:
    def create_port_chain_postcommit(self, context):
        pc = context.current
        pc_params = pc.get('chain_parameters')

        self.nb_api.create(
            sfc.PortChain(
                id=pc['id'],
                topic=pc['project_id'],
                name=pc.get('name'),
                port_pair_groups=pc.get('port_pair_groups', []),
                flow_classifiers=pc.get('flow_classifiers', []),
                protocol=pc_params.get('correlation'),
                chain_id=pc.get('chain_id'),
            ),
        )

    def update_port_chain_postcommit(self, context):
        pc = context.current

        self.nb_api.update(
            sfc.PortChain(
                id=pc['id'],
                topic=pc['project_id'],
                name=pc.get('name'),
                **_get_optional_params(
                    pc,
                    'port_pair_groups',
                    'flow_classifiers',
                )
            ),
        )

    def delete_port_chain(self, context):
        pc = context.current

        self.nb_api.delete(
            sfc.PortChain(
                id=pc['id'],
                topic=pc['project_id'],
            ),
        )

    def create_port_pair_group_postcommit(self, context):
        ppg = context.current

        self.nb_api.create(
            sfc.PortPairGroup(
                id=ppg['id'],
                topic=ppg['project_id'],
                name=ppg.get('name'),
                port_pairs=list(ppg.get('port_pairs', [])),
                # FIXME (dimak) add support for lb_fields, service_type
            ),
        )

    def update_port_pair_group_postcommit(self, context):
        ppg = context.current

        self.nb_api.update(
            sfc.PortPairGroup(
                id=ppg['id'],
                topic=ppg['project_id'],
                name=ppg.get('name'),
                **_get_optional_params(ppg, 'port_pairs')
            ),
        )

    def delete_port_pair_group(self, context):
        ppg = context.current
        self.nb_api.delete(
            sfc.PortPairGroup(
                id=ppg['id'],
                topic=ppg['project_id'],
            ),
        )

    def create_port_pair_postcommit(self, context):
        pp = context.current
        sf_params = pp.get('service_function_parameters', {})

        self.nb_api.create(
            sfc.PortPair(
                id=pp['id'],
                topic=pp['project_id'],
                name=pp.get('name'),
                ingress_port=pp['ingress'],
                egress_port=pp['egress'],
                correlation_mechanism=(
                    sf_params.get('correlation') or sfc.CORR_NONE
                ),
                weight=sf_params.get('weight')
            ),
        )

    def update_port_pair_postcommit(self, context):
        pp = context.current

        self.nb_api.update(
            sfc.PortPair(
                id=pp['id'],
                topic=pp['project_id'],
                name=pp.get('name'),
            ),
        )

    def delete_port_pair(self, context):
        pp = context.current

        self.nb_api.delete(
            sfc.PortPair(
                id=pp['id'],
                topic=pp['project_id'],
            ),
        )

    # Legacy SFC driver API, has to be stubbed due to ABC
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