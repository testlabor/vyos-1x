#!/usr/bin/env python3
#
# Copyright (C) 2020-2021 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import unittest

from base_interfaces_test import BasicInterfaceTest

from vyos.configsession import ConfigSessionError
from vyos.util import get_interface_config
from vyos.template import inc_ip

remote_ip4 = '192.0.2.100'
remote_ip6 = '2001:db8::ffff'
source_if = 'dum2222'
mtu = 1476

class TunnelInterfaceTest(BasicInterfaceTest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._test_ip = True
        cls._test_ipv6 = True
        cls._test_mtu = True
        cls._base_path = ['interfaces', 'tunnel']
        cls.local_v4 = '192.0.2.1'
        cls.local_v6 = '2001:db8::1'
        cls._options = {
            'tun10': ['encapsulation ipip', 'remote 192.0.2.10', 'source-address ' + cls.local_v4],
            'tun20': ['encapsulation gre',  'remote 192.0.2.20', 'source-address ' + cls.local_v4],
        }
        cls._interfaces = list(cls._options)
        # call base-classes classmethod
        super(cls, cls).setUpClass()

    def setUp(self):
        super().setUp()
        self.cli_set(['interfaces', 'dummy', source_if, 'address', self.local_v4 + '/32'])
        self.cli_set(['interfaces', 'dummy', source_if, 'address', self.local_v6 + '/128'])

    def tearDown(self):
        self.cli_delete(['interfaces', 'dummy', source_if])
        super().tearDown()

    def test_ipv4_encapsulations(self):
        # When running tests ensure that for certain encapsulation types the
        # local and remote IP address is actually an IPv4 address

        interface = f'tun1000'
        local_if_addr = f'10.10.200.1/24'
        for encapsulation in ['ipip', 'sit', 'gre', 'gretap']:
            self.cli_set(self._base_path + [interface, 'address', local_if_addr])
            self.cli_set(self._base_path + [interface, 'encapsulation', encapsulation])
            self.cli_set(self._base_path + [interface, 'source-address', self.local_v6])
            self.cli_set(self._base_path + [interface, 'remote', remote_ip6])

            # Encapsulation mode requires IPv4 source-address
            with self.assertRaises(ConfigSessionError):
                self.cli_commit()
            self.cli_set(self._base_path + [interface, 'source-address', self.local_v4])

            # Encapsulation mode requires IPv4 remote
            with self.assertRaises(ConfigSessionError):
                self.cli_commit()
            self.cli_set(self._base_path + [interface, 'remote', remote_ip4])
            self.cli_set(self._base_path + [interface, 'source-interface', source_if])

            # Source interface can not be used with sit and gretap
            if encapsulation in ['sit', 'gretap']:
                with self.assertRaises(ConfigSessionError):
                    self.cli_commit()
                self.cli_delete(self._base_path + [interface, 'source-interface'])

            # Check if commit is ok
            self.cli_commit()

            conf = get_interface_config(interface)
            if encapsulation not in ['sit', 'gretap']:
                self.assertEqual(source_if, conf['link'])

            self.assertEqual(interface, conf['ifname'])
            self.assertEqual(mtu, conf['mtu'])
            self.assertEqual(encapsulation, conf['linkinfo']['info_kind'])
            self.assertEqual(self.local_v4, conf['linkinfo']['info_data']['local'])
            self.assertEqual(remote_ip4,    conf['linkinfo']['info_data']['remote'])
            self.assertTrue(conf['linkinfo']['info_data']['pmtudisc'])

            # cleanup this instance
            self.cli_delete(self._base_path + [interface])
            self.cli_commit()

    def test_ipv6_encapsulations(self):
        # When running tests ensure that for certain encapsulation types the
        # local and remote IP address is actually an IPv6 address

        interface = f'tun1010'
        local_if_addr = f'10.10.200.1/24'
        for encapsulation in ['ipip6', 'ip6ip6', 'ip6gre', 'ip6gretap']:
            self.cli_set(self._base_path + [interface, 'address', local_if_addr])
            self.cli_set(self._base_path + [interface, 'encapsulation', encapsulation])
            self.cli_set(self._base_path + [interface, 'source-address', self.local_v4])
            self.cli_set(self._base_path + [interface, 'remote', remote_ip4])

            # Encapsulation mode requires IPv6 source-address
            with self.assertRaises(ConfigSessionError):
                self.cli_commit()
            self.cli_set(self._base_path + [interface, 'source-address', self.local_v6])

            # Encapsulation mode requires IPv6 remote
            with self.assertRaises(ConfigSessionError):
                self.cli_commit()
            self.cli_set(self._base_path + [interface, 'remote', remote_ip6])

            # Configure Tunnel Source interface
            self.cli_set(self._base_path + [interface, 'source-interface', source_if])
            # Source interface can not be used with ip6gretap
            if encapsulation in ['ip6gretap']:
                with self.assertRaises(ConfigSessionError):
                    self.cli_commit()
                self.cli_delete(self._base_path + [interface, 'source-interface'])

            # Check if commit is ok
            self.cli_commit()

            conf = get_interface_config(interface)
            if encapsulation not in ['ip6gretap']:
                self.assertEqual(source_if, conf['link'])

            self.assertEqual(interface, conf['ifname'])
            self.assertEqual(mtu, conf['mtu'])

            # Not applicable for ip6gre
            if 'proto' in conf['linkinfo']['info_data']:
                self.assertEqual(encapsulation, conf['linkinfo']['info_data']['proto'])

            # remap encapsulation protocol(s) only for ipip6, ip6ip6
            if encapsulation in ['ipip6', 'ip6ip6']:
                encapsulation = 'ip6tnl'

            self.assertEqual(encapsulation, conf['linkinfo']['info_kind'])
            self.assertEqual(self.local_v6, conf['linkinfo']['info_data']['local'])
            self.assertEqual(remote_ip6,    conf['linkinfo']['info_data']['remote'])

            # cleanup this instance
            self.cli_delete(self._base_path + [interface])
            self.cli_commit()

    def test_tunnel_verify_local_dhcp(self):
        # We can not use source-address and dhcp-interface at the same time

        interface = f'tun1020'
        local_if_addr = f'10.0.0.1/24'

        self.cli_set(self._base_path + [interface, 'address', local_if_addr])
        self.cli_set(self._base_path + [interface, 'encapsulation', 'gre'])
        self.cli_set(self._base_path + [interface, 'source-address', self.local_v4])
        self.cli_set(self._base_path + [interface, 'remote', remote_ip4])
        self.cli_set(self._base_path + [interface, 'dhcp-interface', 'eth0'])

        # source-address and dhcp-interface can not be used at the same time
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()
        self.cli_delete(self._base_path + [interface, 'dhcp-interface'])

        # Check if commit is ok
        self.cli_commit()

    def test_tunnel_parameters_gre(self):
        interface = f'tun1030'
        gre_key = '10'
        encapsulation = 'gre'
        tos = '20'

        self.cli_set(self._base_path + [interface, 'encapsulation', encapsulation])
        self.cli_set(self._base_path + [interface, 'source-address', self.local_v4])
        self.cli_set(self._base_path + [interface, 'remote', remote_ip4])

        self.cli_set(self._base_path + [interface, 'parameters', 'ip', 'no-pmtu-discovery'])
        self.cli_set(self._base_path + [interface, 'parameters', 'ip', 'key', gre_key])
        self.cli_set(self._base_path + [interface, 'parameters', 'ip', 'tos', tos])

        # Check if commit is ok
        self.cli_commit()

        conf = get_interface_config(interface)
        self.assertEqual(mtu,           conf['mtu'])
        self.assertEqual(interface,     conf['ifname'])
        self.assertEqual(encapsulation, conf['linkinfo']['info_kind'])
        self.assertEqual(self.local_v4, conf['linkinfo']['info_data']['local'])
        self.assertEqual(remote_ip4,    conf['linkinfo']['info_data']['remote'])
        self.assertEqual(0,             conf['linkinfo']['info_data']['ttl'])
        self.assertFalse(               conf['linkinfo']['info_data']['pmtudisc'])

    def test_gretap_parameters_change(self):
        interface = f'tun1040'
        gre_key = '10'
        encapsulation = 'gretap'
        tos = '20'

        self.cli_set(self._base_path + [interface, 'encapsulation', encapsulation])
        self.cli_set(self._base_path + [interface, 'source-address', self.local_v4])
        self.cli_set(self._base_path + [interface, 'remote', remote_ip4])

        # Check if commit is ok
        self.cli_commit()

        conf = get_interface_config(interface)
        self.assertEqual(mtu,           conf['mtu'])
        self.assertEqual(interface,     conf['ifname'])
        self.assertEqual(encapsulation, conf['linkinfo']['info_kind'])
        self.assertEqual(self.local_v4, conf['linkinfo']['info_data']['local'])
        self.assertEqual(remote_ip4,    conf['linkinfo']['info_data']['remote'])
        self.assertEqual(0,             conf['linkinfo']['info_data']['ttl'])

        # Change remote ip address (inc host by 2
        new_remote = inc_ip(remote_ip4, 2)
        self.cli_set(self._base_path + [interface, 'remote', new_remote])
        # Check if commit is ok
        self.cli_commit()

        conf = get_interface_config(interface)
        self.assertEqual(new_remote,    conf['linkinfo']['info_data']['remote'])

    def test_erspan_v1(self):
        interface = f'tun1070'
        encapsulation = 'erspan'
        ip_key = '77'
        idx = '20'

        self.cli_set(self._base_path + [interface, 'encapsulation', encapsulation])
        self.cli_set(self._base_path + [interface, 'source-address', self.local_v4])
        self.cli_set(self._base_path + [interface, 'remote', remote_ip4])

        self.cli_set(self._base_path + [interface, 'parameters', 'erspan', 'index', idx])

        # ERSPAN requires ip key parameter
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()
        self.cli_set(self._base_path + [interface, 'parameters', 'ip', 'key', ip_key])

        # Check if commit is ok
        self.cli_commit()

        conf = get_interface_config(interface)
        self.assertEqual(mtu,               conf['mtu'])
        self.assertEqual(interface,         conf['ifname'])
        self.assertEqual(encapsulation,     conf['linkinfo']['info_kind'])
        self.assertEqual(self.local_v4,     conf['linkinfo']['info_data']['local'])
        self.assertEqual(remote_ip4,        conf['linkinfo']['info_data']['remote'])
        self.assertEqual(0,                 conf['linkinfo']['info_data']['ttl'])
        self.assertEqual(f'0.0.0.{ip_key}', conf['linkinfo']['info_data']['ikey'])
        self.assertEqual(f'0.0.0.{ip_key}', conf['linkinfo']['info_data']['okey'])
        self.assertEqual(int(idx),          conf['linkinfo']['info_data']['erspan_index'])
        # version defaults to 1
        self.assertEqual(1,                 conf['linkinfo']['info_data']['erspan_ver'])
        self.assertTrue(                    conf['linkinfo']['info_data']['iseq'])
        self.assertTrue(                    conf['linkinfo']['info_data']['oseq'])

        # Change remote ip address (inc host by 2
        new_remote = inc_ip(remote_ip4, 2)
        self.cli_set(self._base_path + [interface, 'remote', new_remote])
        # Check if commit is ok
        self.cli_commit()

        conf = get_interface_config(interface)
        self.assertEqual(new_remote,    conf['linkinfo']['info_data']['remote'])

    def test_ip6erspan_v2(self):
        interface = f'tun1070'
        encapsulation = 'ip6erspan'
        ip_key = '77'
        erspan_ver = 2
        direction = 'ingress'

        self.cli_set(self._base_path + [interface, 'encapsulation', encapsulation])
        self.cli_set(self._base_path + [interface, 'source-address', self.local_v6])
        self.cli_set(self._base_path + [interface, 'remote', remote_ip6])

        # ERSPAN requires ip key parameter
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()
        self.cli_set(self._base_path + [interface, 'parameters', 'ip', 'key', ip_key])

        self.cli_set(self._base_path + [interface, 'parameters', 'erspan', 'version', str(erspan_ver)])

        # ERSPAN index is not valid on version 2
        self.cli_set(self._base_path + [interface, 'parameters', 'erspan', 'index', '10'])
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()
        self.cli_delete(self._base_path + [interface, 'parameters', 'erspan', 'index'])

        # ERSPAN requires direction to be set
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()
        self.cli_set(self._base_path + [interface, 'parameters', 'erspan', 'direction', direction])

        # Check if commit is ok
        self.cli_commit()

        conf = get_interface_config(interface)
        self.assertEqual(mtu,               conf['mtu'])
        self.assertEqual(interface,         conf['ifname'])
        self.assertEqual(encapsulation,     conf['linkinfo']['info_kind'])
        self.assertEqual(self.local_v6,     conf['linkinfo']['info_data']['local'])
        self.assertEqual(remote_ip6,        conf['linkinfo']['info_data']['remote'])
        self.assertEqual(0,                 conf['linkinfo']['info_data']['ttl'])
        self.assertEqual(f'0.0.0.{ip_key}', conf['linkinfo']['info_data']['ikey'])
        self.assertEqual(f'0.0.0.{ip_key}', conf['linkinfo']['info_data']['okey'])
        self.assertEqual(erspan_ver,        conf['linkinfo']['info_data']['erspan_ver'])
        self.assertEqual(direction,         conf['linkinfo']['info_data']['erspan_dir'])
        self.assertTrue(                    conf['linkinfo']['info_data']['iseq'])
        self.assertTrue(                    conf['linkinfo']['info_data']['oseq'])

        # Change remote ip address (inc host by 2
        new_remote = inc_ip(remote_ip6, 2)
        self.cli_set(self._base_path + [interface, 'remote', new_remote])
        # Check if commit is ok
        self.cli_commit()

        conf = get_interface_config(interface)
        self.assertEqual(new_remote,    conf['linkinfo']['info_data']['remote'])

if __name__ == '__main__':
    unittest.main(verbosity=2)