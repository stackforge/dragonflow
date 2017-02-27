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

from dragonflow.common import exceptions
from dragonflow.controller.common import constants
from dragonflow.controller import df_base_app
from dragonflow.db.models import trunk


class TrunkApp(df_base_app.DFlowApp):

    @df_base_app.register_event(trunk.ChildPortSegmentation, 'created')
    def _child_port_segmentation_created(self, child_port_segmentation):
        # Classification rule
        self._add_classification_rule(child_port_segmentation)
        # Dispatch rule
        self._add_dispatch_rule(child_port_segmentation)

    def _get_classification_match(self, child_port_segmentation):
        segmentation_type = child_port_segmentation.segmentation_type
        if segmentation_type == 'vlan':
            # TODO(oanson) Not dynamic enough
            return self.parser.OFPMatch(
                in_port=child_port_segmentation.parent.ofport,
                vlan_vid=child_port_segmentation.segmentation_id
            )
        else:
            raise exceptions.UnsupportedSegmentationType(
                segmentation_type=segmentation_type
            )

    def _get_classification_actions(self, child_port_segmentation):
        segmentation_type = child_port_segmentation.segmentation_type
        lport = child_port_segmentation.port
        network_id = lport.get_external_value('local_network_id')
        # TODO(oanson) This code is very similar to classifier app.
        actions = [
            # Set reg6
            self.parser.OFPActionSetField(reg6=lport.get_unique_key()),
            # Set metadata
            self.parser.OFPActionSetField(metadata=network_id),
        ]
        if segmentation_type == 'vlan':
            actions.append(self.parser.OFPActionPopVlan())
        else:
            raise exceptions.UnsupportedSegmentationType(
                segmentation_type=segmentation_type
            )
        return actions

    def _add_classification_rule(self, child_port_segmentation):
        match = self._get_classification_match(child_port_segmentation)
        actions = self._get_classification_actions(child_port_segmentation)
        inst = [
            self.parser.OFPInstructionActions(
                self.ofproto.OFPIT_APPLY_ACTIONS, actions),
            self.parser.OFPInstructionGotoTable(
                constants.EGRESS_PORT_SECURITY_TABLE),
        ]
        self.mod_flow(
            table_id=constants.INGRESS_CLASSIFICATION_DISPATCH_TABLE,
            priority=constants.PRIORITY_HIGH,
            match=match,
            inst=inst,
        )

    def _add_dispatch_rule(self, child_port_segmentation):
        match = self._get_dispatch_match(child_port_segmentation)
        actions = self._get_dispatch_actions(child_port_segmentation)
        self.mod_flow(
            table_id=constants.INGRESS_DISPATCH_TABLE,
            priority=constants.PRIORITY_MEDIUM,
            match=match,
            actions=actions,
        )

    def _get_dispatch_match(self, child_port_segmentation):
        lport = child_port_segmentation.port
        match = self.parser.OFPMatch(reg7=lport.unique_key)
        return match

    def _get_dispatch_actions(self, child_port_segmentation):
        segmentation_type = child_port_segmentation.segmentation_type
        if segmentation_type == 'vlan':
            # TODO(oanson) Not dynamic enough
            vlan_tag = child_port_segmentation.segmentation_id
            vlan_tag |= self.ofproto.OFPVID_PRESENT
            actions = [self.parser.OFPActionPushVlan(),
                       self.parser.OFPActionSetField(vlan_vid=vlan_tag)]
        else:
            raise exceptions.UnsupportedSegmentationType(
                segmentation_type=segmentation_type
            )
        ofport = child_port_segmentation.parent.ofport
        actions.append(
            self.parser.OFPActionOutput(ofport,
                                        self.ofproto.OFPCML_NO_BUFFER))
        return actions

    @df_base_app.register_event(trunk.ChildPortSegmentation, 'deleted')
    def _child_port_segmentation_deleted(self, child_port_segmentation):
        # Classification rule
        self._delete_classification_rule(child_port_segmentation)
        # Dispatch rule
        self._delete_dispatch_rule(child_port_segmentation)

    def _delete_classification_rule(self, child_port_segmentation):
        match = self._get_classification_match(child_port_segmentation)
        self.mod_flow(
            table_id=constants.INGRESS_CLASSIFICATION_DISPATCH_TABLE,
            priority=constants.PRIORITY_HIGH,
            match=match,
            command=self.ofproto.OFPFC_DELETE_STRICT,
        )

    def _delete_dispatch_rule(self, child_port_segmentation):
        match = self._get_dispatch_match(child_port_segmentation)
        self.mod_flow(
            table_id=constants.INGRESS_DISPATCH_TABLE,
            priority=constants.PRIORITY_MEDIUM,
            match=match,
            command=self.ofproto.OFPFC_DELETE_STRICT,
        )
