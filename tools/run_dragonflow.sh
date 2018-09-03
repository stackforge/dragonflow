#!/bin/bash

# First get all the arguments
while test ${#} -gt 0; do
  case $1 in
    --dragonflow_address)
      shift
      DRAGONFLOW_ADDRESS=$1
      ;;
    --db_address)
      shift
      DB_ADDRESS=$1
      ;;
    --mgmt_address)
      shift
      MANAGEMENT_IP=$1
      ;;
    --db_init)
      DB_INIT=1
      ;;
    --nb_db_driver)
      shift
      NB_DB_DRIVER=$1
      ;;
    --pubsub_driver)
      shift
      PUBSUB_DRIVER=$1
      ;;
    --)
      shift
      break
      ;;
    *)
      echo >&2 "Unknown command line argument: $1"
      exit 1
      ;;
  esac
  shift
done

# Use defaults if not supplied
NB_DB_DRIVER=${NB_DB_DRIVER:-etcd_nb_db_driver}
PUBSUB_DRIVER=${PUBSUB_DRIVER:-etcd_pubsub_driver}

if [ ! -d /etc/dragonflow ]; then
  mkdir -p /etc/dragonflow
fi
# Set parameters to the ini file
if [ ! -e /etc/dragonflow/dragonflow.ini ]; then
  sed -e "s/LOCAL_IP/$DRAGONFLOW_ADDRESS/g" etc/standalone/dragonflow.ini | \
    sed -e "s/MANAGEMENT_IP/$MANAGEMENT_IP/g" | \
    sed -e "s/DB_SERVER_IP/$DB_ADDRESS/g" | \
    sed -e "s/NB_DB_DRIVER/NB_DB_DRIVER/g" | \
    sed -e "s/PUBSUB_DRIVER/PUBSUB_DRIVER/g"  > /etc/dragonflow/dragonflow.ini
fi
if [ ! -e /etc/dragonflow/dragonflow_datapath_layout.yaml ]; then
  cp etc/dragonflow_datapath_layout.yaml /etc/dragonflow
fi

if [ ! -e /etc/neutron ]; then
  ln -s /etc/dragonflow /etc/neutron
fi

if [ ! -e /etc/neutron/neutron.conf ]; then
  touch /etc/neutron/neutron.conf
fi

if [ -n "$DB_INIT" ]; then
  df-db init
fi

if [ -z "$DF_NO_CONTROLLER" ]; then
  /usr/local/bin/df-local-controller --config-file /etc/dragonflow/dragonflow.ini
else
  /bin/bash
fi
