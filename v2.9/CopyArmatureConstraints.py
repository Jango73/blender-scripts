# Blender 2.9
# Author Jango73
#
# This scripts copies the bone constraints from one armature to another.
# Select the source armature, select the destination armature and run the script.
# Both armatures should have same amount of bones with same name.

import bpy

def copyArmatureConstraints(context):

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

    target.select_set(False)
    source.select_set(True)

    bpy.ops.object.posemode_toggle()
    bpy.ops.pose.select_all(action='SELECT')
    sourceBones = bpy.context.selected_pose_bones
    bpy.ops.pose.select_all(action='DESELECT')
    bpy.ops.object.posemode_toggle()

    for bone in sourceBones:

        bone1 = source.pose.bones[bone.name]
        bone2 = target.pose.bones[bone.name]

        if bone2 is not None:
            for constraint in bone2.constraints:
                bone2.constraints.remove(constraint)

            for constraint in bone1.constraints:
                bone2.constraints.copy(constraint)

            for constraint in bone2.constraints:
                if hasattr(constraint, 'target'):
                    if constraint.target == source:
                        constraint.target = target

if __name__ == "__main__":
    copyArmatureConstraints(bpy.context)
