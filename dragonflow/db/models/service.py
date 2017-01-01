# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from jsonmodels import fields
from oslo_utils import timeutils
import six

from dragonflow.common import utils as df_utils
from dragonflow import conf as cfg
import dragonflow.db.field_types as df_fields
import dragonflow.db.model_framework as mf
from dragonflow.db.neutron import lockedobjects_db as lock_db


def generate_service_id(chassis, binary):
    chassis_id = chassis
    if not isinstance(chassis, six.string_types):
        chassis_id = chassis.id
    return df_utils.generate_uuid(chassis_id, binary)


@mf.register_model
@mf.construct_nb_db_model
class Service(mf.ModelBase):
    table_name = 'service'

    chassis = df_fields.ReferenceField('Chassis', required=True)
    binary = fields.StringField(required=True)
    last_seen_up = df_fields.TimestampField()
    disabled = fields.BoolField()
    disabled_reason = fields.StringField()

    def on_create_pre(self):
        self.id = generate_service_id(self.chassis, self.binary)
        # TODO(oanson) Verify it doesn't exist

    def refresh_last_seen(self):
        """Refresh the timestamp in the last_seen_up field to now"""
        self.last_seen_up = timeutils.now()

    @property
    def alive(self):
        """
        Returns true if the service is alive, i.e. if the last time it
        'checked in' is less than the <timeout> ago.
        :return:    True if the service is alive
        """
        last_seen_up = self.last_seen_up
        report_time_diff = timeutils.now() - last_seen_up
        return (report_time_diff <= cfg.CONF.df.service_down_time)

    @classmethod
    def _get_instance_of_bin_on_chassis(cls, nb_api, chassis, binary):
        """
        Return a service instance of the binary running on chassis
        :param nb_api:  NB dataabse API
        :type nb_api:   api_nb.NbApi
        :param chassis: The chassis on which the service runs
        :type chassis:  string or core.Chassis
        :param binary:  The name of the service on the chassis
        :type binary:   String
        :return:        service instance
        """
        return nb_api.get(cls(id=generate_service_id(chassis, binary)))

    @classmethod
    @lock_db.wrap_db_lock(lock_db.RESOURCE_SERVICE_STATUS)
    def update_last_seen(cls, nb_api, chassis, binary):
        """
        Read the service for the given binary on the given chassis from the
        given nb database. Refresh it's last_seen_up field, and save it back
        into the database.
        :param nb_api:  NB dataabse API
        :type nb_api:   api_nb.NbApi
        :param chassis: The chassis on which the service runs
        :type chassis:  string or core.Chassis
        :param binary:  The name of the service on the chassis
        :type binary:   String
        """
        instance = cls._get_instance_of_bin_on_chassis(nb_api, chassis, binary)
        instance.refresh_last_seen()
        nb_api.update(instance)

    @classmethod
    def is_alive(cls, nb_api, chassis, binary):
        """
        Read the service for the given binary on the given chassis from the
        given nb database. Returns true if the service is alive (as defined
        by the alive property)
        :param nb_api:  NB dataabse API
        :type nb_api:   api_nb.NbApi
        :param chassis: The chassis on which the service runs
        :type chassis:  string or core.Chassis
        :param binary:  The name of the service on the chassis
        :type binary:   String
        :return:        True if the service is alive
        """
        instance = cls._get_instance_of_bin_on_chassis(nb_api, chassis, binary)
        return instance.alive
