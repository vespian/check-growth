#!/usr/bin/env python3
# Copyright (c) 2014 Zadane.pl sp. z o.o.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

import os.path as op

#Where am I ?
_module_dir = op.dirname(op.realpath(__file__))
_main_dir = op.abspath(op.join(_module_dir, '..'))
_fabric_base_dir = op.join(_main_dir, 'fabric/')

#Test mountpoint location:
MOUNTPOINT_DIRS = ['/dev/shm/', '/tmp']

#Configfile location
TEST_CONFIG_FILE = op.join(_fabric_base_dir, 'check_growth-mopconfig.yml')

#Test lockfile location:
TEST_LOCKFILE = op.join(_fabric_base_dir, 'filelock.pid')

#Test historyfile location
TEST_STATUSFILE = op.join(_fabric_base_dir, 'check_growth.status.yml')
