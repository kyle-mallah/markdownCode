# gets the features of the services.
# before running this, run get_if_component_is_used.py to check if a service is used. 
# this gives better results in 3.5
import sys
from time import sleep
from constants import get_model_config, DEFAULT_MAX_TOKENS, OPENAI_API_KEY
import project
import declare_or_use_comp_classifier
import get_if_component_is_used
import json
import result_loader

import openai
import tiktoken

ONLY_MISSING = False # only check if the fragment has not yet been processed

system_prompt = """Act as an ai software analyst.
It is your task to find features in the source text that are related to a specific component.

list the features in the source text related to "{0}". For each feature, provide the name of the function or property that the component needs to provide together with a detailed description of what the function or property should do.

ex: 
Feature: The user can select a model from a dropdownbox where the list of models is provided by the service.
function: getModels
description: getModels will retrieve a list of all the models that are currently available. 

Do not include any introduction, explanation comments or notes.
return the results as a json structure. If no results are found, return an empty array."""
user_prompt = """source text:
{0}"""
term_prompt = """Remember: only include features related to '{0}' and return an empty array if nothing is found.

good response:
[
  {{
    "feature": "x",
    "function": "y",
    "description": "z"
  }},
{{
    "feature": "x",
    "property": "y",
    "description": "z"
  }}
]

good response:
[]
 
bad response:
```json
[
  {{
    "feature": "x",
    "function": "y",
    "description": "z"
  }}
]
```
"""


def generate_response(params, key):

    total_tokens = 0
    model = get_model_config('list_component_expansions', key)
    
    def reportTokens(prompt):
        encoding = tiktoken.encoding_for_model(model)
        # print number of tokens in light gray, with first 10 characters of prompt in green
        token_len = len(encoding.encode(prompt))
        print(
            "\033[37m"
            + str(token_len)
            + " tokens\033[0m"
            + " in prompt: "
            + "\033[92m"
            + prompt
            + "\033[0m"
        )
        return token_len

    # Set up your OpenAI API credentials
    openai.api_key = OPENAI_API_KEY

    messages = []
    prompt = system_prompt.format(params['class_name'] )
    messages.append({"role": "system", "content": prompt})
    total_tokens += reportTokens(prompt)
    prompt = user_prompt.format(params['feature_description'])
    messages.append({"role": "user", "content": prompt})
    total_tokens += reportTokens(prompt)
    if term_prompt:
        prompt = term_prompt.format(params['class_name'])
        messages.append({"role": "assistant", "content": prompt})
        total_tokens += reportTokens(prompt)
    
    total_tokens *= 2  # max result can be as long as the input, also need to include the input itself
    if total_tokens > DEFAULT_MAX_TOKENS:
        total_tokens = DEFAULT_MAX_TOKENS
    params = {
        "model": model,
        "messages": messages,
        "max_tokens": total_tokens,
        "temperature": 0,
    }

    # Send the API request
    keep_trying = True
    response = None
    while keep_trying:
        try:
            response = openai.ChatCompletion.create(**params)
            keep_trying = False
        except Exception as e:
            # e.g. when the API is too busy, we don't want to fail everything
            print("Failed to generate response (retrying in 30 sec). Error: ", e)
            sleep(30)
            print("Retrying...")

    # Get the reply from the API response
    if response:
        reply = response.choices[0]["message"]["content"] # type: ignore
        return reply
    return None


def add_result(to_add, result, writer):
    result.append(to_add)
    writer.write(to_add + "\n")
    writer.flush()


def collect_response(title, response, result, writer):
    # get the first line in the component without the ## and the #
    add_result(f'# {title}', result, writer)
    add_result(response, result, writer)


def process_data(writer):
    result = []

    for to_check in project.fragments[2:]:  # skip the first two fragments cause that's the description and dev stack
        if to_check.content == '':
            continue
        if ONLY_MISSING and has_fragment(to_check.full_title):
            continue
        results = {}
        for check_against in declare_or_use_comp_classifier.text_fragments:
            if check_against.content == '':
                continue
            if check_against.title == to_check.title:
                continue
            components = check_against.data
            if not components:
                continue
            fragment_results = {}
            for comp_name, value in components.items():
                if value == 'declare':
                    comp_used = get_if_component_is_used.is_used(to_check.full_title, check_against.title, comp_name)
                    if not comp_used:
                        continue
                    params = {
                        'class_name': comp_name,
                        'feature_description': to_check.content,
                    }
                    response = generate_response(params, to_check.full_title)
                    if response:
                        try:
                            response = json.loads(response)
                            fragment_results[comp_name] = response
                        except Exception as e:
                            print("Failed to parse response: ", e)
                            print("Response: ", response)
            if fragment_results:
                results[check_against.title] = fragment_results
        if results:
            collect_response(to_check.full_title, json.dumps(results), result, writer)
    return result
                    


def main(prompt, class_list, is_used, file=None):
    # read file from prompt if it ends in a .md filetype
    if prompt.endswith(".md"):
        with open(prompt, "r") as promptfile:
            prompt = promptfile.read()

    print("loading project")

    # split the prompt into a toolbar, list of components and a list of services, based on the markdown headers
    project.split_standard(prompt)
    declare_or_use_comp_classifier.load_results(class_list)
    get_if_component_is_used.load_results(is_used)

    print("rendering results")

    if file is None:
        file = 'output'

    file_name = file + "_component_expansion.md"
    open_mode = 'w'
    if ONLY_MISSING:
        load_results(file_name)
        open_mode = 'a'

    # save there result to a file while rendering.
    with open(file_name, open_mode) as writer:
        process_data(writer)
    
    print("done! check out the output file for the results!")


text_fragments = []  # the list of text fragments representing all the results that were rendered.

def load_results(filename, overwrite_file_name=None):
    if not overwrite_file_name:
        # modify the filename so that the filename without extension ends on _overwrite
        overwrite_file_name = filename.split('.')[0] + '_overwrite.' + filename.split('.')[1]
    result_loader.load(filename, text_fragments, True, overwrite_file_name)


def get_data(title):
    '''returns the list of components for the given title'''
    to_search = title.strip()
    if not to_search.startswith('# '):
        to_search = '# ' + to_search
    for fragment in text_fragments:
        if fragment.title == to_search:
            return fragment.data or []
    return []   

def has_fragment(title):
    '''returns true if the title is in the list of fragments'''
    to_search = title.strip()
    if not to_search.startswith('# '):
        to_search = '# ' + to_search
    for fragment in text_fragments:
        if fragment.title == to_search:
            return True
    return False


def get_all_expansions_for(name):
    '''returns a list of all the expansions for the given component name'''
    result = []
    for fragment in text_fragments:
        for title, components in fragment.data.items():
            if name in components:
                result.append(components[name])
    return result

if __name__ == "__main__":

    # Check for arguments
    if len(sys.argv) < 4:
        print("Please provide a prompt")
        sys.exit(1)
    else:
        # Set prompt to the first argument
        prompt = sys.argv[1]
        class_list = sys.argv[2]
        is_used = sys.argv[3]

    # Pull everything else as normal
    file = sys.argv[4] if len(sys.argv) > 4 else None

    # Run the main function
    main(prompt, class_list, is_used, file)