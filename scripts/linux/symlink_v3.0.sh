#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: $0 <blender-path>"
    echo "Example: $0 /opt/blender-3.6/3.6/scripts/addons"
    exit 1
fi

BLENDER_PATH="$1"
ADDONS_DIR="$BLENDER_PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$SCRIPT_DIR/../.."

if [ ! -d "$ADDONS_DIR" ]; then
    echo "Error: $ADDONS_DIR does not exist"
    exit 1
fi

for script in "$REPO_DIR"/v3.0/*.py; do
    name="$(basename "$script")"
    ln -sf "$script" "$ADDONS_DIR/$name"
    echo "Linked: $ADDONS_DIR/$name -> $script"
done
