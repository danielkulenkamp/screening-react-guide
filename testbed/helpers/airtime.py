#!/usr/bin/python

import subprocess
import time
import argparse

from helpers.observer import Observer

DEBUG = False


def xmit_dump(phy):
    filepath = f'/sys/kernel/debug/ieee80211/{phy}/ath9k/xmit'
    cmd = ['cat', filepath]
    output = subprocess.check_output(cmd).decode('utf-8').split()
    survey = {}

    def skip(output, i, to):
        while i < len(output):
            if output[i] == to:
                break
            else:
                i += 1
        return i

    i = 0
    # i = skip(output, i, 'TX-Pkts-All:')
    i = skip(output, i, 'TX-Bytes-All:')
    survey['BE'] = float(output[i+1])
    survey['BK'] = float(output[i+2])
    survey['VI'] = float(output[i+3])
    survey['VO'] = float(output[i+4])

    return survey


def iw_survey_dump(dev):
    cmd = ['iw', dev, 'survey', 'dump']
    output = subprocess.check_output(cmd).decode("utf-8").split()
    survey = {}

    def skip(output, i, to):
        while i < len(output):
            if output[i] == to:
                break
            else:
                i += 1
        return i

    i = 0
    i = skip(output, i, '[in')

    i = skip(output, i, 'active')
    survey['active'] = float(output[i + 2])

    i = skip(output, i, 'busy')
    survey['busy'] = float(output[i + 2])

    i = skip(output, i, 'receive')
    survey['receive'] = float(output[i + 2])

    i = skip(output, i, 'transmit')
    survey['transmit'] = float(output[i + 2])

    return survey


class ChannelObserver(Observer):

    def __init__(self, dev='wls33'):
        super(ChannelObserver, self).__init__(iw_survey_dump, dev)


class AirtimeObserver(Observer):

    def __init__(self, dev='wls33'):
        super(AirtimeObserver, self).__init__(iw_survey_dump, dev)

    def airtime(self):
        self.update()

        active = self.surveysays('active')
        transmit = self.surveysays('transmit')

        if active != 0:
            return transmit/active
        else:
            return 0.0


class QueueAirtimeObserver(AirtimeObserver):

    counter = 0

    def __init__(self, dev='wls33', phy='phy0'):
        super(QueueAirtimeObserver, self).__init__()
        self.phy = 'phy0'
        self.queue_observation_fn = xmit_dump

        self.new_queue_survey = self.queue_observation_fn(self.phy)
        self.old_queue_survey = {}

    def update(self):
        QueueAirtimeObserver.counter += 1
        AirtimeObserver.update(self)
        self.old_queue_survey = self.new_queue_survey
        self.new_queue_survey = self.queue_observation_fn(self.phy)

    def queue_surveysays(self):
        global DEBUG
        new = {}
        if DEBUG:
            print(QueueAirtimeObserver.counter)
        for question in ['BK', 'BE', 'VI', 'VO']:
            # print(f'new survey: {self.new_queue_survey[question]}')
            # print(f'old survey: {self.old_queue_survey[question]}')
            new[question] = self.new_queue_survey[question] - self.old_queue_survey[question]
        # print(new)
        return new

    def queue_airtime(self):
        global DEBUG
        # self.update()

        airtime = self.airtime()
        queues = self.queue_surveysays()

        total_pkts = sum([pkts for _, pkts in queues.items()])


        if total_pkts == 0:
            output =  {"BE": 0.0, "QoS": 0.0}
        else:
            output =  {
                "BE": queues["BE"]/total_pkts*airtime,
                "QoS": queues["VI"]/total_pkts*airtime
            }

        if DEBUG:
            print(f'airtime: {airtime}')
            print(f'total pkts: {total_pkts}')
            print(f'BE: {queues["BE"]}')
            print(f'QoS: {queues["VI"]}')
            print(f'BE airtime: {output["BE"]}')
            print(f'QoS airtime: {output["QoS"]}')

        return output



if __name__ == '__main__':
    p = argparse.ArgumentParser(
            description="Measure airtime using 'iw DEV survey dump'.",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('-d', '--dev', action='store', default='wls33',
            help='wireless interface')
    p.add_argument('-t', '--sleep_time', action='store', default=1.0, type=float,
            help='time (in seconds) to pause between airtime measurements')
    p.add_argument('-o', '--once', action='store_true',
            help="measure airtime once and exit")


    # args = p.parse_args()
    #
    # ao = AirtimeObserver(args.dev)
    # while True:
    #     time.sleep(args.sleep_time)
    #     print(ao.airtime())
    #
    #     if args.once:
    #         break

    args = p.parse_args()
    qao = QueueAirtimeObserver()
    while True:
        time.sleep(args.sleep_time)
        print(qao.queue_airtime())

        if args.once:
            break

