#!/usr/bin/python
import argparse
import sys
import subprocess
import os
import tempfile
import shutil


def log_info(*args):
    log_str = "[*] "
    for curr_a in args:
        log_str = log_str + " " + str(curr_a)
    print(log_str)


def log_error(*args):
    log_str = "[!] "
    for curr_a in args:
        log_str = log_str + " " + str(curr_a)
    print(log_str)


def log_warning(*args):
    log_str = "[?] "
    for curr_a in args:
        log_str = log_str + " " + str(curr_a)
    print(log_str)


def log_success(*args):
    log_str = "[+] "
    for curr_a in args:
        log_str = log_str + " " + str(curr_a)
    print(log_str)


def setup_args():
    parser = argparse.ArgumentParser(description="Instrument Arduino project with LLVM transformations")
    required_named = parser
    required_named.add_argument('-i', dest='src_ico_file',
                                help='Path to the source ico file.',
                                required=True)
    required_named.add_argument('-b', dest='target_build_dir',
                                help='Path to the build directory.',
                                required=True)
    required_named.add_argument('-r', dest='original_repo_dir',
                                help='Path to the original repo directory.',
                                required=True)
    return parser


def run_command(cmd, output_file):
    """Run command with output redirection and return success status"""
    try:
        with open(output_file, 'w') as f:
            result = subprocess.run(cmd, shell=True, check=True, stdout=f, stderr=subprocess.STDOUT)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed with exit code {e.returncode}: {cmd}")
        return False
    except Exception as e:
        log_error(f"Error executing command: {str(e)}")
        return False


def run_default_arduino_build(build_dir, repo_dir, ico_file_path, build_output_file):
    to_run_command_template = (
        "$3/runtime/arduino-1.8.8/arduino-builder -debug-level 5 -verbose -compile "
        "-logger=machine -hardware $3/runtime/arduino-1.8.8/hardware "
        "-hardware $3/runtime/arduino-1.8.8/portable/packages "
        "-tools $3/runtime/arduino-1.8.8/tools-builder "
        "-tools $3/runtime/arduino-1.8.8/hardware/tools/avr "
        "-tools $3/runtime/arduino-1.8.8/portable/packages "
        "-built-in-libraries $3/runtime/arduino-1.8.8/libraries "
        "-libraries $3/runtime/arduino-1.8.8/portable/sketchbook/libraries "
        "-fqbn=arduino:sam:arduino_due_x_dbg -ide-version=10808 "
        "-build-path $1 -warnings=null "
        "-prefs=build.path=$1 -prefs=build.warn_data_percentage=75 "
        "-prefs=runtime.tools.bossac.path=$3/runtime/arduino-1.8.8/portable/packages/arduino/tools/bossac/1.6.1-arduino "
        "-prefs=runtime.tools.bossac-1.6.1-arduino.path=$3/runtime/arduino-1.8.8/portable/packages/arduino/tools/bossac/1.6.1-arduino "
        "-prefs=runtime.tools.arm-none-eabi-gcc.path=$3/runtime/arduino-1.8.8/portable/packages/arduino/tools/arm-none-eabi-gcc/4.8.3-2014q1 "
        "-prefs=runtime.tools.arm-none-eabi-gcc-4.8.3-2014q1.path=$3/runtime/arduino-1.8.8/portable/packages/arduino/tools/arm-none-eabi-gcc/4.8.3-2014q1 "
        "$2"
    )

    to_run_command = to_run_command_template.replace("$3", repo_dir)
    to_run_command = to_run_command.replace("$1", build_dir)
    to_run_command = to_run_command.replace("$2", ico_file_path)

    log_info("Running original arduino build and writing output to:", build_output_file)
    if run_command(to_run_command, build_output_file):
        log_success("Successfully built arduino project.")
        return True
    else:
        log_error("Error occurred while trying to run arduino build.")
        return False


def parse_arduino_builder_out(arduino_builder_output, output_compile_json):
    target_script = os.path.join(os.path.dirname(__file__), "util_scripts/parse_arduino_builder_output.py")
    if not os.path.exists(target_script):
        log_error(f"Parser script not found: {target_script}")
        return False

    to_run_cmd = f"python {target_script} -i {arduino_builder_output} -o {output_compile_json}"
    log_info("Running arduino builder output parser.")
    try:
        subprocess.run(to_run_cmd, shell=True, check=True, capture_output=True, text=True)
        log_success("Finished parsing builder output to json file:", output_compile_json)
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"Parser failed: {e.stderr}")
        return False


def get_bin_path(bin_name):
    try:
        out_p = subprocess.check_output(f'which {bin_name}', shell=True, text=True)
        return out_p.strip()
    except subprocess.CalledProcessError:
        log_error(f"Binary {bin_name} not found in system path")
        sys.exit(-1)


def perform_llvm_transformation(llvm_bc_out, original_build_dir, compile_json_out, clang_path, opt_path, so_path):
    target_script = os.path.join(os.path.dirname(__file__), "llvm_build/arduino_llvm_build.py")
    if not os.path.exists(target_script):
        log_error(f"LLVM transformation script not found: {target_script}")
        return False

    to_run_cmd = (
        f"python {target_script} -l {llvm_bc_out} -b {original_build_dir} "
        f"-m {compile_json_out} -clangp {clang_path} "
        f"-instrument -optp {opt_path} -sopath {so_path}"
    )
    log_info("Running llvm transformations.")
    try:
        subprocess.run(to_run_cmd, shell=True, check=True, capture_output=True, text=True)
        log_success("Finished running llvm transformations.")
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"LLVM transformation failed: {e.stderr}")
        return False


def main():
    arg_parser = setup_args()
    parsed_args = arg_parser.parse_args()
    path_to_ico_file = os.path.abspath(parsed_args.src_ico_file)
    original_repo_dir = os.path.abspath(parsed_args.original_repo_dir)
    target_build_dir = os.path.abspath(parsed_args.target_build_dir)
    llvm_transformation_pass_so = os.path.join(
        os.path.dirname(__file__),
        "llvm_transformation_passes/build/MMIOLogger/libMMIOLogger.so"
    )

    # Validate input paths
    if not os.path.isfile(path_to_ico_file):
        log_error("Provided ico file doesn't exist or is not a file:", path_to_ico_file)
        sys.exit(-1)

    if not os.path.isdir(original_repo_dir):
        log_error("Provided repo directory doesn't exist or is not a directory:", original_repo_dir)
        sys.exit(-1)

    if not os.path.isfile(llvm_transformation_pass_so):
        log_error("LLVM Transformation so file doesn't exist:", llvm_transformation_pass_so)
        sys.exit(-1)

    # Get tool paths
    clang_path = get_bin_path("clang")
    opt_path = get_bin_path("opt")

    # Prepare build directory
    if os.path.exists(target_build_dir):
        log_warning("Cleaning up provided build directory:", target_build_dir)
        shutil.rmtree(target_build_dir, ignore_errors=True)
    os.makedirs(target_build_dir, exist_ok=True)

    # Create temporary directory (will be cleaned up on exit)
    tmp_work_directory = tempfile.mkdtemp()
    log_info("Using Directory:", tmp_work_directory, " as temporary working directory.")

    try:
        # Step 1: Original build to capture commands
        original_build_output = os.path.join(tmp_work_directory, "original_arduino_build_output.txt")
        if not run_default_arduino_build(target_build_dir, original_repo_dir, path_to_ico_file, original_build_output):
            sys.exit(-2)

        # Step 2: Convert build commands to JSON
        output_compile_json = os.path.join(tmp_work_directory, "compile_commands.json")
        if not parse_arduino_builder_out(original_build_output, output_compile_json):
            sys.exit(-3)

        # Step 3: LLVM transformations
        llvm_bit_code_output = os.path.join(tmp_work_directory, "llvm_bitcode_out")
        os.makedirs(llvm_bit_code_output, exist_ok=True)
        if not perform_llvm_transformation(llvm_bit_code_output, target_build_dir, output_compile_json,
                                           clang_path, opt_path, llvm_transformation_pass_so):
            sys.exit(-4)

        # Step 4: Rebuild with modified object files
        modified_build_output = os.path.join(tmp_work_directory, "modified_arduino_build_output.txt")
        if not run_default_arduino_build(target_build_dir, original_repo_dir, path_to_ico_file, modified_build_output):
            sys.exit(-5)

        log_success("All steps completed successfully!")

    finally:
        # Clean up temporary directory
        if os.path.exists(tmp_work_directory):
            log_info("Cleaning up temporary directory:", tmp_work_directory)
            shutil.rmtree(tmp_work_directory, ignore_errors=True)


if __name__ == "__main__":
    main()
