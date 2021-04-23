from statistics import mean
from glob import glob


def parse_data_for_run(run_folder):

    def get_node_directories(run_folder):
        return glob(f'{run_folder}/0*/*')

    def parse_ping_file(ping_file):
        with open(ping_file, 'r') as f:
            lines = f.readlines()

        if not lines:
            return -1, -1

        lines = lines[1:]
        lines = [line for line in lines if "Host" not in line]
        lines = [line.split(' ')[-2] for line in lines]
        lines = [line for line in lines if line != 'nexthop:']
        lines = [line for line in lines if line != 'ms']
        lines = [float(line.split('=')[-1]) for line in lines]
        if not lines:
            return -1, -1

        delay = mean(lines)
        jitter = []

        for i in range(len(lines) - 1):
            jitter.append(abs(lines[i + 1] - lines[i]))
        if len(lines) == 1:
            jitter = -1
        else:
            jitter = mean(jitter)

        return delay, jitter

    def parse_throughput_file(throughput_file):
        with open(throughput_file, 'r') as f:
            lines = f.readlines()
        if not lines:
            return 0
        throughput = int(lines[-1].split(',')[8])

        return throughput

    directories = get_node_directories(run_folder)
    # print(directories)
    assert len(directories) == 4
    for directory in directories:
        ping_file = glob(f'{directory}/*_ping.txt')[0]
        throughput_file = glob(f'{directory}/192*.csv')[0]
        delay, jitter = parse_ping_file(ping_file)
        throughput = parse_throughput_file(throughput_file)

    return delay, jitter, throughput


def get_replicate_data(replicate_folder):
    runs = glob(f'{replicate_folder}/run*')
    runs.sort(key=lambda x: int(x.split('run')[-1]))
    data = []
    for run in runs:
        data.append(parse_data_for_run(run))

    return data

def get_responses(folder):
    replicates = glob(f'{folder}/replicate*')

    data = []
    for replicate in replicates:
        data.append(get_replicate_data(replicate))

    output_data = []
    count = 0

    for i in range(len(data[0])):
        # delay
        delay = mean([data[j][i][0] for j in range(3) if data[j][i][0] != -1])
        jitter = mean([data[j][i][1] for j in range(3) if data[j][i][1] != -1])
        throughput = mean([data[j][i][2] for j in range(3)])
        output_data.append((delay, jitter, throughput))

    return output_data

def output_to_file(responses, filename):
    output = []
    output.append(f'{len(responses)}\t\n')
    output.append('Delay\tJitter\tThroughput\n')
    for response in responses:
        output.append(f'{response[0]}\t{response[1]}\t{response[2]}\n')

    print(output)
    with open(filename, 'w') as f:
        f.writelines(output)


output_to_file(
    get_responses('/Users/danielkulenkamp/Documents/asu/research/thesis/data/thesis_screening/complete/'),
    '/Users/danielkulenkamp/Documents/asu/research/thesis/data/thesis_screening/complete_responses.txt'
)

output_to_file(
    get_responses('/Users/danielkulenkamp/Documents/asu/research/thesis/data/thesis_screening/line_copy/'),
    '/Users/danielkulenkamp/Documents/asu/research/thesis/data/thesis_screening/line_responses.txt'
)
