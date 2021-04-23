#!/usr/bin/python

import subprocess
import time

from helpers.observer import Observer

# TODO: somehow our setup causes there to be three "wls33 stations"
# ...so return the largest collision rate because that's the real wls33

def iw_station_dump(dev):
    cmd = ['iw', dev, 'station', 'dump']
    output = subprocess.check_output(cmd).decode("utf-8").splitlines()

    def match_and_append(line, match, alist):
        parts = line.split(match)
        if len(parts) == 2:
            alist.append(float(parts[1].strip()))

    tx = []
    retry = []
    for line in output:
        match_and_append(line, 'tx packets:', tx)
        match_and_append(line, 'tx retries:', retry)

    survey = {}
    survey['transmit'] = max(tx)
    survey['retry'] = max(retry)
    return survey

class CollisionRateObserver(Observer):

    def __init__(self, dev='wls33'):
        super(CollisionRateObserver, self).__init__(iw_station_dump, dev)

    def collision_rate(self):
        self.update()

        tx_retry = self.surveysays('retry')
        tx_total = self.surveysays('transmit')

        if tx_total != 0:
            return tx_retry/tx_total
        else:
            return 0.0

if __name__ == '__main__':
    observer = CollisionRateObserver('wls33')
    while True:
        time.sleep(1)
        print(observer.collision_rate())
