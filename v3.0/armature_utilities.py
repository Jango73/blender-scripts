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
copied_bone_animation = {}

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

def setSceneFrame(scene, frame):
    frame_int = int(frame)
    subframe = frame - frame_int
    scene.frame_set(frame_int, subframe=subframe)

# -------------------------------------------------------------------------------------------------

def clearArmatureActionKeys(armature):
    if armature.animation_data is None or armature.animation_data.action is None:
        return 0

    action = armature.animation_data.action
    fcurves = list(action.fcurves)

    for fcurve in fcurves:
        action.fcurves.remove(fcurve)

    return len(fcurves)

# -------------------------------------------------------------------------------------------------

def copyBoneAnimationAllFrames(self, context):
    global copied_bone_animation

    armature = getSelectedArmature(context)
    if armature is None:
        self.report({'WARNING'}, "No selected armature")
        return {'CANCELLED'}

    if armature.animation_data is None or armature.animation_data.action is None:
        self.report({'WARNING'}, "Selected armature has no action")
        return {'CANCELLED'}

    action = armature.animation_data.action
    frames = set()

    for fcurve in action.fcurves:
        if fcurve.data_path.startswith('pose.bones["'):
            for key in fcurve.keyframe_points:
                frames.add(float(key.co.x))

    if not frames:
        self.report({'WARNING'}, "No keyed pose frames found")
        return {'CANCELLED'}

    scene = context.scene
    original_frame = scene.frame_current
    original_subframe = scene.frame_subframe
    sorted_frames = sorted(frames)

    copied_bone_animation = {"frames": sorted_frames, "bones_by_frame": {}}

    try:
        for frame in sorted_frames:
            setSceneFrame(scene, frame)
            frame_data = {}

            for bone in armature.pose.bones:
                frame_data[bone.name] = {
                    "location": bone.location.copy(),
                    "rotation_mode": bone.rotation_mode,
                    "rotation_quaternion": bone.rotation_quaternion.copy(),
                    "rotation_euler": bone.rotation_euler.copy(),
                    "rotation_axis_angle": tuple(bone.rotation_axis_angle),
                    "scale": bone.scale.copy(),
                }

            copied_bone_animation["bones_by_frame"][frame] = frame_data
    finally:
        scene.frame_set(original_frame, subframe=original_subframe)

    self.report({'INFO'}, "Copied " + str(len(sorted_frames)) + " keyed frame(s) with loc/rot/scale")
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

def pasteBoneAnimationAllFrames(self, context):
    armature = getSelectedArmature(context)
    if armature is None:
        self.report({'WARNING'}, "No selected armature")
        return {'CANCELLED'}

    if not copied_bone_animation or "frames" not in copied_bone_animation:
        self.report({'WARNING'}, "No copied keyed animation")
        return {'CANCELLED'}

    armature.animation_data_create()
    if armature.animation_data.action is None:
        armature.animation_data.action = bpy.data.actions.new(name=armature.name + "_PosePaste")

    removed_curves = clearArmatureActionKeys(armature)

    scene = context.scene
    original_frame = scene.frame_current
    original_subframe = scene.frame_subframe

    frame_count = 0
    keyed_bone_count = 0

    try:
        for frame in copied_bone_animation["frames"]:
            setSceneFrame(scene, frame)
            frame_data = copied_bone_animation["bones_by_frame"].get(frame, {})

            for bone_name, data in frame_data.items():
                bone = armature.pose.bones.get(bone_name)
                if bone is None:
                    continue

                bone.location = data["location"]
                bone.scale = data["scale"]
                bone.rotation_mode = data["rotation_mode"]

                bone.keyframe_insert(data_path="location")
                bone.keyframe_insert(data_path="scale")

                if bone.rotation_mode == 'QUATERNION':
                    bone.rotation_quaternion = data["rotation_quaternion"]
                    bone.keyframe_insert(data_path="rotation_quaternion")
                elif bone.rotation_mode == 'AXIS_ANGLE':
                    bone.rotation_axis_angle = data["rotation_axis_angle"]
                    bone.keyframe_insert(data_path="rotation_axis_angle")
                else:
                    bone.rotation_euler = data["rotation_euler"]
                    bone.keyframe_insert(data_path="rotation_euler")

                keyed_bone_count += 1

            frame_count += 1
    finally:
        scene.frame_set(original_frame, subframe=original_subframe)

    context.view_layer.update()
    self.report({'INFO'}, "Cleared " + str(removed_curves) + " FCurves, pasted " + str(frame_count) + " frame(s), keyed " + str(keyed_bone_count) + " bone pose(s)")
    return {'FINISHED'}

# -------------------------------------------------------------------------------------------------

def deleteAllScaleKeysFromSelectedBones(self, context):
    armature = context.active_object
    if armature is None or armature.type != 'ARMATURE':
        self.report({'WARNING'}, "No active armature")
        return {'CANCELLED'}

    selected_bones = context.selected_pose_bones or []
    if not selected_bones:
        self.report({'WARNING'}, "No selected bones")
        return {'CANCELLED'}

    if armature.animation_data is None or armature.animation_data.action is None:
        self.report({'WARNING'}, "Active armature has no action")
        return {'CANCELLED'}

    action = armature.animation_data.action
    target_paths = {f'pose.bones["{bone.name}"].scale' for bone in selected_bones}

    removed_curves = 0
    removed_keys = 0

    for fcurve in list(action.fcurves):
        if fcurve.data_path in target_paths:
            removed_keys += len(fcurve.keyframe_points)
            action.fcurves.remove(fcurve)
            removed_curves += 1

    self.report({'INFO'}, "Deleted " + str(removed_keys) + " scale key(s) from " + str(len(selected_bones)) + " selected bone(s)")
    return {'FINISHED'}

# -------------------------------------------------------------------------------------------------

def deleteAllLocationKeysFromSelectedBones(self, context):
    armature = context.active_object
    if armature is None or armature.type != 'ARMATURE':
        self.report({'WARNING'}, "No active armature")
        return {'CANCELLED'}

    selected_bones = context.selected_pose_bones or []
    if not selected_bones:
        self.report({'WARNING'}, "No selected bones")
        return {'CANCELLED'}

    if armature.animation_data is None or armature.animation_data.action is None:
        self.report({'WARNING'}, "Active armature has no action")
        return {'CANCELLED'}

    action = armature.animation_data.action
    target_paths = {f'pose.bones["{bone.name}"].location' for bone in selected_bones}

    removed_keys = 0
    for fcurve in list(action.fcurves):
        if fcurve.data_path in target_paths:
            removed_keys += len(fcurve.keyframe_points)
            action.fcurves.remove(fcurve)

    self.report({'INFO'}, "Deleted " + str(removed_keys) + " location key(s) from " + str(len(selected_bones)) + " selected bone(s)")
    return {'FINISHED'}

# -------------------------------------------------------------------------------------------------

def deleteAllRotationKeysFromSelectedBones(self, context):
    armature = context.active_object
    if armature is None or armature.type != 'ARMATURE':
        self.report({'WARNING'}, "No active armature")
        return {'CANCELLED'}

    selected_bones = context.selected_pose_bones or []
    if not selected_bones:
        self.report({'WARNING'}, "No selected bones")
        return {'CANCELLED'}

    if armature.animation_data is None or armature.animation_data.action is None:
        self.report({'WARNING'}, "Active armature has no action")
        return {'CANCELLED'}

    action = armature.animation_data.action
    rotation_paths = set()
    for bone in selected_bones:
        prefix = f'pose.bones["{bone.name}"].'
        rotation_paths.add(prefix + "rotation_euler")
        rotation_paths.add(prefix + "rotation_quaternion")
        rotation_paths.add(prefix + "rotation_axis_angle")

    removed_keys = 0
    for fcurve in list(action.fcurves):
        if fcurve.data_path in rotation_paths:
            removed_keys += len(fcurve.keyframe_points)
            action.fcurves.remove(fcurve)

    self.report({'INFO'}, "Deleted " + str(removed_keys) + " rotation key(s) from " + str(len(selected_bones)) + " selected bone(s)")
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

class POSE_OT_DeleteAllScaleKeys(Operator):
    bl_idname = "pose.delete_all_scale_keys"
    bl_label = "Delete all scale keys"
    bl_description = "Deletes all scale keys of selected bones on active armature action"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE' and context.active_object and context.active_object.type == 'ARMATURE'

    def execute(self, context):
        return deleteAllScaleKeysFromSelectedBones(self, context)

# -------------------------------------------------------------------------------------------------

class POSE_OT_DeleteAllLocationKeys(Operator):
    bl_idname = "pose.delete_all_location_keys"
    bl_label = "Delete all location keys"
    bl_description = "Deletes all location keys of selected bones on active armature action"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE' and context.active_object and context.active_object.type == 'ARMATURE'

    def execute(self, context):
        return deleteAllLocationKeysFromSelectedBones(self, context)

class POSE_OT_DeleteAllRotationKeys(Operator):
    bl_idname = "pose.delete_all_rotation_keys"
    bl_label = "Delete all rotation keys"
    bl_description = "Deletes all rotation keys of selected bones on active armature action"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE' and context.active_object and context.active_object.type == 'ARMATURE'

    def execute(self, context):
        return deleteAllRotationKeysFromSelectedBones(self, context)

# -------------------------------------------------------------------------------------------------

class POSE_OT_ScaleEachBoneModal(Operator):
    """Scale each selected bone individually by moving mouse up/down"""
    bl_idname = "pose.scale_each_bone_modal"
    bl_label = "Scale each bone (interactive)"
    bl_description = "Scales each selected bone individually. Move mouse up/down to adjust, LMB/Enter to confirm"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE' and context.selected_pose_bones

    def invoke(self, context, event):
        self.initial_scales = {bone.name: bone.scale.copy() for bone in context.selected_pose_bones}
        if not self.initial_scales:
            self.report({'WARNING'}, "No bones selected")
            return {'CANCELLED'}
        self.init_mouse_y = event.mouse_y
        self.factor = 1.0
        self.has_moved = False
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set(
            "Scale each bone: 1.000  |  Move mouse up/down  |  LMB/Enter: confirm  |  RMB/Esc: cancel"
        )
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            delta = (event.mouse_y - self.init_mouse_y) * 0.005
            self.factor = max(0.001, 1.0 + delta)
            if abs(delta) > 0.001:
                self.has_moved = True
            for bone in context.selected_pose_bones:
                if bone.name in self.initial_scales:
                    bone.scale = self.initial_scales[bone.name] * self.factor
            context.area.header_text_set(
                f"Scale each bone: {self.factor:.3f}  |  Move mouse up/down  |  LMB/Enter: confirm  |  RMB/Esc: cancel"
            )
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        elif event.type == 'RET' and event.value == 'PRESS':
            context.area.header_text_set(None)
            self.report({'INFO'}, f"Scaled each bone by {self.factor:.3f}")
            return {'FINISHED'}

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if not self.has_moved:
                return {'RUNNING_MODAL'}
            context.area.header_text_set(None)
            self.report({'INFO'}, f"Scaled each bone by {self.factor:.3f}")
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            for bone in context.selected_pose_bones:
                if bone.name in self.initial_scales:
                    bone.scale = self.initial_scales[bone.name]
            context.area.header_text_set(None)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}


class POSE_OT_ScaleEachBoneApply(Operator):
    """Apply a scale factor to each selected bone individually"""
    bl_idname = "pose.scale_each_bone_apply"
    bl_label = "Scale each bone"
    bl_description = "Multiplies the local scale of each selected bone by the given factor"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE' and context.selected_pose_bones

    def execute(self, context):
        factor = context.scene.bone_individual_scale
        count = 0
        for bone in context.selected_pose_bones:
            bone.scale *= factor
            count += 1
        self.report({'INFO'}, f"Scaled {count} bone(s) by {factor:.3f}")
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
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (context.object is not None)

    def draw(self, context):
        layout = self.layout

        layout.operator("object.copy_armature_constraints")
        layout.operator("object.copy_bone_positions_rotations")
        layout.operator("object.paste_bone_positions_rotations")
        layout.operator("object.copy_bone_animation_all_frames")
        layout.operator("object.paste_bone_animation_all_frames")

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

class OBJECT_OT_CopyBoneAnimationAllFrames(bpy.types.Operator):
    """Copy Bone Animation All Frames"""
    bl_idname = "object.copy_bone_animation_all_frames"
    bl_label = "Copy animation"
    bl_description = "Copies location, rotation and scale for all keyed frames of selected armature"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        return copyBoneAnimationAllFrames(self, context)

class OBJECT_OT_PasteBoneAnimationAllFrames(bpy.types.Operator):
    """Paste Bone Animation All Frames"""
    bl_idname = "object.paste_bone_animation_all_frames"
    bl_label = "Paste animation"
    bl_description = "Clears target keys, then pastes copied location, rotation and scale on all copied keyed frames"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        return pasteBoneAnimationAllFrames(self, context)

class OBJECT_PT_bone_utilities(bpy.types.Panel):
    bl_idname = "OBJECT_PT_bone_utilities"
    bl_label = "Bone Utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE'

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.operator(POSE_OT_MarkStartPose.bl_idname)
        box.operator(POSE_OT_CopyDelta.bl_idname)
        box.operator(POSE_OT_PasteDelta.bl_idname)
        box.operator(POSE_OT_DeleteAllLocationKeys.bl_idname)
        box.operator(POSE_OT_DeleteAllRotationKeys.bl_idname)
        box.operator(POSE_OT_DeleteAllScaleKeys.bl_idname)

        box = layout.box()
        box.label(text="Individual Bone Scale", icon='FULLSCREEN_ENTER')
        box.operator(POSE_OT_ScaleEachBoneModal.bl_idname)
        row = box.row(align=True)
        row.prop(context.scene, "bone_individual_scale")
        row.operator(POSE_OT_ScaleEachBoneApply.bl_idname, text="Apply")

# -------------------------------------------------------------------------------------------------
# Registering

addon_keymaps = []

def register():
    bpy.utils.register_class(OBJECT_OT_CopyArmatureConstraints)
    bpy.utils.register_class(OBJECT_OT_CopyBonePositionsRotations)
    bpy.utils.register_class(OBJECT_OT_PasteBonePositionsRotations)
    bpy.utils.register_class(OBJECT_OT_CopyBoneAnimationAllFrames)
    bpy.utils.register_class(OBJECT_OT_PasteBoneAnimationAllFrames)
    bpy.utils.register_class(OBJECT_PT_armature_utilities)
    bpy.utils.register_class(OBJECT_PT_bone_utilities)
    bpy.utils.register_class(POSE_OT_MarkStartPose)
    bpy.utils.register_class(POSE_OT_CopyDelta)
    bpy.utils.register_class(POSE_OT_PasteDelta)
    bpy.utils.register_class(POSE_OT_DeleteAllLocationKeys)
    bpy.utils.register_class(POSE_OT_DeleteAllRotationKeys)
    bpy.utils.register_class(POSE_OT_DeleteAllScaleKeys)
    bpy.utils.register_class(POSE_OT_ScaleEachBoneModal)
    bpy.utils.register_class(POSE_OT_ScaleEachBoneApply)
    bpy.types.Scene.bone_individual_scale = bpy.props.FloatProperty(
        name="Scale",
        description="Scale factor to apply to each selected bone",
        default=2.0,
        min=0.001,
    )

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    bpy.utils.unregister_class(OBJECT_OT_CopyArmatureConstraints)
    bpy.utils.unregister_class(OBJECT_OT_CopyBonePositionsRotations)
    bpy.utils.unregister_class(OBJECT_OT_PasteBonePositionsRotations)
    bpy.utils.unregister_class(OBJECT_OT_CopyBoneAnimationAllFrames)
    bpy.utils.unregister_class(OBJECT_OT_PasteBoneAnimationAllFrames)
    bpy.utils.unregister_class(OBJECT_PT_armature_utilities)
    bpy.utils.unregister_class(OBJECT_PT_bone_utilities)
    bpy.utils.unregister_class(POSE_OT_MarkStartPose)
    bpy.utils.unregister_class(POSE_OT_CopyDelta)
    bpy.utils.unregister_class(POSE_OT_PasteDelta)
    bpy.utils.unregister_class(POSE_OT_DeleteAllLocationKeys)
    bpy.utils.unregister_class(POSE_OT_DeleteAllRotationKeys)
    bpy.utils.unregister_class(POSE_OT_DeleteAllScaleKeys)
    bpy.utils.unregister_class(POSE_OT_ScaleEachBoneModal)
    bpy.utils.unregister_class(POSE_OT_ScaleEachBoneApply)
    del bpy.types.Scene.bone_individual_scale

if __name__ == "__main__":
    register()
