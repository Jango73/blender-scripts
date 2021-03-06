# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Armature utilities",
    "author": "Jango73",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "description": "Operations on armatures",
    "category": "Object",
}

import bpy

# -----------------------------------------------------------------------------

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
    current_frame = context.scene.frame_current

    bones = source.proxy
    bones_collection = source.proxy_collection
    bones_collection_hide_viewport = bones_collection.hide_viewport
    bones_collection.hide_viewport = False
    old_proxy_object.select_set(False)
    bpy.ops.object.delete()

    context.view_layer.objects.active = bones_collection
    target_proxy_object = bpy.ops.object.proxy_make(object=bones.name)
    target_proxy_object = context.view_layer.objects.active

    target_proxy_object.animation_data_create()
    target_proxy_object.animation_data.action = old_proxy_object.animation_data.action

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

    context.scene.frame_set(context.scene.frame_start)
    context.scene.frame_set(current_frame)

    target_proxy_object.select_set(True)

    return {'FINISHED'}

def copyArmatureConstraints(self, context):
    target = context.selected_objects[0]

    if target is None:
        return {'CANCELLED'}

    # get active object
    source = context.active_object

    if source is None:
        return {'CANCELLED'}

    if target == source:
        target = context.selected_objects[1]

    if target is None:
        return {'CANCELLED'}

    target.select_set(False)
    source.select_set(True)

    bpy.ops.object.posemode_toggle()
    bpy.ops.pose.select_all(action='SELECT')
    sourceBones = context.selected_pose_bones
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

    self.report({'INFO'}, "Copied " + source.name + " bone constraints to " + target.name)

    return {'FINISHED'}

# -----------------------------------------------------------------------------
# Operators

class OBJECT_OT_RefreshArmatureProxy(bpy.types.Operator):
    """Refresh Armature Proxy"""
    bl_idname = "object.refresh_armature_proxy"
    bl_label = "Refresh armature proxy"
    bl_description = "Refreshes the proxy for an armature that exists in a linked collection"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return refreshArmatureProxy(context)

class OBJECT_OT_CopyArmatureConstraints(bpy.types.Operator):
    """Copy Armature Constraints"""
    bl_idname = "object.copy_armature_constraints"
    bl_label = "Copy armature constraints"
    bl_description = "Copies the bone contraints from an armature to another"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return copyArmatureConstraints(self, context)

# -----------------------------------------------------------------------------
# Panels

class OBJECT_PT_armature_utilities(bpy.types.Panel):
    bl_idname = "OBJECT_PT_armature_utilities"
    bl_label = "Armature Utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"
    bl_context = 'objectmode'

    @classmethod
    def poll(cls, context):
        return (context.object is not None)

    def draw(self, context):
        layout = self.layout

        layout.operator("object.refresh_armature_proxy")
        layout.operator("object.copy_armature_constraints")

# -----------------------------------------------------------------------------
# Registering

def register():
    bpy.utils.register_class(OBJECT_OT_RefreshArmatureProxy)
    bpy.utils.register_class(OBJECT_OT_CopyArmatureConstraints)
    bpy.utils.register_class(OBJECT_PT_armature_utilities)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_RefreshArmatureProxy)
    bpy.utils.unregister_class(OBJECT_OT_CopyArmatureConstraints)
    bpy.utils.unregister_class(OBJECT_PT_armature_utilities)

if __name__ == "__main__":
    register()
