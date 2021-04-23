#!/usr/bin python

import time
import os
import socket
import struct
import json
import random
import pickle

import lsb_release_ex as lsb

from fabric import Connection
from fabric import task
from fabric.group import ThreadingGroup

from invoke import run

from patchwork.files import exists

from utils.conn_matrix import ConnMatrix
from experiment_descriptors import dynamic_exps, complete_exps, line_exps, star_exps

"""
For the fabric tasks, my convention here is to put the first argument as 'c'
if the task does NOT use the passed in connection object. If the task DOES use
the passed in connection object, it will be called 'conn'. 

You don't have to pass in a value for c, because the default value is None. 
"""


# Change these parameters to the necessary values
USERNAME = 'USERNAME'

# Path to where the GitHub repository is stored
PROJECT_PATH = '/groups/wall2-ilabt-iminds-be/WILAB-PROJECT/react80211'

# Path to where you want to save the data
DATA_PATH = '/groups/wall2-ilabt-iminds-be/WILAB_PROJECT/data/'

# Path to the Python binary (has been tested with 3.9.x, lower versions may work)
PYTHON_PATH = '/groups/wall2-ilabt-iminds-be/WILAB_PROJECT/pyenv/versions/3.9.0/bin/python'


HOSTS = []
HOSTS_DRIVER = []
HOSTS_TX_POWER = []
HOSTS_IPS = {}


def set_hosts(host_file):
    global HOSTS
    global HOSTS_DRIVER
    global HOSTS_TX_POWER
    global HOSTS_IPS

    hosts_info_file = open(host_file, 'r').readlines()

    hosts_info=[]
    for i in hosts_info_file:
        if not i.startswith("#"):
            hosts_info.append(i)

    HOSTS = [i.split(',')[0] for i in hosts_info]
    HOSTS_DRIVER = [i.split(',')[1].replace("\n", "") for i in hosts_info]
    HOSTS_TX_POWER = [i.split(',')[2].replace("\n", "") for i in hosts_info]
    for host in HOSTS:
        ip_index = HOSTS.index(host)
        HOSTS_IPS[host] = f'192.168.0.{ip_index + 1}'

# set nodes
set_hosts('node_info.txt')


@task
def install_python_deps(c):
    """Install python dependencies. """
    global HOSTS

    group = ThreadingGroup(*HOSTS)
    group.run("sudo apt-get update; sudo apt-get install -y python-scapy python-netifaces python-numpy python-flask")


@task
def set_tx_power(c, interface = 'wls33', tx_power = 1):
    """Sets tx_power for an interface. """
    global HOSTS

    group = ThreadingGroup(*HOSTS)
    group.run(f'sudo iwconfig {interface} txpower {tx_power}')


@task
def network(c, frequency = 2412, interface = 'wls33',
            rts = 'off', mac_address = 'aa:bb:cc:dd:ee:ff'):
    """Sets up ad-hoc network between the nodes. """
    global HOSTS
    global HOSTS_DRIVER
    global HOSTS_TX_POWER
    global HOSTS_IPS

    monitor_interface = 'mon0'

    for host in HOSTS:
        ip_index = HOSTS.index(host)
        print(host)
        driver = HOSTS_DRIVER[ip_index]
        tx_power = HOSTS_TX_POWER[ip_index]


        ip_addr = HOSTS_IPS[host]
        rate = 6
        essid = 'test'

        # backports_str = '/groups/wall2-ilabt-iminds-be/react/backports/16/backports-cw-tuning/'
        backports_str = PROJECT_PATH + "driver_extension/"

        # associate host
        conn = Connection(host)
        # conn.run(f'cd {backports_str}')

        # This command has to be together, in order for the kernel modules to load
        # it uses relative folders in the load.sh script, so we need to be inside
        # the backports patch folder
        conn.run(f'cd {backports_str};sudo ./load.sh', warn=True)

        conn.run(f'sudo iwconfig {interface} mode ad-hoc', warn=True)
        conn.run(f'sudo ifconfig {interface} {ip_addr} up', warn=True)
        conn.run(f'sudo iwconfig {interface} txpower {tx_power}dbm', warn=True)
        conn.run(f'sudo iwconfig {interface} rate {rate}M fixed', warn=True)
        conn.run(f'sudo iw dev {interface} ibss join {essid} {frequency} fixed-freq {mac_address}', warn=True)

        conn.run(f'sudo iw dev {interface} interface add {monitor_interface} type monitor')
        conn.run(f'sudo ifconfig {monitor_interface} up')
        conn.run(f'sudo iwconfig {interface} rts {rts}')



@task
def stop_react_all(c):
    """Stops react on all nodes. """
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    for conn in group:
        stop_react(conn)


@task
def stop_react(conn):
    """Stops react on the node connected to with the given conn parameter. """
    screen_stop_session(conn, 'react')


@task
def stop_salt_all(c):
    """Stops react on all nodes. """
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    for conn in group:
        stop_salt(conn)


@task
def run_react_new(conn, out_dir, offered_airtime=0.8, tuner='salt', qos_claim=0.0, be_claim = 0.80,
                  cw_min=0, cw_max=1023, qos_prealloc=None, be_prealloc=None, filename=None,
                  shaping=True, debug=False):
    """Starts react on the node connected to with the given conn parameter."""
    global PROJECT_PATH
    global PYTHON_PATH

    arguments = [tuner, f'{out_dir}/', str(offered_airtime), str(qos_claim), str(be_claim)]

    if filename:
        arguments.append('-e')
        arguments.append(filename)

    arguments.append(f'-x {cw_min}')
    arguments.append(f'-y {cw_max}')

    if shaping:
        arguments.append('--shaping')
    if qos_prealloc:
        arguments.append(f'-q {qos_prealloc}')
    if be_prealloc:
        arguments.append(f'-b {be_prealloc}')
    if debug:
        arguments.append('--debug')

    react_path = os.path.join(PROJECT_PATH, 'testbed')

    stop_react(conn)

    executable_path = f"sudo {PYTHON_PATH} -u {react_path}/react.py {' '.join(arguments)}"
    print(executable_path)
    screen_start_session(conn, 'react', executable_path)


################################################################################
# misc


def dot2long(ip):
    """Converts human readable IP address to a bit-packed machine format. """
    return struct.unpack("!L", socket.inet_aton(ip))[0]


def long2dot(ip):
    """Converts bit-packet machine IP address to human readable format. """
    return socket.inet_ntoa(struct.pack('!L', ip))


@task
def get_mac(conn, dev='wls33'):
    """Gets the mac address of the device connected to with the given conn object. """
    global PYTHON_PATH
    cmd = f"{PYTHON_PATH} -c 'from netifaces import *; print(ifaddresses(\"{dev}\")[17][0][\"addr\"])'"
    result = conn.run(cmd).stdout.splitlines()[0]

    return result


@task
def get_my_ip(conn, dev = 'wls33'):
    """Gets the IP address of the device connected to with the given conn object. """
    global PYTHON_PATH
    cmd = f"{PYTHON_PATH} -c 'from netifaces import *; print(ifaddresses(\"{dev}\")[AF_INET][0][\"addr\"])'"
    result = conn.run(cmd).stdout.splitlines()[0]
    return result


@task
def time_sync(c):
    """Synchronizes the time among the nodes. This is imprecise, PTPd is better for precision. """
    global HOSTS
    group = ThreadingGroup(*HOSTS)
    for conn in group:
        conn.run('sudo service ntp stop')
        conn.run('sudo ntpdate time.nist.gov')


@task
def reboot(c):
    """Reboots all nodes. """
    global HOSTS
    group = ThreadingGroup(*HOSTS)
    for conn in group:
        conn.run('sudo reboot')


@task
def check_awake(c):
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    all_awake = False
    while not all_awake:
        all_awake = True
        time.sleep(10)
        try:
            for conn in group:
                result = conn.run(':')
                for key, item in result.items():
                    if not item.ok:
                        all_awake = False
        except Exception:
            print('Not awake yet... Trying again in 10s...')
    print('All awake!')


@task
def start_test_screens(c):
    """Starts screens for react, mgen, and tshark on all nodes"""
    global HOSTS
    group = ThreadingGroup(*HOSTS)
    group.run('screen -S mgen', pty=False)
    group.run('screen -S react', pty=False)
    group.run('screen -S tshark', pty=False)

@task
def all_up(c):
    """A way to make sure you are connected to all the nodes. """
    global HOSTS
    group = ThreadingGroup(*HOSTS)
    group.run(':')
    group.run('echo UP')


@task
def screen_start_session(conn, name, cmd):
    """Start a screen session with the given command on the node connected to with the given conn object. """
    conn.run(f'screen -S {name} -dm bash -c "{cmd}"', pty=False)


@task
def screen_stop_session(conn, name, interrupt = False):
    """Stop a screen session with the given name on the node connected to with the given conn object. """
    if interrupt:
        conn.run(f'screen -S {name} -p 0 -X stuff " "', warn=True)
    else:
        conn.run(f'screen -S {name} -X quit', warn=True)


@task
def screen_stop_all(c):
    """Stop all screen sessions on all nodes, except for PTPd sessions. """
    global HOSTS

    for host in HOSTS:
        conn = Connection(host)
        conn.run('screen -wipe', warn=True)

        result = conn.run('ls /var/run/screen/S-$(whoami)')
        sessions = result.stdout.strip().split()

        for name in sessions:
            if name.split('.')[1] != 'running' and name.split('.')[1] != 'ptpd' and name.split('.')[1] != 'tshark':
                screen_stop_session(conn, name)


@task
def iperf_start_servers(c):
    """Starts UDP and TCP iperf servers on all of the nodes. """
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    for conn in group:
        screen_start_session(conn, 'iperf_server_udp', 'iperf -s -u')
        screen_start_session(conn, 'iperf_server_tcp', 'iperf -s')


@task
def iperf_start_clients(conn, host_out_dir, conn_matrix,
                        tcp = False, tos='0x00', window_size=None, no_delay=False, rate=None, time=120, extra=False):
    """Starts iperf clients on the nodes. It uses the passed ConnMatrix to determine which IP address to send to. """
    # for server in conn_matrix.links(get_my_ip(conn)):
    server = conn_matrix.links(get_my_ip(conn))
    if not server:
        return
    print(server)
    print(f'conn.host: {conn.host}')
    print(server)
    cmd = 'iperf -c {}'.format(server[0])
    if not tcp:
        if rate is not None:
            cmd += f' -u -b {rate}'
        else:
            cmd += ' -u -b {}'.format(server[1])

    # if window_size is not None:
    if window_size is not None:
        cmd += f' -w {window_size}'
    if no_delay:
        cmd += ' --nodelay'

    cmd += ' -S {}'.format(tos)
    cmd += f' -t {time} -i 1 -yC'

    # Use -i (ignore signals) so that SIGINT propagted up pipe to iperf
    if extra:
        cmd += ' | tee -i {}/{}_extra.csv'.format(host_out_dir, server[0])
    else:
        cmd += ' | tee -i {}/{}.csv'.format(host_out_dir, server[0])
    print(f'cmd: {cmd}')
    screen_start_session(conn, 'iperf_client', cmd)


@task
def start_pings(conn, host_out_dir, conn_matrix, tos='0x00', extra=False):
    """Starts pings on a node according to the connection matrix. This is done to measure delay, so we can later
    calculate both delay and jitter in addition to the throughput and drop rate with iperf. """
    server = conn_matrix.links(get_my_ip(conn))
    if not server:
        return
    print(server)
    print(f'conn.host: {conn.host}')
    print(server)
    if extra:
        cmd = f'ping {server[0]} -Q {tos} | tee -i {host_out_dir}/{server[0]}_ping_extra.txt'
    else:
        cmd = f'ping {server[0]} -Q {tos} | tee -i {host_out_dir}/{server[0]}_ping.txt'
    print(f'cmd: {cmd}')
    screen_start_session(conn, 'ping_client', cmd)


@task
def ping_test(c):
    """Tests pings for the nodes."""
    global USERNAME
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    cm = ConnMatrix()
    cm.add('192.168.0.1', r'192.168.0.3', '6Mbps')
    cm.add('192.168.0.3', r'192.168.0.1', '6Mbps')

    first = True
    for conn in group:
        if first:
            tos = '0xe0'
            first = False
        else:
            tos = '0x00'

        start_pings(conn, f"/users/{USERNAME}/", cm, tos=tos)

@task
def iperf_test(c):
    """Tests iperf on one of the nodes. """
    global USERNAME
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    cm = ConnMatrix()
    cm.add('192.168.0.1', r'192.168.0.2', '6Mbps')
    cm.add('192.168.0.2', r'192.168.0.3', '6Mbps')
    cm.add('192.168.0.3', r'192.168.0.4', '6Mbps')
    cm.add('192.168.0.4', r'192.168.0.1', '6Mbps')

    for conn in group:
        iperf_start_clients(conn, f"/users/{USERNAME}/", cm)


@task
def iperf_stop_clients(c):
    """Stops all iperf clients on all of the nodes. """
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    for conn in group:
        screen_stop_session(conn, 'iperf_client', interrupt=True)


@task
def make_out_directory(conn, out_dir = '/groups/wall2-ilabt-iminds-be/react/data/test',
                       trial_dir = None, unique = True):
    """Makes an output directory at the given location. Does not overwrite directories,
    instead will increment the counter and create a new directory each time called. """
    expand_user_cmd = f"python -c 'import os; print(os.path.expanduser(\"{out_dir}\"))'"
    out_dir = run(expand_user_cmd).stdout.splitlines()[0]

    i = 0
    while True:
        sub_directories = [out_dir, '{:03}'.format(i)]

        # subdirs = []
        # subdirs.append(out_dir)
        # subdirs.append('{:03}'.format(i))
        if trial_dir is not None:
            sub_directories.append(trial_dir)
        sub_directories.append(conn.host)

        host_out_dir = '/'.join(sub_directories)

        if not unique or not(exists(conn, path=host_out_dir, runner=None)):
            break

        i += 1

    print(host_out_dir)
    conn.run(f'mkdir -p {host_out_dir}')
    return host_out_dir


@task
def reset_netifaces(c):
    global HOSTS
    group = ThreadingGroup(*HOSTS)
    for conn in group:
        conn.run('sudo ifconfig wls33 down')
        conn.run('sudo ifconfig wls33 up')


@task
def setup_tc(c, iface='wls33', initial_rate='6mbit'):
    global HOSTS

    dst_nodes = [
        '192.168.0.1',
        '192.168.0.2',
        '192.168.0.3',
        '192.168.0.4',
    ]

    commands = [
        f'sudo tc qdisc add dev {iface} root handle 1:0 htb default 30',
        f'sudo tc class add dev {iface} parent 1:0 classid 1:1 htb rate {initial_rate}',
    ]
    for node in dst_nodes:
        commands.append(
            f'sudo tc filter add dev {iface} protocol all parent 1: u32 match ip dst {node} flowid 1:1'
        )

    for host in HOSTS:
        for command in commands:
            with Connection(host) as conn:
                conn.run(command, warn=True)



@task
def setup(c):
    """Sets up all of the nodes. Includes time synchronization, creating the ad-hoc network,
    and starting iperf servers. """
    screen_stop_all(c)
    time_sync(c)
    network(c, frequency = 5180)
    iperf_start_servers(c)


@task
def set_dcf(c):
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    commands = [
        'sudo echo "0 2 15 1023 0" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
        'sudo echo "1 2 15 1023 0" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
        'sudo echo "2 2 15 1023 0" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
        'sudo echo "3 2 15 1023 0" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
    ]

    for command in commands:
        for conn in group:
            conn.run(command)


@task
def set_edca(c):
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    commands = [
        'sudo echo "0 7 15 1023 0" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
        'sudo echo "1 3 15 1023 0" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
        'sudo echo "2 2 7 15 3" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
        'sudo echo "3 2 3 7 1" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
    ]

    for command in commands:
        for conn in group:
            conn.run(command)

@task
def set_edca_react(c):
    global HOSTS
    group = ThreadingGroup(*HOSTS)

    commands = [
        'sudo echo "0 2 15 1023 0" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
        'sudo echo "1 2 15 1023 0" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
        'sudo echo "2 2 7 15 3" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
        'sudo echo "3 2 3 7 1" | sudo tee /sys/kernel/debug/ieee80211/phy0/ath9k/txq_params',
    ]

    for command in commands:
        for conn in group:
            conn.run(command)



@task
def stop_exp(c):
    """Stops experiment. Involves stopping all screen sessions and restarting iperf servers. """
    screen_stop_all(c)
    iperf_start_servers(c)



########################################################
## Screening Experiments ###############################
########################################################

levels = [
    ['yes', 'no'], # REACT param
    [0, 15], # REACT param
    [511, 1023], # REACT param
    ['BE', 'QoS', 'BE_QoS'], # ConnMatrix param
    ['node1', 'node2', 'node3', 'node4'], # ConnMatrix param
    [0, 10, 25, 50], # REACT param
    ['DCF', 'EDCA', 'REACT_80', 'REACT_85', 'REACT_90', 'REACTQoS_80', 'REACTQoS_85', 'REACTQoS_90'], # REACT param
    ['UDP_500K', 'UDP_1M', 'UDP_5M', 'UDP_10M', # iperf param
     'TCP_8K_D', 'TCP_64K_D', 'TCP_128K_D', 'TCP_256K_D',
     'TCP_8K_N', 'TCP_64K_N', 'TCP_128K_N', 'TCP_256K_N'],
]

def get_LA_rows(la):
    """Reads in the locating array from the file, converts it from factor levels to 
    parameters that can be used to run the experiment. Also shuffles the array so 
    each replicate is run in a different order. """

    with open(la, 'r') as f:
        lines = f.readlines()
    num_rows = int(lines[1].split('\t')[0].strip())
    num_params = int(lines[1].split('\t')[1].strip())

    params = []

    for param in lines[2].split('\t'):
        params.append(param.strip())
    params = params[:-1]
    params = [int(param) for param in params]

    first_row = 3 + num_params + 1

    rows = []
    i = 0
    for row in range(first_row, num_rows+first_row):
        run = [line.strip() for line in lines[row].split('\t')][:-1]
        run = [int(r) for r in run]
        run.insert(0,i)
        i += 1
        rows.append(run)

    random.shuffle(rows)
    return rows


def get_conn_matrices(type, qos_node_flow_type, qos_node):
    """Builds a ConnMatrix object based on the parameters passed in. Basically a 
    helper function to simplify the code in the screening() function. """

    extra_cm = None
    cm = ConnMatrix()
    qos_ip = '192.168.0.1'
    if type == 'complete':
        cm.add('192.168.0.1', r'192.168.0.2', '3Mbps')
        cm.add('192.168.0.2', r'192.168.0.3', '1Mbps')
        cm.add('192.168.0.3', r'192.168.0.4', '1Mbps')
        cm.add('192.168.0.4', r'192.168.0.1', '1Mbps')
        if qos_node_flow_type == 'BE_QoS':
            extra_cm = ConnMatrix()  # extra cm will always be the BE flow
            extra_cm.add('192.168.0.1', r'192.168.0.3', '1Mbps')
            extra_cm.add('192.168.0.3', r'NONE', '0.0Mbps')
        qos_ip = '192.168.0.1'
    elif type == 'line':
        if qos_node == 'node1':
            cm.add('192.168.0.1', r'192.168.0.2', '3Mbps')
            cm.add('192.168.0.2', r'192.168.0.1', '1Mbps')
            cm.add('192.168.0.3', r'192.168.0.4', '1Mbps')
            cm.add('192.168.0.4', r'192.168.0.3', '1Mbps')
            if qos_node_flow_type == 'BE_QoS':
                extra_cm = ConnMatrix()  # extra cm will always be the BE flow
                extra_cm.add('192.168.0.1', r'192.168.0.2', '1Mbps')
                extra_cm.add('192.168.0.2', r'NONE', '0.0Mbps')
            qos_ip = '192.168.0.1'
        elif qos_node == 'node2':
            cm.add('192.168.0.1', r'192.168.0.2', '1Mbps')
            cm.add('192.168.0.2', r'192.168.0.1', '3Mbps')
            cm.add('192.168.0.3', r'192.168.0.4', '1Mbps')
            cm.add('192.168.0.4', r'192.168.0.3', '1Mbps')
            if qos_node_flow_type == 'BE_QoS':
                extra_cm = ConnMatrix()  # extra cm will always be the BE flow
                extra_cm.add('192.168.0.2', r'192.168.0.3', '1Mbps')
                extra_cm.add('192.168.0.3', r'NONE', '0.0Mbps')
            qos_ip = '192.168.0.2'
        elif qos_node == 'node3':
            cm.add('192.168.0.1', r'192.168.0.2', '1Mbps')
            cm.add('192.168.0.2', r'192.168.0.1', '1Mbps')
            cm.add('192.168.0.3', r'192.168.0.4', '3Mbps')
            cm.add('192.168.0.4', r'192.168.0.3', '1Mbps')
            if qos_node_flow_type == 'BE_QoS':
                extra_cm = ConnMatrix()  # extra cm will always be the BE flow
                extra_cm.add('192.168.0.3', r'192.168.0.2', '1Mbps')
                extra_cm.add('192.168.0.2', r'NONE', '0.0Mbps')
            qos_ip = '192.168.0.3'
        elif qos_node == 'node4':
            cm.add('192.168.0.1', r'192.168.0.2', '1Mbps')
            cm.add('192.168.0.2', r'192.168.0.1', '1Mbps')
            cm.add('192.168.0.3', r'192.168.0.4', '1Mbps')
            cm.add('192.168.0.4', r'192.168.0.3', '3Mbps')
            if qos_node_flow_type == 'BE_QoS':
                extra_cm = ConnMatrix()  # extra cm will always be the BE flow
                extra_cm.add('192.168.0.4', r'192.168.0.3', '1Mbps')
                extra_cm.add('192.168.0.3', r'NONE', '0.0Mbps')
            qos_ip = '192.168.0.4'
    return cm, extra_cm, qos_ip



@task
def screening(c, run, type, params):
    """Function for executing a single test from the locating array. 
    Used by the run_screening function"""

    global HOSTS
    group = ThreadingGroup(*HOSTS)

    shaping = True if params[0] == 'yes' else False
    cw_min = params[1]
    cw_max = params[2]
    qos_node_flow_type = params[3]
    if type == 'line':
        qos_node = params[4]
        qos_demand = params[5]
        protocol = params[6]
        flow_info = params[7]
    # elif type == 'complete':
    else:
        qos_node = 'node1'
        qos_demand = params[4]
        protocol = params[5]
        flow_info = params[6]

    cm, extra_cm, qos_ip = get_conn_matrices(type, qos_node_flow_type, qos_node)

    # make the output directories
    out_dirs = {}
    for conn in group:
        out_dirs[conn.host] = \
            make_out_directory(
                conn,
                f'{DATA_PATH}screening/{type}/run{run}'
            )

    # set the MAC protocol
    protocol = protocol.split('_')
    if len(protocol) == 1:
        use = protocol[0].lower()
        offered_airtime = 0.8
    else:
        if protocol[0] == 'REACT':
            use = 'react'
        # elif protocol[0] == 'REACTQoS':
        else:
            use = 'react_qos'
        offered_airtime = int(protocol[1]) / 100.0

    # sets access category parameters
    if use == 'dcf' or use == 'react':
        print('DCF or REACT')
        set_dcf(c)
    elif use == 'edca':
        print('EDCA')
        set_edca(c)
    elif use == 'react_qos':
        print('REACT QOS')
        set_edca_react(c)

    # starts REACT running on all of the nodes
    print('starting REACT')
    for conn in group:
        if use == 'dcf' or use == 'edca':
            tuner = 'dot'
        else:
            tuner = 'salt'

        # setting BE/QoS claims for REACt
        # qos_claim, be_claim = get_demand_amounts(use, qos_demand, cm, extra_cm)
        if use == 'dcf' or use == 'edca':
            qos_claim, be_claim = 0.0, 0.0
        elif use == 'react':
            qos_claim, be_claim = 0.0, 1.0
        elif use == 'react_qos':
            if get_my_ip(conn) == qos_node:
                # this is the qos node
                # now we need to check if we have two flows or one
                qos_claim = qos_demand
                if extra_cm is not None:
                    be_claim = 1.0
                else:
                    be_claim = 0.0
            else:
                # just a be node
                qos_claim, be_claim = 0.0, 1.0
        else:
            print("Error -- no qos_claim")
            print(f'use: {use}')
            raise AssertionError()

        run_react_new(
            conn,
            out_dirs[conn.host],
            tuner=tuner,
            qos_claim=qos_claim,
            be_claim=be_claim,
            offered_airtime=offered_airtime,
            cw_min=cw_min,
            cw_max=cw_max,
            shaping=shaping
        )

    # start pings for collecting delay and jitter
    print('starting pings')
    for conn in group:
        if (use == 'react_qos' or use == 'edca') and get_my_ip(conn) == qos_node:
            tos = '0xa0'
        else:
            tos = '0x00'
        start_pings(conn, out_dirs[conn.host], cm, tos=tos)

        if extra_cm is not None and get_my_ip(conn) == qos_node:
            start_pings(conn, out_dirs[conn.host], extra_cm, tos='0x00')

    # starts iperf streams for throughput
    print('starting iperf')
    for conn in group:
        if (use == 'react_qos' or use == 'edca') and get_my_ip(conn) == qos_node:
            tos = '0xa0'
        else:
            tos = '0x00'

        # parsing of TCP_8K_N
        print(flow_info)
        new_flow_info = flow_info.split('_')

        if new_flow_info[0] == 'TCP':
            tcp = True
            window_size = new_flow_info[1]
            no_delay = False if new_flow_info[2] == 'D' else True
        else:
            tcp = False
            rate = new_flow_info[1]

        if tcp:
            iperf_start_clients(conn, out_dirs[conn.host], cm, tos=tos, tcp=tcp, no_delay=no_delay, window_size=window_size, time=60)
        else:
            iperf_start_clients(conn, out_dirs[conn.host], cm, tos=tos, rate=rate, time=60)

        # if QoS is sending two flowx
        if extra_cm is not None and get_my_ip(conn) == qos_node:
            if tcp:
                iperf_start_clients(conn, out_dirs[conn.host], cm, tos=tos, tcp=tcp, no_delay=no_delay,
                                    window_size=window_size, time=60, extra=True)
            else:
                iperf_start_clients(conn, out_dirs[conn.host], extra_cm, tos='0x00', rate=rate, time=60, extra=True)

    print('running experiment for 120 seconds')
    time.sleep(65)

    print('stopping experiment')
    stop_exp(c)


@task
def set_LA_file(c):
    line_path = f'{PROJECT_PATH}/LAs/line/line_la.tsv'
    # line_path = f'/Users/danielkulenkamp/Documents/asu/research/thesis/react80211/LAs/line/line_la.tsv'
    comp_path = f'{PROJECT_PATH}/LAs/complete/comp_la.tsv'
    test_path = f'{PROJECT_PATH}/LAs/test/test_la.tsv'
    # for exp in ['line', 'complete']:
    for exp in ['line']:
        print(f'Type: {exp}')
        if exp == 'line':
            path = line_path
        elif exp == 'complete':
            path = comp_path
        else:
            path = test_path
            exp = 'line'

        LA_rows = get_LA_rows(path)
        print(LA_rows)

        with open(f'{PROJECT_PATH}/LAs/temp/temp.pkl', 'wb') as f:
            pickle.dump(LA_rows, f)



@task
def run_screening_one(c):
    la = f'{PROJECT_PATH}/LAs/temp/temp.pkl'

    rows = []
    with open(la, 'rb') as f:
        rows = pickle.load(f)

    if not rows:
        print("We are all done! ")
        return
    else:
        print(f'We have {len(rows)} rows left')

    current_row = rows.pop(0)
    params = []
    exp = 'line'
    for j in range(1, len(current_row)):
        if exp == 'complete' and j >= 5:
            params.append(levels[j][current_row[j]])
        else:
            params.append(levels[j - 1][current_row[j]])

    print(f'row: {current_row}')
    screening(c, current_row[0], exp, params)
    time.sleep(5)

    with open(la, 'wb') as f:
        pickle.dump(rows,f)

    print("DONE")


@task
def run_screening_complete_one(c):
    la = f'{PROJECT_PATH}/LAs/temp/temp.pkl'

    rows = []
    with open(la, 'rb') as f:
        rows = pickle.load(f)

    if not rows:
        print("We are all done! ")
        return
    else:
        print(f'We have {len(rows)} rows left')

    current_row = rows.pop(0)
    params = []
    exp = 'complete'
    for j in range(1, len(current_row)):
        if exp == 'complete' and j >= 5:
            params.append(levels[j][current_row[j]])
        else:
            params.append(levels[j - 1][current_row[j]])

    print(f'row: {current_row}')
    screening(c, current_row[0], exp, params)
    time.sleep(5)

    with open(la, 'wb') as f:
        pickle.dump(rows,f)

    print("DONE")
