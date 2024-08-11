import subprocess
import os
import shutil
import random
import argparse


def build_project(commit, project_folder, solver, sanitizer=False, jobs=1):
    try:
        print(f"Building commit: {commit}")
        new_folder = f"{project_folder}_{commit}"

        if os.path.exists(new_folder):
            subprocess.run("find . -mindepth 1 -not -path \"./build*\" -delete", cwd=new_folder, shell=True)
            return new_folder

        shutil.copytree(project_folder, new_folder)
        subprocess.run(["git", "checkout", commit], cwd=new_folder, check=True)

        if solver == "z3":
            command = f"python3 scripts/mk_make.py -d && cd build && make -j{jobs}"
        elif solver in ["cvc5", "cvc4"]:
            command = f"./configure.sh debug --auto-download --assertions && cd build && make -j{jobs}"

        if sanitizer:
            if solver == "z3":
                command = f'CFLAGS+="-fsanitize=address -fsanitize-recover=address -U_FORTIFY_SOURCE -fno-omit-frame-pointer -fno-common" ' \
                          f'CXXFLAGS+="-fsanitize=address -fsanitize-recover=address -U_FORTIFY_SOURCE -fno-omit-frame-pointer -fno-common" ' \
                          f'LDFLAGS+="-fsanitize=address" CC=clang CXX=clang++ {command}'
            else:
                command = command.replace("--assertions", "--asan --assertions")
        # hide the output
        build_process = subprocess.Popen(command, cwd=new_folder, shell=True, executable='/bin/bash',
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        build_process.communicate()  # Wait for the build to finish

        # remove source code to save space. Use "find . -mindepth 1 -not -path "./build*" -delete"
        # to remove all files except the build folder
        subprocess.run("find . -mindepth 1 -not -path \"./build*\" -delete", cwd=new_folder, shell=True)

        return new_folder

    except subprocess.CalledProcessError as e:
        print(f"Failed to build the project: {e}")
        return None


def test_commit(smt2_file, solver_path, message, timeout=10):
    try:
        result = subprocess.run(
            f"timeout {timeout}s {solver_path} {smt2_file}",
            check=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        output = result.stdout.decode('utf-8') + result.stderr.decode('utf-8')
        # The bug is found in the commit if the message is in the output
        print(f"Output: {output}")
        return message in output and not (message.startswith("sat") and output.startswith("unsat"))

    except subprocess.CalledProcessError:
        print("Failed to run the solver")
        return None


def find_commit(commits, project_folder, key_word, bug_file, solver, commit_type):
    """
    This function finds the commit by binary search.
    If you want to find the first commit that induces the bug, it means the bug does not exist in the previous commits but exists in the current commit.
    If you want to find the commit that fixes the bug, it means the bug exists in the previous commits but does not exist in the current commit.
    """
    low, high = 0, len(commits) - 1

    while low <= high:
        print(f"Low: {low}, High: {high}")
        mid = (low + high) // 2
        print(f"Mid: {mid}")
        new_folder = None

        while new_folder is None:
            new_folder = build_project(commits[mid], project_folder, solver, jobs=24)
            if new_folder is None:
                mid = random.randint(low, high)
        solver_path = os.path.join(new_folder, "build")
        if solver == "z3":
            solver_path = solver_path + "/z3" 
        elif solver == "cvc5":
            solver_path = solver_path + "/bin/cvc5"
        # solver_path = os.path.join(new_folder, "build", "z3" if solver == "z3" else "bin", "cvc5" if solver == "cvc5" else "")
        print(f"Solver path: {solver_path}")

        solver_result = test_commit(bug_file, solver_path, key_word)
        if solver_result is None:
            print(f"Failed to test the commit: {commits[mid]}")
            print(f"The range of the commits is from {commits[low]} to {commits[high]}")
            print("Please check the commit manually")
            return None
        if commit_type == "inducing":
            if solver_result:
                print(f"Found the bug in commit: {commits[mid]}")
                low = mid + 1
            else:
                print(f"No bug in commit: {commits[mid]}")
                high = mid - 1
        elif commit_type == "fixing":
            if solver_result:
                high = mid - 1
            else:
                low = mid + 1

    return commits[low] if low < len(commits) else None


def read_commit_file(commit_file):
    with open(commit_file, 'r') as f:
        commits = [line.split()[0] for line in f if line.strip()]
    return commits


def main(commit_file, target_project, message, test_file, commit_type, start_commit=None, end_commit=None):
    if not os.path.exists(target_project):
        print("Cloning the project")
        subprocess.run(
            ["git", "clone", f"https://github.com/{'Z3Prover/z3' if target_project == 'z3' else 'cvc5/cvc5'}.git"]
        )
        if not os.path.exists(target_project):
            print("Failed to clone the project")
            return

    if not os.path.exists(commit_file):
        commit_file = os.path.join(target_project, "commits.txt")
        subprocess.run("git log --oneline --abbrev=7 > commits.txt", cwd=target_project, executable='/bin/bash', shell=True)
        if not os.path.exists(commit_file):
            print("Failed to get the commit file")
            return 

    commits = read_commit_file(commit_file)

    start_index = commits.index(start_commit) if start_commit else len(commits)
    end_index = commits.index(end_commit) + 1 if end_commit else 0
    print(f"Searching from {start_index} to {end_index}")
    commits = commits[end_index:start_index]
    # time.sleep(5)

    interesting_commit = find_commit(commits, target_project, message, test_file, target_project, commit_type)
    if interesting_commit is None:
        print("Failed to find the interesting commit")
    else:
        print(f"Bug {commit_type} commit: {interesting_commit}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='This script finds the commit that induces or fixes the bug')
    parser.add_argument('commit_file', type=str, help='The file that contains the commits of the project')
    parser.add_argument('target_project', type=str, help='The target project')
    parser.add_argument('message', type=str, help='The message that indicates the bug')
    parser.add_argument('test_file', type=str, help='The test file')
    parser.add_argument('commit_type', type=str, help='The type of the commit: inducing or fixing')
    parser.add_argument('--start_commit', type=str, help='The start commit')
    parser.add_argument('--end_commit', type=str, help='The end commit')
    args = parser.parse_args()

    main(args.commit_file, args.target_project, args.message, args.test_file, args.commit_type, args.start_commit, args.end_commit)

    # main("commits.txt", "z3", "unknown", "small.smt2", "inducing", "9eb566b", "1e6b137")