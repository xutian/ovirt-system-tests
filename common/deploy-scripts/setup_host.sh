set -e

cp /etc/sysconfig/network-scripts/ifcfg-eth0 /tmp/tmp
cat /tmp/tmp | grep -v HWADDR > /etc/sysconfig/network-scripts/ifcfg-eth0
rm -f /tmp/tmp

sed -i '/proxy/d' /etc/yum.conf
echo "proxy=http://148.87.19.20:80" >> /etc/yum.conf
sed -i '/proxy/d' /etc/yum.repos.d/ovirt-4.2.repo
sed -i '/proxy/d' /etc/yum.repos.d/ovirt-4.2-dependencies.repo 


yum install -y deltarpm
#workaround for https://bugzilla.redhat.com/show_bug.cgi?id=1258868
# It delays tuned initialization, as dbus is rejecting 'partial' files
# that were just installed via RPM. Workaround: restart dbus.
# Cuts 2 minutes from host installation
yum update -y tuned && systemctl restart dbus
