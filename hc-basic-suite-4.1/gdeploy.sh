#!/bin/bash -e
HOST0ADDR=$1
HOST1ADDR=$2
HOST2ADDR=$3

sed \
    -e "s,@HOST0@,${HOST0ADDR},g" \
    -e "s,@HOST1@,${HOST1ADDR},g" \
    -e "s,@HOST2@,${HOST2ADDR},g" \
    < /root/robo.conf.in \
    > /root/robo.conf

gdeploy -c /root/robo.conf


RET_CODE=$?
if [ ${RET_CODE} -ne 0 ]; then
    echo "gdeploy failed with status ${RET_CODE}."
    exit ${RET_CODE}
fi
