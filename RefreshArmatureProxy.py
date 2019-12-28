# Blender 2.8
#
# This scripts refreshes the proxy for an armature in a linked collection
# Useful when you have made changes to bone constraints of an armature in blender file A
# and wish to have those constraints applied to a proxy in blender file B that links to
# your armature in file A
#
# What it does:
# - Makes a copy of the active proxy armature
# - Deletes the active proxy armature
# - Creates a new armature proxy from the collection where the previously deleted proxy came from
#   (This new proxy contains fresh new bone constraints)
# - From <firstFrame> to <lastFrame>, jumping every <frameStep> frames, copies the pose from the
#   copied proxy to the new proxy
# - Delete the copied proxy (contains old bone constraints)
#
# Usage:
# - Make sure auto keyframing is enabled
# - Make sure your armature proxy and the collection it comes from are visible
# - Set the variables below to suit your scene needs:
#   * firstFrame: start of animation for pose copies
#   * lastFrame: end of animation for pose copies
#   * frameStep: numbe of frames to jump after each pose copy

import bpy

firstFrame = 0
lastFrame = 20
frameStep = 10

def getFirstArmature(list):
    print(list)
    armatures = [ob for ob in list if ob.type == 'ARMATURE']
    print(armatures)
    return armatures[0]

def copyPose(context, source, target):
    if bpy.ops.object.mode_set.poll():
        context.view_layer.objects.active = source
        bpy.ops.object.mode_set(mode='POSE')
        for b in source.data.bones:
            b.select = True
        bpy.ops.pose.copy()
        bpy.ops.object.mode_set(mode='OBJECT')

        print(context.view_layer.objects.active)

        context.view_layer.objects.active = target
        bpy.ops.object.mode_set(mode='POSE')
        for b in source.data.bones:
            b.select = True
        bpy.ops.pose.paste()
        bpy.ops.object.mode_set(mode='OBJECT')

        print(context.view_layer.objects.active)

def refreshArmatureProxy(context):

    source = context.selected_objects[0]

    if source is None:
        return {'CANCELLED'}

    coll = source.users_collection[0]
    temp = source.copy()
    temp.name = "toto"
    coll.objects.link(temp)

    bones = source.proxy
    bones_collection = source.proxy_collection
    temp.select_set(False)
    bpy.ops.object.delete()

    context.view_layer.objects.active = bones_collection
    target = bpy.ops.object.proxy_make(object=bones.name)
    target = context.view_layer.objects.active

    for f in range(firstFrame, lastFrame + 1, frameStep):
        bpy.context.scene.frame_set(f)
        copyPose(context, temp, target)

    bones_collection.select_set(False)
    target.select_set(False)
    temp.select_set(True)
    bpy.ops.object.delete()

if __name__ == "__main__":
    refreshArmatureProxy(bpy.context)
