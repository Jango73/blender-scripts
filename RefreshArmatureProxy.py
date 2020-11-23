# Blender 2.8
#
# This scripts refreshes the proxy for an armature that exists in a linked collection
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
# - Deletes the copied proxy (the one that contains old bone constraints)
#
# Usage:
# - Make sure auto keyframing is enabled ('Auto Keying' in timeline view)
# - Make sure your armature proxy is visible and selected, in object mode
# - Set animation start and end as desired
# - Set the variable below to suit your scene needs:
#   * frameStep: numbe of frames to jump after each pose copy

import bpy

frameStep = 10

def getFirstArmature(list):
    print(list)
    armatures = [ob for ob in list if ob.type == 'ARMATURE']
    return armatures[0]

def copyPose(context, source, target):
    if bpy.ops.object.mode_set.poll():
        context.view_layer.objects.active = source
        bpy.ops.object.mode_set(mode='POSE')
        for b in source.data.bones:
            b.select = True
        bpy.ops.pose.copy()
        bpy.ops.object.mode_set(mode='OBJECT')

        context.view_layer.objects.active = target
        bpy.ops.object.mode_set(mode='POSE')
        for b in target.data.bones:
            b.select = True
        bpy.ops.pose.paste()
        bpy.ops.object.mode_set(mode='OBJECT')

def refreshArmatureProxy(context):

    source = context.selected_objects[0]

    if source is None:
        return {'CANCELLED'}

    coll = source.users_collection[0]
    old_proxy_object = source.copy()
    old_proxy_object.name = "foobar"
    coll.objects.link(old_proxy_object)

    old_proxy_show_in_front = old_proxy_object.show_in_front
    current_frame = bpy.context.scene.frame_current

    bones = source.proxy
    bones_collection = source.proxy_collection
    bones_collection_hide_viewport = bones_collection.hide_viewport
    bones_collection.hide_viewport = False
    old_proxy_object.select_set(False)
    bpy.ops.object.delete()

    context.view_layer.objects.active = bones_collection
    target_proxy_object = bpy.ops.object.proxy_make(object=bones.name)
    target_proxy_object = context.view_layer.objects.active

    # Copy every nth frame from old proxy (old_proxy_object) to new proxy (target_proxy_object)
    for f in range(bpy.context.scene.frame_start, bpy.context.scene.frame_end + 1, frameStep):
        bpy.context.scene.frame_set(f)
        copyPose(context, old_proxy_object, target_proxy_object)

    bones_collection.hide_viewport = bones_collection_hide_viewport
    bones_collection.select_set(False)

    target_proxy_object.show_in_front = old_proxy_show_in_front
    target_proxy_object.select_set(False)

    # Copy properties from old proxy to new proxy
    # (Only those existing in new proxy)
    for p in old_proxy_object.keys():
        if not p.startswith("_"):
            if p in target_proxy_object.keys():
                target_proxy_object[p] = old_proxy_object[p]

    old_proxy_object.select_set(True)
    bpy.ops.object.delete()

    target_proxy_object.hide_viewport = True
    target_proxy_object.hide_render = True

    target_proxy_object.hide_viewport = False
    target_proxy_object.hide_render = False

    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    bpy.context.scene.frame_set(current_frame)

    target_proxy_object.select_set(True)

if __name__ == "__main__":
    refreshArmatureProxy(bpy.context)
