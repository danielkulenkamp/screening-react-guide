
import subprocess
from collections import defaultdict
import argparse

parser = argparse.ArgumentParser(description='Run LA analysis code automatically and determine the possible best model based on relative change in R squared between the last and current model.')
parser.add_argument('executable', metavar='executable_path', type=str, help='Path to LA analysis executable (Search)')
parser.add_argument('data_path', metavar='data_path', type=str, help='Path to the folder containing the locating array, the factor data file, the responses folder, and the output folder. ')
parser.add_argument('LA_name', metavar='LA_name', type=str, help='Name of the locating array file (ends in .tsv)')
parser.add_argument('FD_name', metavar='FD_name', type=str, help='Name of the factor data file (ends in .tsv and must match LA file)')
parser.add_argument('responses_folder', metavar='responses_folder', type=str, help='Name of the folder containing the response files')
parser.add_argument('output_folder', metavar='output_folder', type=str, help='Name of the folder where the models will be saved')
parser.add_argument('responses', metavar='responses', type=str, nargs='+', help='List of response columns in the response folder')
parser.add_argument('--threshold', default='0.01', type=float)
parser.add_argument('--min_num_terms', default='2', type=int)
parser.add_argument('--max_num_terms', default='10', type=int)
parser.add_argument('--num_models', default='50', type=int)
parser.add_argument('--num_new_models', default='50', type=int)
parser.add_argument('--debug', action="store_true", help='Run the LA analysis tool in debug mode')

args = parser.parse_args()

executable_path = args.executable
data_path = args.data_path
LA_path = data_path + args.LA_name
FD_path = data_path + args.FD_name
responses_path = data_path + args.responses_folder + '/'
output_path = data_path + args.output_folder + '/'
responses = args.responses
r_squared_threshold = args.threshold
debug = args.debug

def get_model(response, num_terms):
    global executable_path, LA_path, FD_path, responses_path, debug, num_models, num_new_models
    output = subprocess.check_output([executable_path, LA_path, FD_path, 'analysis',  responses_path, f'{response}', f'{1 if debug else 0}', f'{num_terms}', f'{num_models}', f'{num_new_models}'])
    s = output.decode('utf-8').split('Final Models Ranking: ')[1]
    model = s.split('Model 2')[0]

    occurrence_counts = output.decode('utf-8').split('Occurrence Counts')[1]

    r_squared = model.split('(')[1].split(')')[0]
    print(r_squared)
    d = {
        'num_terms': num_terms,
        'top_model': model,
        'occurrence_counts': occurrence_counts,
        'r_squared': float(r_squared),
    }
    return d


models = defaultdict(list)
min_num_terms = args.min_num_terms
max_num_terms = args.max_num_terms
num_models = args.num_models
num_new_models = args.num_new_models

for response in responses:
    print(f'Response: {response}')
    print('-'*20)
    last_r_squared = 0
    best_model = None
    best_model_index = None
    for i in range(min_num_terms, max_num_terms+1):
        print(f'Num_terms: {i}, R squared: ', end='')
        new_model = get_model(response, i)
        models[response].append( new_model )
        if new_model['r_squared'] - last_r_squared < r_squared_threshold:
            print(f'Best model probably: {best_model_index} terms')
        else:
            best_model = models[response][-1]
            best_model_index = i
        last_r_squared = new_model['r_squared']
            
    print('\n\n')

    with open(f'{output_path}/{response}.txt', 'w') as f:
        f.write(f'Response: {response}\n')
        f.write(f'Num_models: {num_models}, num_new_models: {num_new_models}\n')
        f.write(f'R squared threshold: {r_squared_threshold}, min_num_terms: {min_num_terms}, max_num_terms: {max_num_terms}\n\n')
        f.write(f'Best model: {best_model["num_terms"]} terms\n')
        f.write(f'{best_model["top_model"]}\n')
        f.write('Occurence Counts: \n')
        f.write(f'{best_model["occurrence_counts"]}\n\n')

        f.write('-'*110)
        f.write('\n')
        f.write('-'*110)
        f.write('\n\n')
        f.write('Other models: \n\n')

        for index in range(len(models[response])):
            f.write(f'Num terms: {models[response][index]["num_terms"]}\n')
            f.write(f'{models[response][index]["top_model"]}\n')
            f.write('Occurrence Counts: \n')
            f.write(f'{models[response][index]["occurrence_counts"]}\n\n')

            f.write('-'*110)
            f.write('\n')




