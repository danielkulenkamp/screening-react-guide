# Screening Experiments with REACT

## Getting Started


### Prerequisites

This user guide is designed to be used with the wilab-2 testbed, with the ZOTAC type nodes. It is likely possible to run the code elsewhere, but has not yet been tested. Additionally, the driver extension used to enable precise tuning of 802.11's contention window is made for the ath9k driver. 

Requirements:
- wilab-2
- ZOTAC type nodes
- ath9k driver
- Ubuntu 16.04

The first thing to do is to swap in some nodes on wilab. The two screening experiments included here require a complete topology of four nodes, or a line topology of four nodes. This guide will focus on the complete topology experiment, because it is easier to find a complete topology. 

Once the nodes are swapped in, we will need to install the dependencies. Python 3 is required (3.9.0 was used in development and testing, although a lower version probably works). The following command will install all of the necessary Python dependencies:

pip3 install fabric netifaces scapy numpy patchwork

Once the python dependencies are installed, the driver extension to enable REACT needs to be compiled. From the GitHub repo folder, execute the following:

cd driver-extension
make

We use the Fabric framework to orchestrate the experiments. Fabric requires a "fabfile" to know what commands to run from the command line utility. All of the commands for running the screening experiment can be found in fabfile.py inside the top-level directory of this repo. The file uses a host file, called "node_info.txt", which contains the hosts, drivers, and tx_power levels for the nodes. This file needs to be present in order for calls to fab to work properly. We provide an example of such a file in "node_info.txt.tmpl", which will need to be renamed to "node_info.txt" and updated with the proper nodes and tx_power levels required for the desired topology. 

Once we have the "node_info.txt" file set up, we can run the setup from fabric. From the repo folder, execute this command, to set up the nodes using Fabric:

fab setup

This command will set up the wireless interfaces on each of the nodes, assign IP addresses, time synchronize the nodes, and load the kernel extension. It's important to only run setup once, as running it multiple times may cause issues with the interfaces. If you run into issues or reboot nodes, it will be need to run again. 

After running setup, we are ready to run the screening experiments. The way the experiments are set up to run ensures that the run order is randomized, and that if an issue interrupts the execution of an experiment, we don't have to re-run all tests. To manage this, the rows from the locating array are converted to a python list in memory, which is then saved as a Python pickle file at the end of each test. In this way, we could individually run each line without losing our place, or use a script to run it automatically for us. In our case, we chose to write a simple shell script to manage this for us. Before we can run the shell script, we must set up the pickle file. For this, run the following command: 

fab set-LA-file

Now, we can start running the screening experiment. For this, ensure that the "run_screening.sh" script is executable: 

chmod +x run_screening.sh

And then execute it:

./run_screening.sh

The experiments can also be run line by line by using the following command:

fab run-screening-one

At any time after running experiments line-by-line, the automation can be re-started by just running the run_screening.sh script. 

The experiments will take at least a few hours to complete. Typically it is necessary to run a few replicates, say three, to ensure that data is collected for all tests and nodes. Occassionally data won't report for some nodes so this is a necessary precaution. 

Once three replicates have been run, we need to average the data into one set of responses. For this, we can use utils/screening_data.py. Make sure to update the paths at the end of the file to the correct paths for your data generated. Once that's updated, run this command:

python3 utils/screening_data.py

This will generate one set of responses for our screening experiment. Once the responses are generated, we are ready to run the analysis. 

