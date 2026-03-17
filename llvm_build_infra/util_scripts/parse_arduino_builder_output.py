"""
Script that converts arduino builder compilation output
to nice json output.
This json could be used to get bitcode files for the corresponding targets.
"""
import argparse
import os
import sys
import json
from typing import List, Dict


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
    parser = argparse.ArgumentParser(
        description="Convert Arduino builder output to compile_commands.json format"
    )
    parser.add_argument('-i', dest='builder_output',
                        help='Path to the arduino builder output file',
                        required=True)
    parser.add_argument('-o', dest='compile_commands_out',
                        default="compile_commands.json",
                        help='Path to the output compile_commands.json file (default: compile_commands.json)')
    parser.add_argument('-w', dest='used_work_dir',
                        default=os.getcwd(),
                        help='Working directory used for running arduino builder command (default: current directory)')
    return parser


def usage():
    log_error("Invalid Usage.")
    log_error(f"Run: python {__file__} --help to know the correct usage.")
    sys.exit(-1)


def is_known_compiler(curr_com: str) -> bool:
    """Check if the command is a known compiler (gcc/g++)"""
    known_compilers = ['gcc', 'g++']
    return any(curr_com.endswith(compiler) for compiler in known_compilers)


def process_builder_output(output_file: str) -> List[str]:
    """Extract compilation commands from builder output"""
    try:
        with open(output_file, "r") as f:
            all_lines = [line.strip() for line in f.readlines() if line.strip()]
    except IOError as e:
        log_error(f"Failed to read builder output file: {e}")
        sys.exit(-1)

    # Filter lines that start with a known compiler
    compiler_lines = []
    for line in all_lines:
        parts = line.split()
        if len(parts) > 2 and is_known_compiler(parts[0].strip()):
            compiler_lines.append(line.strip())

    # Filter out preprocessing commands (-E) and keep compilation commands (-c)
    compilation_lines = [
        line for line in compiler_lines
        if " -E " not in line and " -c " in line
    ]

    return compilation_lines


def get_json_string(compilation_line: str, work_dir: str) -> Dict:
    """Convert a compilation line to compile_commands.json entry"""
    parts = compilation_line.strip().split()
    compiler_name = parts[0]
    options = []
    output_files = []
    input_files = []
    is_output = False
    idx = 1

    while idx < len(parts):
        part = parts[idx].strip()
        idx += 1

        if is_output:
            output_files.append(part)
            is_output = False
            continue

        # Handle arguments with spaces (e.g., -DUSB_PRODUCT="My Product")
        if part.startswith(("\"-DUSB_MANUFACTURER", "\"-DUSB_PRODUCT")):
            if idx < len(parts):
                part += " " + parts[idx]
                idx += 1
            options.append(part)
            continue

        if part == "-o":
            is_output = True
            continue

        # Classify as option or input file
        if part.startswith("-") or not os.path.exists(part):
            options.append(part)
        else:
            input_files.append(os.path.abspath(part))

    return {
        "directory": os.path.abspath(work_dir),
        "command": compilation_line,
        "file": input_files[0] if input_files else "",
        "output": output_files[0] if output_files else "",
        "compiler": compiler_name,
        "arguments": options
    }


def main():
    arg_parser = setup_args()
    parsed_args = arg_parser.parse_args()

    # Validate inputs
    input_file = parsed_args.builder_output
    output_file = parsed_args.compile_commands_out
    work_dir = parsed_args.used_work_dir

    if not os.path.isfile(input_file):
        log_error(f"Input builder output file does not exist: {input_file}")
        usage()

    if not os.path.isdir(work_dir):
        log_error(f"Working directory does not exist: {work_dir}")
        usage()

    # Log configuration
    log_info("Input builder output file:", input_file)
    log_info("Work directory:", work_dir)
    log_info("Output json file:", output_file)

    # Process output
    log_info("Parsing builder output file...")
    compilation_lines = process_builder_output(input_file)
    log_info(f"Extracted {len(compilation_lines)} compilation commands")

    if not compilation_lines:
        log_warning("No compilation commands found in builder output")
        compile_commands = []
    else:
        log_info("Converting to compile_commands.json format...")
        compile_commands = [get_json_string(line, work_dir) for line in compilation_lines]

    # Write output
    try:
        with open(output_file, "w") as f:
            json.dump(compile_commands, f, sort_keys=True, indent=2, separators=(',', ': '))
        log_success(f"Successfully wrote {len(compile_commands)} entries to {output_file}")
    except IOError as e:
        log_error(f"Failed to write output file: {e}")
        sys.exit(-2)


if __name__ == "__main__":
    main()
