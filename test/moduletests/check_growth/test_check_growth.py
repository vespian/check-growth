#!/usr/bin/env python3
# Copyright (c) 2014 Zadane.pl sp. z o.o.
# Copyright (c) 2013 Spotify AB
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

# Global imports:
import mock
import os
import subprocess
import sys
import unittest

# To perform local imports first we need to fix PYTHONPATH:
pwd = os.path.abspath(os.path.dirname(__file__))
sys.path.append(os.path.abspath(pwd + '/../../modules/'))

# Local imports:
import file_paths as paths
import check_growth


class TestCheckGrowth(unittest.TestCase):

    # Used by side effects:
    @staticmethod
    def _terminate_script(*unused):
        raise SystemExit(0)

    # Fake configuration data factory:
    def _script_conf_factory(self, **kwargs):
        good_configuration = {"lockfile": paths.TEST_LOCKFILE,
                              "history_file": paths.TEST_STATUSFILE,
                              "timeframe": 365,
                              "max_averaging_window": 14,
                              "min_averaging_window": 7,
                              "memory_mon_enabled": True,
                              "memory_mon_warn_reduction": 20,
                              "memory_mon_crit_reduction": 40,
                              "disk_mon_enabled": True,
                              "disk_mountpoints": ["/fake/mountpoint/",
                                                   "/faker/mountpoint/",
                                                   "/not/a/mountpoint"],
                              "disk_mon_warn_reduction": 20,
                              "disk_mon_crit_reduction": 40,
                              }

        def func(key):
            config = good_configuration.copy()
            config.update(kwargs)
            self.assertIn(key, config)
            return config[key]

        return func

    @mock.patch('sys.exit')
    def test_command_line_parsing(self, SysExitMock):
        old_args = sys.argv

        # General parsing:
        sys.argv = ['./check_growth.py', '-v', '-s', '-c', './check_growth.json']
        parsed_cmdline = check_growth.parse_command_line()
        self.assertEqual(parsed_cmdline, {'std_err': True,
                                          'config_file': './check_growth.json',
                                          'verbose': True,
                                          'clean_histdata': False,
                                          })

        # Config file should be a mandatory argument:
        sys.argv = ['./check_growth.py', ]
        # Suppres warnings from argparse
        with mock.patch('sys.stderr'):
            parsed_cmdline = check_growth.parse_command_line()
        SysExitMock.assert_called_once_with(2)

        # Test default values:
        sys.argv = ['./check_growth.py', '-c', './check_growth.json']
        parsed_cmdline = check_growth.parse_command_line()
        self.assertEqual(parsed_cmdline, {'std_err': False,
                                          'config_file': './check_growth.json',
                                          'verbose': False,
                                          'clean_histdata': False,
                                          })

        sys.argv = old_args

    @mock.patch('check_growth.ScriptConfiguration')
    @mock.patch('check_growth.ScriptStatus')
    def test_config_verification(self, ScriptStatusMock, ScriptConfigurationMock):
        ScriptStatusMock.notify_immediate.side_effect = self._terminate_script

        # Check if values are checked for being greater than 0:
        ScriptConfigurationMock.get_val.side_effect = \
            self._script_conf_factory(timeframe=-7,
                                      max_averaging_window=-3,
                                      memory_mon_warn_reduction=-10,
                                      memory_mon_crit_reduction=-100,
                                      disk_mon_warn_reduction=0,
                                      disk_mon_crit_reduction=-5)
        with self.assertRaises(SystemExit):
            check_growth.verify_conf()
        status, msg = ScriptStatusMock.notify_immediate.call_args[0]
        self.assertEqual(status, 'unknown')
        self.assertIn('Timeframe should be a positive int', msg)
        self.assertIn('Max averaging window should be a positive int', msg)
        self.assertIn('memory_mon_warn_reduction should be a positive int', msg)
        self.assertIn('memory_mon_crit_reduction should be a positive int', msg)
        self.assertIn('disk_mon_warn_reduction should be a positive int', msg)
        self.assertIn('disk_mon_crit_reduction should be a positive int', msg)

        # Check if limits are sane:
        ScriptConfigurationMock.get_val.side_effect = \
            self._script_conf_factory(memory_mon_warn_reduction=30,
                                      memory_mon_crit_reduction=20,
                                      disk_mon_warn_reduction=10,
                                      disk_mon_crit_reduction=5)
        with self.assertRaises(SystemExit):
            check_growth.verify_conf()
        status, msg = ScriptStatusMock.notify_immediate.call_args[0]
        self.assertEqual(status, 'unknown')
        self.assertIn('memory_mon_warn_reduction should be lower ' +
                      'than memory_mon_crit_reduction', msg)
        self.assertIn('disk_mon_warn_reduction should be lower than ' +
                      'disk_mon_crit_reduction', msg)

        # Check checking if at least one check type is enabled:
        ScriptConfigurationMock.get_val.side_effect = \
            self._script_conf_factory(memory_mon_enabled=False,
                                      disk_mon_enabled=False,)
        with self.assertRaises(SystemExit):
            check_growth.verify_conf()
        status, msg = ScriptStatusMock.notify_immediate.call_args[0]
        self.assertEqual(status, 'unknown')
        self.assertIn('There should be at least one resourece check enabled.',
                      msg)

        # Check if good configuration is accepted:
        ScriptConfigurationMock.get_val.side_effect = \
            self._script_conf_factory(disk_mountpoints=paths.MOUNTPOINT_DIRS)
        check_growth.verify_conf()

    @mock.patch('check_growth.fetch_inode_usage')
    @mock.patch('check_growth.fetch_disk_usage')
    @mock.patch('check_growth.fetch_memory_usage')
    @mock.patch('check_growth.find_planned_grow_ratio')
    @mock.patch('check_growth.find_current_grow_ratio')
    @mock.patch('check_growth.HistoryFile')
    @mock.patch('check_growth.sys.exit')
    @mock.patch('check_growth.ScriptLock')
    @mock.patch('check_growth.ScriptStatus')
    @mock.patch('check_growth.verify_conf')
    @mock.patch('check_growth.ScriptConfiguration')
    @mock.patch('check_growth.logging')
    def test_script_logic(self, LoggingMock, ScriptConfigurationMock,
                          VerifyConfMock, ScriptStatusMock, ScriptLockMock,
                          SysExitMock, HistFileMock, FindCurGrowRatMock,
                          FindPlGrowRatMock, FindMemUsageMock,
                          FindDiskUsageMock, FindInodeUsageMock):
        # Set up phase
        ScriptStatusMock.notify_immediate.side_effect = self._terminate_script

        def dummy_datapoints(dtype, path=None, data_type=None):
            if dtype in ('memory', 'disk'):
                return (1212, 1232, 500, 1563)
            else:
                self.fail("Unsupported datapoints type requested: {0}.".format(
                          dtype))

        FindDiskUsageMock.side_effect = lambda mountpoint: (1000, 2000)
        FindInodeUsageMock.side_effect = lambda mountpoint: (2000, 4000)
        FindMemUsageMock.side_effect = lambda: (1000, 2000)
        HistFileMock.get_datapoints.side_effect = dummy_datapoints

        # Test initialization and history cleaning:
        ScriptConfigurationMock.get_val.side_effect = \
            self._script_conf_factory(memory_mon_warn_reduction=30,
                                      memory_mon_crit_reduction=20,
                                      disk_mon_warn_reduction=10,
                                      disk_mon_crit_reduction=5)
        with self.assertRaises(SystemExit):
            check_growth.main(config_file=paths.TEST_CONFIG_FILE,
                              clean_histdata=True)

        ScriptConfigurationMock.load_config.assert_called_once_with(
            paths.TEST_CONFIG_FILE)
        ScriptLockMock.init.assert_called_once_with(paths.TEST_LOCKFILE)
        self.assertTrue(ScriptStatusMock.init.called)
        self.assertTrue(ScriptLockMock.aqquire.called)
        self.assertTrue(VerifyConfMock.called)
        HistFileMock.init.assert_called_once_with(location=paths.TEST_STATUSFILE,
                                                  max_averaging_window=14,
                                                  min_averaging_window=7)
        self.assertTrue(HistFileMock.clear_history.called)
        self.assertTrue(HistFileMock.save.called)

        for prefix in ('disk', 'memory'):
            if prefix == 'disk':
                # Test memory checks:
                ScriptConfigurationMock.get_val.side_effect = \
                    self._script_conf_factory(memory_mon_enabled=False,
                                              disk_mountpoints=['/tmp/'])
            elif prefix == 'memory':
                # Test memory checks:
                ScriptConfigurationMock.get_val.side_effect = \
                    self._script_conf_factory(disk_mon_enabled=False)

            # test handling of insufficient data case:
            HistFileMock.verify_dataspan.side_effect = \
                lambda prefix, path=None, data_type=None: -1

            check_growth.main(config_file=paths.TEST_CONFIG_FILE)

            status, msg = ScriptStatusMock.update.call_args[0]
            self.assertEqual(status, 'unknown')
            ScriptStatusMock.update.reset_mock()

            # restore mock to something valid:
            HistFileMock.verify_dataspan.side_effect = \
                lambda prefix, path=None, data_type=None: 4

            # Test warning limit:
            FindPlGrowRatMock.side_effect = \
                lambda cur_usage, max_usage, timeframe: 100
            FindCurGrowRatMock.side_effect = lambda datapoints: 130
            FindPlGrowRatMock.reset_mock()
            FindCurGrowRatMock.reset_mock()

            check_growth.main(config_file=paths.TEST_CONFIG_FILE)

            if prefix == 'disk':
                self.assertEqual(FindPlGrowRatMock.call_args_list,
                                 [mock.call(1000, 2000, 365),
                                  mock.call(2000, 4000, 365)])
                self.assertEqual(FindCurGrowRatMock.call_args_list,
                                 [mock.call((1212, 1232, 500, 1563), ),
                                  mock.call((1212, 1232, 500, 1563), )])
            else:
                FindPlGrowRatMock.assert_called_with(1000, 2000, 365)
                FindCurGrowRatMock.assert_called_with((1212, 1232, 500, 1563),)
            FindPlGrowRatMock.reset_mock()
            FindCurGrowRatMock.reset_mock()

            status, msg = ScriptStatusMock.update.call_args[0]
            self.assertEqual(status, 'warn')
            ScriptStatusMock.update.reset_mock()

            # Test critical limit:
            FindPlGrowRatMock.side_effect = lambda cur_usage, max_usage, timeframe: 100
            FindCurGrowRatMock.side_effect = lambda datapoints: 160
            FindPlGrowRatMock.reset_mock()
            FindCurGrowRatMock.reset_mock()

            check_growth.main(config_file=paths.TEST_CONFIG_FILE)

            status, msg = ScriptStatusMock.update.call_args[0]
            self.assertEqual(status, 'crit')
            ScriptStatusMock.update.reset_mock()

            # Test the case when limits are kept:
            FindPlGrowRatMock.side_effect = lambda cur_usage, max_usage, timeframe: 100
            FindCurGrowRatMock.side_effect = lambda datapoints: 60
            FindPlGrowRatMock.reset_mock()
            FindCurGrowRatMock.reset_mock()

            check_growth.main(config_file=paths.TEST_CONFIG_FILE)

            status, msg = ScriptStatusMock.update.call_args[0]
            self.assertEqual(status, 'ok')

    def test_memusage_fetch(self):
        cur_mem, max_mem = check_growth.fetch_memory_usage()

        cur_mem = int(cur_mem)
        max_mem = int(max_mem)

        output = subprocess.check_output(['/usr/bin/free', '-m'], shell=False,
                                         universal_newlines=True).split('\n')

        correct_maxmem = int(output[1].split()[1])
        correct_curmem = int(output[2].split()[2])

        diff_max = abs(correct_maxmem - max_mem)
        diff_cur = abs(correct_curmem - cur_mem)

        # Rounding problems and usage variations over time - so lets make 20% of
        # effort, and get 80 of errors detected :D
        self.assertLessEqual(diff_max, 15)
        self.assertLessEqual(diff_cur, 15)

    def test_inodeusage_fetch(self):
        cur_inode, max_inode = check_growth.fetch_inode_usage(
            paths.MOUNTPOINT_DIRS[0])

        cur_inode = int(cur_inode)
        max_inode = int(max_inode)

        output = subprocess.check_output(['/usr/bin/df', '-i',
                                         paths.MOUNTPOINT_DIRS[0]],
                                         shell=False,
                                         universal_newlines=True).split('\n')

        correct_maxinode = int(output[1].split()[1])
        correct_curinode = int(output[1].split()[2])

        self.assertEqual(correct_maxinode, max_inode)
        self.assertEqual(correct_curinode, cur_inode)

    def test_diskusage_fetch(self):
        cur_disk, max_disk = check_growth.fetch_disk_usage(paths.MOUNTPOINT_DIRS[0])

        cur_disk = int(cur_disk)
        max_disk = int(max_disk)

        output = subprocess.check_output(['/usr/bin/df', '-m',
                                         paths.MOUNTPOINT_DIRS[0]],
                                         shell=False,
                                         universal_newlines=True).split('\n')

        correct_maxdisk = int(output[1].split()[1])
        correct_curdisk = int(output[1].split()[2])

        diff_max = abs(correct_maxdisk - max_disk)
        diff_cur = abs(correct_curdisk - cur_disk)

        # Rounding problems, try 20% of effort, 80 of errors detected :D
        self.assertLessEqual(diff_max, 3)
        self.assertLessEqual(diff_cur, 3)

    def test_growth_ratio_calculation(self):
        result = check_growth.find_planned_grow_ratio(252, 11323, 365)

        self.assertTrue(result, 31.02)
        result = check_growth.find_current_grow_ratio({1: 5, 20: 100, 30: 150})

        self.assertTrue(result, 5)

    def test_histfile_syntax_checking(self):
        conf_file = self._script_conf_factory(disk_mon_enabled=False)
        max_averaging_window = conf_file("max_averaging_window")
        min_averaging_window = conf_file("min_averaging_window")
        history_file = conf_file("history_file")

        # Initialize the class:
        check_growth.HistoryFile.init(history_file, max_averaging_window,
                                      min_averaging_window)

        # FIXME - not sure about copypasting, but not sure about breaking the
        # interface (_verify_resource_types is private) either...

        # add_datapoint - only memory and disk datatypes are permitted:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.add_datapoint('dummy', 10)

        # add_datapoint - disk resource type should be defined:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.add_datapoint(prefix='disk',
                                                   path='/dev/shm',
                                                   datapoint=10)

        # add_datapoint - disk resource path should be valid:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.add_datapoint(prefix='disk',
                                                   path='no-a-path',
                                                   datapoint=10,
                                                   data_type='inode')

        # add_datapoint - disk resource type should be valid
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.add_datapoint(prefix='disk',
                                                   path='/dev/shm',
                                                   datapoint=10,
                                                   data_type='fooBar')

        # add_datapoint - datapoint should be a float or int object
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.add_datapoint(prefix='disk',
                                                   path='/dev/shm',
                                                   datapoint='foo',
                                                   data_type='inode')

        # verify_dataspan - only memory and disk datatypes are permitted:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.verify_dataspan('dummy', 10)

        # verify_dataspan - disk resource type should be defined:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.verify_dataspan(prefix='disk',
                                                     path='/dev/shm')

        # verify_dataspan - disk resource path should be valid:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.verify_dataspan(prefix='disk',
                                                     path='no-a-path',
                                                     data_type='inode')

        # verify_dataspan - disk resource type should be valid
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.verify_dataspan(prefix='disk',
                                                     path='/dev/shm',
                                                     data_type='fooBar')

        # get_dataspan - only memory and disk datatypes are permitted:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.get_dataspan('dummy', 10)

        # get_dataspan - disk resource type should be defined:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.get_dataspan(prefix='disk',
                                                  path='/dev/shm')

        # get_dataspan - disk resource path should be valid:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.get_dataspan(prefix='disk',
                                                  path='no-a-path',
                                                  data_type='inode')

        # get_dataspan - disk resource type should be valid
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.get_dataspan(prefix='disk',
                                                  path='/dev/shm',
                                                  data_type='fooBar')

        # get_datapoints - only memory and disk datatypes are permitted:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.get_datapoints('dummy', 10)

        # get_datapoints - disk resource type should be defined:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.get_datapoints(prefix='disk',
                                                    path='/dev/shm')

        # get_datapoints - disk resource path should be valid:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.get_datapoints(prefix='disk',
                                                    path='no-a-path',
                                                    data_type='inode')

        # get_datapoints - disk resource type should be valid
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.get_datapoints(prefix='disk',
                                                    path='/dev/shm',
                                                    data_type='fooBar')

    @mock.patch('time.time')
    def test_histfile_timespan_calculation(self, TimeMock):
        conf_file = self._script_conf_factory(disk_mon_enabled=False)
        max_averaging_window = conf_file("max_averaging_window")
        min_averaging_window = conf_file("min_averaging_window")
        history_file = conf_file("history_file")
        cur_time = 1500000000

        # Test creating empty file and adding just one datapoint for each datatype
        TimeMock.side_effect = lambda: cur_time

        check_growth.HistoryFile.init(history_file, max_averaging_window,
                                      min_averaging_window)

        check_growth.HistoryFile.add_datapoint('memory', 1)
        check_growth.HistoryFile.add_datapoint('disk', 1, path='/tmp/',
                                               data_type='inode')
        check_growth.HistoryFile.add_datapoint('disk', 1, path='/tmp/',
                                               data_type='space')

        # Now - move the clock 24h ahead:
        TimeMock.side_effect = lambda: cur_time + 1 * 3600 * 24 + 1

        check_growth.HistoryFile.add_datapoint('memory', 2)
        check_growth.HistoryFile.add_datapoint('disk', 2, path='/tmp/',
                                               data_type='inode')
        check_growth.HistoryFile.add_datapoint('disk', 2, path='/tmp/',
                                               data_type='space')

        dataspan_memory = check_growth.HistoryFile.get_dataspan('memory')
        dataspan_disk_i = check_growth.HistoryFile.get_dataspan('disk',
                                                                '/tmp/',
                                                                'inode')
        dataspan_disk_s = check_growth.HistoryFile.get_dataspan('disk',
                                                                '/tmp/',
                                                                'space')

        self.assertEqual(dataspan_memory, 1)
        self.assertEqual(dataspan_disk_i, 1)
        self.assertEqual(dataspan_disk_s, 1)

        self.assertLess(check_growth.HistoryFile.verify_dataspan('memory'), 0)
        self.assertLess(check_growth.HistoryFile.verify_dataspan(
            'disk', '/tmp/', 'inode'), 0)
        self.assertLess(check_growth.HistoryFile.verify_dataspan(
            'disk', '/tmp/', 'space'), 0)

        # Now move the clock enough to cover min_averaging_window:
        TimeMock.side_effect = lambda: cur_time + \
            (0.1 + min_averaging_window) * 3600 * 24 + 1

        check_growth.HistoryFile.add_datapoint('memory', 3)
        check_growth.HistoryFile.add_datapoint('disk', 3, path='/tmp/',
                                               data_type='inode')
        check_growth.HistoryFile.add_datapoint('disk', 3, path='/tmp/',
                                               data_type='space')

        dataspan_memory = check_growth.HistoryFile.get_dataspan('memory')
        dataspan_disk_i = check_growth.HistoryFile.get_dataspan(
            'disk', '/tmp/', 'inode')
        dataspan_disk_s = check_growth.HistoryFile.get_dataspan(
            'disk', '/tmp/', 'space')

        self.assertEqual(dataspan_memory, min_averaging_window + 0.1)
        self.assertEqual(dataspan_disk_i, min_averaging_window + 0.1)
        self.assertEqual(dataspan_disk_s, min_averaging_window + 0.1)

        self.assertGreater(check_growth.HistoryFile.verify_dataspan('memory'), 0)
        self.assertGreater(check_growth.HistoryFile.verify_dataspan(
            'disk', '/tmp/', 'inode'), 0)
        self.assertGreater(check_growth.HistoryFile.verify_dataspan(
            'disk', '/tmp/', 'space'), 0)

    @mock.patch('time.time')
    def test_histfile_workflow(self, TimeMock):
        conf_file = self._script_conf_factory(disk_mon_enabled=False)
        max_averaging_window = conf_file("max_averaging_window")
        min_averaging_window = conf_file("min_averaging_window")
        history_file = conf_file("history_file")
        cur_time = 1000000000

        # Test creating empty file and adding just one datapoint for each datatype
        TimeMock.side_effect = lambda: cur_time

        check_growth.HistoryFile.init(history_file, max_averaging_window,
                                      min_averaging_window)

        # Remove old entries:
        check_growth.HistoryFile.clear_history()

        check_growth.HistoryFile.add_datapoint('memory', 10356)
        check_growth.HistoryFile.add_datapoint('disk', 134321, path='/tmp/',
                                               data_type='inode')
        check_growth.HistoryFile.add_datapoint('disk', 354334321, path='/tmp/',
                                               data_type='space')

        TimeMock.side_effect = lambda: cur_time + max_averaging_window * \
            3600 * 24 + 1

        check_growth.HistoryFile.add_datapoint('memory', 234453)
        check_growth.HistoryFile.add_datapoint('disk', 234321, path='/tmp/',
                                               data_type='inode')
        check_growth.HistoryFile.add_datapoint('disk', 654334321, path='/tmp/',
                                               data_type='space')

        check_growth.HistoryFile.save()

        # Test reading existing file and adding few more points:
        check_growth.HistoryFile.init(history_file, max_averaging_window,
                                      min_averaging_window)

        TimeMock.side_effect = lambda: cur_time + (max_averaging_window + 1) * \
            3600 * 24

        check_growth.HistoryFile.add_datapoint('memory', 575553)
        check_growth.HistoryFile.add_datapoint('disk', 234234367, path='/tmp/',
                                               data_type='inode')
        check_growth.HistoryFile.add_datapoint('disk', 652314121, path='/tmp/',
                                               data_type='space')

        # Test whether we have new and saved data and that old data got
        # trimmed:
        memory_data = check_growth.HistoryFile.get_datapoints('memory')
        disk_data_space = check_growth.HistoryFile.get_datapoints('disk',
                                                                  path='/tmp/',
                                                                  data_type='space')
        disk_data_inode = check_growth.HistoryFile.get_datapoints('disk',
                                                                  path='/tmp/',
                                                                  data_type='inode')

        self.assertEqual(memory_data, {1001296000: 575553, 1001209601: 234453})
        self.assertEqual(disk_data_space,
                         {1001296000: 652314121, 1001209601: 654334321})
        self.assertEqual(disk_data_inode,
                         {1001296000: 234234367, 1001209601: 234321})

        check_growth.HistoryFile.save()


if __name__ == '__main__':
    unittest.main()
