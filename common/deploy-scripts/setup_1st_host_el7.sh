#!/bin/bash -xe
set -ex

sed -i '/proxy/d' /etc/yum.conf
sed -i '/proxy/d' /etc/yum.repos.d/ovirt-4.2.repo
sed -i '/proxy/d' /etc/yum.repos.d/ovirt-4.2-dependencies.repo 
sed -i '/keepcache/a\proxy=http://148.87.19.20:80' /etc/yum.conf
sed -i '/keepcache/a\timeout=120' /etc/yum.conf
sed -i '/keepcache/a\retries=20' /etc/yum.conf

yum-config-manager --enable ol7_optional_latest ol7_developer_EPEL ol7_gluster312 ol7_openstack50 ol7_openstack50_extras
yum install -y deltarpm 
yum install -y yum-plugin-priorities
rpm -q iproute-4.11.0-14.el7.x86_64 || yum install -y iproute-tc

yum-config-manager  --save --setopt=ol7_kvm.priority=10 >/dev/null 2>&1
yum-config-manager  --save --setopt=ol7_latest.priority=20 >/dev/null 2>&1
yum-config-manager  --save --setopt=ol7_openstack50.priority=99 > /dev/null 2>&1
yum-config-manager  --save --setopt=ol7_openstack50_extras.priority=99 > /dev/null 2>&1
yum update -y qemu-kvm qemu-img
yum-config-manager --save --setopt=ol7_kvm.exclude=libvirt*
yum install -y ovirt-host
 
sed -i '/# ssl =/ a\ssl =true' /etc/vdsm/vdsm.conf 

#sed -i '/#auth_tcp =/ a\auth_tcp = "sasl"' /etc/libvirt/libvirtd.conf

sed -i '/#spice_tls =/ a\spice_tls = 1' /etc/libvirt/qemu.conf 

vdsm-tool configure --force

systemctl restart vdsmd

rm -rf /dev/shm/*.rpm /dev/shm/yum
