import os


executable_path = 'la-analysis/Search'
data_path = 'example_data/complete/'
LA_name = 'comp_la.tsv'
FD_name = 'comp_factors.tsv'
responses_folder = 'responses/'
output_folder = 'models/'
responses = " ".join(['Delay', 'Jitter', 'Throughput'])

os.system(
    f'python3 run_analysis.py {executable_path} {data_path} {LA_name} {FD_name} {responses_folder} {output_folder} {responses}'
)