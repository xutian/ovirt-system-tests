#
# Copyright 2018 Red Hat, Inc.
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
import ovirtsdk4


def sd_deactivation_error_not_due_to_busy(error):
    """
    :param error: the error raised by a storage domain deactivation request
    :return: true if the error is not a 'storage domain busy' error.
    """
    CANNOT_DEACTIVATE = 'Cannot deactivate'
    HAS_RUNNING_TASKS = 'while there are running tasks'
    RELATED_OP = 'Related operation is currently in progress'
    return not (
        isinstance(error, ovirtsdk4.Error) and
        CANNOT_DEACTIVATE in str(error) and
        (HAS_RUNNING_TASKS in str(error) or RELATED_OP in str(error))
    )


def sd_destroy_error_not_due_to_busy(error):
    """
    :param error: the error raised by a storage domain destroy request
    :return: true if the error is not a 'storage domain busy' error.
    """
    CANNOT_DESTROY = 'Cannot destroy'
    RELATED_OP = 'Related operation is currently in progress'
    TRY_AGAIN_LATER = 'Please try again later'
    return not (
        isinstance(error, ovirtsdk4.Error) and
        CANNOT_DESTROY in str(error) and
        RELATED_OP in str(error) and
        TRY_AGAIN_LATER in str(error)
    )
