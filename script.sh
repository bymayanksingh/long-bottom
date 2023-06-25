#!/bin/bash

if [ $# -eq 0 ]; then
    echo "No filename provided. Usage: $0 filename"
    exit 1
fi

output_file=$2

while true; do
    echo $(date) >> $output_file
    sleep 0.5
done