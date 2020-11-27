# Blender 2.9
# Author Jango73
#
# This scripts copies the properties from one object to another object.
# Only the properties not existing in the 2nd object are copied from the 1st.
# Select the source armature, select the destination armature and run the script.

import bpy

def syncObjectProperties(context):

    source = context.selected_objects[0]

    if source is None:
        return {'CANCELLED'}

    # get active object
    target = context.active_object

    if target is None:
        return {'CANCELLED'}

    if target == source:
        source = context.selected_objects[1]

    if source is None:
        return {'CANCELLED'}

    props = source["_RNA_UI"]

    for p in props.keys():
        if not p.startswith("_"):
            if p not in target.keys():
                target[p] = source[p]

if __name__ == "__main__":
    syncObjectProperties(bpy.context)
