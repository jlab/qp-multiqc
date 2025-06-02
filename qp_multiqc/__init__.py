# -----------------------------------------------------------------------------
# Copyright (c) 2025, Tobias Gruetgen.
#
# Distributed under the terms of the BSD 3-clause License License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from qiita_client import QiitaPlugin, QiitaCommand

from .multiqc import run_multiqc

# TODO: include relevant imports here
# from .mycommand import my_command_function

# Initialize the plugin
plugin = QiitaPlugin(
    'multiqc', # name
    '0.0.1', # version 
    'Qiita Plugin: run multiqc for quality control of sequence data',) # description'

req_params = {'Demultiplexed sequences': ('artifact', ['Demultiplexed'])}
opt_params = {'Wordcloud width': ['integer', '400']}
outputs = {'MultiQC Report':'BIOM'} # output artifact type??? TODO: check this
dflt_param_set = {'Defaults': {'Wordcloud width': 400,}}

run_multiqc_cmd = QiitaCommand(
    'Run Multiqc',  # The command name
    'Generates MultiQC Reports from Fastq Sequences',  # The command description
    run_multiqc,  # function : callable
    req_params, # required parameters
    opt_params, # optional parameters
    outputs, # output Artifact 
    dflt_param_set) # default parameter set


plugin.register_command(run_multiqc_cmd)

# TODO: Define your commands. Here is an example on how to define one command.
# You can define as many as needed

# followed by the description of the API
# req_params = {'Input artifact': ('artifact', ['Demultiplexed']),
#               'Input integer': ('integer', 1000)}
# req_params is a dictionary defining the requried parameters of the command.
# "required" means that the user is forced to provide a value in the Qiita GUI
# The keys are the parameter names and the values are 2-tuples in which the
# first element of the tuple is the parameter  type and the second element
# is defined as:
#   If the parameter type is an artifact, then is a list with the accepted
#       artifact type
#   Otherwise is a default value for the parameter
#
# opt_params = {'Input parameter': ('string', 'Default')}
# opt_params is a dictionary defining the optional parameters of the command.
# "optional" means that the user is not forced to provide a value in the Qiita
# GUI and a default value will be used. The structure of the dictionary is the
# same as in "req_params"
#
# outputs = {'output 1': 'BIOM'}
# outputs is a dictionary defining the outputs of your command. The keys of the
# dictionary are the output names and the value are the artifact type. At this
# time, the command is forced to generate an artifact as an output. You can
# define as many key-value pairs in the dictionary as needed, but your command
# should ALWAYS generate all those outputs (i.e. optional outputs are currently
# not supported)
#
# dflt_param_set = {'Param Set 1': {'input_parameter': 'A value'}}
# dflt_param_set is a dictionary defining sets of default parameters for your
# command. In the processing pipeline, the user will only have access to this
# parameter set while in the analysis pipeline the user will be able to modify
# each individual parameter. This should be used to guide the user with
# recommended parameter set under different circumstances. The keys of the
# dictionary is the parameter set name, while the values is a dictionary in
# which keys are parameter names and values are the values for those parameters

# cmd = QiitaCommand("My Command", "My command does this", my_command_function,
#                    req_params, opt_params, outputs, dflt_param_set,
#                    analysis_only=True)
# This call defines a QiitaCommand object so it can be registered to the plugin
# The API of the QiitaCommand class is:
# QiitaCommand(COMMAND_NAME, COMMAND_SHORT_DESCRIPTION,
#              FUNCTION_EXECUTING_THE_COMMAND, REQUIRED_PARAMS,
#              OPTIONAL_PARAMS, OUTPUTS, DEFAULT_PARAMETER_SET, analysis_only)
# Where analysis only is a boolean indicating if the command should be made
# available only in the analysis pipeline or it can also be available in the
# study processing pipeline

