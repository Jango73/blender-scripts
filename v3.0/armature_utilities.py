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
import mathutils
from bpy.types import Operator
from bpy.props import StringProperty

# -------------------------------------------------------------------------------------------------

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

# -------------------------------------------------------------------------------------------------
# Operators

class OBJECT_OT_CopyArmatureConstraints(bpy.types.Operator):
    """Copy Armature Constraints"""
    bl_idname = "object.copy_armature_constraints"
    bl_label = "Copy armature constraints"
    bl_description = "Copies the bone contraints from an armature to another"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return copyArmatureConstraints(self, context)

# -------------------------------------------------------------------------------------------------
# Save start pose and delta pose
start_pose = {}
pose_delta = {}
copied_bone_transforms = {}

# -------------------------------------------------------------------------------------------------

def getSelectedArmature(context):
    obj = context.active_object
    if obj and obj.type == 'ARMATURE':
        return obj

    for selected_obj in context.selected_objects:
        if selected_obj.type == 'ARMATURE':
            return selected_obj

    return None

# -------------------------------------------------------------------------------------------------

def copyBonePositionsRotations(self, context):
    global copied_bone_transforms

    armature = getSelectedArmature(context)
    if armature is None:
        self.report({'WARNING'}, "No selected armature")
        return {'CANCELLED'}

    copied_bone_transforms.clear()

    for bone in armature.pose.bones:
        copied_bone_transforms[bone.name] = {
            'location': bone.location.copy(),
            'rotation_mode': bone.rotation_mode,
            'rotation_quaternion': bone.rotation_quaternion.copy(),
            'rotation_euler': bone.rotation_euler.copy(),
            'rotation_axis_angle': tuple(bone.rotation_axis_angle),
        }

    self.report({'INFO'}, "Copied pose transforms for " + str(len(copied_bone_transforms)) + " bone(s)")
    return {'FINISHED'}

# -------------------------------------------------------------------------------------------------

def pasteBonePositionsRotations(self, context):
    armature = getSelectedArmature(context)
    if armature is None:
        self.report({'WARNING'}, "No selected armature")
        return {'CANCELLED'}

    if not copied_bone_transforms:
        self.report({'WARNING'}, "No copied bone transforms")
        return {'CANCELLED'}

    pasted_count = 0
    inserted_keys_count = 0
    use_auto_key = context.scene.tool_settings.use_keyframe_insert_auto

    for bone in armature.pose.bones:
        if bone.name not in copied_bone_transforms:
            continue

        data = copied_bone_transforms[bone.name]
        bone.location = data['location']
        bone.rotation_mode = data['rotation_mode']

        if bone.rotation_mode == 'QUATERNION':
            bone.rotation_quaternion = data['rotation_quaternion']
            if use_auto_key:
                bone.keyframe_insert(data_path="rotation_quaternion")
        elif bone.rotation_mode == 'AXIS_ANGLE':
            bone.rotation_axis_angle = data['rotation_axis_angle']
            if use_auto_key:
                bone.keyframe_insert(data_path="rotation_axis_angle")
        else:
            bone.rotation_euler = data['rotation_euler']
            if use_auto_key:
                bone.keyframe_insert(data_path="rotation_euler")

        if use_auto_key:
            bone.keyframe_insert(data_path="location")
            inserted_keys_count += 1

        pasted_count += 1

    context.view_layer.update()

    if use_auto_key:
        self.report({'INFO'}, "Pasted pose transforms on " + str(pasted_count) + " bone(s), inserted keys on " + str(inserted_keys_count) + " bone(s)")
    else:
        self.report({'INFO'}, "Pasted pose transforms on " + str(pasted_count) + " bone(s)")
    return {'FINISHED'}

# -------------------------------------------------------------------------------------------------

class POSE_OT_MarkStartPose(Operator):
    bl_idname = "pose.mark_start_pose"
    bl_label = "Mark Start Pose"
    bl_description = "Mark the current pose as the start pose"
    
    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'ARMATURE'
    
    def execute(self, context):
        global start_pose
        armature = context.active_object
        pose_bones = armature.pose.bones
        
        # Clear previous start pose
        start_pose.clear()
        
        # Store current pose (rotation, location, scale)
        for bone in pose_bones:
            start_pose[bone.name] = {
                'rotation': bone.rotation_quaternion.copy() if bone.rotation_mode == 'QUATERNION' else bone.rotation_euler.to_quaternion(),
                'location': bone.location.copy(),
                'scale': bone.scale.copy()
            }
        
        self.report({'INFO'}, "Marked current pose as start pose")
        return {'FINISHED'}

# -------------------------------------------------------------------------------------------------

class POSE_OT_CopyDelta(Operator):
    bl_idname = "pose.copy_delta"
    bl_label = "Copy Pose Delta"
    bl_description = "Copy the delta between marked start pose and current pose"
    
    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'ARMATURE' and start_pose
    
    def execute(self, context):
        global pose_delta
        armature = context.active_object
        pose_bones = armature.pose.bones
        
        # Clear previous delta
        pose_delta.clear()
        
        # Calculate delta for each bone
        for bone in pose_bones:
            if bone.name in start_pose:
                # Get start and end (current) pose
                start_data = start_pose[bone.name]
                end_rot = bone.rotation_quaternion.copy() if bone.rotation_mode == 'QUATERNION' else bone.rotation_euler.to_quaternion()
                end_loc = bone.location.copy()
                end_scale = bone.scale.copy()
                
                # Calculate delta
                delta_rot = end_rot @ start_data['rotation'].inverted()
                delta_loc = end_loc - start_data['location']
                delta_scale = mathutils.Vector([end_scale[i] / start_data['scale'][i] if start_data['scale'][i] != 0 else 1.0 for i in range(3)])
                
                pose_delta[bone.name] = {
                    'rotation': delta_rot,
                    'location': delta_loc,
                    'scale': delta_scale
                }
        
        self.report({'INFO'}, "Copied delta from start pose to current pose")
        return {'FINISHED'}

# -------------------------------------------------------------------------------------------------

class POSE_OT_PasteDelta(Operator):
    bl_idname = "pose.paste_delta"
    bl_label = "Paste Pose Delta"
    bl_description = "Apply the copied pose delta to the current pose"
    
    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'ARMATURE' and pose_delta
    
    def execute(self, context):
        armature = context.active_object
        pose_bones = armature.pose.bones
        
        # Apply delta to each bone
        for bone in pose_bones:
            if bone.name in pose_delta:
                delta_data = pose_delta[bone.name]
                
                # Apply rotation
                current_rot = bone.rotation_quaternion.copy() if bone.rotation_mode == 'QUATERNION' else bone.rotation_euler.to_quaternion()
                new_rot = delta_data['rotation'] @ current_rot
                if bone.rotation_mode == 'QUATERNION':
                    bone.rotation_quaternion = new_rot
                else:
                    bone.rotation_euler = new_rot.to_euler(bone.rotation_mode)
                
                # Apply location
                bone.location += delta_data['location']
                
                # Apply scale
                for i in range(3):
                    bone.scale[i] *= delta_data['scale'][i]
        
        self.report({'INFO'}, "Pasted pose delta")
        return {'FINISHED'}

# -------------------------------------------------------------------------------------------------
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
        layout.operator("object.copy_bone_positions_rotations")
        layout.operator("object.paste_bone_positions_rotations")

class OBJECT_OT_CopyBonePositionsRotations(bpy.types.Operator):
    """Copy Bone Positions/Rotations"""
    bl_idname = "object.copy_bone_positions_rotations"
    bl_label = "Copy bone positions/rotations"
    bl_description = "Copies pose bone positions and rotations from selected armature"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        return copyBonePositionsRotations(self, context)

class OBJECT_OT_PasteBonePositionsRotations(bpy.types.Operator):
    """Paste Bone Positions/Rotations"""
    bl_idname = "object.paste_bone_positions_rotations"
    bl_label = "Paste bone positions/rotations"
    bl_description = "Pastes copied pose bone positions and rotations to selected armature"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        return pasteBonePositionsRotations(self, context)

class OBJECT_PT_bone_utilities(bpy.types.Panel):
    bl_idname = "OBJECT_PT_bone_utilities"
    bl_label = "Bone Utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE'

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.operator(POSE_OT_MarkStartPose.bl_idname)
        box.operator(POSE_OT_CopyDelta.bl_idname)
        box.operator(POSE_OT_PasteDelta.bl_idname)

# -------------------------------------------------------------------------------------------------
# Registering

def register():
    bpy.utils.register_class(OBJECT_OT_CopyArmatureConstraints)
    bpy.utils.register_class(OBJECT_OT_CopyBonePositionsRotations)
    bpy.utils.register_class(OBJECT_OT_PasteBonePositionsRotations)
    bpy.utils.register_class(OBJECT_PT_armature_utilities)
    bpy.utils.register_class(OBJECT_PT_bone_utilities)
    bpy.utils.register_class(POSE_OT_MarkStartPose)
    bpy.utils.register_class(POSE_OT_CopyDelta)
    bpy.utils.register_class(POSE_OT_PasteDelta)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_CopyArmatureConstraints)
    bpy.utils.unregister_class(OBJECT_OT_CopyBonePositionsRotations)
    bpy.utils.unregister_class(OBJECT_OT_PasteBonePositionsRotations)
    bpy.utils.unregister_class(OBJECT_PT_armature_utilities)
    bpy.utils.unregister_class(OBJECT_PT_bone_utilities)
    bpy.utils.unregister_class(POSE_OT_MarkStartPose)
    bpy.utils.unregister_class(POSE_OT_CopyDelta)
    bpy.utils.unregister_class(POSE_OT_PasteDelta)

if __name__ == "__main__":
    register()
