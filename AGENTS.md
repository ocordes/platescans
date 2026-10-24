# AGENTS.md

Project rules and conventions for working in this repository.

## Project type

* This is a Python project.
* Python runs inside a virtual environment; activate it before running any Python, pip, or script commands.
* Install dependencies with `pip install -r requirements.txt`.
* All necessary packages must be listed in `requirements.txt` at the project root. If a script needs a new package, add it there.

## Scope

* Stay within this folder and its subfolders only. Do not read from, write to, or modify files outside of this project directory.

## Input data

* The input data lives in the `files/` folder.
* Never modify, move, rename, or delete the files in `files/`. Treat them as read-only inputs.

## Documentation

* All documentation should be stored in the `docs/` subfolder.
* Create the folder if it does not exist yet.

## Results

* All results should go in the `results/` subfolder.

## Project check scripts

* All project check scripts (linting, type checking, tests, validation, etc.) should be stored in the `pscripts/` subfolder.
