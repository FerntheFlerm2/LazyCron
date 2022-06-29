#!/usr/bin/python3
# LazyCron - "Your computer will get around to it eventually."
# Usage: Run with -h for help.

################################################################################

import os
import time

import shared
import how_busy
import scheduler
from chronology import fmt_time, local_time
from timewatch import TimeWatch
from scheduler import aprint


from sd.msgbox import msgbox
from sd.easy_args import easy_parse
from sd.common import itercount, gohome, check_install, rfs, mkdir, warn, tman


def parse_args():
    "Parse arguments"
    positionals = [\
    ["schedule", '', str, 'schedule.txt'],
    "Filename to read schedule from."
    ]
    args = [\
    ['polling', 'polling_rate', float, 1],
    "How often to check (minutes)",
    ['idle', '', float, 0],
    "How long to wait before going to sleep (minutes) 0=Disable",
    ['verbose', '', int, 1],
    "What messages to print",
    ['testing', '', bool],
    "Do everything, but actually run the scripts.",
    ['logs', '', str, '/tmp/LazyCron_logs'],
    "Logging directory",
    ['skip', '', bool],
    "Don't run apps on startup, wait a bit.",
    ['stagger', '', float, 0],
    "Wait x minutes between starting programs.",
    ]
    return easy_parse(args,
                      positionals,
                      usage='<schedule file>, options...',
                      description='Monitor the system for idle states and run scripts at the best time.')


def is_busy(min_net=10e3, min_disk=1e6):
    '''
    Return True if disk or network usage above defaults
    min_net  = Network usage
    min_disk = Disk usage
    '''
    def fmt(num):
        return rfs(num)+'/s'

    net_usage = how_busy.get_network_usage(5, 4)
    if net_usage >= min_net:
        aprint("Busy: Network Usage:", fmt(net_usage))
        return True

    disk_usage = how_busy.all_disk_usage(5, 4)
    if disk_usage >= min_disk:
        aprint("Busy: Disk usage:", fmt(disk_usage))
        return True

    aprint("Not Busy - Network Usage:", fmt(net_usage), "Disk usage:", fmt(disk_usage))
    return False




def main(args, verbose=1):
    polling_rate = 0                        # Time to rest at the end of every loop
    idle_sleep = args.idle * 60             # Go to sleep after this long plugged in
    schedule_file = args.schedule           # Tab seperated input file
    testing_mode = args.testing             # Don't actually do anything

    tw = TimeWatch(verbose=verbose)
    last_schedule_read = 0                  # last time the schedule file was read
    last_run = 0                            # Time when the last program was started
    schedule_apps = []                      # Apps found in schedule.txt
    cur_day = time.localtime().tm_yday      # Used for checking for new day


    for counter in itercount():
        # Sleep at the end of every loop
        missing = tw.sleep(polling_rate)
        # Loop again to avoid edge case where the machine wakes up and is immediately put back to sleep
        while missing > 2 and missing > polling_rate / 10:
            missing = tw.sleep(polling_rate)
        polling_rate = args.polling_rate * 60

        # Check for a new day
        if time.localtime().tm_yday != cur_day:
            tw.reset()
            cur_day = time.localtime().tm_yday
            print(time.strftime('\n\nToday is %A, %-m-%d'), '\n' + '#' * 80)
            if verbose >= 2:
                print("Elapsed", fmt_time(tw.elapsed))
                for proc in schedule_apps:
                    proc.print()
                    print('\n')


        # Read the schedule file if it's been updated
        if os.path.getmtime(schedule_file) > last_schedule_read:
            if last_schedule_read:
                aprint("Schedule file updated:", '\n' + '#' * 80)
            else:
                # The first run
                print("\n\nSchedule file:", '\n' + '#' * 80)
            last_schedule_read = time.time()
            schedule_apps = scheduler.read_schedule(schedule_apps, schedule_file, msgbox if counter else warn)
            print('\n')
            # Add skip req to procs if specified in command line
            if args.skip:
                for proc in schedule_apps:
                    if 'skip' not in proc.reqs:
                        proc.reqs['skip'] = 1

        # Run scripts
        for proc in schedule_apps:
            if args.stagger and (time.time() - last_run) / 60 < args.stagger:
                break

            if proc.ready(tw, polling_rate):
                proc.run(testing_mode=testing_mode)
                last_run = time.time()


        # Put the computer to sleep after checking to make sure nothing is going on.
        if idle_sleep and tw.idle > idle_sleep:
            if shared.COMP.plugged_in():
                # Plugged mode waits for idle system.
                ready, results = tman.query(is_busy, max_age=polling_rate * 1.5)
                if ready:
                    if not results:
                        print("Going to sleep\n")
                        if not testing_mode:
                            tw.sleepy_time()
                            polling_rate = 2
            else:
                # Battery Mode doesn't wait for idle system.
                print("Idle and unplugged. Going to sleep.\n")
                if not testing_mode:
                    tw.sleepy_time()
                    polling_rate = 2


if __name__ == "__main__":
    UA = parse_args()
    if UA.idle:
        check_install('iostat', 'sar',
                      msg='''sudo apt install sysstat sar
                      --idle requires iostat () to determine if the computer can be put to sleep.''')
    # Min level to print messages:
    shared.VERBOSE = UA.verbose
    shared.LOG_DIR = UA.logs
    mkdir(UA.logs)
    gohome()
    os.nice(5)
    print("Log started at:", local_time(shared.START_TIME), '=', int(shared.START_TIME))
    main(UA, shared.VERBOSE)
