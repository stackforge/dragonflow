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
import collections


DatapathElement = collections.namedtuple(
    'DatapathElement',
    ('name', 'type', 'params'),
)


class Connector(
    collections.namedtuple(
        'Connector',
        ('element', 'type', 'connector'),
    ),
):
    @classmethod
    def from_string(cls, val):
        return cls(*val.split(':'))


DatapathWire = collections.namedtuple(
    'DatapathWire',
    ('exitpoint', 'entrypoint'),
)

DatapathConfig = collections.namedtuple(
    'DatapathConfig',
    ('elements', 'wires'),
)


def get_datapath_config():
    return DatapathConfig(
        elements=(
            DatapathElement(
                name='trunk',
                type='trunk',
                params={},
            ),
        ),
        wires=(
            DatapathWire(
                endpoint=Connector.from_string('?:?:?'),
                entrypoint=Connector.from_string(
                    'trunk:in:classification_input',
                )
            ),
            DatapathWire(
                endpoint=Connector.from_string(
                    'trunk:out:classification_output',
                ),
                entrypoint=Connector.from_string('?:?:?'),
            ),
            DatapathWire(
                endpoint=Connector.from_string('?:?:?'),
                entrypoint=Connector.from_string(
                    'trunk:in:dispatch_input',
                ),
            ),
            DatapathWire(
                endpoint=Connector.from_string(
                    'trunk:out:dispatch_output',
                ),
                entrypoint=Connector.from_string('?:?:?'),
            ),
        )
    )
