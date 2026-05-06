#!/bin/sh
touch "$(git rev-parse --show-toplevel)/logs/$(date +%Y%m%d%H%M%S).log"