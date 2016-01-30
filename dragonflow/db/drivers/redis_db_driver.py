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

import redis
from dragonflow.db.drivers.redis_mgt import RedisMgt
from oslo_log import log

from dragonflow.common import exceptions as df_exceptions
from dragonflow.db import db_api

LOG = log.getLogger(__name__)


class RedisDbDriver(db_api.DbApi):

    def __init__(self):
        super(RedisDbDriver, self).__init__()
        self.client = []
        self.remote = []
# need realize connection to DBcluster,record DB Cluster Slot
    redis_mgt = RedisMgt()
    def initialize(self, db_ip, db_port, **args):
        # get remote ip port list
        self.redis_mgt.init_default_node(db_ip, db_port)
        self.redis_mgt.get_cluster_topology()
        self.remote = self.redis_mgt.get_master_list()
        for i in range(len(self.remote)):
            ip_port = self.remote[i]['ip_port'].split(':')
            self.client.append(redis.client.StrictRedis(host=ip_port[0],port=ip_port[1])

    @staticmethod
    def get_redis_mgt():
        return redis_mgt

    def support_publish_subscribe(self):
        return True

    def get_index_from_ip_port(self,ip_port):
        i = 0
        for i in range(len(self.remote)):
            if self.remote[i]['ip_port'] == ip_port:
                return i
        return None

    # return nil is not found
    def get_key(self, table, key,topic=None):
        if topic is None:
            local_key = ('{'+table + '.' + '*' + '}' + '.'+key)
        else:
            local_key = ('{'+table + '.' + topic + '}' + '.'+key)
        try:
            ip_port = self.redis_mgt.assign_to_node(local_key)
            i = self.get_index_from_ip_port(ip_port)
            if i is None:
                raise df_exceptions.DBKeyNotFound(key=local_key)
            return self.client[i].get(local_key)
        except Exception, exception:
            raise df_exceptions.DBKeyNotFound(key=local_key)

    def set_key(self, table, key, value,topic=None):
        if topic is None:
            local_key = ('{'+table + '.' + '*' + '}' + '.'+key)
        else:
            local_key = ('{'+table + '.' + topic + '}' + '.'+key)
        try:
            ip_port = self.redis_mgt.assign_to_node(local_key)
            i = self.get_index_from_ip_port(ip_port)
            if i is None:
                raise df_exceptions.DBKeyNotFound(key=local_key)
            res = self.client[i].set(local_key,value)
            if not res :
                self.client[i].delete('{'+table + '.' + topic + '}' + '.'+key)
            return res
        except Exception, exception:
            raise df_exceptions.DBKeyNotFound(key=local_key)
            
    def create_key(self, table, key, value,topic=None):
        if topic is None:
            local_key = ('{'+table + '.' + '*' + '}' + '.'+key)
        else:
            local_key = ('{'+table + '.' + topic + '}' + '.'+key)
        try:
            ip_port = self.redis_mgt.assign_to_node(local_key)
            i = self.get_index_from_ip_port(ip_port)
            if i is None:
                raise df_exceptions.DBKeyNotFound(key=local_key)
            res = self.client[i].set(local_key, value)
            if not res :
                self.client[i].delete(local_key)
            return res
        except Exception, exception:
            raise df_exceptions.DBKeyNotFound(key=local_key)
    # return 0 means not found
    def delete_key(self, table, key,topic=None):
        if topic is None:
            local_key = ('{'+table + '.' + '*' + '}' + '.'+key)
        else:
            local_key = ('{'+table + '.' + topic + '}' + '.'+key)
        try:
            ip_port = self.redis_mgt.assign_to_node(local_key)
            i = self.get_index_from_ip_port(ip_port)
            if i is None:
                raise df_exceptions.DBKeyNotFound(key=local_key)
            return self.client[i].delete(local_key)
        except Exception, exception:
            raise df_exceptions.DBKeyNotFound(key=local_key)
    # return nil is not found
    def get_all_entries(self,table,topic=None):
        if topic is None:
            local_key = ('{'+table + '.' + '*' + '}' + '.'+'*')
        else:
            local_key = ('{'+table + '.' + topic + '}' + '.'+'*')
        try:
            ip_port = self.redis_mgt.assign_to_node(local_key)
            i = self.get_index_from_ip_port(ip_port)
            if i is None:
                raise df_exceptions.DBKeyNotFound(key=local_key)
            return self.client[i].get(local_key)
        except Exception, exception:
             raise df_exceptions.DBKeyNotFound(key=local_key)

    def get_all_keys(self, table, topic=None):
        pass

    def _allocate_unique_key(self):
        pass

    def allocate_unique_key(self):
        pass

        # no need to realize
    def register_notification_callback(self, callback, topics=None):
        pass

    def uuid_to_key (self,tenant_id, table,uuid):
        local_key = ('{'+table + '.' + tenant_id + '}' + '.'+uuid)
        return local_key

    def check_connection(self,ip_port):
        try:
            i = self.get_index_from_ip_port(ip_port)
            if i is None:
                raise redis.exceptions.ConnectionError
            self.client[i].get(None)
        except (redis.exceptions.ConnectionError,
                redis.exceptions.BusyLoadingError):
            return False
        return True

    def register_topic_for_notification(self, topic):
        pass

    def unregister_topic_for_notification(self, topic):
        pass


