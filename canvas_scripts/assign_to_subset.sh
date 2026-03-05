#!/bin/bash

python3 assign_to_subset.py \
  --base "https://olin.instructure.com" \
  --course 1000 \
  --assignment $1 \
  --csv subset.csv \
  --only-visible
