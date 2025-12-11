# PoliFlow Extractor

This repository contains two implementations of the PolifFlow Extractor: one for the CNCF Serverless Workflow v0.8 and another for the PoliFlow Language.

## Extractor for the CNCF Serverless Workflow

This Extractor is stored within the `serverless-workflow/src/` directory.
After installing the requirements (from the `requirements.txt` file), it can be executed using the following command:
```
python main.py -w [path to workflow file] -s [paths to the subflows files (if there are any)]
```

Using this command, the user can specify the source file with the workflow descriptor and the files with the subflows descriptors (if there are multiple, these must be separated with a space; if there are no subflows, the user does not need to provide the `-s` flag).

The extracted allowed paths are saved in the directory `serverless-workflow/src/extracted/` in a new directory with the name of the workflow file (without the extension).
For example, if the workflow file is `application.sw.yaml`, the allowed paths will be saved in `serverless-workflow/src/extracted/application/`.
In this directory, the Extractor will create multiple JSON and YAML files, each pair for each entity (function, event, callback) present in the workflow.
The JSON file content can then be used for the PoliFlow Enforcer.
The YAML file has the same constructs as the corresponding JSON file but allows the user to more easily understand the paths extracted.

Furthermore, we also give the possibility of using the `-d` flag. If it is set, the Extractor will consider loop iterations as being dependent on the previous ones.
However, by default (if the flag is not provided), the loop iterations are considered independent, which is the default behavior of the CNCF Serverless Workflow v0.8.

The directory `serverless-workflow/test-workflows/` stores multiple examples of serverless workflows.
These were already extracted, and the allowed paths are saved in `serverless-workflow/src/extracted/`.
Nevertheless, an example of using the Extractor with one of these workflows is:
```
python main.py -w ../test-workflows/loop.sw.yaml -s ../test-workflows/subloop.sw.yaml
```

### Note

The requirements in `requirements.txt` might not be enough.
This Extractor script uses the most up to date development version of the [CNCF Serverless Workflow Python SDK](https://github.com/serverlessworkflow/sdk-python) at the date of writing (commit `ab7b6d4d6998be2add8af7494faadd2bb16d1e94`).


## Extractor for the PoliFlow Language

The second Extractor implementation in this repository is for the PoliFlow Language.
In this implementation, we considered that it would be used for direct-call-based applications, i.e., applications where functions call other functions or services directly (without relying on workflows or events).
Therefore, it outputs both rules for inbound and outbound calls.

This implementation is stored in the `poliflow-language/src/` directory.
As with the other Extractor, the requirements are stored in the `requirements.txt` file.
However, it also requires the PoliFlow language package to be installed.
The easiest way of doing so is to clone that repository locally and then, in the virtual environment of the Extractor, run:
```
pip install [directory to the cloned PoliFlow language repository]
```

Then, the Extractor can be run with the following command:

```
python main -w [path to workflow file]
```

Then, as with the previous Extractor, it saves the allowed paths in YAML and JSON files within the `poliflow-language/src/extracted/` directory, under a directory with the workflow file name.
