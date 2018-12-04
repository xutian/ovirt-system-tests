#
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
import os

import nose.tools as nt
from ovirtlago import testlib


@testlib.with_ovirt_prefix
def test_initialize_engine(prefix):
    engine = prefix.virt_env.engine_vm()

    answer_file_src = os.path.join(
        os.environ.get('SUITE'),
        'engine-answer-file.conf'
    )
    engine.copy_to(
        answer_file_src,
        '/tmp/answer-file-pre',
    )

    result = engine.ssh(
        [
            'OTOPI_DEBUG=1',
            'engine-setup',
            '--accept-defaults',
            '--config-append=/tmp/answer-file-pre',
        ],
    )

    engine.ssh(
        [
            'ss',
            '-anp',
        ],
    )

    nt.eq_(
        result.code, 0, 'engine-setup failed. Exit code is %s' % result.code
    )

    testlib.assert_true_within_long(
        lambda: engine.service('ovirt-engine').alive()
    )

    testlib.assert_true_within_short(
        lambda: engine.service('ovirt-engine-dwhd').alive()
    )
