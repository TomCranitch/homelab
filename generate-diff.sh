#!/usr/bin/env bash

# Allows us to read user input below, assigns stdin to keyboard
exec < /dev/tty

flux-local test --path cluster/ --enable-helm

#echo "generating diff..."

#flux-local diff hr -A --path cluster/

#while true; do
#    read -p "do you bless the diff? " yn
#    case $yn in
#        [Yy]* ) break;;
#        [Nn]* ) exit 1;;
#        * ) echo "please answer yes or no.";;
#    esac
#done
