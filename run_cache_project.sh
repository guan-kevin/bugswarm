#!/usr/bin/env bash

# Get the absolute path to the directory containing this script. Source: https://stackoverflow.com/a/246128.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Include common functions and constants.
source "${SCRIPT_DIR}"/common.sh

TOTAL_STEPS=$((3))
# CacheDependency, MetadataPackager, ArtifactLogPackager.
STAGE='Cache Project'

USAGE='Usage: bash run_cache_project.sh [-r <repo-slug>] [-t <threads>] [-c <component-directory>] [-ca "<caching-args>"]'

# Extract command line arguments.
OPTS=$(getopt -o c:r:t:ca --long component-directory:,repo:,threads:,caching-args 'run-cache-project' -- "$@")
while true; do
    case "$1" in
      # Shift twice for options that take an argument.
      -c | --component-directory ) component_directory="$2"; shift; shift ;;
      -r | --repo                ) repo="$2";                shift; shift ;;
      -t | --threads             ) threads="$2";             shift; shift ;;
      -ca | --caching-args       ) caching_args="$2";        shift; shift ;;
      -- ) shift; break ;;
      *  ) break ;;
    esac
done

# Perform checks and set defaults for command line arguments.

if [ -z "${repo}" ]; then
    echo "${USAGE}"
    exit 1
fi

if [[ -z "${threads}" ]]; then
    echo 'The number of threads is not specified. Defaulting to 1 thread.'
    threads=1
fi

if [[ -z "${component_directory}" ]]; then
    component_directory="$SCRIPT_DIR"
fi

if [[ ${repo} != *"/"* ]]; then
    echo '[   ERROR] --- The repo slug must be in the form <username>/<project> (e.g. google/guice). Exiting.'
    exit 1
fi

# The task name is the repo slug after replacing slashes with hypens.
if [ ${repo} ]; then
    task_name="$(echo ${repo} | tr / -)"
fi

if [[ -z "${caching_args}" ]]; then
    caching_args=""
fi

reproducer_dir="${component_directory}"/reproducer
cache_dep_dir="${component_directory}"/cache-dependency

# Check for existence of the required repositories.
check_repo_exists ${reproducer_dir} 'reproducer'
check_repo_exists ${cache_dep_dir} 'cache-dependency'

print_step "${STAGE}" ${TOTAL_STEPS} 'CacheDependency'
cd ${reproducer_dir}
echo "[    INFO] --- Running: python3 get_reproducer_output.py -i output/result_json/$task_name.json -o $task_name"
python3 get_reproducer_output.py -i output/result_json/${task_name}.json -o ${task_name}
cd ${cache_dep_dir}

if [ ! -s ${reproducer_dir}/input/${task_name} ]; then
    echo "[   ERROR] --- ${reproducer_dir}/input/${task_name} does not exist, which should be created by get_reproducer_output.py."
    echo '[   ERROR] --- Either all reproducible artifacts have been cached, or there were no reproducible artifacts to begin with.'
    exit 1
fi

echo 'Attempting to cache the following artifacts:'
cat ${reproducer_dir}/input/${task_name}
echo "[    INFO] --- Running: python3 CacheMaven.py ${reproducer_dir}/input/${task_name} ${task_name} --workers ${threads} --task_json ${reproducer_dir}/output/result_json/${task_name}.json ${caching_args}"
python3 CacheMaven.py ${reproducer_dir}/input/${task_name} ${task_name} --workers ${threads} --task_json ${reproducer_dir}/output/result_json/${task_name}.json ${caching_args}
exit_if_failed 'CacheDependency encountered an error.'

# MetadataPackager (push artifact metadata to the database)
print_step "${STAGE}" ${TOTAL_STEPS} 'MetadataPackager'
cd ${reproducer_dir}
python3 packager.py -i output/result_json/${task_name}.json
exit_if_failed 'MetadataPackager encountered an error.'

print_step "${STAGE}" ${TOTAL_STEPS} 'ArtifactLogPackager'
python3 add_artifact_logs.py ${task_name}
exit_if_failed 'ArtifactLogPackager encountered an error.'

print_stage_done "${STAGE}"
