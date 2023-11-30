#!/usr/bin/env bash

echo "generating diff..."

flux-local diff hr -A --path cluster/

while true; do
    read -p "do you bless the diff? " yn
    case $yn in
        [Yy]* ) break;;
        [Nn]* ) exit 1;;
        * ) echo "please answer yes or no.";;
    esac
done
