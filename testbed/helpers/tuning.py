#!/usr/bin/python

import sys
import argparse
import time
import subprocess
import statistics

from helpers.airtime import AirtimeObserver, ChannelObserver, QueueAirtimeObserver
from helpers.collision_rate import CollisionRateObserver



class TunerBase(object):

    def __init__(self, iface, log_file):
        # TODO: implement iface --> phy translation
        assert(iface == 'wls33')
        phy = 'phy0'

        self.cr_observer = CollisionRateObserver(iface)

        self.txq_params_fname = '/sys/kernel/debug/ieee80211/'
        self.txq_params_fname += phy
        self.txq_params_fname += '/ath9k/txq_params'

        self.log_file = log_file

    def set_cw(self, cw, qumID=1, aifs=2, burst=0):
        # qumId = qumID
        # aifs = aifs
        cwmin = int(cw)
        cwmax = int(cw)
        # burst = burst

        txq_params_msg = '{} {} {} {} {}'.format(qumID, aifs, cwmin, cwmax, burst)
        f_cw = open(self.txq_params_fname, 'w')
        f_cw.write(txq_params_msg)
        f_cw.close()

    def log(self, alloc, airtime, cw_prev, cw, cr, aifs, log_file=None):
        if log_file is None:
            log_file = self.log()

        log_file.write('{:.5f},{:.5f},{:.5f},{},{},{:.5f},{}\n'.format(
                time.time(), alloc, airtime, cw_prev, cw, cr, aifs))
        log_file.flush()

    def update_cw(self, alloc, airtime):
        self.log(alloc, airtime, -1, -1, self.cr_observer.collision_rate(), -1)


class QueueTuner(TunerBase):

    def __init__(self, iface, log_directory, cw_init, beta, k, cw_min=0, cw_max=1023, enable_react=True):
        super(QueueTuner, self).__init__(iface, '')

        self.log_directory = log_directory
        self.qos_logfile = open(f'{log_directory}/qos_react.csv', 'w')
        self.be_logfile = open(f'{log_directory}/be_react.csv', 'w')

        self.cr_observer = CollisionRateObserver(iface)

        self.cw_min = cw_min
        self.cw_max = cw_max

        self.k = k
        self.beta = beta
        self.cw_prev_be = cw_init
        self.cw_prev_qos = cw_init
        self.smooth_be = None
        self.smooth_qos = None

        self.enable_react= enable_react

    def update_cw_queues(self, be_alloc, be_airtime, qos_alloc, qos_airtime):
        if self.enable_react:
            if self.smooth_be is None:
                self.smooth_be = be_airtime
            else:
                self.smooth_be = self.beta*be_airtime + (1.0 - self.beta) * self.smooth_be

            if self.smooth_qos is None:
                self.smooth_qos = qos_airtime
            else:
                self.smooth_qos = self.beta*qos_airtime + (1.0 - self.beta) * self.smooth_qos

            cw_be = int((self.smooth_be - be_alloc) * self.k) + self.cw_prev_be
            print(f'self.cw_min: {self.cw_min}, cw_be: {cw_be}')
            cw_be = self.cw_min if cw_be < self.cw_min else cw_be
            cw_be = self.cw_max if cw_be > self.cw_max else cw_be

            cw_qos = int((self.smooth_qos - qos_alloc) * self.k) + self.cw_prev_qos
            cw_qos = self.cw_min if cw_qos < self.cw_min else cw_qos
            cw_qos = self.cw_max if cw_qos > self.cw_max else cw_qos

            self.set_cw(cw_be, qumID=1, aifs=3)
            self.set_cw(cw_qos, qumID=2, aifs=2)

            self.log(be_alloc, be_airtime, self.cw_prev_be, cw_be, self.cr_observer.collision_rate(), 2, log_file=self.be_logfile)
            self.log(qos_alloc, qos_airtime, self.cw_prev_qos, cw_qos, self.cr_observer.collision_rate(), 2, log_file=self.qos_logfile)
            self.cw_prev_be = cw_be
            self.cw_prev_qos = cw_qos
        else:
            self.log(be_alloc, be_airtime, -1, -1, self.cr_observer.collision_rate(), 2, log_file=self.be_logfile)
            self.log(qos_alloc, qos_airtime, -1, -1, self.cr_observer.collision_rate(), 2, log_file=self.qos_logfile)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='New CW tuning implementation.',
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('-k', action='store', default=200.0, type=float,
                   help='k-multiplier for airtime tuning')
    p.add_argument('-b', action='store', default=0.6, type=float, help='beta value')
    p.add_argument('-n', '--no_tuning', action='store_true',
                   help="don't actually do any tuning (but still log airtime)")
    p.add_argument('-z', '--new_version', action='store_true')
    p.add_argument('-c', '--cw_initial', action='store', default=0, type=int,
                   help='initial CW value')
    p.add_argument('-t', '--sleep_time', action='store', default=1.0,
                   type=float, help='length (in seconds) of observation interval')
    p.add_argument('-a', '--airtime_alloc', action='store', default=0.20,
                   type=float, help='airtime allocated to this node via REACT')
    p.add_argument('-f', '--output_path', action='store', default='/users/dkulenka/')
    p.add_argument('-d', '--alloc_be', action='store', default=0.20, type=float)
    p.add_argument('-e', '--alloc_qos', action='store', default=0.0, type=float)
    p.add_argument('-y', '--renew', action='store_true')
    p.add_argument('--debug', action='store_true')
    args = p.parse_args()


    if args.new_version:
        if args.no_tuning:
            enable = False
        else:
            enable = True
        tuner = QueueTuner('wls33', args.output_path, args.cw_initial, args.b, args.k, enable_react=enable)
    elif args.no_tuning:
        # TODO: change this back to TunerBase??
        tuner = TunerBase('wls33', sys.stdout)

    ao = AirtimeObserver()
    qao = QueueAirtimeObserver()

    while True:
        time.sleep(args.sleep_time)

        if args.new_version:
            airtimes = qao.queue_airtime()
            tuner.update_cw_queues(args.alloc_be, airtimes['BE'], args.alloc_qos, airtimes['QoS'])
        else:
            airtime = ao.airtime()
            tuner.update_cw(args.airtime_alloc, airtime)
