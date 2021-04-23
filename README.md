# Screening Experiments with REACT

This repository contains the necessary code to perform a locating array-based screening experiment on the w.iLab-t wireless testbed using the new REACT<sub>QoS</sub> MAC protocol. The two experiments described here first appeared in [1]. 

## Getting Started

### Introduction

Screening experiments are an important first step in determining which factors should be included in implementation, and which ones can be safely eliminated from consideration. Locating array based screening experiments use the properties of locating arrays to reduce the number of tests needed to discover influential factors and 2-way interactions with many less tests than other traditional methods. 

This guide provides a guide to reproducing the experiments conducted in [1]. 

### Prerequisites

This user guide is designed to be used with the w.iLab.t-2 testbed. The Zotac type nodes were used, and though it is likely possible to run the code elsewhere or using different node types, this guide focuses on this specific hardware. Additionally, the driver extension used to enable precise tuning of 802.11's contention window is made for the ath9k driver

Requirements:
- w.iLab.t-2 testbed
- at least 4 ZOTAC type nodes
- `ath9k` driver
- Ubuntu 16.04 installed on the nodes

The first thing to do is to swap in some nodes on wilab. For more detailed instructions on how to swap in nodes, please refer to the w.iLab.t documentation [here](https://doc.ilabt.imec.be/ilabt/wilab/getting_started.html "here"). The two screening experiments included here require a complete topology of four nodes, or a line topology of four nodes. This guide will focus on the complete topology experiment, because it is easier to find a complete topology. 

### Setting Up the Nodes

Once the nodes are swapped in, we will need to install the dependencies. Python 3 is required (3.9.0 was used in development and testing, although a lower version probably works). The following command will install all of the necessary Python dependencies:

	pip3 install fabric netifaces scapy numpy patchwork

Once the python dependencies are installed, the driver extension to enable REACT needs to be compiled. From the GitHub repo folder, execute the following:

	cd driver-extension
	make

#### Fabric
We use the Fabric framework to orchestrate the experiments. Fabric requires a "fabfile" to know what commands to run from the command line utility. All of the commands for running the screening experiment can be found in fabfile.py inside the top-level directory of this repo. 

There are four lines that need to be changed inside `fabfile.py` in order to work with the swapped in nodes and user. They are shown below and are lines 33-43 in `fabfile.py'. 

	# Change these parameters to the necessary values
	USERNAME = 'USERNAME'

	# Path to where the GitHub repository is stored
	PROJECT_PATH = '/groups/wall2-ilabt-iminds-be/WILAB-PROJECT/react80211'

	# Path to where you want to save the data
	DATA_PATH = '/groups/wall2-ilabt-iminds-be/WILAB_PROJECT/data/'

	# Path to the Python binary (has been tested with 3.9.x, lower versions may work)
	PYTHON_PATH = '/groups/wall2-ilabt-iminds-be/WILAB_PROJECT/pyenv/versions/3.9.0/bin/python'


The file uses a host file, called `node_info.txt`, which contains the hosts, drivers, and `tx_power` levels for the nodes. This file needs to be present in order for calls to fab to work properly. We provide an example of such a file in `node_info.txt.tmpl`, which will need to be renamed to `node_info.txt` and updated with the proper nodes and `tx_power` levels required for the desired topology. Please add the specific nodes you have reserved here, as fabric needs to know which hosts to run commands on. 

Once we have the `node_info.txt` file set up, we can run the setup from fabric. From the repo folder, execute this command, to set up the nodes using Fabric:

	fab setup

This command will set up the wireless interfaces on each of the nodes, assign IP addresses, time synchronize the nodes, and load the kernel extension. It's important to only run setup once, as running it multiple times may cause issues with the interfaces. If you run into issues or reboot nodes, it will be need to run again. 

### Setting Up the Screening Experiment

After running setup, we are ready to run the screening experiments. The way the experiments are set up to run ensures that the run order is randomized, and that if an issue interrupts the execution of an experiment, we don't have to re-run all tests. To manage this, the rows from the locating array are converted to a python list in memory, which is then saved as a Python pickle file at the end of each test. In this way, we can individually run each line without losing our place, or use a script to run it automatically for us. In our case, we supply a simple shell script to manage this for us. Before we can run the shell script, we must set up the pickle file. For this, run the following command: 

	fab set-LA-file

Now, we can start running the screening experiment. For this, ensure that the `run_screening.sh` script is executable: 

	chmod +x run_screening.sh

And then execute it:

	./run_screening.sh

The experiments can also be run line by line by using the following command:

	fab run-screening-one

At any time after running experiments line-by-line, the automation can be re-started by just running the `run_screening.sh` script. 

The experiments will take at least a few hours to complete. Typically it is necessary to run a few replicates, say three, to ensure that data is collected for all tests and nodes. Occassionally nodes won't report data for some runs so this is a necessary precaution. 

### Processing Data from Replicates
Once three replicates have been run, we need to average the data into one set of responses. For this, we can use `utils/screening_data.py`. Make sure to update the paths at the end of the file to the correct paths for your data generated. Once that's updated, run this command:

	python3 utils/screening_data.py

This will generate one set of responses for our screening experiment. Once the responses are generated, we are ready to run the analysis. 

### Running Analysis

This repository includes the analysis tool for locating array based screening experiments. The tool has several configurable parameters that can be used to affect the model generated. To compile the tool, navigate to the `la-analysis/` folder and run `make`. 

	cd la-analysis
	make

To simplify the use of the analysis tool, we include a `run_analysis.py` script that will automatically generate models with successively increasing number of terms (up to a user specified value), and then select the best one based on when the R-squared for the new model is less than some user-specified value. We also include an `example_run_analysis.py` script that gives an example of how to pass in the parameters for the analysis script. To run the example analysis, simply run:

	python3 example_run_analysis.py

For non-example data, the `run_analysis.py` script takes in 7 required parameters. They are described below:

- `executable_path`: This is the path to the analysis executable. If compiled directly in the repository, it is simply `"la-analysis/Search"`
- `data_path`: This is the path to the folder containing the locating array and factor data, the output folder, and the responses folder. 
- `LA_name`: This is the name of the locating array, without any path preceding it (assuming it is inside the data path folder)
- `FD_name`: This is the name of the factor data file, again without any path preceding it
- `responses_folder`: This is the path to the folder containing the response files, which in the example data here is called `"responses/"`
- `output_folder`: This is the path to the output folder where the model output will go, which in the example data is called `"models/"`
- `responses`: This is one or more column names from the response output file. In this case, we will pass in `Delay Jitter Throughput`, so the analysis will be run for each of the three responses in the response file. 

So, to run the analysis on the example data, we could run the following command for the complete topology:

	python3 run_analysis.py la-analysis/Search example_data/complete/ comp_la.tsv comp_factors.tsv responses/ models/ Delay Jitter Throughput

For more information on how to run the analysis tool directly, without using the helper script, please refer to the command line output or to the README of an earlier version of the analysis here: https://github.com/sseidel16/v4-la-tools.

## References
[1] D. J. Kulenkamp, "Extending REACT to Support Quality of Service: Algorithms and Implementation, With Screening and Performance Experiments on a Wireless Testbed," Master's Thesis, 2021. 

[2] Y. Akhtar, F. Zhang, C. J. Colbourn, J. Stufken, and V. R. Syrotiuk, “Scalable level-wise screening using locating arrays,” Unpublished manuscript, October 2020.


