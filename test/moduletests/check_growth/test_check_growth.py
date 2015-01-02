#!/usr/bin/env python3
# Copyright (c) 2015 Pawel Rozlach
# Copyright (c) 2014 Pawel Rozlach
# Copyright (c) 2014 Brainly.com sp. z o.o.
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
import ddt
import mock
import os
import subprocess
import sys
import unittest

from ddt import ddt, data

# To perform local imports first we need to fix PYTHONPATH:
pwd = os.path.abspath(os.path.dirname(__file__))
sys.path.append(os.path.abspath(pwd + '/../../modules/'))

# Local imports:
import file_paths as paths
import check_growth

# Constants:
DF_COMMAND = '/bin/df'  # FIXME - should be autodetected


class TestsBaseClass(unittest.TestCase):

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
class TestCommandLineParsing(unittest.TestCase):
    def setUp(self):
        self._old_args = sys.argv

    def tearDown(self):
        sys.argv = self._old_args

    def test_proper_command_line_parsing(self, *unused):
        sys.argv = ['./check_growth.py', '-v', '-s', '-c', './check_growth.json']
        parsed_cmdline = check_growth.parse_command_line()
        self.assertEqual(parsed_cmdline, {'std_err': True,
                                          'config_file': './check_growth.json',
                                          'verbose': True,
                                          'clean_histdata': False,
                                          })

    def test_config_file_missing_from_commandline(self, SysExitMock):
        sys.argv = ['./check_growth.py', ]
        # Suppres warnings from argparse
        with mock.patch('sys.stderr'):
            check_growth.parse_command_line()
        SysExitMock.assert_called_once_with(2)

    def test_default_command_line_args(self, *unused):
        sys.argv = ['./check_growth.py', '-c', './check_growth.json']
        parsed_cmdline = check_growth.parse_command_line()
        self.assertEqual(parsed_cmdline, {'std_err': False,
                                          'config_file': './check_growth.json',
                                          'verbose': False,
                                          'clean_histdata': False,
                                          })


class TestSystemMeasurement(unittest.TestCase):
    def test_memusage_fetch(self):

        with open(paths.TEST_MEMINFO, 'r') as fh:
            tmp = fh.read()

        m = mock.mock_open(read_data=tmp)
        with mock.patch('check_growth.open', m, create=True):
            cur_mem, max_mem = check_growth.fetch_memory_usage()

        self.assertLessEqual(cur_mem, 3808.93)
        self.assertLessEqual(max_mem, 24058.3)

    def test_inodeusage_fetch(self):
        cur_inode, max_inode = check_growth.fetch_inode_usage(
            paths.MOUNTPOINT_DIRS[0])

        cur_inode = int(cur_inode)
        max_inode = int(max_inode)

        output = subprocess.check_output([DF_COMMAND, '-i',
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

        output = subprocess.check_output([DF_COMMAND, '-m',
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


class TestConfigVerification(TestsBaseClass):

    def setUp(self):
        self.mocks = {}
        for patched in ['check_growth.ScriptConfiguration',
                        'check_growth.ScriptStatus']:
            patcher = mock.patch(patched)
            self.mocks[patched] = patcher.start()
            self.addCleanup(patcher.stop)

        self.mocks['check_growth.ScriptStatus'].notify_immediate.side_effect = \
            self._terminate_script

    def test_values_greater_than_zero(self):
        self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
            self._script_conf_factory(timeframe=-7,
                                      max_averaging_window=-3,
                                      memory_mon_warn_reduction=-10,
                                      memory_mon_crit_reduction=-100,
                                      disk_mon_warn_reduction=0,
                                      disk_mon_crit_reduction=-5)
        with self.assertRaises(SystemExit):
            check_growth.verify_conf()
        status, msg = self.mocks['check_growth.ScriptStatus'].notify_immediate.call_args[0]
        self.assertEqual(status, 'unknown')
        self.assertIn('Timeframe should be a positive int', msg)
        self.assertIn('Max averaging window should be a positive int', msg)
        self.assertIn('memory_mon_warn_reduction should be a positive int', msg)
        self.assertIn('memory_mon_crit_reduction should be a positive int', msg)
        self.assertIn('disk_mon_warn_reduction should be a positive int', msg)
        self.assertIn('disk_mon_crit_reduction should be a positive int', msg)

    def test_limits_sanity(self):
        self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
            self._script_conf_factory(memory_mon_warn_reduction=30,
                                      memory_mon_crit_reduction=20,
                                      disk_mon_warn_reduction=10,
                                      disk_mon_crit_reduction=5)
        with self.assertRaises(SystemExit):
            check_growth.verify_conf()
        status, msg = self.mocks['check_growth.ScriptStatus'].notify_immediate.call_args[0]
        self.assertEqual(status, 'unknown')
        self.assertIn('memory_mon_warn_reduction should be lower ' +
                      'than memory_mon_crit_reduction', msg)
        self.assertIn('disk_mon_warn_reduction should be lower than ' +
                      'disk_mon_crit_reduction', msg)

    def test_at_least_one_checktype_enabled(self):
        self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
            self._script_conf_factory(memory_mon_enabled=False,
                                      disk_mon_enabled=False,)
        with self.assertRaises(SystemExit):
            check_growth.verify_conf()
        status, msg = self.mocks['check_growth.ScriptStatus'].notify_immediate.call_args[0]
        self.assertEqual(status, 'unknown')
        self.assertIn('There should be at least one resourece check enabled.',
                      msg)

    def test_configuration_ok(self):
        self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
            self._script_conf_factory(disk_mountpoints=paths.MOUNTPOINT_DIRS)
        check_growth.verify_conf()


@ddt
class TestHistFileUpdateMethodsSyntaxChecking(TestsBaseClass):

    def setUp(self):
        conf_file = self._script_conf_factory(disk_mon_enabled=False)
        max_averaging_window = conf_file("max_averaging_window")
        min_averaging_window = conf_file("min_averaging_window")
        history_file = conf_file("history_file")

        # Initialize the class:
        check_growth.HistoryFile.init(history_file, max_averaging_window,
                                      min_averaging_window)

    def test_disk_resource_defined(self):
        # add_datapoint - disk resource type should be defined:
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.add_datapoint(prefix='disk',
                                                   path='/dev/shm',
                                                   datapoint=10)

    def test_datapoint_valid_type(self):
        # add_datapoint - datapoint should be a float or int object
        with self.assertRaises(ValueError):
            check_growth.HistoryFile.add_datapoint(prefix='disk',
                                                   path='/dev/shm',
                                                   datapoint='foo',
                                                   data_type='inode')

    @data('verify_dataspan', 'get_dataspan', 'get_datapoints')
    def test_datapoint_type_defined(self, method):
        args = {'prefix': 'disk',
                'path': '/dev/shm'}
        with self.assertRaises(ValueError):
            getattr(check_growth.HistoryFile, method)(**args)

    @data('add_datapoint', 'verify_dataspan', 'get_dataspan', 'get_datapoints')
    def test_only_disk_or_memory_permitted(self, method):
        with self.assertRaises(ValueError):
            getattr(check_growth.HistoryFile, method)('dummy', 10)

    @data('add_datapoint', 'verify_dataspan', 'get_dataspan', 'get_datapoints')
    def test_disk_resource_path_valid(self, method):
        args = {"prefix": 'disk',
                "path": 'no-a-path',
                "data_type": 'inode'}
        if method == 'add_datapoint':
            args["datapoint"] = 10
        with self.assertRaises(ValueError):
            getattr(check_growth.HistoryFile, method)(**args)

    @data('add_datapoint', 'verify_dataspan', 'get_dataspan', 'get_datapoints')
    def test_disk_resource_type_valid(self, method):
        args = {"prefix": 'disk',
                "path": '/dev/shm',
                "data_type": 'fooBar'}
        if method == 'add_datapoint':
            args["datapoint"] = 10
        with self.assertRaises(ValueError):
            getattr(check_growth.HistoryFile, method)(**args)


@ddt
class TestScriptLogic(TestsBaseClass):

    def setUp(self):
        self.mocks = {}
        for patched in ['check_growth.fetch_inode_usage',
                        'check_growth.fetch_disk_usage',
                        'check_growth.fetch_memory_usage',
                        'check_growth.find_planned_grow_ratio',
                        'check_growth.find_current_grow_ratio',
                        'check_growth.HistoryFile',
                        'check_growth.ScriptLock',
                        'check_growth.ScriptStatus',
                        'check_growth.verify_conf',
                        'check_growth.ScriptConfiguration',
                        'check_growth.logging',
                        ]:
            patcher = mock.patch(patched)
            self.mocks[patched] = patcher.start()
            self.addCleanup(patcher.stop)

        self.mocks['check_growth.ScriptStatus'].notify_immediate.side_effect = \
            self._terminate_script

        self.mocks['check_growth.ScriptStatus'].notify_agregated.side_effect = \
            self._terminate_script

        self.mocks['check_growth.fetch_disk_usage'].return_value = (1000, 2000)
        self.mocks['check_growth.fetch_inode_usage'].return_value = (2000, 4000)
        self.mocks['check_growth.fetch_memory_usage'].return_value = (1000, 2000)
        self.mocks['check_growth.HistoryFile'].verify_dataspan.return_value = 10
        self.mocks['check_growth.HistoryFile'].get_datapoints.side_effect = \
            self._dummy_datapoints
        self.mocks['check_growth.find_planned_grow_ratio'].return_value = 100
        self.mocks['check_growth.find_current_grow_ratio'].return_value = 60

    @staticmethod
    def _dummy_datapoints(dtype, path=None, data_type=None):
        if dtype in ('memory', 'disk'):
            return (1212, 1232, 500, 1563)
        else:
            self.fail("Unsupported datapoints type requested: {0}.".format(
                        dtype))

    def test_allok(self):
        self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
            self._script_conf_factory()
        with self.assertRaises(SystemExit):
            check_growth.main(config_file=paths.TEST_CONFIG_FILE)

        # Configuration is loaded:
        self.mocks['check_growth.ScriptConfiguration'].load_config.assert_called_once_with(
            paths.TEST_CONFIG_FILE)
        self.assertTrue(self.mocks['check_growth.verify_conf'].called)

        # Lock is properly handled:
        self.mocks['check_growth.ScriptLock'].init.assert_called_once_with(
            paths.TEST_LOCKFILE)
        self.assertTrue(self.mocks['check_growth.ScriptLock'].aqquire.called)

        # Monitoring is notified:
        self.assertTrue(self.mocks['check_growth.ScriptStatus'].init.called)
        self.assertTrue(self.mocks['check_growth.ScriptStatus'].notify_agregated.called)

        # Data is stored:
        self.mocks['check_growth.HistoryFile'].init.assert_called_once_with(
            location=paths.TEST_STATUSFILE,
            max_averaging_window=14,
            min_averaging_window=7)
        self.assertTrue(self.mocks['check_growth.HistoryFile'].save.called)

        # Status is OK
        status, msg = self.mocks['check_growth.ScriptStatus'].update.call_args[0]
        self.assertEqual(status, 'ok')

    def test_history_cleaning(self):
        self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
            self._script_conf_factory()
        with self.assertRaises(SystemExit):
            check_growth.main(config_file=paths.TEST_CONFIG_FILE,
                              clean_histdata=True)

        self.assertTrue(self.mocks['check_growth.HistoryFile'].clear_history.called)
        self.assertTrue(self.mocks['check_growth.HistoryFile'].save.called)

    @data('disk', 'memory')
    def test_insufficient_input_data(self, prefix):
        if prefix == 'disk':
            # Test memory checks:
            self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
                self._script_conf_factory(memory_mon_enabled=False,
                                          disk_mountpoints=['/tmp/'])
        elif prefix == 'memory':
            # Test memory checks:
            self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
                self._script_conf_factory(disk_mon_enabled=False)

        self.mocks['check_growth.HistoryFile'].verify_dataspan.return_value = -1

        with self.assertRaises(SystemExit):
            check_growth.main(config_file=paths.TEST_CONFIG_FILE)

        status, msg = self.mocks['check_growth.ScriptStatus'].update.call_args[0]
        self.assertEqual(status, 'unknown')

    @data(("warn", 130), ("crit", 160))
    def test_disk_alert_condition(self, data):
        self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
            self._script_conf_factory(memory_mon_enabled=False,
                                        disk_mountpoints=['/tmp/'])

        self.mocks['check_growth.find_current_grow_ratio'].return_value = data[1]

        with self.assertRaises(SystemExit):
            check_growth.main(config_file=paths.TEST_CONFIG_FILE)

        self.assertEqual(self.mocks['check_growth.find_planned_grow_ratio'].call_args_list,
                            [mock.call(1000, 2000, 365),
                            mock.call(2000, 4000, 365)])
        self.assertEqual(self.mocks['check_growth.find_current_grow_ratio'].call_args_list,
                            [mock.call((1212, 1232, 500, 1563), ),
                            mock.call((1212, 1232, 500, 1563), )])

        status, msg = self.mocks['check_growth.ScriptStatus'].update.call_args[0]
        self.assertEqual(status, data[0])

    @data(("warn", 130), ("crit", 160))
    def test_memory_alert_condition(self, data):
        self.mocks['check_growth.ScriptConfiguration'].get_val.side_effect = \
            self._script_conf_factory(disk_mon_enabled=False)

        self.mocks['check_growth.find_current_grow_ratio'].return_value = data[1]

        with self.assertRaises(SystemExit):
            check_growth.main(config_file=paths.TEST_CONFIG_FILE)

        self.mocks['check_growth.find_planned_grow_ratio'].assert_called_with(1000, 2000, 365)
        self.mocks['check_growth.find_current_grow_ratio'].assert_called_with((1212, 1232, 500, 1563),)

        status, msg = self.mocks['check_growth.ScriptStatus'].update.call_args[0]
        self.assertEqual(status, data[0])

class TestHistFile(TestsBaseClass):

    def setUp(self):
        conf_file = self._script_conf_factory(disk_mon_enabled=False)
        self.max_averaging_window = conf_file("max_averaging_window")
        self.min_averaging_window = conf_file("min_averaging_window")
        self.history_file = conf_file("history_file")
        self.cur_time = 1000000000

        patcher = mock.patch('check_growth.time.time')
        self.time_mock = patcher.start()
        self.addCleanup(patcher.stop)
        self.time_mock.return_value = self.cur_time

        try:
            os.unlink(self.history_file)
        except FileNotFoundError:
            pass

        check_growth.HistoryFile.init(self.history_file, self.max_averaging_window,
                                      self.min_averaging_window)

    def test_histfile_timespan_calculation(self):
        check_growth.HistoryFile.add_datapoint('memory', 1)
        check_growth.HistoryFile.add_datapoint('disk', 1, path='/tmp/',
                                               data_type='inode')
        check_growth.HistoryFile.add_datapoint('disk', 1, path='/tmp/',
                                               data_type='space')

        # Now - move the clock 24h ahead:
        self.time_mock.return_value = self.cur_time + 1 * 3600 * 24 + 1

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

        # Now move the clock enough to cover self.min_averaging_window:
        self.time_mock.return_value = self.cur_time + (0.1 + self.min_averaging_window) * 3600 * 24 + 1

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

        self.assertEqual(dataspan_memory, self.min_averaging_window + 0.1)
        self.assertEqual(dataspan_disk_i, self.min_averaging_window + 0.1)
        self.assertEqual(dataspan_disk_s, self.min_averaging_window + 0.1)

        self.assertGreater(check_growth.HistoryFile.verify_dataspan('memory'), 0)
        self.assertGreater(check_growth.HistoryFile.verify_dataspan(
            'disk', '/tmp/', 'inode'), 0)
        self.assertGreater(check_growth.HistoryFile.verify_dataspan(
            'disk', '/tmp/', 'space'), 0)

    def test_histfile_load(self):
        check_growth.HistoryFile.add_datapoint('memory', 10356)
        check_growth.HistoryFile.add_datapoint('disk', 134321, path='/tmp/',
                                               data_type='inode')
        check_growth.HistoryFile.add_datapoint('disk', 354334321, path='/tmp/',
                                               data_type='space')

        self.time_mock.return_value = self.cur_time + self.max_averaging_window * \
            3600 * 24 + 1

        check_growth.HistoryFile.add_datapoint('memory', 234453)
        check_growth.HistoryFile.add_datapoint('disk', 234321, path='/tmp/',
                                               data_type='inode')
        check_growth.HistoryFile.add_datapoint('disk', 654334321, path='/tmp/',
                                               data_type='space')

        check_growth.HistoryFile.save()

        # Test reading existing file and adding few more points:
        check_growth.HistoryFile.init(self.history_file, self.max_averaging_window,
                                      self.min_averaging_window)

        self.time_mock.return_value = self.cur_time + (self.max_averaging_window + 1) * \
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


if __name__ == '__main__':
    unittest.main()
