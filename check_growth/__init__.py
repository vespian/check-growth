#!/usr/bin/env python3
# Copyright (c) 2014 Pawel Rozlach
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

# Imports:
from pymisc.monitoring import ScriptStatus
from pymisc.script import RecoverableException, ScriptConfiguration, ScriptLock
import argparse
import logging
import logging.handlers as lh
import numpy
import os
import sys
import time
import yaml

# Defaults:
LOCKFILE_LOCATION = './'+os.path.basename(__file__)+'.lock'
CONFIGFILE_LOCATION = './'+os.path.basename(__file__)+'.conf'


class HistoryFile():
    """
    Abstraction of all the operations on historical datapoints

    This class takes care of storing, retreiving, and trimming of historical
    datapoints, plus some additionall syntax checking.

    Attributes:
        _data: a nested hash with the data itself
        _location: location of the file where data is stored betwean script runs
        _max_averaging_window: please see class's init() method
        _min_averaging_window: please see class's init() method
    """
    _data = {}
    _location = None
    _max_averaging_window = None
    _min_averaging_window = None

    @classmethod
    def _remove_old_datapoints(cls):
        """
        Remove all the datapoints older than cls._max_averaging_window from
        the internal storage.
        """
        cur_time = time.time()
        averaging_border = cur_time - cls._max_averaging_window * 3600 * 24
        cur_dict = cls._data['datapoints']['memory']
        cls._data['datapoints']['memory'] = {x: cur_dict[x] for x in
                                             cur_dict.keys() if x >
                                             averaging_border}
        for mountpoint in cls._data['datapoints']['disk'].keys():
            for data_type in cls._data['datapoints']['disk'][mountpoint].keys():
                cur_dict = cls._data['datapoints']['disk'][mountpoint][data_type]
                cls._data['datapoints']['disk'][mountpoint][data_type] = \
                    {x: cur_dict[x] for x in cur_dict.keys()
                        if x > averaging_border}

    @classmethod
    def _verify_resource_types(cls, prefix=None, path=None, data_type=None):
        if prefix is None or prefix not in ['disk', 'memory']:
            raise ValueError('Not supported prefix during datapoint addition')
        if prefix == 'disk':
            if path is None or not os.path.exists(path) or \
                    data_type not in ['inode', 'space']:
                raise ValueError('data_type and path params are required for' +
                                 ' "disk" prefix')

    @classmethod
    def init(cls, location, max_averaging_window, min_averaging_window):
        """
        Initialize HistoryFIle class.

        Class either fetches stored datapoints from the file or creates empty
        storage. It takes care of setting some internal fields as well.

        Args:
            location: location of the file where data is stored or should be
                stored. File is in YAML format.
            max_averaging_window: maximum time span betwean the oldest and newest
                datapoint. Points older that this are removed and are no longer
                taken into consideration.
            min_averaging_window: minimum time span betwean the oldest and newest
                datapoint which permits calculation of the growth ratio.
        """
        cls._max_averaging_window = max_averaging_window
        cls._min_averaging_window = min_averaging_window
        cls._location = location

        try:
            with open(location, 'r') as fh:
                cls._data = yaml.load(fh)
        except (IOError, yaml.YAMLError):
            cls._data = {'datapoints': {'memory': {}, 'disk': {}}}
        else:
            cls._remove_old_datapoints()

    @classmethod
    def add_datapoint(cls, prefix, datapoint, path=None, data_type=None):
        """
        Add a datapoint to the internal store.

        This method takes care of some simple sanity-checking and addition of
        the new datapoints.

        Args:
            prefix: either 'disk' or 'memory' - whether a datapoint is actually
                a disk usage or memory usage
            datapoint: current value of the resource
            path: in case of the 'disk' resource - the path where device
                relevant to the datapoint is mounted.
            data_type: in case of the 'disk' respource - whether it is an inode
                usage or disk space usage

        Raises:
            ValueError: input data is invalid
        """
        cls._verify_resource_types(prefix, path, data_type)
        float(datapoint)
        cur_time = round(time.time())
        if prefix == 'memory':
            cls._data['datapoints'][prefix][cur_time] = datapoint
        else:
            if path not in cls._data['datapoints'][prefix].keys():
                cls._data['datapoints'][prefix][path] = dict()
                cls._data['datapoints'][prefix][path]['inode'] = dict()
                cls._data['datapoints'][prefix][path]['space'] = dict()
            cls._data['datapoints'][prefix][path][data_type][cur_time] = datapoint

    @classmethod
    def verify_dataspan(cls, prefix, path=None, data_type=None):
        """
        Check whether we have enough data to calculate growth ratio.

        This method calculates the difference between current timespan for
        the given resource (memory or disk-inode or disk-space) and the
        min_averaging_window.

        Args:
            prefix: same as for add_datapoint() method
            path: same as for add_datapoint() method
            data_type: same as for add_datapoint() method

        Returns:
            Difference expressed in number of days. If it is negative then
            there is not enough data to process.
        """
        cls._verify_resource_types(prefix, path, data_type)
        dataspan = cls.get_dataspan(prefix, path, data_type)
        return (dataspan - cls._min_averaging_window)

    @classmethod
    def get_dataspan(cls, prefix, path=None, data_type=None):
        """
        Return the difference (in days) betwean oldest and latest data sample
        for given reource type

        Args:
            prefix: same as for add_datapoint() method
            path: same as for add_datapoint() method
            data_type: same as for add_datapoint() method

        Returns:
            Data span for given rousource type expressed in days.
        """
        cls._verify_resource_types(prefix, path, data_type)
        if prefix == 'memory':
            timestamps = cls._data['datapoints'][prefix].keys()
        else:
            timestamps = cls._data['datapoints'][prefix][path][data_type].keys()
        dataspan = round((max(timestamps) - min(timestamps))/(3600*24), 2)
        return dataspan

    @classmethod
    def get_datapoints(cls, prefix, path=None, data_type=None):
        """
        Get all datapoints for given data type.

        This method ensures that all datapoints not older than averaging
        window are returned for the given resource type.

        Args:
            prefix: same as for add_datapoint() method
            path: same as for add_datapoint() method
            data_type: same as for add_datapoint() method

        Returns:
            A dictionary with timestamps as keys and resource usages as values.

        Raises:
            ValueError: input data is invalid
        """
        cls._verify_resource_types(prefix, path, data_type)
        cls._remove_old_datapoints()
        if prefix == 'disk':
            datapoints = cls._data['datapoints'][prefix][path][data_type]
        else:
            datapoints = cls._data['datapoints'][prefix]
        return datapoints

    @classmethod
    def clear_history(cls):
        """
        Remove all datapoints.
        """
        for res_type in cls._data['datapoints'].keys():
            cls._data['datapoints'][res_type] = dict()

    @classmethod
    def save(cls):
        """
        Save all the datapoints.

        This method saves all datapoints not older than
        (max_averaging_window - 1) * 3600 * 24 seconds to the the file provided
        in init() call.
        """
        cls._remove_old_datapoints()
        with open(cls._location, 'w') as fh:
            data = yaml.dump(cls._data, default_flow_style=False)
            fh.write(data)


def fetch_memory_usage():
    """
    Fetch current memory usage.

    Returns:
    A tuple: (memory used, memory total), in megabytes.
    """
    # Calculation based on 'free' source:
    # used = MemTotal - MemFree - Cached - Slab - Buffers
    # total = MemTotal
    with open('/proc/meminfo', 'r') as fh:
        data = fh.read()
    used = 0
    total = 0
    # Using fh.readlines() would be more convinient but it makes testing difficult
    for line in data.split('\n'):
        if line == '':
            continue
        tmp = line.split()
        if tmp[0][:-1] in ['MemFree', 'Cached', 'Slab', 'Buffers']:
            used -= int(tmp[1])
        elif tmp[0][:-1] == 'MemTotal':
            used += int(tmp[1])
            total = int(tmp[1])

    return round(used/1024, 2), round(total/1024, 2)

def fetch_disk_usage(mountpoint):
    """
    Fetch current disk usage.

    Args:
        mountpoint: path to mountpoint for which current usage data should be
        fetched.

    Returns:
    A tuple: (disk usage, total disk space available), in megabytes.
    """
    statvfs = os.statvfs(mountpoint)
    cur_u = round(statvfs.f_frsize * (statvfs.f_blocks-statvfs.f_bavail)/1024**2, 2)
    max_u = round(statvfs.f_frsize * statvfs.f_blocks/1024**2, 2)

    return cur_u, max_u


def fetch_inode_usage(mountpoint):
    """
    Fetch current inode usage.

    Args:
        mountpoint: path to mountpoint for which current usage data should be
        fetched.

    Returns:
    A tuple: (inode usage, total inodes available).
    """
    statvfs = os.statvfs(mountpoint)
    cur_u = statvfs.f_files - statvfs.f_ffree
    max_u = statvfs.f_files

    return cur_u, max_u


def find_planned_grow_ratio(cur_usage, max_usage, timeframe):
    """
    Calculate 'ideal' growth ratio for a resource.

    Units-agnostic function used to calculate ideal resource grow ratio,
    basing soley on the available resources and given timeframe.

    Args:
        cur_usage: current resource usage
        max_usage: how much of the resource there is in general
        timeframe: for how long given resource should be sufficient

    Returns:
    See below :)
    """
    return round(max_usage/timeframe, 2)


def find_current_grow_ratio(datapoints):
    """
    Find current grow ratio of the resource.

    Units-agnostic function which calculates current resource grow ratio,
    basing on the historic data. This is done using linear regression.
    Assuming that resource growth during current timeframe can be approximed by

        y = ax + b

    then y is current usage, a is current growth ratio and b is usage generated
    earlier, before the begining of our time window.

    Args:
    datapoints: a dictionary with timestamps as keys and resource usages as
        values.

    Returns:
        resource-units/day with 2 digit precision.
    """
    sorted_x = sorted(datapoints.keys())
    y = numpy.array([datapoints[x] for x in sorted_x])
    x = numpy.array(sorted_x)

    A = numpy.vstack([x, numpy.ones(len(x))]).T

    m, c = numpy.linalg.lstsq(A, y)[0]

    slope, intercept = numpy.linalg.lstsq(A, y)[0]

    return round(slope*3600*24, 2)


def parse_command_line():
    parser = argparse.ArgumentParser(
        description='Simple resource usage check',
        epilog="Author: Pawel Rozlach <pawel.rozlach@zadane.pl>",
        add_help=True,)
    parser.add_argument(
        '--version',
        action='version',
        version='1.0')
    parser.add_argument(
        "-c", "--config-file",
        action='store',
        required=True,
        help="Location of the configuration file")
    parser.add_argument(
        "-v", "--verbose",
        action='store_true',
        required=False,
        help="Provide extra logging messages.")
    parser.add_argument(
        "-s", "--std-err",
        action='store_true',
        required=False,
        help="Log to stderr instead of syslog")
    parser.add_argument(
        "-d", "--clean-histdata",
        action='store_true',
        required=False,
        help="ACK abnormal growth")

    args = parser.parse_args()
    return {'std_err': args.std_err,
            'verbose': args.verbose,
            'config_file': args.config_file,
            'clean_histdata': args.clean_histdata,
            }


def verify_conf():
    msg = []
    prefixes = []

    timeframe = ScriptConfiguration.get_val('timeframe')
    max_averaging_window = ScriptConfiguration.get_val('max_averaging_window')
    min_averaging_window = ScriptConfiguration.get_val('min_averaging_window')

    if timeframe <= 0:
        msg.append('Timeframe should be a positive int.')

    if max_averaging_window <= 0:
        msg.append('Max averaging window should be a positive int.')

    if 0.5 * timeframe <= max_averaging_window:
        msg.append('Max averaging windown should not be grater than ' +
                   '0.5 * timeframe.')

    if min_averaging_window >= max_averaging_window:
        msg.append('Maximum averaging windown should be grater than ' +
                   'minimal averaging window.')

    if ScriptConfiguration.get_val('memory_mon_enabled'):
        prefixes.append('memory_mon_')
    if ScriptConfiguration.get_val('disk_mon_enabled'):
        prefixes.append('disk_mon_')
    if not prefixes:
        msg.append('There should be at least one resourece check enabled.')
    for prefix in prefixes:
        warn_reduction = ScriptConfiguration.get_val(prefix + 'warn_reduction')
        crit_reduction = ScriptConfiguration.get_val(prefix + 'crit_reduction')
        if warn_reduction <= 0:
            msg.append(prefix + 'warn_reduction should be a positive int.')

        if crit_reduction <= 0:
            msg.append(prefix + 'crit_reduction should be a positive int.')

        if warn_reduction >= crit_reduction:
            msg.append(prefix + "warn_reduction should be lower than " +
                       prefix + "crit_reduction.")

    if ScriptConfiguration.get_val('disk_mon_enabled'):
        mountpoints = ScriptConfiguration.get_val('disk_mountpoints')
        for mountpoint in mountpoints:
            # ismount seems to not properly detect all mount types :/
            # if not (os.path.exists(mountpoint) and os.path.ismount(mountpoint)):
            if not os.path.exists(mountpoint):
                msg.append('disk_mountpoint {0} '.format(mountpoint) +
                           'does not point to a valid mountpoint.')

    # if there are problems with configuration file then there is no point
    # in continuing:
    if msg:
        ScriptStatus.notify_immediate('unknown',
                                      "Configuration file contains errors: " +
                                      ' '.join(msg))

    # Everything is fine:
    return


def main(config_file, std_err=False, verbose=True, clean_histdata=False):
    """
    Main function of the script

    Args:
        config_file: file path of the config file to load
        std_err: whether print logging output to stderr
        verbose: whether to provide verbose logging messages
        clean_histdata: all historical data should be cleared
    """

    try:
        # Configure logging:
        fmt = logging.Formatter('%(filename)s[%(process)d] %(levelname)s: ' +
                                '%(message)s')
        logger = logging.getLogger()
        if verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        if std_err:
            handler = logging.StreamHandler()
        else:
            handler = lh.SysLogHandler(address='/dev/log',
                                       facility=lh.SysLogHandler.LOG_USER)
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        logger.debug("{0} is starting, ".format(os.path.basename(__file__)) +
                     "command line arguments: " +
                     "config_file={0}, ".format(config_file) +
                     "std_err={0}, ".format(std_err) +
                     "verbose={0}, ".format(verbose) +
                     "clean_histdata={0}".format(clean_histdata)
                     )

        # FIXME - Remember to correctly configure syslog, otherwise rsyslog will
        # discard messages
        ScriptConfiguration.load_config(config_file)

        logger.debug("Loaded configuration: " +
                     str(ScriptConfiguration.get_config())
                     )

        # Initialize reporting to monitoring system:
        ScriptStatus.init(nrpe_enable=True)

        # Make sure that we are the only ones running on the server:
        ScriptLock.init(ScriptConfiguration.get_val('lockfile'))
        ScriptLock.aqquire()

        # Some basic sanity checking:
        verify_conf()

        # We are all set, lets do some real work:
        HistoryFile.init(location=ScriptConfiguration.get_val('history_file'),
                         max_averaging_window=ScriptConfiguration.get_val(
                             'max_averaging_window'),
                         min_averaging_window=ScriptConfiguration.get_val(
                             'min_averaging_window'))

        if clean_histdata:
            HistoryFile.clear_history()
            HistoryFile.save()
            ScriptStatus.notify_immediate('unknown',
                                          'History data has been cleared.')

        timeframe = ScriptConfiguration.get_val('timeframe')

        # FIXME: not sure how to refactor this, copypaste does not seem the best
        # solution :(
        def do_status_processing(prefix, current_growth, planned_growth,
                                 mountpoint=None, data_type=None):
            warn_tresh = 1 + (ScriptConfiguration.get_val(
                prefix + '_mon_warn_reduction')/100)
            crit_tresh = 1 + (ScriptConfiguration.get_val(
                prefix + '_mon_crit_reduction')/100)

            if prefix == 'disk' and data_type == 'inode':
                units = 'inodes/day'
            else:
                units = 'MB/day'

            if prefix == 'disk':
                rname = data_type + \
                    ' usage growth for mount {0}'.format(mountpoint)
            else:
                rname = '{0} usage growth'.format(prefix)

            rname = rname.capitalize()

            if current_growth > planned_growth * warn_tresh:
                msg = '{0} exceeds planned growth '.format(rname) + \
                      '- current: {0} {1}'.format(current_growth, units) + \
                      ', planned: {0} {1}.'.format(planned_growth, units)
                if current_growth > planned_growth * crit_tresh:
                    ScriptStatus.update('crit', msg)
                else:
                    ScriptStatus.update('warn', msg)
            else:
                ScriptStatus.update('ok',
                                    '{0} is OK ({1} {2}).'.format(
                                        rname, current_growth, units))

        if ScriptConfiguration.get_val('memory_mon_enabled'):
            cur_usage, max_usage = fetch_memory_usage()
            HistoryFile.add_datapoint('memory', cur_usage)
            tmp = HistoryFile.verify_dataspan('memory')
            if tmp < 0:
                ScriptStatus.update('unknown', 'There is not enough data ' +
                                    'to calculate current memory ' +
                                    'usage growth: {0} '.format(abs(tmp)) +
                                    'days more is needed.')
            else:
                datapoints = HistoryFile.get_datapoints('memory')

                planned_growth = find_planned_grow_ratio(cur_usage, max_usage,
                                                         timeframe)
                current_growth = find_current_grow_ratio(datapoints)

                logging.debug('memory -> ' +
                              'current_growth: {0}, '.format(current_growth) +
                              'planned_growth: {0}'.format(planned_growth))

                do_status_processing('memory', current_growth, planned_growth)

        if ScriptConfiguration.get_val('disk_mon_enabled'):
            mountpoints = ScriptConfiguration.get_val('disk_mountpoints')
            for dtype in ['space', 'inode']:
                for mountpoint in mountpoints:
                    if dtype == 'inode':
                        cur_usage, max_usage = fetch_inode_usage(mountpoint)
                    else:
                        cur_usage, max_usage = fetch_disk_usage(mountpoint)
                    HistoryFile.add_datapoint('disk', cur_usage,
                                              data_type=dtype,
                                              path=mountpoint)
                    tmp = HistoryFile.verify_dataspan('disk',
                                                      data_type=dtype,
                                                      path=mountpoint)
                    if tmp < 0:
                        ScriptStatus.update('unknown',
                                            'There is not enough data to ' +
                                            'calculate current disk ' + dtype +
                                            ' usage growth for mountpoint ' +
                                            '{0}: {1} '.format(
                                                mountpoint, abs(tmp)) +
                                            'days more is needed.')
                    else:
                        datapoints = HistoryFile.get_datapoints('disk',
                                                                data_type=dtype,
                                                                path=mountpoint)
                        planned_growth = find_planned_grow_ratio(cur_usage,
                                                                 max_usage,
                                                                 timeframe)
                        current_growth = find_current_grow_ratio(datapoints)

                        logging.debug('disk, ' +
                                      'mountpoint {0}, '.format(mountpoint) +
                                      'data_type {0}: '.format(dtype) +
                                      'current_growth: {0}'.format(current_growth) +
                                      'planned_growth: {0}'.format(planned_growth))
                        do_status_processing('disk', current_growth, planned_growth,
                                             mountpoint=mountpoint, data_type=dtype)

        HistoryFile.save()
        ScriptStatus.notify_agregated()
        ScriptLock.release()

    except RecoverableException as e:
        msg = str(e)
        logging.critical(msg)
        ScriptStatus.notify_immediate('unknown', msg)
        sys.exit(1)
    except AssertionError as e:
        # Unittests require it:
        raise
    except Exception as e:
        msg = "Exception occured: {0}".format(e.__class__.__name__)
        logging.exception(msg)
        print(msg)  # We can use notify immediate here :(
        sys.exit(3)
