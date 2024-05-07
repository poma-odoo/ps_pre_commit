#!/usr/bin/env python3
from collections import defaultdict
import pathlib
import re
import subprocess
import sys


def get_changed_modules():
    """
    Returns the names of modules that have been changed in the commit based on the staged changes.
    :return: A set of strings representing the names of changed modules.
    """
    files = subprocess.check_output(["git", "diff-index", "--cached", "--name-only", "HEAD"], text=True).splitlines()

    folders = set(pathlib.Path(file).parent for file in files)
    return set(folder.name for folder in folders if (folder / "__manifest__.py").exists())


def get_commit_msg():
    """
    Retrieves the commit message from the file specified in the command line arguments and returns it.
    :return: The commit message as a multiline string.
    """
    with open(sys.argv[1]) as f:
        commit_msg = f.read()
    return commit_msg

def get_branch_name():
    """
    Retrieves the name of the current branch.
    :return: The name of the current branch
    """
    return subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()

def get_task_id_from_branch(branch):
    """
    Retrieves the task ID from the branch name.
    :param str branch: The name of the branch
    :return: The task ID as a string or an empty string
    """
    res = re.search(r"([_-](\d+)[_-])", branch)
    if not res:
        return ""
    return res.group(1)

def parse_commit_msg(commit_msg):
    """
    Parses the commit message and returns a dictionary of the parsed information.

    It looks only on the first line of the commit message and for a predetermined pattern, defined here
    https://github.com/odoo-ps/psbe-process/wiki/Commits-message-guidelines#template
    as:
    [TYPE_OF_CHANGE][TASK_ID] custom_module_name: brief description of the change
    custom_module_name is optional and not returned as it will be defined in this script
    
    :param str commit_msg: The commit message to parse 
    :return: A dictionary of the parsed information or None if the message could not be parsed
    """
    res = re.search(r"^\[(?P<type>\w+)\]\s*(?P<task_id>\[\d+\])\]?\s*(?:[a-zA-Z0-9,_ -]*:)?(?P<msg>.*)", commit_msg)
    if not res:
        return None
    res = res.groupdict()
    if res.get("task_id"):
        res["task_id"] = res.task_id.strip("[] ")
    if not res.get("task_id"):  # if there is no task id or the task id is empty
        task_id = get_task_id_from_branch(get_branch_name())
        if not task_id:
            return None
        res["task_id"] = task_id
    res["type"] = res["type"].strip().upper()

    return res.groupdict()


def group_modules(changed_modules, sep="_"):
    """
    Generate a grouped list of modules based on their prefixes, separated by the separator.
    If the grouped list is too big, it will be split into multiple subgroups.

    The logic is as follows:
    - If a prefix contains only one module, add it directly to the list.
    - If it has three or fewer modules, add it to the list as prefix_{rest1,rest2,...}.
    - If it has more than three modules, try to split it into subgroups.
    - If there are more than 3 subgroups, add it to the list as prefix_sep_*.
    - Otherwise, apply the same logic to the subgroups.

    :param changed_modules: A list of module names
    :param sep: The separator to use

    :return: A list of module names grouped by their prefixes

    >>> group_modules(['custom_module_a', 'custom_module_b', 'custom_module_c'])
    ['custom_{module_a, module_b, module_c}']
    >>> group_modules(['custom_module_a', 'custom_module_b', 'custom_module_c', 'custom_module_d'])
    ['custom_module_{*}']
    """
    grouped_modules = []
    modules_by_prefix = defaultdict(list)

    for module in changed_modules:
        prefix = module.split(sep)[0]
        modules_by_prefix[prefix].append(module)

    for prefix, modules in modules_by_prefix.items():
        if len(modules) == 1:
            grouped_modules.extend(modules)
        elif len(modules) <= 3:
            grouped_modules.append(f"{prefix}_{{{','.join(modules)}}}")
        else:
            sub_groups = defaultdict(list)
            for module in modules:
                sub_prefix = sep.join(module.split(sep)[:2])
                sub_groups[sub_prefix].append(module)

            if len(sub_groups) > 3:
                grouped_modules.append(f"{prefix}{sep}*")
            else:
                for sub_prefix, sub_modules in sub_groups.items():
                    if len(sub_modules) == 1:
                        grouped_modules.extend(sub_modules)
                    elif len(sub_modules) <= 3:
                        grouped_modules.append(f"{sub_prefix}{sep}{{{','.join(sub_modules)}}}")
                    else:
                        grouped_modules.append(f"{sub_prefix}{sep}*")

    return grouped_modules


def main():
    commit_msg_list = get_commit_msg().splitlines()
    message_head = commit_msg_list[0]
    message_body = "\n".join(commit_msg_list[1:])
    if message_body[:1] != ["\n"]:
        message_body = "\n" + message_body

    parsed_msg = parse_commit_msg(message_head)
    if not parsed_msg:
        print(f"Failed to parse commit message: {message_head}")
        exit(1)
    changed_modules = get_changed_modules(message_head)
    if len(changed_modules) == 0:
        print("No changed modules found")
        exit(0)
    if len(changed_modules) <= 3:
        new_head = (
            f"[{parsed_msg['type']}][{parsed_msg['task_id']}] " f"{', '.join(changed_modules)}: {parsed_msg['msg']}"
        )
    else:
        # try to group modules
        new_head = (
            f"[{parsed_msg['type']}][{parsed_msg['task_id']}] "
            f"{', '.join(group_modules(changed_modules))}: {parsed_msg['msg']}"
        )
    new_message = f"{new_head}\n{message_body}"
    with open(sys.argv[1], "w") as f:
        f.write(new_message)


if __name__ == "__main__":
    main()
