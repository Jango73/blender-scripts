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
    "version": (3, 0),
    "blender": (3, 0, 0),
    "description": "Operations on armatures",
    "category": "Object",
}

import bpy

# -----------------------------------------------------------------------------

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

        layout.operator("object.copy_armature_constraints")

# -----------------------------------------------------------------------------
# Registering

def register():
    bpy.utils.register_class(OBJECT_OT_CopyArmatureConstraints)
    bpy.utils.register_class(OBJECT_PT_armature_utilities)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_CopyArmatureConstraints)
    bpy.utils.unregister_class(OBJECT_PT_armature_utilities)

if __name__ == "__main__":
    register()
