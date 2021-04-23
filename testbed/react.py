
import time
import sys
import signal
from multiprocessing import Process, Queue, Lock
import subprocess
import json
import re
import os
import math
from typing import List
import argparse

import netifaces
from scapy.layers.dot11 import RadioTap
from scapy.layers.dot11 import Dot11
from scapy.sendrecv import sendp, sniff
from helpers.airtime import AirtimeObserver, QueueAirtimeObserver
from helpers.buffer_observer import BufferObserver
from helpers.tuning import TunerSALT, TunerRENEW, TunerBase, QueueTuner
from react_algorithm import REACT

processes = []


def signal_handler(sig, frame):
    global processes
    print("you pressed ctrl c")
    for p in processes:
        p.terminate()
        # p.join()

    for p in processes:
        print(p.exitcode)
    sys.exit()


def usage(in_opt: str, ext_in_opt: List[str]) -> None:
    print("input error: here optionlist: \n{0} --> {1}\n".format(in_opt, str(ext_in_opt)))


class React(Process):

    def __init__(self, algorithm: str = 'dot', log_folder: str = None, offered_capacity: float = 0.8,
                 be_claim: float = 1.0, qos_claim: float = 0.0, be_prealloc: float = 0.0, qos_prealloc: float = 0.0,
                 cw_min: int = 0, cw_max: int = 1023, shaping: bool = True, debug: bool = False):
        Process.__init__(self)

        # Inter process cooperation vars
        self._processes = []
        self._sender_queue = Queue()
        self._sniffer_queue = Queue()
        self._cw_queue = Queue(maxsize=1) # (QoS claim, BE claim)
        self._new_claims_queue = Queue() # (QoS claim, BE claim)
        self._console_lock = Lock()

        # React vars
        self._i_time: float = 0.1
        self._interface: str = 'wls33'
        self._mon_interface: str = 'mon0'
        self._enable_react = False
        self._enable_shaper = shaping

        assert(algorithm == 'salt' or algorithm == 'dot' or algorithm == 'renew')

        if algorithm == 'salt':
            self._enable_react = True
        elif algorithm == 'renew':
            self._enable_react = True

        self._algorithm: str = algorithm
        self._data_path: str = log_folder
        self._start_time: float = time.time()
        self._sleep_time: float = self._i_time
        self._maximum_capacity: float = 1
        self._offered_capacity = offered_capacity - be_prealloc - qos_prealloc
        self._be_claim: float = be_claim
        self._qos_claim: float = qos_claim
        self._be_prealloc: float = be_prealloc
        self._qos_prealloc: float = qos_prealloc
        self._beta = 0.4
        self._k = 500
        self._cw_min = cw_min
        self._cw_max = cw_max

        # shaping vars
        self._max_bandwith = 6
        # self._shaper_value = f'{round(self._initial_claim * self._max_bandwith, 1)}mbit'
        self._shaper_value = None
        self._debug = debug

        self._counter = 0

        self.my_mac = str(netifaces.ifaddresses(self._interface)[netifaces.AF_LINK][0]['addr'])

    def _update_shaper(self, current_claim):
        new_shaper_value = f'{round(self._offered_capacity * current_claim * self._max_bandwith, 1)}mbit'

        if self._debug:
            with self._console_lock:
                print(f'old shaper value: {self._shaper_value}')
                print(f'new shaper value: {new_shaper_value}')

        if self._shaper_value != new_shaper_value:
            self._shaper_value = new_shaper_value
            command = f'sudo tc class change dev {self._interface} parent 1:0 classid 1:1 htb rate {self._shaper_value}'

            if self._debug:
                with self._console_lock:
                    print(f'running command: {command}')

            subprocess.run([command], shell=True)

    def _react_updater(self) -> None:
        if self._debug:
            with self._console_lock:
                print("react_updater: process started")

        react = REACT(
            self.my_mac,
            capacity=self._maximum_capacity,
            be_magnitude=self._be_claim,
            qos_magnitude=self._qos_claim
        )
        # if self._qos:
        #     react = REACT(self.my_mac, capacity=self._maximum_capacity, be_magnitude=0, qos_magnitude=self._initial_claim)
        # else:
        #     react = REACT(self.my_mac, capacity=self._maximum_capacity, be_magnitude=self._initial_claim, qos_magnitude=0)

        if self._debug:
            with self._console_lock:
                react.print_all_offers()

        # first check for updated claims
        # then check sniffer queue
        # then update state
        # then add packet to sender queue
        # then update cw

        while True:
            time.sleep(self._sleep_time)

            # check for updated claims
            if not self._new_claims_queue.empty():
                qos_claim, be_claim = self._new_claims_queue.get(False)
                react.update_magnitude(qos_claim, be_claim)

            # pull a packet from the sniffer queue
            # save the packet
            if not self._sniffer_queue.empty():
                if self._debug:
                    with self._console_lock:
                        print(f'Got new packet from sniffer queue')
                new_packets = {}
                while not self._sniffer_queue.empty():
                    neigh_name, packet = self._sniffer_queue.get(False)
                    new_packets[neigh_name] = packet

                for neigh_name, packet in new_packets.items():
                    react.new_be_offer(neigh_name, packet['be_offer'])
                    react.new_qos_claim(neigh_name, packet['qos_claim'])
                    react.new_be_claim(neigh_name, packet['be_claim'])

                    # if math.isclose(0, packet['be_claim']):
                    #     # we have a qos claim
                    #     react.new_qos_claim(neigh_name, packet['qos_claim'])
                    # else:
                    #     # we have a be claim
                    #     react.new_be_claim(neigh_name, packet['be_claim'])

                    for dictionary in packet['qos']:
                        if dictionary['sta_name'] == react.name:
                            react.new_qos_offer(neigh_name, dictionary['qos_offer'])

            else:
                if self._debug:
                    with self._console_lock:
                        print(f"react_updater: couldn't pull packet from queue")

            # update_claim, update_offer
            react.update_offer()
            react.update_claim()

            # create packet to send to
            pkt_to_send = {}
            react.update_timestamp()
            pkt_to_send['t'] = react.get_timestamp()
            pkt_to_send['be_offer'] = react.get_be_offer()
            pkt_to_send['be_claim'] = react.get_be_claim()
            pkt_to_send['qos_claim'] = react.get_qos_claim()

            items = react.qos_items()

            qos_offers = []
            for offer in items:
                sta = {
                    'sta_name': offer[0],
                    'qos_offer': offer[1],
                }
                qos_offers.append(sta)

            pkt_to_send['qos'] = qos_offers

            json_data = json.dumps(pkt_to_send)
            self._sender_queue.put(json_data)

            # check dead nodes
            timeout = 120
            # react.check_timeouts(timeout)

            current_qos_claim, current_be_claim = react.get_claim()
            if self._debug:
                with self._console_lock:
                    print(f'get_claim: ({current_qos_claim},{current_be_claim})')

            if self._enable_shaper:
                self._update_shaper(current_qos_claim+current_be_claim)

            if self._cw_queue.empty():
                self._cw_queue.put((current_qos_claim, current_be_claim))

            if self._counter % 20 == 0:
                with self._console_lock:
                    react.print_all_offers()

            self._counter = (self._counter % 20) + 1

    def _cw_updater(self) -> None:
        if self._debug:
            with self._console_lock:
                print("cw_updater: process started")
                print(f"cw_updater: data path is {self._data_path}")

        # be_log_file = open(self._data_path, 'w')
        cw_initial = 0

        # if self._enable_react:
        #     assert (self._algorithm == 'salt' or self._algorithm == 'renew')
        #     if self._algorithm == 'salt':
        #         tuner = TunerSALT(self._interface, log_file, cw_initial, self._beta, self._k, qos=self._qos)
        #     elif self._algorithm == 'renew':
        #         tuner = TunerRENEW(self._interface, log_file, cw_initial)
        #     else:
        #         raise Exception("Unknown tuner type!")
        # else:
        #     tuner = TunerBase(self._interface, log_file)

        tuner = QueueTuner(
            self._interface,
            self._data_path,
            cw_initial,
            self._beta,
            self._k,
            cw_min=self._cw_min,
            cw_max=self._cw_max,
            enable_react=self._enable_react
        )

        current_qos_claim = self._qos_claim
        current_be_claim = self._be_claim
        qao = QueueAirtimeObserver()
        bo = BufferObserver()
        while True:
            s = self._sleep_time - ((time.time() - self._start_time) % self._sleep_time)
            s = 1

            time.sleep(s)

            if self._enable_react:
                # we check if the queue has a new claim for us
                if not self._cw_queue.empty():
                    current_qos_claim, current_be_claim = self._cw_queue.get(False)
                    if self._debug:
                        with self._console_lock:
                            print(f"Queue had current claim of ({current_qos_claim},{current_be_claim})")
                # else:
                #     if self._debug:
                #         with self._console_lock:
                #             print("Queue was empty, it should just use the old value")

            # get the airtime, calculate the allocation
            airtimes = qao.queue_airtime()
            qos_alloc = float(self._offered_capacity) * current_qos_claim
            be_alloc = float(self._offered_capacity) * current_be_claim
            # grab the queue lens for debugging purposes
            # buffer_lens = bo.queue_lens()
            tuner.update_cw_queues(
                be_alloc + self._be_prealloc,
                airtimes['BE'],
                qos_alloc + self._qos_prealloc,
                airtimes['QoS']
            )

    def _sender(self) -> None:

        def send_ctrl_msg(json_data: str, my_mac: str, mon_interface: str = 'mon0') -> None:
            a = RadioTap() / Dot11(addr1="ff:ff:ff:ff:ff:ff", addr2=my_mac, addr3="ff:ff:ff:ff:ff:ff") / json_data
            sendp(a, iface=mon_interface, verbose=0)

        if self._debug:
            with self._console_lock:
                print("sender: process started")

        # first we have to get the initial packet. So we need to wait until the react updater gives us one
        packet_to_send = self._sender_queue.get()

        while True:
            if not self._sender_queue.empty():
                packet_to_send = self._sender_queue.get(False)
            # else:
                # if self._debug:
                #     with self._console_lock:
                #         print('SENDER PROCESS: Queue was empty, so we should use the same packet')

            # send the packet
            try:
                send_ctrl_msg(packet_to_send, self.my_mac)
            except Exception as err:
                if self._debug:
                    with self._console_lock:
                        print(f'sender exception: {err}')
                pass

            time.sleep(self._i_time / 10 - ((time.time() - self._start_time) % (self._i_time / 10)))

    def _sniffer(self):
        if self._debug:
            with self._console_lock:
                print("sniffer: process started")

        call_timeout = self._i_time
        call_count = 10
        packet_filter = 'ether dst ff:ff:ff:ff:ff:ff'

        while True:
            packet_list = sniff(iface=self._mon_interface, count=call_count, timeout=call_timeout, store=1,
                                filter=packet_filter)

            for packet in packet_list:
                try:
                    rx_mac = str(packet.addr2)
                    if rx_mac != self.my_mac:
                        payload = bytes(packet[3])
                        if 'claim' in str(payload):
                            # if self._debug:
                            #     with self._console_lock:
                            #         print('claim in packet')
                            # TODO: Make sure that removing the \{ and \} don't mess up the correctness
                            payload = '{' + re.search(r'{(.*)}', str(payload)).group(1) + '}'

                            if self._debug:
                                with self._console_lock:
                                    print(f'sniffer: payload -> {payload}')
                            curr_pkt = json.loads(payload)

                            # pass the packet to the react updater process
                            self._sniffer_queue.put((rx_mac, curr_pkt))
                except Exception as err:
                    if self._debug:
                        with self._console_lock:
                            print("sniffer exception: ", err)
                    pass

    def terminate(self):
        for process in self._processes:
            with self._console_lock:
                print("Terminating REACT")

            process.terminate()
            process.join()

        for process in self._processes:
            print(process.exitcode)

    def new_demand(self, qos_demand, be_demand) -> None:
        self._new_claims_queue.put((qos_demand, be_demand))

    def run(self) -> None:
        sender_process = Process(
            target=self._sender,
            args=()
        )

        sniffer_process = Process(
            target=self._sniffer,
            args=()
        )

        cw_process = Process(
            target=self._cw_updater,
            args=()
        )

        react_updater_process = Process(
            target=self._react_updater,
            args=()
        )

        if self._enable_react:
            if self._debug:
                with self._console_lock:
                    print('Starting all processes')
            self._processes = [sender_process, sniffer_process, cw_process, react_updater_process]
        else:
            if self._debug:
                with self._console_lock:
                    print('Starting just cw process')
            self._processes = [cw_process]

        if self._debug:
            with self._console_lock:
                print(f'Num threads: {len(self._processes)}')

        try:
            for process in self._processes:
                process.start()
        except Exception as err:
            print(err)
            print('Error: unable to start threads')
            self.terminate()

        while True:
            pass


def restricted_float(x):
    try:
        x = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{x} not a floating-point literal')

    if not (0.0 <= x <= 1.0):
        raise argparse.ArgumentTypeError(f'{x} not in range [0.0, 1.0]')
    return x


def restricted_int(x):
    try:
        x = int(x)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{x} not an integer literal')

    if not (0 <= x <= 1023):
        raise argparse.ArgumentTypeError(f'{x} not in range [0, 1023]')
    return x


def path_exists(filepath):
    parts = os.path.split(filepath)
    if not os.path.exists(parts[0]):
        raise argparse.ArgumentTypeError(f'{parts[0]} is not a valid directory')
    return filepath


def file_exists(file):
    if not os.path.isfile(file):
        raise argparse.ArgumentTypeError(f'{file} does not exist')
    return file


def main() -> None:
    global processes

    parser = argparse.ArgumentParser()
    parser.add_argument('tuner_algorithm', choices=['salt', 'renew', 'dot'], type=str,
                        help='algorithm used to perform tuning of contention window')
    parser.add_argument('output_folder', type=path_exists, help='file used for logging REACT info')
    parser.add_argument('capacity', type=restricted_float,
                        help='capacity offered to nodes (between 0 and 1)')
    parser.add_argument('initial_qos_claim', type=restricted_float,
                        help='initial QoS claim for react algorithm, between 0 and 1 (0% and 100%)')
    parser.add_argument('initial_be_claim', type=restricted_float,
                        help='initial BE claim for react algorithm, between 0 and 1 (0% and 100%)')
    parser.add_argument('-q', '--qos_prealloc', type=float, default=0.0,
                        help='used in multihop mode, to preallocate a certain amount of qos airtime '
                             'to flows running through this node')
    parser.add_argument('-b', '--be_prealloc', type=float, default=0.0,
                        help='used in multihop mode, to preallocate a certain amount of be airtime '
                             'to flows running through this node')
    parser.add_argument('-e', '--experiment_file', type=file_exists,
                        help='runs react in dynamic mode, adjusts claims based on json file contents')
    parser.add_argument('-x', '--cw_min', type=restricted_int, help='min value for cw')
    parser.add_argument('-y', '--cw_max', type=restricted_int, help='min value for cw')
    parser.add_argument('-s', '--shaping', help='activate shaping to assist tuning', action='store_true')
    parser.add_argument('--debug', action='store_true')

    args = parser.parse_args()

    tuner_algorithm = args.tuner_algorithm
    output_folder = args.output_folder
    initial_qos_claim = args.initial_qos_claim
    initial_be_claim = args.initial_be_claim
    qos_prealloc = args.qos_prealloc
    be_prealloc = args.be_prealloc
    cw_min = args.cw_min if args.cw_min else 0
    cw_max = args.cw_max if args.cw_max else 1023
    shaping = True if args.shaping else False
    debug = True if args.debug else False

    signal.signal(signal.SIGINT, signal_handler)


    r = React(
        algorithm=tuner_algorithm,
        log_folder=output_folder,
        qos_claim=initial_qos_claim,
        be_claim=initial_be_claim,
        be_prealloc=be_prealloc,
        qos_prealloc=qos_prealloc,
        cw_min=cw_min,
        cw_max=cw_max,
        shaping=shaping,
        debug=debug
    )
    # r = React(algorithm=tuner_algorithm, output_path=output_file, claim=initial_claim,
    #           qos=qos, shaping=shaping, debug=debug)
    processes = [r]
    r.start()

    if args.experiment_file:
        print('Working through exp file')
        with open(args.experiment_file, 'r') as f:
            exp = json.load(f)

        for event in exp['events']:
            print(f'Updating claim: {event["claim"]}')
            r.new_demand(event['qos'], event['claim'])
            time.sleep(event['duration'])

        print('Terminating react process')
        r.terminate()
        # r.join()
        print(r.exitcode)
        sys.exit()
    else:
        while True:
            pass


if __name__ == '__main__':
    main()
