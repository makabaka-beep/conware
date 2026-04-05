#!/bin/sh
# sudo snap install arduino-cli
# arduino-cli core install arduino:sam
arduino-cli compile   --fqbn arduino:sam:arduino_due_x   --build-path ./build_uninstrumented   .

