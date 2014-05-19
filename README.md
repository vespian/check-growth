## Configuration

Actions taken by the script are determined by its command line and the
configuration file. The command line has a build-in help system:

> usage: check_growth.py [-h] [--version] -c CONFIG_FILE [-v] [-s] [-d]
> 
> Simple resource usage check
> 
> optional arguments:
>   -h, --help            show this help message and exit
>   --version             show program's version number and exit
>   -c CONFIG_FILE, --config-file CONFIG_FILE
>                         Location of the configuration file
>   -v, --verbose         Provide extra logging messages.
>   -s, --std-err         Log to stderr instead of syslog
>   -d, --clean-histdata  ACK abnormal growth
> 
> Author: Pawel Rozlach <pawel.rozlach@zadane.pl>

The configuration file is a plain YAML document. It's syntax is as follows:

```
lockfile: /tmp/check_growth.lock
history_file: ./test/fabric/check_growth.status.yml

#Units of days
timeframe: 365
max_averaging_window: 3
min_averaging_window: 1.5

memory_mon_enabled: true
#Percentage:
memory_mon_warn_reduction: 20
memory_mon_crit_reduction: 40

disk_mon_enabled: true
disk_mountpoint: /dev/shm/
#Percentage:
disk_mon_warn_reduction: 20
disk_mon_crit_reduction: 40
```

## Operation
The script depending on the value of $memory_mon_enabled and $disk_mon_enabled
collects current memory, disk or memory and disk usage data along with maximal
usage (total RAM installed, total disk space available). The mountpoint where
the checked filesystem is mounted is specified by $disk_mountpoint.

The ideal growth ratio is calculated basing on the resource's max usage and the
$timeframe value by simply dividing former by the latter. The result is in MB/day
and simply states that if the given resource is to be used for at least $timeframe
number of days then the daily growth ratio should not be greater than this value.

The current growt ratio for a given resource is calculated in a more complicated
 way. Firstly, during each run of the script current usage values are fetched
and stored in the $history_file file as a YAML document. When there are at least
3 datapoints and the time difference between the oldest and the most recent one
is higher than $min_averaging_window then a linear regression is calculated and
the slope value equals to the current groth ratio. All datapoints older than
$max_averaging_window are discared and removed from $history_file.

For each resource type (memory, disk) current and ideal growth ratios are compared
and if current growth ration is greater than ideal one by more than
$<type>_mon_warn_reduction percent then a warning is issued. Similarly, the critical
threshold is handled using $<type>_mon_crit_reduction.