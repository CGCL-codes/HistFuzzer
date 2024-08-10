import subprocess
import os
import shutil
import random


def build_z3(commit, project_folder, sanitizer=False, jobs=1):
    try:
        # copy the folder to a new folder
        print("Building commit: " + commit)
        new_folder = project_folder + "_" + commit

        if os.path.exists(new_folder):
            return new_folder
        shutil.copytree(project_folder, new_folder)
        # checkout to the commit
        subprocess.run(["git", "checkout", commit], cwd=new_folder, check=True)
        command = f"python3 scripts/mk_make.py -d; cd build; make -j{jobs}"
        if sanitizer:
            command = f"CFLAGS+=\"-fsanitize=address -fsanitize-recover=address -U_FORTIFY_SOURCE -fno-omit-frame-pointer -fno-common\" CXXFLAGS+=\"-fsanitize=address -fsanitize-recover=address -U_FORTIFY_SOURCE -fno-omit-frame-pointer -fno-common\" LDFLAGS+=\"-fsanitize=address\" CC=clang CXX=clang++ {command}"
        
        build_process = subprocess.Popen(command, cwd=new_folder, shell=True, executable='/bin/bash')
        return new_folder
    except subprocess.CalledProcessError as e:
        if build_process.returncode != 0:
            print("Failed to build the project")
            return None


def build_cvc(commit, project_folder, sanitizer=False, jobs=1):
    try:
        # copy the folder to a new folder
        print("Building commit: " + commit)
        new_folder = project_folder + "_" + commit

        if os.path.exists(new_folder):
            return new_folder
        shutil.copytree(project_folder, new_folder)
        # checkout to the commit
        subprocess.run(["git", "checkout", commit], cwd=new_folder, check=True)
        command = f"./configure.sh debug --auto-download --assertions; cd build; make -j{jobs}"
        if sanitizer:
            command = f"./configure.sh debug --auto-download --asan --assertions; cd build; make -j{jobs}"

        build_process = subprocess.Popen(command, cwd=new_folder, shell=True, executable='/bin/bash')
        return new_folder

    except subprocess.CalledProcessError as e:
        if build_process.returncode != 0:
            print("Failed to build the project")
            return None
    

    

def test_commit(smt2_file, solver_path, message, timeout=10):
    # run the test, the command is "build/bin/z3 -smt2 -st -T:10 smt2_file"
    try:
        result = subprocess.run(f"timeout {timeout}s " + solver_path + " " + smt2_file + "> output.txt 2>&1", check=True, shell=True, executable='/bin/bash', stderr=subprocess.PIPE)
        # check the output
        stderr_output = result.stderr.decode('utf-8')
        with open("output.txt", 'r') as f:
            output = f.read()
        if message in output or message in stderr_output:
            if message.startswith("sat") and output.startswith("unsat"):
                return False
            return True
        else:
            return False
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            return True


def find_bug_inducing_commit(commits, project_folder, key_word, bug_file, solver):
    # Start the bisect process
    low = 0
    high = len(commits) - 1

    while low <= high:
        mid = (low + high) // 2
        new_folder = None
        # Checkout to the commit
        # subprocess.run(["git", "checkout", commits[mid]], check=True)
        while new_folder is None:
            if solver == "z3":
                new_folder = build_z3(commits[mid], project_folder=project_folder)
            elif solver == "cvc5" or solver == "cvc4":
                new_folder = build_cvc(commits[mid], project_folder=project_folder)
            if new_folder is None:
                mid = random.randint(low, high)
        if solver == "z3":
            solver_path = new_folder + "/build/z3"
        elif solver == "cvc5":
            solver_path = new_folder + "/build/bin/cvc5"
        # Build and test the commit
        if test_commit(bug_file, solver_path, key_word, timeout=10):
            # If the bug is present, the bug-inducing commit is in the right half
            low = mid + 1
        else:
            # If the bug is not present, the bug-inducing commit is in the left half
            high = mid - 1

    # The bug-inducing commit is the first commit in the right half
    bug_inducing_commit = commits[low] if low < len(commits) else None

    return bug_inducing_commit


def read_commit_file(commit_file):
    with open(commit_file, 'r') as f:
        commits = f.read().splitlines()
    # Split the commits into two parts: 30d1800c3 #6916
    commit_list = []
    for commit in commits:
        if commit != "":
            commit_list.append(commit.split(" ")[0])

    return commit_list


if __name__ == "__main__":
    # The file contains the commits to be tested
    commit_file = "/root/z3-ver/z3/commits.txt"
    # The folder of the project
    project_folder = "/root/z3-ver/z3"
    # The keyword in the output
    key_word = "AddressSanitizer"
    # The file to be tested
    bug_file = "/root/z3-ver/bug.smt2"
    commits = read_commit_file(commit_file)
    # remove items after the specified commit
    commits = commits[commits.index("76f9e1d2b"):commits.index("e2db2b864")]
    print(commits)


    bug_inducing_commit = find_bug_inducing_commit(commits, project_folder, key_word, bug_file)
    print(bug_inducing_commit)