#!/usr/bin/env python3
#
# Copyright (C) 2021 VyOS maintainers and contributors
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

import os

from sys import exit

from vyos.config import Config
from vyos.configdict import dict_merge
from vyos.template import render_to_string
from vyos.util import dict_search
from vyos.xml import defaults
from vyos import ConfigError
from vyos import frr
from vyos import airbag
airbag.enable()

frr_daemon = 'bgpd'

def get_config(config=None):
    if config:
        conf = config
    else:
        conf = Config()
    base = ['protocols', 'rpki']

    rpki = conf.get_config_dict(base, key_mangling=('-', '_'), get_first_key=True)
    if not conf.exists(base):
        return rpki

    # We have gathered the dict representation of the CLI, but there are default
    # options which we need to update into the dictionary retrived.
    default_values = defaults(base)
    rpki = dict_merge(default_values, rpki)

    return rpki

def verify(rpki):
    if not rpki:
        return None

    if 'cache' in rpki:
        preferences = []
        for peer, peer_config in rpki['cache'].items():
            for mandatory in ['port', 'preference']:
                if mandatory not in peer_config:
                    raise ConfigError(f'RPKI cache "{peer}" {mandatory} must be defined!')

            if 'preference' in peer_config:
                preference = peer_config['preference']
                if preference in preferences:
                    raise ConfigError(f'RPKI cache with preference {preference} already configured!')
                preferences.append(preference)

            if 'ssh' in peer_config:
                files = ['private_key_file', 'public_key_file', 'known_hosts_file']
                for file in files:
                    if file not in peer_config['ssh']:
                        raise ConfigError('RPKI+SSH requires username, public/private ' \
                                          'keys and known-hosts file to be defined!')

                    filename = peer_config['ssh'][file]
                    if not os.path.exists(filename):
                        raise ConfigError(f'RPKI SSH {file.replace("-","-")} "{filename}" does not exist!')

    return None

def generate(rpki):
    rpki['new_frr_config'] = render_to_string('frr/rpki.frr.tmpl', rpki)
    return None

def apply(rpki):
    # Save original configuration prior to starting any commit actions
    frr_cfg = frr.FRRConfig()
    frr_cfg.load_configuration(frr_daemon)
    frr_cfg.modify_section('rpki', '')
    frr_cfg.add_before(r'(ip prefix-list .*|route-map .*|line vty)', rpki['new_frr_config'])
    frr_cfg.commit_configuration(frr_daemon)

    # If FRR config is blank, re-run the blank commit x times due to frr-reload
    # behavior/bug not properly clearing out on one commit.
    if rpki['new_frr_config'] == '':
        for a in range(5):
            frr_cfg.commit_configuration(frr_daemon)

    return None

if __name__ == '__main__':
    try:
        c = get_config()
        verify(c)
        generate(c)
        apply(c)
    except ConfigError as e:
        print(e)
        exit(1)